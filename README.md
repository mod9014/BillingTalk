# 청구금 알림톡 발송기

매월 엑셀로 정리한 관리비/임대료 청구 내역을 카카오 알림톡(예약발송)으로
자동 발송하는 로컬 실행형 도구입니다. 개인정보는 로컬 PC와 Solapi API
호출 외에는 어디도 거치지 않도록 설계되어 있습니다.

## 구조

- `main.py` — 실행 진입점 (PyInstaller 빌드 대상, 127.0.0.1 전용 바인딩)
- `app/` — FastAPI 백엔드
  - `routes/` — setup / upload / schedule / status
  - `services/` — excel_parser / solapi_client / storage(SQLite)
- `frontend/` — 정적 HTML/JS 대시보드
- `.github/workflows/release.yml` — Windows 실행파일 자동 빌드

## 개발 원칙

1. Solapi API 키는 `~/.officetel-bill/config.json`에만 저장 (저장소 커밋 금지)
2. 세입자 개인정보는 로컬 SQLite에만 저장
3. 서버는 `127.0.0.1`에만 바인딩 — 외부 네트워크 노출 금지
4. 발송 상태는 웹훅이 아닌 폴링(수동 새로고침 + 자동 폴링)으로 확인

## 로컬 실행

```bash
pip install -r requirements.txt
python main.py
```

## TODO

- [ ] 각 모듈 구현 (services/, routes/)
- [ ] 최초 설정 화면 완성
- [ ] 엑셀 → 템플릿 변수 매핑 검증 로직
- [ ] Windows 실행파일 빌드 확인 후 macOS/Linux 매트릭스 추가
