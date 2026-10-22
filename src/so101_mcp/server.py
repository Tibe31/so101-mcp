"""SO-101 MCP server: bounded, limit-checked motion for a SO-101 / SO-ARM101 arm.

The server talks to the arm through an existing LeRobot installation and an
existing LeRobot calibration. No cameras, policies or recalibration are involved.

Safety model:
  * every target is checked against per-joint limits from config.json before
    anything moves (a rejected target moves nothing);
  * motion is a bounded linear interpolation in steps of at most
    ``max_step_degrees``, never a jump;
  * joints and poses are never guessed: missing limits are an error.

Collisions between links, or with the environment, are NOT checked.
"""

from __future__ import annotations

import json
import math
import os
import threading
import time
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

ENV_CONFIG = "SO101_MCP_CONFIG"
PLACEHOLDER_PORTS = {"", "COM_CHANGE_ME"}
PLACEHOLDER_IDS = {"", "YOUR_EXISTING_ID"}
MAX_STEPS = 600

# Hints for MCP clients: movement tools act on the physical world, so clients can ask
# for confirmation. Reading state and listing poses are read-only.
READ_ONLY = ToolAnnotations(readOnlyHint=True, openWorldHint=True)
MOTION = ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=True)

app = FastMCP("so101-movements")

_lock = threading.RLock()
_robot = None
_cfg: dict[str, Any] | None = None


# --------------------------------------------------------------------------- config
def config_path() -> Path:
    """Config file: $SO101_MCP_CONFIG, otherwise ./config.json."""
    env = os.environ.get(ENV_CONFIG)
    return Path(env).expanduser() if env else Path.cwd() / "config.json"


def load_config(path: Path | None = None) -> dict[str, Any]:
    path = path or config_path()
    if not path.is_file():
        raise RuntimeError(
            f"Config file not found: {path}. Copy config.example.json to config.json "
            f"or set {ENV_CONFIG}."
        )
    cfg = json.loads(path.read_text(encoding="utf-8"))
    if cfg.get("port", "") in PLACEHOLDER_PORTS or cfg.get("robot_id", "") in PLACEHOLDER_IDS:
        raise RuntimeError("Set port and robot_id in config.json to your existing LeRobot values")
    step = float(cfg.get("max_step_degrees", 1.0))
    rate = float(cfg.get("updates_per_second", 15))
    if not 0 < step <= 2 or not 1 <= rate <= 20:
        raise ValueError("max_step_degrees must be 0..2; updates_per_second 1..20")
    return cfg


def cfg() -> dict[str, Any]:
    global _cfg
    if _cfg is None:
        _cfg = load_config()
    return _cfg


def reload_config() -> dict[str, Any]:
    global _cfg
    _cfg = load_config()
    return _cfg


def _is_number(value: Any) -> bool:
    return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value)


def _limit_for(joint: str) -> tuple[float, float]:
    lim = cfg().get("limits", {}).get(joint)
    if not isinstance(lim, (list, tuple)) or len(lim) != 2 or not all(_is_number(v) for v in lim):
        raise ValueError(f"Missing verified limit for joint {joint} in config.json")
    lo, hi = float(lim[0]), float(lim[1])
    if lo > hi:
        raise ValueError(f"Invalid limit for joint {joint}: min is greater than max")
    return lo, hi


def _gripper_endpoint(key: str) -> float:
    value = cfg().get("gripper", {}).get(key)
    if not _is_number(value):
        raise ValueError(f"Configure verified gripper.{key} first")
    return float(value)


# --------------------------------------------------------------------------- robot
def robot():
    """Connect lazily, once. Refuses to run on an uncalibrated arm."""
    global _robot
    if _robot is None:
        try:
            from lerobot.robots.so_follower import SO101Follower, SO101FollowerConfig
        except ImportError as exc:
            raise RuntimeError(
                "LeRobot is not installed. Install it with: uv sync --extra robot"
            ) from exc
        c = cfg()
        # Do not specify cameras: this server only owns the arm's serial port.
        obj = SO101Follower(SO101FollowerConfig(port=c["port"], id=c["robot_id"]))
        # calibrate=False: an interactive calibration prompt would corrupt the MCP stdio stream.
        obj.connect(calibrate=False)
        if not obj.is_calibrated:
            obj.disconnect()
            raise RuntimeError(
                "No valid calibration found for this robot_id. Calibrate first with "
                "`lerobot-calibrate --robot.type=so101_follower --robot.port=<PORT> --robot.id=<ID>`."
            )
        _robot = obj
    return _robot


