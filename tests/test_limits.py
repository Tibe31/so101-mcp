import pytest

from so101_mcp.limits import limits_from_calibration

CALIBRATION = {
    "shoulder_pan": {"id": 1, "range_min": 792, "range_max": 3242},
    "shoulder_lift": {"id": 2, "range_min": 800, "range_max": 3177},
    "elbow_flex": {"id": 3, "range_min": 981, "range_max": 3141},
    "wrist_flex": {"id": 4, "range_min": 811, "range_max": 3141},
    "wrist_roll": {"id": 5, "range_min": 113, "range_max": 3912},
    "gripper": {"id": 6, "range_min": 2032, "range_max": 3205},
}


def test_limits_without_margin():
    limits = limits_from_calibration(CALIBRATION, margin=0)
    assert limits["shoulder_pan"] == [-107.69, 107.69]
    assert limits["wrist_roll"] == [-166.99, 166.99]
    assert "gripper" not in limits


def test_margin_shrinks_limits():
    assert limits_from_calibration(CALIBRATION, margin=3)["shoulder_pan"] == [-104.69, 104.69]


def test_margin_too_large():
    with pytest.raises(ValueError):
        limits_from_calibration(CALIBRATION, margin=200)
