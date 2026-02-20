# session-controller

Resume 감지, 세션 초기화, 비용 추적, 정지 조건 체크

## 스크립트

### session_manager.py
세션 라이프사이클 전체 관리
```python
from session_manager import (
    check_resume, display_resume_prompt, archive_old_session,
    create_new_session, update_session_progress, close_session,
    get_pending_pairs
)

# 시작 시
session = check_resume()
if session:
    if display_resume_prompt(session):
        pairs = get_pending_pairs()  # 미완료 항목만
    else:
        archive_old_session(session)
        session = create_new_session(boards, settings)
else:
    session = create_new_session(boards, settings)

# 매 생성 완료 후
update_session_progress(combo_id, "done", cost, is_flash)

# 세션 종료 시
close_session("수량 도달")
```

**active-session.json 위치:** `/output/logs/active-session.json`

### cost_tracker.py
비용 누적 + 일일/월간 자동 리셋
```python
from cost_tracker import add_cost, get_daily_total, get_monthly_total, set_limits
add_cost(0.134, is_flash=False)
daily = get_daily_total()
monthly = get_monthly_total()
```

**비용 파일:** `/config/cost-tracker.json`
날짜가 변경되면 일일 카운터 자동 리셋, 월이 변경되면 월간 카운터 자동 리셋.

### stop_checker.py
6개 정지 조건 순차 확인
```python
from stop_checker import check_stop_conditions
should_stop, reason = check_stop_conditions(
    generated, failed, target_count,
    start_time, max_duration_hours,
    session_cost, session_cost_cap,
    daily_total, daily_cap,
    monthly_total, monthly_cap,
    all_models_exhausted
)
```

**정지 조건 순서:**
1. 수량 도달 (`generated >= target_count`)
2. 시간 초과 (`elapsed >= max_duration_hours`)
3. 세션 비용 상한
4. 일일 비용 상한
5. 월간 비용 상한
6. 모든 모델 소진 (Pro + Flash 모두 429)
