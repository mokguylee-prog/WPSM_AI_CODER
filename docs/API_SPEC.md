# Sm_AICoder API 명세서

- 서버 주소: `http://localhost:8888`
- 백엔드: FastAPI + llama-cpp-python
- 모델 형식: GGUF
- 기본 응답 인코딩: UTF-8
- 기본 요청 본문 형식: `application/json`

---

## 전체 엔드포인트 목록

| 메서드 | 경로 | 설명 | 주요 사용자 |
| ------ | ---- | ---- | ----------- |
| GET | `/` | 웹 대시보드 | 브라우저 |
| GET | `/health` | 서버와 모델 상태 확인 | GUI, CLI, 서버 런처 |
| POST | `/generate` | 단발성 코드 생성 | 외부 스크립트 |
| POST | `/chat` | 다중 턴 대화 | GUI, CLI |
| GET | `/stats` | 통계와 최근 요청 조회 | 웹 대시보드 |
| GET | `/logs/download` | 로그 파일 다운로드 | 브라우저 |

---

## 1. GET `/health`

서버가 응답 가능한지와 어떤 모델이 로드되었는지 확인합니다.
`server/server.py`도 이 엔드포인트를 폴링합니다.

### /health 응답 예시

```json
{
  "status": "ok",
  "model": "qwen2.5-coder-7b-instruct-q4_k_m.gguf"
}
```

### /health 응답 필드

| 필드 | 타입 | 설명 |
| ---- | ---- | ---- |
| `status` | string | 정상일 때 항상 `"ok"` 입니다. |
| `model` | string | 현재 로드된 GGUF 파일명입니다. |

### /health 오류 코드

| 상태 코드 | 상황 |
| --------- | ---- |
| 503 | 서버는 떴지만 모델 로딩이 끝나지 않은 상태 |
| 연결 거부 | 서버 프로세스가 실행 중이 아님 |

### /health 호출 예

```python
import requests

resp = requests.get("http://localhost:8888/health", timeout=3)
print(resp.json())
```

---

## 2. POST `/chat`

대화 히스토리를 포함해 요청하는 다중 턴 대화용 엔드포인트입니다.
GUI와 CLI 클라이언트가 이 엔드포인트를 사용합니다.

### /chat 요청 예시

```json
{
  "messages": [
    {
      "role": "user",
      "content": "C 언어로 PID 제어 코드 만들어줘"
    }
  ],
  "max_tokens": 1024,
  "temperature": 0.3,
  "top_p": 0.95
}
```

### /chat 요청 필드

| 필드 | 타입 | 기본값 | 필수 | 설명 |
| ---- | ---- | ------ | ---- | ---- |
| `messages` | array | 없음 | 예 | 대화 히스토리 배열 |
| `messages[].role` | string | 없음 | 예 | `user` 또는 `assistant` |
| `messages[].content` | string | 없음 | 예 | 메시지 본문 |
| `max_tokens` | int | `1024` | 아니오 | 최대 생성 토큰 수 |
| `temperature` | float | `0.3` | 아니오 | 생성 다양성 |
| `top_p` | float | `0.95` | 아니오 | 누적 확률 컷오프 |

> 첫 번째 메시지가 `system`이 아니면 서버가 기본 시스템 프롬프트를
> 앞에 자동으로 추가합니다.

### /chat 응답 예시

```json
{
  "response": "요청한 코드와 설명이 여기에 들어갑니다.",
  "elapsed_ms": 12430,
  "message": {
    "role": "assistant",
    "content": "요청한 코드와 설명이 여기에 들어갑니다."
  },
  "model": "qwen2.5-coder-7b-instruct-q4_k_m.gguf",
  "usage": {
    "prompt_tokens": 87,
    "completion_tokens": 312,
    "total_tokens": 399
  }
}
```

### /chat 응답 필드

| 필드 | 타입 | 설명 |
| ---- | ---- | ---- |
| `response` | string | 생성된 전체 텍스트 |
| `elapsed_ms` | int | 추론에 걸린 시간(ms) |
| `message` | object | assistant 메시지 객체 |
| `model` | string | 현재 모델 파일명 |
| `usage.prompt_tokens` | int | 입력 토큰 수 |
| `usage.completion_tokens` | int | 생성 토큰 수 |
| `usage.total_tokens` | int | 총 토큰 수 |

### /chat 다중 턴 예시

```json
{
  "messages": [
    {
      "role": "user",
      "content": "C 언어로 링크드 리스트 만들어줘"
    },
    {
      "role": "assistant",
      "content": "이전 응답 내용"
    },
    {
      "role": "user",
      "content": "삭제 함수도 추가해줘"
    }
  ]
}
```

### /chat 오류 코드

| 상태 코드 | 상황 |
| --------- | ---- |
| 422 | 요청 JSON 형식이 잘못됨 |
| 503 | 모델 로딩 중 |

---

## 3. POST `/generate`

히스토리 없이 프롬프트 하나만 보내는 단발성 생성용 엔드포인트입니다.

### /generate 요청 예시

```json
{
  "prompt": "버블 정렬 C 코드",
  "system": "You are an expert C/C++ programming assistant...",
  "max_tokens": 1024,
  "temperature": 0.3,
  "top_p": 0.95
}
```

### /generate 요청 필드

| 필드 | 타입 | 기본값 | 필수 | 설명 |
| ---- | ---- | ------ | ---- | ---- |
| `prompt` | string | 없음 | 예 | 사용자 요청 본문 |
| `system` | string | 기본 시스템 프롬프트 | 아니오 | 시스템 지시문 |
| `max_tokens` | int | `1024` | 아니오 | 최대 생성 토큰 수 |
| `temperature` | float | `0.3` | 아니오 | 생성 다양성 |
| `top_p` | float | `0.95` | 아니오 | 누적 확률 컷오프 |

