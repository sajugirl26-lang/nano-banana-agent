# notifier

Slack 웹훅 알림 전송

## 설정
`/config/settings.json` 의 `notifications.slack_webhook_url` 에 Slack Incoming Webhook URL 설정.
URL이 없거나 기본값이면 알림 비활성화 (세션 진행에 영향 없음).

## 스크립트

### slack_notify.py
```python
from slack_notify import (
    notify_session_complete,
    notify_model_switch,
    notify_consecutive_errors,
    notify_cost_limit
)

# 세션 완료
notify_session_complete(session_id, pro_count, flash_count, total_cost, drive_ok, total, stop_reason)

# 모델 전환 (Pro → Flash)
notify_model_switch("Pro", "Flash", "키 3개 모두 429")

# 연속 실패
notify_consecutive_errors(5, "API 에러 메시지")

# 비용 상한
notify_cost_limit("일일", 50.0, 49.87)
```

## 알림 이벤트

| 이벤트 | 이모지 | 트리거 |
|--------|--------|--------|
| 세션 완료 | ✅ | 세션 종료 시 |
| Flash 전환 | ⚡ | Pro → Flash 전환 시 |
| 연속 실패 | ⚠️ | 5회 연속 에러 |
| 비용 상한 | ⚠️ | 일일/월간/세션 상한 도달 |
