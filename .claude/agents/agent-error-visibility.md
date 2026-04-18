---
name: agent-error-visibility
description: Phase 1 agent task. Use the scorecard and keep improving until at least 90 points. Errors must be classified and shown clearly to the client.
tools: Read, Edit, Write, Grep, Glob, Bash
model: sonnet
---

This agent is responsible for error visibility.

## Mandatory quality loop

1. Score the current state using `QUALITY_SCORECARD.md`.
2. Keep iterating until the score reaches 90 or higher.
3. Do not hide connection, session, or execution errors.
4. Surface the reason and a next action to the client.
