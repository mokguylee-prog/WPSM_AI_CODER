# Sm_AICoder API 명세서

**서버:** `http://localhost:8888`  
**백엔드:** FastAPI + llama-cpp-python (GGUF 모델)  
**인코딩:** UTF-8  
**Content-Type:** `application/json`

---

## 전체 엔드포인트 목록

| 메서드 | 경로 | 설명 | 사용 클라이언트 |
|--------|------|------|----------------|
| GET | `/` | 웹 대시보드 (HTML) | 브라우저 |
| GET | `/health` | 서버·모델 상태 확인 | GUI·CLI·server.py |
| POST | `/generate` | 단발성 코드 생성 | 외부 도구 |
| POST | `/chat` | 다중 턴 대화 | GUI·CLI 클라이언트 |
| GET | `/stats` | 통계 + 최근 요청 이력 | 웹 대시보드 |
| GET | `/logs/download` | 요청 로그 파일 다운로드 | 브라우저 |

---

## 1. GET `/health`

서버와 모델이 정상 동작 중인지 확인한다. `server.py`가 기동 대기 시 폴링에 사용한다.

### 응답 `200 OK`

```json
{
  "status": "ok",
  "model": "qwen2.5-coder-7b-instruct-q4_k_m.gguf"
}
```

| 필드 | 타입 | 설명 |
|------|------|------|
| `status` | string | 항상 `"ok"` |
| `model` | string | 로드된 GGUF 파일명 |

### 오류

| 상태 코드 | 상황 |
|-----------|------|
| 503 | 서버 기동 중 (모델 로딩 전) |
| 연결 거부 | 서버 프로세스 미실행 |

### 사용 예

```python
import requests
r = requests.get("http://localhost:8888/health", timeout=3)
print(r.json())  # {'status': 'ok', 'model': '...'}
```

---

## 2. POST `/chat`

다중 턴 대화 엔드포인트. GUI 클라이언트와 CLI 클라이언트가 사용한다.  
호출 측이 전체 대화 히스토리를 `messages` 배열에 담아 전송한다.

### 요청 Body

```json
{
  "messages": [
    {"role": "user", "content": "C 언어로 PID 제어 코드 만들어줘"}
  ],
  "max_tokens": 1024,
  "temperature": 0.3,
  "top_p": 0.95
}
```

| 필드 | 타입 | 기본값 | 필수 | 설명 |
|------|------|--------|------|------|
| `messages` | array | — | ✅ | 대화 히스토리 (role + content) |
| `messages[].role` | string | — | ✅ | `"user"` 또는 `"assistant"` |
| `messages[].content` | string | — | ✅ | 메시지 내용 |
| `max_tokens` | int | `1024` | — | 최대 생성 토큰 수 (1 ~ 4096) |
| `temperature` | float | `0.3` | — | 창의성 (0.0 = 결정적, 2.0 = 창의적) |
| `top_p` | float | `0.95` | — | 누적 확률 컷오프 |

> **주의:** `system` 역할 메시지를 첫 번째로 넣지 않으면 서버가 기본 시스템 프롬프트를 자동 삽입한다.

### 응답 `200 OK`

```json
{
  "response": "```c\n#include <stdio.h>\n...\n```",
  "elapsed_ms": 12430,
  "message": {
    "role": "assistant",
    "content": "```c\n#include <stdio.h>\n...\n```"
  },
  "model": "qwen2.5-coder-7b-instruct-q4_k_m.gguf",
  "usage": {
    "prompt_tokens": 87,
    "completion_tokens": 312,
    "total_tokens": 399
  }
}
```

| 필드 | 타입 | 설명 |
|------|------|------|
| `response` | string | 생성된 텍스트 (GUI·CLI가 직접 읽는 필드) |
| `elapsed_ms` | int | 추론 소요 시간 (밀리초) |
| `message` | object | llama-cpp 원본 message 객체 |
| `model` | string | 로드된 모델 파일명 |
| `usage.prompt_tokens` | int | 입력 토큰 수 |
| `usage.completion_tokens` | int | 생성 토큰 수 |
| `usage.total_tokens` | int | 합계 토큰 수 |

### 다중 턴 대화 예시

```json
{
  "messages": [
    {"role": "user",      "content": "C 언어로 링크드 리스트 만들어줘"},
    {"role": "assistant", "content": "```c\n...(이전 응답)...\n```"},
    {"role": "user",      "content": "거기에 삭제 함수도 추가해줘"}
  ]
}
```

### 오류

| 상태 코드 | 상황 |
|-----------|------|
| 422 | 요청 Body 형식 오류 |
| 503 | 모델 로딩 중 |

---

## 3. POST `/generate`

단발성 코드 생성. 히스토리 없이 프롬프트 하나만 전송한다.

### 요청 Body

```json
{
  "prompt": "버블 정렬 C 코드",
  "system": "You are an expert C/C++ programming assistant...",
  "max_tokens": 1024,
  "temperature": 0.3,
  "top_p": 0.95
}
```

| 필드 | 타입 | 기본값 | 필수 | 설명 |
|------|------|--------|------|------|
| `prompt` | string | — | ✅ | 코드 생성 요청 내용 |
| `system` | string | 기본 시스템 프롬프트 | — | 시스템 역할 지시 |
| `max_tokens` | int | `1024` | — | 최대 생성 토큰 수 |
| `temperature` | float | `0.3` | — | 창의성 |
| `top_p` | float | `0.95` | — | 누적 확률 컷오프 |

### 응답 `200 OK`

```json
{
  "generated": "```c\n#include <stdio.h>\n...\n```",
  "model": "qwen2.5-coder-7b-instruct-q4_k_m.gguf",
  "prompt_tokens": 45,
  "generated_tokens": 198
}
```

| 필드 | 타입 | 설명 |
|------|------|------|
| `generated` | string | 생성된 텍스트 |
| `model` | string | 로드된 모델 파일명 |
| `prompt_tokens` | int | 입력 토큰 수 |
| `generated_tokens` | int | 생성 토큰 수 |

---

## 4. GET `/stats`

서버 가동 통계와 최근 20건의 요청·응답 이력을 반환한다.  
웹 대시보드가 5초마다 폴링한다.

### 응답 `200 OK`

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
      "response": "```c\n...\n```",
      "prompt_tokens": 87,
      "gen_tokens": 312,
      "elapsed_ms": 21430
    }
  ]
}
```

