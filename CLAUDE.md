# 나노바나나 프로 영감 생성 에이전트

> **목적**: Pinterest 보드 핀 + 자동 랜덤 단어 조합 → Gemini API 이미지 대량 생성

---

## 1. 에이전트 역할 및 개요

나는 Claude Code 에이전트로서 이 시스템의 오케스트레이터다. 사용자의 자연어 명령(`시작해`, `멈춰`, `상태 알려줘`)으로 전체 파이프라인을 제어한다.

**판단이 필요한 작업 (내가 직접 처리):**
- 초기 단어 DB 생성 (창의적 단어 + 영어 설명)
- 프롬프트 템플릿 설계
- 보드 선택 UI, 세션 설정 안내

**반복 실행 (Python 스크립트가 처리):**
- Pinterest 로그인/보드/URL 수집
- 핀 이미지 사전 다운로드
- 고정 템플릿 치환 → Gemini API 호출
- Resume 감지, 비용 추적, 정지 조건 체크
- Drive 업로드, Slack 알림, HTML 뷰어 생성

---

## 2. 전체 파이프라인

```
[워크플로우 P] Pinterest 연동
  로그인 → 보드 목록 → 핀 URL 수집(증분) → 이미지 사전 다운로드

[워크플로우 0] 초기 설정 (1회성)
  단어 DB → 프롬프트 템플릿 → Drive 연결 → 비용 상한 설정

[워크플로우 1] 생성 세션 (반복)
  Resume 감지 → 보드 선택 → 세션 설정
  → Word1+Word2 랜덤 → 템플릿 치환 → 로컬 핀 5장 → API 호출
  → 로컬 저장 → 정지 조건 체크 → (루프)
  → Drive 업로드 → HTML 뷰어 → Slack 알림
```

---

## 3. Pinterest 연동

### 3.1 로그인
```bash
python .claude/skills/pinterest-connector/scripts/login.py
```
쿠키: `/config/credentials/pinterest-cookies.json`

### 3.2 보드 목록 조회
```bash
python .claude/skills/pinterest-connector/scripts/list_boards.py
```

### 3.3 보드 선택 UI (세션마다)
```
═══ Pinterest 보드 목록 ═══
1. 🔒 aesthetic-mood (87핀) — 캐시 ✓
2. 🔒 dark-fantasy (120핀) — 캐시 없음
3. 🌐 nature-vibes (200핀) — 캐시 ✓
═══════════════════════════
레퍼런스 보드 선택 (번호, 복수는 쉼표로: 예 1,3):
```
- 복수 선택 → 핀 풀 합산
- 캐시 없거나 1시간 이상 경과 → 자동 수집

### 3.4 핀 URL 수집 (증분 갱신)
```bash
python .claude/skills/pinterest-connector/scripts/collect_urls.py <board_name> <board_url>
```
캐시: `/config/boards/{board-name}.json`

### 3.5 이미지 사전 다운로드
```bash
python .claude/skills/pin-fetcher/scripts/prefetch_pins.py <board_name1> [board_name2]
```
로컬 캐시: `/tmp/pins/{board-name}/{pin_id}.jpg`
- 이미 있으면 스킵 (캐시 재활용)
- 3MB 초과 → 리사이즈 (1500px, quality 80)
- 성공률 < 80% → 경고 + 계속 진행

---

## 4. 생성 세션

### 4.1 세션 설정 UI
```
═══ 세션 설정 ═══
• 보드: aesthetic-mood, nature-vibes (핀 총 287개)
• 생성 수량: 200장  (또는 "무제한" 입력)
• 실행 시간: 3시간  (또는 "무제한")
• 이 세션 비용 상한: $30  (Enter로 스킵)
▶ 시작
```

### 4.2 세션 루프
매 이미지 생성 시:
1. `random_picker.py` → Word1, Word2 랜덤 선택
2. `prompt_builder.py` → 템플릿 치환 (LLM 없음)
3. `/tmp/pins/` 에서 5장 랜덤 선택 → base64
4. `generate.py` → Gemini API 호출
5. `track_pins.py` → metadata.json에 즉시 기록
6. `cost_tracker.py` → 비용 업데이트
7. `session_manager.py` → active-session.json 업데이트
8. `stop_checker.py` → 6개 정지 조건 확인

---

## 5. Resume 처리

스크립트 시작 시 `/output/logs/active-session.json` 확인:

```
이전 세션 발견: ses_20260217_103000
진행: 127/200장 완료, $17.02 사용
이어서 진행하시겠습니까? (y/n)
```
- y → `status: "pending"` 항목만 실행 (중복 생성 방지)
- n → 이전 세션 archived 처리 → 새 세션 시작

---

## 6. 세션 제어 정책

### 6.1 정지 조건 (매 생성 완료 후 순차 확인)
1. 수량 도달: `generated >= target_count`
2. 시간 초과: `elapsed >= max_duration_hours`
3. 세션 비용: `session_cost >= session_cost_cap`
4. 일일 비용: `daily_total + next_cost > daily_cap`
5. 월간 비용: `monthly_total + next_cost > monthly_cap`
6. 모델 소진: Pro + Flash 모두 429

### 6.2 비용 체크 (매 생성 직전)
- 다음 이미지 예상 비용 계산
- 세션/일일/월간 상한 초과 예상 시 사전 중단

