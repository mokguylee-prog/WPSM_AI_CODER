# TODO

## 1. 프로젝트 리네이밍: StarCoder3 -> Sm_AICoder

- [x] 소스코드 내 "StarCoder3" 문자열 전체를 "Sm_AICoder"로 변경
  - [x] server/scripts/api_server.py (FastAPI title, 대시보드 HTML, 서버 시작 메시지)
  - [x] client/client.py (클라이언트 배너)
  - [x] client/gui_client.py (윈도우 타이틀)
  - [x] server/server.py
  - [x] client/make_icon.py (주석)
  - [x] start_server.ps1, start_gui.ps1 (메시지)
  - [x] build_client.ps1 (EXE 이름: StarCoder3Client -> Sm_AiCoderClient)
  - [x] server/scripts/setup_d_drive.ps1 (경로)
  - [x] server/scripts/check_env.py (경로)
- [x] 문서 파일 업데이트
  - [x] README.md
  - [x] CLAUDE.md
  - [x] docs/API_SPEC.md
  - [x] install.md, docs/install.md
- [x] .gitignore EXE 예외명 변경

## 2. GitHub 리포지토리 이전: WPSM_AI_CODER

- [x] 기존 git 이력 제거 (.git 삭제)
- [x] 새 git 저장소 초기화 (git init, main 브랜치)
- [x] GitHub에 WPSM_AI_CODER 리포지토리 생성
- [x] 새 리포지토리로 push 완료
  - Remote: <https://github.com/mokguylee-prog/WPSM_AI_CODER>

## 3. Client OpenFolder / Paste / Preview

- [x] GUI Client에 OpenFolder 버튼 추가
- [x] 선택 폴더 기준 파일/폴더 생성 기능 추가
- [x] 폴더 트리를 VS Code처럼 접기/펼치기 가능하게 개선
- [x] 선택 폴더의 파일 내용을 프롬프트에 참조하도록 연결
- [x] 클립보드 이미지 붙여넣기 지원 추가
- [x] 이미지 미리보기 패널 추가
- [x] Pillow 의존성 추가
- [x] 현재 세션 내용 문서화
  - [x] Sm_AICoder_dialog/DiagStarCoder_20260418000000.md
- [x] 에이전트 파일 반영 강제 확인
  - [x] Sm_AICoder_dialog/DiagStarCoder_20260418010000.md