| 필드 | 타입 | 설명 |
|------|------|------|
| `model` | string | 로드된 모델 파일명 |
| `uptime_sec` | int | 서버 기동 후 경과 시간(초) |
| `total_requests` | int | 누적 요청 수 |
| `total_prompt_tokens` | int | 누적 입력 토큰 수 |
| `total_generated_tokens` | int | 누적 생성 토큰 수 |
| `avg_response_ms` | int | 평균 응답 시간(ms) |
| `recent` | array | 최근 요청 최대 20건 (최신순) |
| `recent[].time` | string | 요청 시각 (`YYYY-MM-DD HH:MM:SS`) |
| `recent[].prompt` | string | 사용자 입력 전문 |
| `recent[].response` | string | AI 응답 전문 |
| `recent[].prompt_tokens` | int | 해당 요청의 입력 토큰 수 |
| `recent[].gen_tokens` | int | 해당 요청의 생성 토큰 수 |
| `recent[].elapsed_ms` | int | 해당 요청의 응답 시간(ms) |

---

## 5. GET `/logs/download`

`logs/requests.log` 파일을 JSON Lines 형식으로 다운로드한다.

### 응답

- `Content-Type: text/plain; charset=utf-8`
- `Content-Disposition: attachment; filename="requests.log"`

### 로그 파일 형식 (JSON Lines)

파일의 각 줄이 독립된 JSON 객체다.

```jsonl
{"time": "2026-04-17 15:02:35", "prompt": "C#으로 작업이 가능한가?", "response": "네, 가능합니다...", "prompt_tokens": 52, "gen_tokens": 180, "elapsed_ms": 14200}
{"time": "2026-04-17 15:09:29", "prompt": "C 언어로 FFT 처리하는 함수", "response": "```c\n...\n```", "prompt_tokens": 63, "gen_tokens": 421, "elapsed_ms": 29800}
```

### 오류

| 상태 코드 | 상황 |
|-----------|------|
| 404 | 요청 기록 없음 (로그 파일 미생성) |

---

## 6. GET `/`

웹 대시보드 HTML 페이지를 반환한다. 브라우저에서 직접 접근한다.

- `Content-Type: text/html; charset=utf-8`
- 5초마다 `/stats`를 자동 폴링해 화면을 갱신한다.
- 테이블 행 클릭 시 전체 프롬프트·응답을 모달로 표시한다.

---

## 클라이언트별 사용 엔드포인트

```
┌─────────────────────┬──────────┬──────────┬──────────┬──────────┐
│ 클라이언트           │ /health  │ /chat    │/generate │ /stats   │
├─────────────────────┼──────────┼──────────┼──────────┼──────────┤
│ server.py (런처)    │    ✅    │          │          │          │
│ GUI 클라이언트       │    ✅    │    ✅    │          │          │
│ CLI 클라이언트       │    ✅    │    ✅    │          │          │
│ 웹 대시보드          │          │          │          │    ✅    │
│ 외부 도구/스크립트   │    ✅    │    ✅    │    ✅    │    ✅    │
└─────────────────────┴──────────┴──────────┴──────────┴──────────┘
```

---

## 시스템 프롬프트 (기본값)

모든 대화에 자동 삽입되는 시스템 지시문:

```
You are an expert C/C++ programming assistant.
When the user asks you to write code, provide complete, working code.
When creating project files, show the full file contents.
Respond in the same language the user writes in (Korean if Korean, English if English).
Keep explanations concise unless asked for details.
```

---

## 서버 설정값

| 항목 | 값 | 설명 |
|------|----|------|
| `PORT` | `8888` | 수신 포트 |
| `N_CTX` | `4096` | 컨텍스트 길이 (토큰) |
| `N_THREADS` | `8` | CPU 스레드 수 |
| `N_GPU_LAYERS` | `0` | GPU 오프로드 레이어 (CPU 전용) |
| `MODEL_DIR` | `Sm_AICoder/models/gguf` | GGUF 파일 탐색 경로 |
| `LOG_FILE` | `logs/requests.log` | 요청 로그 저장 경로 |
| `recent_requests` | 최대 20건 | 메모리 내 최근 요청 보관 수 |

---

## 연동 흐름도

```
사용자
  │
  ├─ GUI 클라이언트 (gui_client.py)
  │     ├── GET  /health   → 5초마다 상태 확인
  │     └── POST /chat     → 대화 전송 (히스토리 포함)
  │
  ├─ CLI 클라이언트 (client.py)
  │     ├── GET  /health   → 접속 확인
  │     └── POST /chat     → 대화 전송 (히스토리 포함)
  │
  └─ 브라우저 (localhost:8888)
        ├── GET  /          → 대시보드 HTML
        ├── GET  /stats     → 5초마다 통계 폴링
        └── GET  /logs/download → 로그 파일 다운로드

server.py (백그라운드 런처)
  └── GET /health → 90초 내 응답 대기 후 "준비 완료" 출력
```