---

## 7. 모델 전환 정책

```
[1순위] Pro (gemini-3-pro-image-preview)
  $0.134/장, 2K PNG
  └─ 모든 키 429 → Flash 전환 + Slack 알림

[2순위] Flash (gemini-2.5-flash-image)
  $0.039/장, 1K PNG
  ├─ 매 10회마다 Pro 복귀 시도
  └─ Flash도 429 → 60초 대기 → Pro 재시도 → 실패 시 세션 종료
```

API 키는 `/config/api-keys.json`에서 코드 변경 없이 추가 가능.

---

## 8. 프롬프트 조립 규칙

**LLM 호출 없음** — 고정 템플릿 + 문자열 치환만 사용.

```
{word1} → 한국어 단어 (예: 사랑)
{word1_en} → 영어 설명 (예: love, tender warmth, longing)
{word2} → 한국어 단어 (예: 톱니바퀴)
{word2_en} → 영어 설명 (예: gear, clockwork, mechanism)
```

템플릿: `/config/prompt-templates.json` (사용자 직접 수정 가능)
선택 방식: round-robin (순환)

---

## 9. 핀 추적

- **메타데이터**: `reference_pins` 필드에 핀 URL 5개 저장
- **HTML 뷰어**: 세션 종료 시 `generate_viewer.py` 실행
  - 위치: `/output/images/{date}/session-{id}-pins.html`
  - 기능: 이미지 ↔ 참조 핀 시각 대조, 검색/필터/정렬

---

## 10. Slack 알림 정책

| 이벤트 | 트리거 |
|--------|--------|
| 세션 완료 | 세션 종료 시 |
| Flash 전환 | Pro → Flash 전환 시 |
| 연속 실패 | 5회 연속 에러 |
| 비용 상한 | 일일/월간/세션 상한 도달 |

설정: `/config/settings.json` > `notifications.slack_webhook_url`
URL 없으면 알림 비활성화 (세션 진행에 영향 없음).

---

## 11. 스킬 호출 규칙

| 스킬 | 트리거 | 스크립트 |
|------|--------|--------|
| pinterest-connector | 로그인/보드/URL 수집 | login.py, list_boards.py, collect_urls.py |
| pin-fetcher | 보드 선택 후 세션 전 | prefetch_pins.py |
| image-generator | 매 이미지 생성 | generate.py |
| word-manager | 초기 설정 + 세션마다 | init_words.py, random_picker.py |
| session-controller | 세션 시작/종료/매 생성 후 | session_manager.py, cost_tracker.py, stop_checker.py |
| notifier | 이벤트 발생 시 | slack_notify.py |
| pin-tracker | 매 생성 후 + 세션 종료 | track_pins.py, generate_viewer.py |
| drive-uploader | 세션 완료 시 | upload.py |
| session-reporter | 세션 완료 시 | report.py |

---

## 12. 설정 파일 참조

| 파일 | 내용 |
|------|------|
| `/config/api-keys.json` | Gemini API 키 풀 |
| `/config/settings.json` | 모델명, 속도, Slack 웹훅 |
| `/config/cost-tracker.json` | 비용 누적 (일일/월간) |
| `/config/word1-db.json` | Word1 단어 DB |
| `/config/word2-pool.json` | Word2 수식어 풀 |
| `/config/prompt-templates.json` | 프롬프트 템플릿 |
| `/config/boards/{name}.json` | 핀 URL 캐시 |
| `/config/drive-config.json` | Drive 설정 |
| `/output/logs/active-session.json` | 현재 세션 상태 (Resume용) |

---

## 13. 에러 처리

| 에러 | 처리 |
|------|------|
| API 429 | 키 로테이션 → Flash 전환 |
| 연속 5회 실패 | 30초 대기 + Slack 알림 |
| 핀 다운로드 실패 | 스킵 + 로그 (세션 계속) |
| Drive 업로드 실패 | failed-uploads.json 기록 → 다음 세션 재시도 |
| 쿠키 만료 | 재로그인 안내 |
| 세션 중단 | active-session.json 유지 → Resume |

---

## 14. 사용자 명령 인터페이스

| 명령 | 동작 |
|------|------|
| `시작해` | 세션 시작 (Resume 감지 → 보드 선택 → 설정) |
| `멈춰` / `중단` | 현재 이미지 완료 후 세션 종료 |
| `상태 알려줘` | 현재 진행률, 비용, 모델 상태 출력 |
| `재시도` | 마지막 실패 항목 재시도 |
| `보드 갱신` | Pinterest 보드 목록 + 핀 URL 증분 갱신 |
| `Drive 설정` | Google Drive OAuth 초기화 |
| `초기 설정` | 단어 DB + 프롬프트 템플릿 생성 |

---

## 15. 초기 설정 체크리스트

```
□ Gemini API 키 → /config/api-keys.json
□ Pinterest 로그인 (pinterest-dl login)
□ Google Drive OAuth 설정 (선택)
□ 비용 상한 설정 (일일/월간)
□ Slack 웹훅 URL (선택)
□ 단어 DB 초기화 (init_words.py)
□ 단어 DB + 프롬프트 템플릿 검토/수정
```
