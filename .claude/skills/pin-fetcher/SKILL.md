# pin-fetcher

핀 이미지 사전 다운로드 → `/tmp/pins/{board-name}/`

세션 중 Pinterest 네트워크 의존성을 완전히 제거하기 위해 세션 시작 전 핀 이미지를 전량 로컬에 다운로드한다.

## 언제 호출하나
- 보드 선택 후, 세션 시작 전
- `/tmp/pins/` 내 이미지 수가 보드 핀의 80% 미만일 때

## 스크립트

### prefetch_pins.py
```bash
python .claude/skills/pin-fetcher/scripts/prefetch_pins.py <board_name1> [board_name2 ...]
```

**처리 로직:**
1. `/config/boards/{board-name}.json` 에서 핀 URL 목록 로드
2. `/tmp/pins/{board-name}/{pin_id}.jpg` 존재하면 스킵 (캐시 재활용)
3. HTTP GET → 저장
   - 3MB 초과 → JPEG 리사이즈 (max 1500px, quality 80%)
   - 실패 → 스킵 + 로그
4. 8 스레드 병렬 다운로드

**함수:**
- `prefetch_board(board_name)` — 단일 보드 다운로드
- `prefetch_boards(board_names)` — 복수 보드 다운로드
- `get_local_pins(board_names)` — 세션용 로컬 핀 경로 목록 반환

## 출력
`/tmp/pins/{board-name}/{pin_id}.jpg`

## 성공 기준
전체 핀의 80% 이상 다운로드 성공

## 에러 처리
- 개별 실패 → 스킵 + 로그 (전체 세션 영향 없음)
- 전체 80% 미만 → 경고 출력 + 계속 진행
