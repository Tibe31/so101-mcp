# so101-mcp

An [MCP](https://modelcontextprotocol.io) server that lets an AI assistant in any MCP client (Claude Code, Claude Desktop, Cursor, VS Code, ...) move a **SO-101 / SO-ARM101** robot arm, with per-joint safety limits. It talks to the arm through your existing [LeRobot](https://github.com/huggingface/lerobot) installation and calibration.

> **Safety first.** This software moves a real robot. It checks every target against per-joint limits and moves in small, bounded steps, but it does **not** detect collisions between links, with the table, or with people. Keep the work area clear, keep a hand on the power supply, and never run it with anyone near the arm. Use at your own risk (see the license).

Not affiliated with Hugging Face, TheRobotStudio, Anthropic or Cursor.

## Tools

| Tool | What it does |
|---|---|
| `get_robot_state` | Reads the current joint positions. No movement. |
| `list_safe_poses` | Lists the named poses defined in `config.json`. |
| `move_to_pose(name)` | Moves smoothly to a named pose. |
| `move_joints({joint: value})` | Moves one or more joints to absolute positions (degrees). All joints move together. |
| `move_joint_by(joint, delta_degrees)` | Rotates one joint by a relative amount. |
| `open_gripper` / `close_gripper` / `cycle_gripper(n)` | Gripper control between configured endpoints. |

Every movement tool refuses the **whole** request, and moves nothing, if any target is outside the configured limits or a limit is missing.

## Joints

| # | Name | Moves |
|---|---|---|
| 1 | `shoulder_pan` | base rotation (left/right) |
| 2 | `shoulder_lift` | upper arm (forward/back) |
| 3 | `elbow_flex` | elbow |
| 4 | `wrist_flex` | wrist up/down |
| 5 | `wrist_roll` | rotation of the gripper |
| 6 | `gripper` | opening (about 0-100) |

Sign conventions depend on your calibration and assembly. On the author's arm, negative `shoulder_pan` turns left. Check each joint with a small move before relying on a direction.

## Requirements

- A SO-101 arm, already **calibrated with LeRobot** (the server refuses to run on an uncalibrated arm).
- [uv](https://docs.astral.sh/uv/) and Python 3.12+.

## Install

```bash
git clone https://github.com/Tibe31/so101-mcp
cd so101-mcp
uv sync --extra robot
```

The `robot` extra installs LeRobot and its dependencies (large download). Run this once yourself, so your MCP client does not time out on first start.

If the arm is not calibrated yet:

```bash
uv run --extra robot lerobot-calibrate --robot.type=so101_follower --robot.port=COM4 --robot.id=my_arm
```

## Configure

```bash
cp config.example.json config.json    # copy config.example.json config.json on Windows
```

1. Set `port` (for example `COM4` or `/dev/ttyACM0`) and `robot_id` (the id used at calibration time).
2. Generate the joint limits from your calibration file (the path is printed by `lerobot-calibrate`; it lives under `~/.cache/huggingface/lerobot/calibration/` unless `HF_LEROBOT_CALIBRATION` is set):

   ```bash
   uv run so101-limits path/to/my_arm.json --margin 3
   ```

   Paste the printed `limits` into `config.json`. The margin keeps the motors a few degrees away from the mechanical end stops. The numbers assume LeRobot's degree mode (the default for `SO101FollowerConfig`).
3. Set the gripper: read `get_robot_state` with the gripper fully open and fully closed, then fill `gripper.open`, `gripper.closed` and `limits.gripper` (`[min, max]`).
4. Optional: add poses. Put the arm in a safe position, read it with `get_robot_state`, and copy the values into `poses`:

   ```json
   "poses": {
     "rest": {"shoulder_pan": 0, "shoulder_lift": -103.9, "elbow_flex": 93.4,
              "wrist_flex": 78.0, "wrist_roll": -90.0, "gripper": 2.0}
   }
   ```

   Pose values must fall inside the limits, and the gripper in a pose must not be below `limits.gripper`.

`max_step_degrees` (0-2) and `updates_per_second` (1-20) set the speed: roughly their product in degrees per second. Increase them gradually.

`config.json` holds your own port, id, limits and poses: it is git-ignored.

## Use with an MCP client

The server speaks MCP over stdio, so it works with any MCP client. Before adding it, check that it starts on its own: `uv run --extra robot so101-mcp` should wait silently for input (stop it with Ctrl+C). Use the absolute path of `config.json` in `SO101_MCP_CONFIG`, so it does not depend on the working directory.

### Claude Code

1. Add the server (replace the paths with yours; on Windows use `C:\path\to\so101-mcp`):

   ```bash
   claude mcp add so101 --env SO101_MCP_CONFIG=/path/to/so101-mcp/config.json -- \
     uv run --directory /path/to/so101-mcp --extra robot so101-mcp
   ```

   By default the server is available only in the current project. Add `--scope user` to make it available everywhere.
2. Check it: `claude mcp list` should show `so101` as connected. Inside Claude Code, `/mcp` shows its status and tools.
3. Ask for something small first: "read the robot state", then "rotate shoulder_pan by 5 degrees".
4. Claude Code asks for permission the first time a tool is used. Approve movement tools one call at a time rather than "always allow".

To remove it: `claude mcp remove so101`.

### Claude Desktop

Edit `claude_desktop_config.json` (Settings > Developer > Edit Config), then restart Claude Desktop:

```json
{
  "mcpServers": {
    "so101": {
      "command": "uv",
      "args": ["run", "--directory", "C:\\path\\to\\so101-mcp", "--extra", "robot", "so101-mcp"],
      "env": {"SO101_MCP_CONFIG": "C:\\path\\to\\so101-mcp\\config.json"}
    }
  }
}
```

### Cursor

Create `.cursor/mcp.json` in your project (or `~/.cursor/mcp.json` for all projects). The format is the same as for Claude Desktop:

```json
{
  "mcpServers": {
    "so101": {
      "command": "uv",
      "args": ["run", "--directory", "C:\\path\\to\\so101-mcp", "--extra", "robot", "so101-mcp"],
      "env": {"SO101_MCP_CONFIG": "C:\\path\\to\\so101-mcp\\config.json"}
    }
  }
}
```

Then enable `so101` in Cursor's MCP settings. Keep tool approval on (no auto-run) for the movement tools.

### Other clients

Any client that can launch a stdio MCP server works: use `uv` as the command, `["run", "--directory", "<repo>", "--extra", "robot", "so101-mcp"]` as the arguments and `SO101_MCP_CONFIG` as an environment variable.

### All clients

Only one client at a time can hold the arm's serial port: close LeLab, LeRobot scripts and any other MCP client first (for example, Claude Desktop while using Cursor). Whether a client asks for confirmation before moving the arm depends on the client; the server only marks movement tools as destructive.

Then ask things like "read the robot state", "rotate joint 1 left by 30 degrees" or "go to the rest pose".

## Troubleshooting

- **`Access is denied` / `ClearCommError` on the port**: another program holds the serial port (LeLab, a LeRobot script, another MCP client). Close it, or replug the USB cable, then restart the server.
- **`Missing verified limit for joint ...`**: the joint has no `[min, max]` in `limits`.
- **`Target for ... is outside the locally configured safe limits`**: the target (or a pose value) is outside the limits. Nothing moved.
- **`LeRobot is not installed`**: install with `uv sync --extra robot` and start the server with `--extra robot`.
- **The reading is a few tenths of a degree off the target**: normal motor tolerance and settling.

## Development

```bash
uv run pytest
```

The tests use a fake robot, so no hardware or LeRobot install is needed.

## Limitations

- No collision checking (links, table, people). No kinematics: moves are in joint space, not centimeters.
- Fixed speed profile, set only through the config.
- **A movement cannot be interrupted.** A single move can run for up to about 40 seconds (600 steps at the slowest rate) while the server holds a lock, and the MCP client cannot cancel it. If a step fails midway, the arm stays where it stopped. Keep the power supply within reach.
- Limits are checked on the final target only. The path between start and target is a straight line in joint space and is not checked for collisions.
- The server does not manage the arm's torque when it exits. Do not assume the arm will hold or release its position; check this on your setup.
- `config.json` is read once at startup: restart the server after changing limits or poses.
- Movement tools carry MCP annotations (`destructiveHint`), so clients can ask for confirmation before moving the arm. Keep that confirmation enabled.

## License

MIT, see [LICENSE](LICENSE).
