---
name: streaming-cancel
description: Phase 4 agent task. Use the scorecard and keep iterating until reconnect, cancel, and stream recovery reach 90 points or higher.
tools: Read, Edit, Grep, Glob, Bash
model: sonnet
---

This agent is responsible for streaming, cancel, and reconnect behavior.

## Mandatory quality loop

1. Score the current implementation using `QUALITY_SCORECARD.md`.
2. If reconnect stability is below target, fix that first.
3. Do not stop until the score is 90 or higher.
4. Make sure stale streams do not mark the server offline.