### /generate 응답 예시

```json
{
  "generated": "생성된 코드와 설명",
  "model": "qwen2.5-coder-7b-instruct-q4_k_m.gguf",
  "prompt_tokens": 45,
  "generated_tokens": 198
}
```

### /generate 응답 필드

| 필드 | 타입 | 설명 |
| ---- | ---- | ---- |
| `generated` | string | 생성된 텍스트 |
| `model` | string | 현재 모델 파일명 |
| `prompt_tokens` | int | 입력 토큰 수 |
| `generated_tokens` | int | 생성 토큰 수 |

### /generate 오류 코드

| 상태 코드 | 상황 |
| --------- | ---- |
| 422 | 요청 JSON 형식이 잘못됨 |
| 503 | 모델 로딩 중 |

---

## 4. GET `/stats`

서버 통계와 최근 요청 최대 20건을 반환합니다.
웹 대시보드가 5초마다 이 값을 읽습니다.

### /stats 응답 예시

```json
{
  "model": "qwen2.5-coder-7b-instruct-q4_k_m.gguf",
  "uptime_sec": 3720,
  "total_requests": 12,
  "total_prompt_tokens": 1840,
  "total_generated_tokens": 5230,
  "avg_response_ms": 18400,
  "recent": [
    {
      "time": "2026-04-17 15:31:09",
      "prompt": "C 언어로 PID 제어 코드 만들어줘",
      "response": "응답 내용",
      "prompt_tokens": 87,
      "gen_tokens": 312,
      "elapsed_ms": 21430
    }
  ]
}
```

### /stats 응답 필드

| 필드 | 타입 | 설명 |
| ---- | ---- | ---- |
| `model` | string | 현재 모델 파일명 |
| `uptime_sec` | int | 서버 시작 후 경과 시간(초) |
| `total_requests` | int | 누적 요청 수 |
| `total_prompt_tokens` | int | 누적 입력 토큰 수 |
| `total_generated_tokens` | int | 누적 생성 토큰 수 |
| `avg_response_ms` | int | 평균 응답 시간(ms) |
| `recent` | array | 최근 요청 목록 |
| `recent[].time` | string | 요청 시각 |
| `recent[].prompt` | string | 사용자 입력 |
| `recent[].response` | string | 모델 응답 |
| `recent[].prompt_tokens` | int | 입력 토큰 수 |
| `recent[].gen_tokens` | int | 생성 토큰 수 |
| `recent[].elapsed_ms` | int | 응답 시간(ms) |

---

## 5. GET `/logs/download`

현재 로그 파일을 JSON Lines 형식으로 다운로드합니다.
실제 파일 경로는 `server/logs/requests_*.log` 패턴입니다.

### /logs/download 응답 헤더

- `Content-Type: text/plain; charset=utf-8`
- `Content-Disposition: attachment; filename="requests.log"`

### /logs/download 로그 형식 예시

```jsonl
{"time":"2026-04-17 15:02:35","prompt":"예시 요청","response":"예시 응답"}
{"time":"2026-04-17 15:09:29","prompt":"두 번째 요청","response":"두 번째 응답"}
```

### /logs/download 오류 코드

| 상태 코드 | 상황 |
| --------- | ---- |
| 404 | 로그 파일이 아직 만들어지지 않음 |

---

## 6. GET `/`

웹 대시보드 HTML을 반환합니다.

- `Content-Type`은 `text/html; charset=utf-8` 입니다.
- 5초마다 `/stats`를 다시 호출해 화면을 갱신합니다.
- 최근 요청 행을 클릭하면 상세 모달을 띄웁니다.

---

## 클라이언트별 사용 엔드포인트

- `server/server.py`: `GET /health`
- GUI 클라이언트: `GET /health`, `POST /chat`
- CLI 클라이언트: `GET /health`, `POST /chat`
- 웹 대시보드: `GET /stats`, `GET /logs/download`, `GET /`
- 외부 도구: 필요 시 전 엔드포인트 사용 가능

---

## 기본 시스템 프롬프트

```text
You are an expert C/C++ programming assistant.
When the user asks you to write code, provide complete, working code.
When creating project files, show the full file contents.
Respond in the same language the user writes in.
Keep explanations concise unless asked for details.
```

---

## 서버 설정값

| 항목 | 값 | 설명 |
| ---- | --- | ---- |
| `PORT` | `8888` | 수신 포트 |
| `N_CTX` | `4096` | 컨텍스트 길이 |
| `N_THREADS` | `8` | CPU 스레드 수 |
| `N_GPU_LAYERS` | `0` | GPU 오프로드 레이어 |
| `MODEL_DIR` | `Sm_AICoder/models/gguf` | 모델 탐색 경로 |
| `LOG_FILE` | `server/logs/requests_*.log` | 요청 로그 경로 |
| `recent_requests` | 최대 20건 | 메모리 내 최근 요청 보관 수 |

---

## 연동 흐름

```text
사용자
  ├─ GUI 클라이언트
  │   ├─ GET  /health
  │   └─ POST /chat
  ├─ CLI 클라이언트
  │   ├─ GET  /health
  │   └─ POST /chat
  └─ 브라우저
      ├─ GET /
      ├─ GET /stats
      └─ GET /logs/download

server/server.py
  └─ GET /health 로 준비 완료까지 대기
```
