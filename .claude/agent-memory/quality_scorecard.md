# Quality Scorecard Memory

This project uses a 100-point scorecard to judge whether work follows the core principles.

## Pass rule

- 90 points or higher: pass
- below 90 points: keep improving

## Main dimensions

- Server resilience
- Client feedback clarity
- Reconnect stability
- Observability
- Recovery workflow

## Required loop

1. Score the current state.
2. Fix the lowest-scoring items first.
3. Score again.
4. Repeat until the score reaches 90 or higher.

