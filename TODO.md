# TODO

## 1. 프로젝트 리네이밍: StarCoder3 -> Sm_AICoder

- [x] 소스코드 내 "StarCoder3" 문자열 전체를 "Sm_AICoder"로 변경
  - [x] scripts/api_server.py (FastAPI title, 대시보드 HTML, 서버 시작 메시지)
  - [x] client.py (클라이언트 배너)
  - [x] gui_client.py (윈도우 타이틀)
  - [x] server.py
  - [x] make_icon.py (주석)
  - [x] start_server.ps1, start_gui.ps1 (메시지)
  - [x] build_client.ps1 (EXE 이름: StarCoder3Client -> Sm_AiCoderClient)
  - [x] scripts/setup_d_drive.ps1 (경로)
  - [x] scripts/check_env.py (경로)
- [x] 문서 파일 업데이트
  - [x] README.md
  - [x] CLAUDE.md
  - [x] docs/API_SPEC.md
  - [x] install.md, docs/install.md

## 2. GitHub 리포지토리 이전: WPSM_AI_CODER

- [ ] 기존 git 이력 제거 (.git 삭제)
- [ ] 새 git 저장소 초기화
- [ ] GitHub에 WPSM_AI_CODER 리포지토리 생성
- [ ] 새 리포지토리로 push
