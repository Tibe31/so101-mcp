import asyncio
import json

import pytest

from so101_mcp import server

JOINTS = ["shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex", "wrist_roll", "gripper"]


class FakeRobot:
    def __init__(self):
        self.pos = {j: 0.0 for j in JOINTS}
        self.actions = []

    def get_observation(self):
        return {f"{j}.pos": v for j, v in self.pos.items()}

    def send_action(self, action):
        self.actions.append(dict(action))
        for key, value in action.items():
            self.pos[key.removesuffix(".pos")] = value
        return action


@pytest.fixture
def fake(tmp_path, monkeypatch):
    cfg = {
        "port": "COM9",
        "robot_id": "test",
        "max_step_degrees": 1.0,
        "updates_per_second": 15,
        "gripper": {"open": 90.0, "closed": 2.0},
        "limits": {
            "shoulder_pan": [-100, 100],
            "shoulder_lift": [-100, 100],
            "elbow_flex": [-90, 90],
            "wrist_flex": None,
            "wrist_roll": [-160, 160],
            "gripper": [1.0, 92.0],
        },
        "poses": {"rest": {"shoulder_pan": 10, "elbow_flex": -5}, "empty": {}},
    }
    path = tmp_path / "config.json"
    path.write_text(json.dumps(cfg))
    monkeypatch.setenv(server.ENV_CONFIG, str(path))
    server.reload_config()
    robot = FakeRobot()
    monkeypatch.setattr(server, "robot", lambda: robot)
    monkeypatch.setattr(server.time, "sleep", lambda s: None)
    return robot


def test_move_joints_reaches_target_in_bounded_steps(fake):
    result = server.move_joints({"shoulder_pan": -10})
    assert result["shoulder_pan"] == pytest.approx(-10)
    assert len(fake.actions) == 10
    deltas = [abs(b["shoulder_pan.pos"] - a["shoulder_pan.pos"]) for a, b in zip(fake.actions, fake.actions[1:])]
    assert max(deltas) <= 1.0 + 1e-9


def test_out_of_limit_target_moves_nothing(fake):
    with pytest.raises(ValueError, match="outside"):
        server.move_joints({"shoulder_pan": 20, "elbow_flex": 95})
    assert fake.actions == []


def test_missing_limit_is_an_error(fake):
    with pytest.raises(ValueError, match="Missing verified limit"):
        server.move_joints({"wrist_flex": 1})
    assert fake.actions == []


def test_unknown_joint_and_bad_values_rejected(fake):
    with pytest.raises(ValueError):
        server.move_joints({"nope": 1})
    with pytest.raises(ValueError):
        server.move_joints({"shoulder_pan": True})
    with pytest.raises(ValueError):
        server.move_joints({"shoulder_pan": float("nan")})
    with pytest.raises(ValueError):
        server.move_joints({})
    assert fake.actions == []


def test_move_joint_by_is_relative(fake):
    fake.pos["wrist_roll"] = -90.0
    result = server.move_joint_by("wrist_roll", 30)
    assert result["wrist_roll"] == pytest.approx(-60)
    with pytest.raises(ValueError):
        server.move_joint_by("wrist_roll", 500)


def test_poses(fake):
    assert server.list_safe_poses() == ["rest"]
    result = server.move_to_pose("rest")
    assert result["shoulder_pan"] == pytest.approx(10)
    assert result["elbow_flex"] == pytest.approx(-5)
    with pytest.raises(ValueError):
        server.move_to_pose("empty")
    with pytest.raises(ValueError):
        server.move_to_pose("missing")


def test_gripper_endpoints(fake):
    assert server.open_gripper()["gripper"] == pytest.approx(90.0)
    assert server.close_gripper()["gripper"] == pytest.approx(2.0)
    assert server.cycle_gripper(2)["cycles_completed"] == 2
    with pytest.raises(ValueError):
        server.cycle_gripper(0)


def test_placeholder_config_is_rejected(tmp_path):
    path = tmp_path / "c.json"
    path.write_text(json.dumps({"port": "COM_CHANGE_ME", "robot_id": "YOUR_EXISTING_ID"}))
    with pytest.raises(RuntimeError):
        server.load_config(path)


def test_step_and_rate_bounds_are_enforced(tmp_path):
    path = tmp_path / "c.json"
    path.write_text(json.dumps({"port": "COM9", "robot_id": "x", "max_step_degrees": 5}))
    with pytest.raises(ValueError):
        server.load_config(path)


def test_tool_annotations_mark_motion_tools():
    tools = {t.name: t for t in asyncio.run(server.app.list_tools())}
    read_only = {"get_robot_state", "list_safe_poses"}
    assert set(tools) >= read_only
    for name, tool in tools.items():
        assert tool.annotations is not None
        assert tool.annotations.readOnlyHint is (name in read_only)
