---
name: so101-robot
description: Safely operate a SO-101 / SO-ARM101 robot arm through the so101-mcp server. Use when the user asks to read the arm's state, move a joint, go to a saved pose, or open/close the gripper, and the so101 MCP tools (get_robot_state, move_joints, move_joint_by, move_to_pose, open_gripper, close_gripper, cycle_gripper, list_safe_poses) are available.
---

# Operating the SO-101 arm with so101-mcp

This skill tells you when and how to use the `so101` MCP tools. The arm is a real physical robot: a bad command can damage it, the table or a person. The server enforces per-joint limits, but it does **not** detect collisions and a movement cannot be interrupted once it starts (it can last up to about 40 seconds).

## Before any movement

1. Call `get_robot_state` first. It does not move the arm and shows the current position of every joint in degrees (gripper roughly 0-100).
2. Tell the user in one line what you are about to do (joint, direction, amount) and wait for their go-ahead unless they have already asked for exactly that move.
3. Never assume the work area is clear. If the user has not said so in this conversation, ask once before the first movement.

## Choosing the right tool

| Goal | Tool |
|---|---|
| See where the arm is | `get_robot_state` |
| See which saved poses exist | `list_safe_poses` |
| Go to a saved pose | `move_to_pose(name)` |
| Move one joint by an amount ("turn left 10 degrees") | `move_joint_by(joint, delta_degrees)` |
| Move one or more joints to absolute angles | `move_joints({joint: value})` |
| Open or close the gripper | `open_gripper`, `close_gripper` |
| Repeat open/close | `cycle_gripper(times)`, 1 to 5 times |

Joint names: `shoulder_pan`, `shoulder_lift`, `elbow_flex`, `wrist_flex`, `wrist_roll`, `gripper`.

## Rules

- **Start small.** For a joint you have not moved yet in this session, use `move_joint_by` with a small delta (5 degrees or less), then read the state again to check the direction before moving more. Do not trust sign conventions: they depend on the user's calibration and assembly.
- **One step at a time.** Prefer one small movement followed by a state check over a large multi-joint jump. Use `move_joints` with several joints only for targets you have checked against the current state.
- **Respect the limits.** If a tool answers that a target is outside the configured limits, or that a limit is missing, stop. Do not retry with slightly different numbers to get around it, and do not suggest editing `config.json` limits just to make a move succeed. Tell the user what was refused and why.
- **Only use saved poses by name.** Never invent a pose. If the pose does not exist, report it and offer `list_safe_poses`.
- **Gripper endpoints come from the config.** If `open_gripper` or `close_gripper` reports that an endpoint is not configured, tell the user to set `gripper.open` / `gripper.closed` in `config.json`. Do not guess values.
- **Stop on anything unexpected.** If the reading after a move is far from the target, a tool errors in the middle of a task, or the user reports odd motion, do not send more movement commands. Ask the user to check the arm and keep a hand on the power supply.
- **No hidden loops.** Do not repeat movement tools in a loop or script a sequence the user has not approved step by step.
- **The port can be busy.** If a tool reports that the serial port is denied or in use, another program (LeLab, a LeRobot script, another MCP client) holds it. Ask the user to close it; do not try to work around it.

## After a movement

Report the final joint positions from the tool result in plain words (for example "shoulder_pan is now -9.8 degrees"). A difference of a few tenths of a degree from the target is normal motor tolerance.

## What this skill cannot do

- It cannot see the arm or the environment, and it cannot check for collisions with the table, objects or people.
- It does not move in centimeters: all motion is in joint angles.
- It does not calibrate the arm. If the server reports no calibration, the user must run `lerobot-calibrate` first.