def positions() -> dict[str, float]:
    observation = robot().get_observation()
    return {k.removesuffix(".pos"): float(v) for k, v in observation.items() if k.endswith(".pos")}


def move_targets(targets: dict[str, Any]) -> dict[str, float]:
    """Validate every target against the limits, then move smoothly to it."""
    if not isinstance(targets, dict) or not targets:
        raise ValueError("Unknown joint or empty target")
    current = positions()
    if any(j not in current for j in targets):
        raise ValueError("Unknown joint or empty target")
    if not all(_is_number(v) for v in targets.values()):
        raise ValueError("Invalid target value")
    clean = {j: float(v) for j, v in targets.items()}

    for joint, target in clean.items():
        lo, hi = _limit_for(joint)
        if not lo <= target <= hi:
            raise ValueError(f"Target for {joint} is outside the locally configured safe limits")

    step = float(cfg().get("max_step_degrees", 1.0))
    rate = float(cfg().get("updates_per_second", 15))
    steps = max(1, math.ceil(max(abs(clean[j] - current[j]) for j in clean) / step))
    if steps > MAX_STEPS:
        raise ValueError("Motion too long; choose a closer target")

    for i in range(1, steps + 1):
        # Bounded linear interpolation, never a jump to servo extremes.
        fraction = i / steps
        action = {f"{j}.pos": current[j] + (clean[j] - current[j]) * fraction for j in clean}
        robot().send_action(action)
        time.sleep(1.0 / rate)
    return positions()


# --------------------------------------------------------------------------- tools
@app.tool(annotations=READ_ONLY)
def get_robot_state() -> dict:
    """Read calibrated motor positions (no intentional movement)."""
    with _lock:
        return positions()


@app.tool(annotations=READ_ONLY)
def list_safe_poses() -> list[str]:
    """Show only pre-taught named poses. Never guess an extreme pose."""
    poses = cfg().get("poses", {})
    return sorted(k for k, p in poses.items() if isinstance(p, dict) and p)


@app.tool(annotations=MOTION)
def move_to_pose(name: str) -> dict:
    """Move slowly to a locally taught and verified safe pose by name. Do not use if work area is obstructed."""
    poses = cfg().get("poses", {})
    with _lock:
        if name not in poses or not isinstance(poses[name], dict) or not poses[name]:
            raise ValueError("Unknown/unconfigured pose. Ask operator to teach a safe pose first.")
        return move_targets(poses[name])


@app.tool(annotations=MOTION)
def move_joints(targets: dict[str, float]) -> dict:
    """Move one or more joints to absolute positions (degrees; gripper 0-100).
    Example: {"shoulder_pan": -50, "wrist_roll": 0}. Joints not listed stay in place.
    Every target must be inside the limits in config.json, otherwise nothing moves.
    Do not use if work area is obstructed."""
    if not isinstance(targets, dict) or not targets:
        raise ValueError("targets must be a non-empty object of joint: value")
    with _lock:
        return move_targets(targets)


@app.tool(annotations=MOTION)
def move_joint_by(joint: str, delta_degrees: float) -> dict:
    """Rotate a single joint by a relative amount from its current position.
    Example: joint="shoulder_pan", delta_degrees=-10 (negative pan = left).
    The final position must be inside the limits in config.json, otherwise nothing moves."""
    if not _is_number(delta_degrees):
        raise ValueError("delta_degrees must be a number")
    with _lock:
        current = positions()
        if joint not in current:
            raise ValueError("Unknown joint")
        return move_targets({joint: current[joint] + float(delta_degrees)})


@app.tool(annotations=MOTION)
def cycle_gripper(times: int) -> dict:
    """Open then close gripper a specified number of times (1-5), using operator-validated calibrated endpoints."""
    if type(times) is not int or times < 1 or times > 5:
        raise ValueError("times must be an integer from 1 through 5")
    opened, closed = _gripper_endpoint("open"), _gripper_endpoint("closed")
    with _lock:
        for _ in range(times):
            move_targets({"gripper": opened})
            move_targets({"gripper": closed})
        return {"cycles_completed": times, "gripper_position": positions().get("gripper")}


@app.tool(annotations=MOTION)
def open_gripper() -> dict:
    """Slowly open gripper to the operator-verified safe position."""
    target = _gripper_endpoint("open")
    with _lock:
        return move_targets({"gripper": target})


@app.tool(annotations=MOTION)
def close_gripper() -> dict:
    """Slowly close gripper to the operator-verified safe position."""
    target = _gripper_endpoint("closed")
    with _lock:
        return move_targets({"gripper": target})


def main() -> None:
    app.run(transport="stdio")


if __name__ == "__main__":
    main()
