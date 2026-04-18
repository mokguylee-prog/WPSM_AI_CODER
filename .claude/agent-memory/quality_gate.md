# Quality Gate Memory

The agent must treat quality as a loop, not a one-time check.

## Gate rules

- Score the current implementation before large changes.
- Do not stop until the score is at least 90.
- Reconnect stability is a first-class requirement.
- Server health, session health, and stream health must be separated.
- Client failures must show the reason and a next action.

