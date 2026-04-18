---
name: feedback_test_approach
description: 테스트 실행 시 주의사항 및 검증된 접근 방식
type: feedback
---

curl로 /chat 엔드포인트 테스트 시 "There was an error parsing the body" 오류가 발생한다.
Python urllib 또는 requests로 호출하면 정상 동작한다.

**Why:** curl의 Windows/bash 환경에서 멀티라인 JSON 이스케이프가 FastAPI Pydantic 모델 파싱에 실패함.
**How to apply:** /chat, /agent/run 등 중첩 JSON 바디를 보낼 때는 항상 Python 스크립트로 호출할 것.

서버 직접 기동 금지 — 사용자 승인 받기.
**Why:** 사용자가 명시적으로 요청한 규칙 (측정과 보고만).
**How to apply:** 서버가 미기동 상태면 .\start_server.ps1 안내만 하고 대기.

/agent/run 테스트는 300s timeout 설정으로는 부족. 에이전트 loop 자체가 내부 /chat timeout=300s를 사용하므로 최소 600s 이상 필요.
**Why:** agent_loop._call_llm의 requests.post timeout=300, 그리고 OpenFolder 컨텍스트 포함 시 실제로 300초 초과.
**How to apply:** 스모크 테스트용 agent/run은 max_iterations=2, max_tokens=128로 제한하거나, /agent/stream을 사용.
