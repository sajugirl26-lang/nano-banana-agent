#!/usr/bin/env python3
"""6개 정지 조건 순차 확인"""
import json
import time
from pathlib import Path

SETTINGS_FILE = Path(__file__).parents[4] / "config" / "settings.json"

def _load_prices():
    if SETTINGS_FILE.exists():
        with open(SETTINGS_FILE, encoding="utf-8") as f:
            s = json.load(f)
        return (
            s.get("price_pro", 0.134),
            s.get("price_flash", 0.039),
            s.get("price_pro_batch", 0.067),
            s.get("price_flash_batch", 0.0195),
        )
    return 0.134, 0.039, 0.067, 0.0195

PRICE_PRO, PRICE_FLASH, PRICE_PRO_BATCH, PRICE_FLASH_BATCH = _load_prices()


def check_stop_conditions(
    generated: int,
    failed: int,
    target_count: int,
    start_time: float,
    max_duration_hours: float,
    session_cost: float,
    session_cost_cap: float | None,
    daily_total: float,
    daily_cap: float,
    monthly_total: float,
    monthly_cap: float,
    all_models_exhausted: bool,
    next_is_flash: bool = False,
    is_batch: bool = False
) -> tuple:
    """정지 조건 확인. (should_stop: bool, reason: str)"""
    if is_batch:
        next_cost = PRICE_FLASH_BATCH if next_is_flash else PRICE_PRO_BATCH
    else:
        next_cost = PRICE_FLASH if next_is_flash else PRICE_PRO

    # ① 수량 도달
    if target_count > 0 and generated >= target_count:
        return True, f"수량 도달 ({generated}/{target_count}장)"

    # ② 시간 초과
    if max_duration_hours > 0:
        elapsed_hours = (time.time() - start_time) / 3600
        if elapsed_hours >= max_duration_hours:
            return True, f"시간 제한 ({max_duration_hours}시간)"

    # ③ 세션 비용 상한
    if session_cost_cap and session_cost_cap > 0:
        if session_cost + next_cost > session_cost_cap:
            return True, f"세션 비용 상한 (${session_cost_cap:.2f})"

    # ④ 일일 비용 상한
    if daily_cap > 0 and daily_total + next_cost > daily_cap:
        return True, f"일일 비용 상한 (${daily_cap:.2f})"

    # ⑤ 월간 비용 상한
    if monthly_cap > 0 and monthly_total + next_cost > monthly_cap:
        return True, f"월간 비용 상한 (${monthly_cap:.2f})"

    # ⑥ 모든 모델 소진
    if all_models_exhausted:
        return True, "모든 모델 한도 소진"

    return False, ""


def format_elapsed(start_time: float) -> str:
    elapsed = time.time() - start_time
    h = int(elapsed // 3600)
    m = int((elapsed % 3600) // 60)
    s = int(elapsed % 60)
    return f"{h}시간 {m}분 {s}초"
