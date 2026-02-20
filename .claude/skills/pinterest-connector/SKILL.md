# pinterest-connector

Pinterest 계정 로그인, 보드 목록 조회, 핀 URL 수집 (증분 갱신 포함)

## 언제 호출하나
- 최초 설정 시 Pinterest 로그인
- 세션 시작 전 보드 목록 갱신
- 핀 URL 캐시가 없거나 1시간 이상 경과 시

## 스크립트

### login.py
Pinterest 계정 쿠키 로그인 (pinterest-dl 사용)
```bash
python .claude/skills/pinterest-connector/scripts/login.py
```
- 출력: `/config/credentials/pinterest-cookies.json`

### list_boards.py
내 보드 목록 조회 (비공개 포함)
```bash
python .claude/skills/pinterest-connector/scripts/list_boards.py
```
- 출력: `/config/pinterest-boards.json`

### collect_urls.py
보드 핀 URL 수집 (증분 갱신)
```bash
python .claude/skills/pinterest-connector/scripts/collect_urls.py <board_name> <board_url>
```
- 출력: `/config/boards/{board-name}.json`
- 신규: 전체 수집 / 기존: 증분 (추가/삭제만 처리)

## 성공 기준
- 쿠키 파일 생성 + 비공개 보드 접근 확인
- 보드 목록 1개 이상
- 핀 수집: 실제 보드와 90% 이상 일치

## 에러 처리
- 쿠키 만료 → 재로그인 안내
- 증분 실패 → 전체 재수집 폴백
