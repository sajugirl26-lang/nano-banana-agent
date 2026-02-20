# 나노바나나 에이전트 설치 가이드

## 1. 사전 요구사항

### Python 패키지 설치
```bash
pip install pinterest-dl pillow requests google-generativeai \
            google-auth google-auth-oauthlib google-api-python-client
```

### 패키지 역할
| 패키지 | 용도 |
|--------|------|
| `pinterest-dl` | Pinterest 로그인 + 핀 수집 |
| `pillow` | 핀 이미지 리사이즈 |
| `requests` | HTTP 다운로드 |
| `google-generativeai` | Gemini API 이미지 생성 |
| `google-auth`, `google-auth-oauthlib` | Google OAuth |
| `google-api-python-client` | Google Drive API |

---

## 2. Gemini API 설정

### 2.1 Google Cloud 프로젝트 생성
1. [Google Cloud Console](https://console.cloud.google.com) 접속
2. 프로젝트 생성 (최대 3개 권장 — Rate Limit 분산)
3. **Gemini API** 활성화
4. **결제 활성화 + Tier 1** 업그레이드 (Rate Limit 향상)

### 2.2 API 키 발급
1. `APIs & Services` → `Credentials` → `API Key 생성`
2. `/config/api-keys.json` 에 추가:

```json
{
  "keys": [
    {
      "id": "key_1",
      "project": "my-project-alpha",
      "api_key": "AIza...",
      "daily_limit": 40
    },
    {
      "id": "key_2",
      "project": "my-project-beta",
      "api_key": "AIza...",
      "daily_limit": 40
    }
  ],
  "global": {
    "min_interval_seconds": 20,
    "ipm_limit": 3,
    "daily_limit_per_key": 40,
    "max_retry": 3,
    "cooldown_seconds": 60
  }
}
```

> **키 추가**: 코드 변경 없이 `keys` 배열에 항목 추가하면 됩니다.

---

## 3. Pinterest 로그인

```bash
cd nano-banana-agent
python .claude/skills/pinterest-connector/scripts/login.py
```

- 브라우저가 열리면 Pinterest 로그인
- 로그인 후 창 닫기
- 쿠키 저장: `/config/credentials/pinterest-cookies.json`

> **주의**: 비공개 보드 접근을 위해 실제 계정으로 로그인해야 합니다.

---

## 4. 단어 DB 초기화

```bash
python .claude/skills/word-manager/scripts/init_words.py
```

생성 파일:
- `/config/word1-db.json` — 감정/자연/판타지/일상/추상 5개 카테고리, 100개 단어
- `/config/word2-pool.json` — 200개 수식어 풀

이후 파일을 직접 편집하여 단어 추가/수정 가능합니다.

---

## 5. 프롬프트 템플릿 설정

`/config/prompt-templates.json` 편집:

```json
{
  "templates": [
    {
      "id": "my_template",
      "text": "Your prompt with {word1}({word1_en}) and {word2}({word2_en}), style description..."
    }
  ]
}
```

**필수 플레이스홀더:** `{word1}`, `{word1_en}`, `{word2}`, `{word2_en}`

---

## 6. 비용 상한 설정

`/config/cost-tracker.json` 편집:

```json
{
  "limits": {
    "daily_cost_cap": 50.00,
    "monthly_cost_cap": 500.00,
    "session_cost_cap_default": null
  }
}
```

---

## 7. Google Drive 설정 (선택)

### 7.1 OAuth 2.0 (개인 계정)
1. [Google Cloud Console](https://console.cloud.google.com) → `APIs & Services` → `Credentials`
2. `OAuth 2.0 Client ID` 생성 (데스크톱 앱 유형)
3. JSON 다운로드 → `/config/credentials/oauth-client.json` 에 저장
4. Drive API 활성화:

```bash
python .claude/skills/drive-uploader/scripts/drive_setup.py
```

### 7.2 Service Account (GCP 프로젝트 내)
1. `IAM & Admin` → `Service Accounts` → 생성
2. `Drive API` 권한 부여
3. JSON 키 다운로드 → `/config/credentials/drive-sa.json`
4. `drive_setup.py` 실행

---

## 8. Slack 알림 설정 (선택)

1. Slack 워크스페이스 → `앱` → `Incoming Webhooks` 추가
2. 웹훅 URL 복사
3. `/config/settings.json` 수정:

```json
{
  "notifications": {
    "slack_webhook_url": "https://hooks.slack.com/services/T.../B.../..."
  }
}
```

---

## 9. 세션 시작

Claude Code를 이 프로젝트 폴더에서 실행:

```bash
cd nano-banana-agent
claude
```

그리고 대화창에서:
```
시작해
```

---

## 10. 폴더 구조

```
nano-banana-agent/
├── CLAUDE.md                    ← 에이전트 메인 설정
├── .claude/skills/              ← 스킬 모듈
│   ├── pinterest-connector/
│   ├── pin-fetcher/
│   ├── image-generator/
│   ├── word-manager/
│   ├── session-controller/
│   ├── notifier/
│   ├── pin-tracker/
│   ├── drive-uploader/
│   └── session-reporter/
├── config/                      ← 설정 파일 (수동 편집)
│   ├── api-keys.json            ← API 키 (반드시 설정!)
│   ├── settings.json
│   ├── cost-tracker.json
│   ├── word1-db.json
│   ├── word2-pool.json
│   ├── prompt-templates.json
│   └── boards/                  ← 핀 URL 캐시 (자동 생성)
├── tmp/pins/                    ← 핀 이미지 캐시 (자동 생성)
└── output/                      ← 생성 결과 (자동 생성)
    ├── images/{date}/
    └── logs/
```

---

## 11. 비용 참고

| 모델 | 해상도 | 단가 |
|------|--------|------|
| Pro (gemini-3-pro-image-preview) | 2K PNG | $0.134/장 |
| Flash (gemini-2.5-flash-image) | 1K PNG | $0.039/장 |

| 시나리오 | 예상 수량/일 | 예상 비용/일 |
|---------|------------|------------|
| 보수적 (2장/분, 8시간) | ~960장 | ~$129 |
| 적극적 (3장/분, 12시간) | ~2,160장 | ~$289 |

> **권장**: 처음에는 일일 상한 $10-20로 시작하여 결과를 확인하세요.
