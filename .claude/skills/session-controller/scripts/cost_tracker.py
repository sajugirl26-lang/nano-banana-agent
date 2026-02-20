#!/usr/bin/env python3
"""비용 추적 — 세션/일일/월간 누적, 자동 리셋"""
import json
from datetime import date
from pathlib import Path

CONFIG_DIR = Path(__file__).parents[4] / "config"
COST_FILE = CONFIG_DIR / "cost-tracker.json"


def load_tracker() -> dict:
    if not COST_FILE.exists():
        t = _default_tracker()
        save_tracker(t)
        return t
    with open(COST_FILE, encoding="utf-8") as f:
        return json.load(f)


def save_tracker(data: dict):
    COST_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(COST_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _default_tracker() -> dict:
    today = str(date.today())
    month = today[:7]
    return {
        "limits": {
            "daily_cost_cap": 50.00,
            "monthly_cost_cap": 500.00,
            "session_cost_cap_default": None
        },
        "daily": {
            "date": today,
            "pro_count": 0, "pro_cost": 0.0,
            "flash_count": 0, "flash_cost": 0.0,
            "total_cost": 0.0
        },
        "monthly": {
            "month": month,
            "pro_count": 0, "pro_cost": 0.0,
            "flash_count": 0, "flash_cost": 0.0,
            "total_cost": 0.0
        }
    }


def _ensure_current(data: dict) -> dict:
    """일일/월간 날짜 확인 후 리셋"""
    today = str(date.today())
    month = today[:7]
    if data["daily"]["date"] != today:
        data["daily"] = {
            "date": today,
            "pro_count": 0, "pro_cost": 0.0,
            "flash_count": 0, "flash_cost": 0.0,
            "total_cost": 0.0
        }
    if data["monthly"]["month"] != month:
        data["monthly"] = {
            "month": month,
            "pro_count": 0, "pro_cost": 0.0,
            "flash_count": 0, "flash_cost": 0.0,
            "total_cost": 0.0
        }
    return data


def add_cost(cost: float, is_flash: bool):
    """생성 완료 후 비용 추가"""
    data = _ensure_current(load_tracker())
    if is_flash:
        data["daily"]["flash_count"] += 1
        data["daily"]["flash_cost"] = round(data["daily"]["flash_cost"] + cost, 4)
        data["monthly"]["flash_count"] += 1
        data["monthly"]["flash_cost"] = round(data["monthly"]["flash_cost"] + cost, 4)
    else:
        data["daily"]["pro_count"] += 1
        data["daily"]["pro_cost"] = round(data["daily"]["pro_cost"] + cost, 4)
        data["monthly"]["pro_count"] += 1
        data["monthly"]["pro_cost"] = round(data["monthly"]["pro_cost"] + cost, 4)
    data["daily"]["total_cost"] = round(data["daily"]["total_cost"] + cost, 4)
    data["monthly"]["total_cost"] = round(data["monthly"]["total_cost"] + cost, 4)
    save_tracker(data)


def get_daily_total() -> float:
    return _ensure_current(load_tracker())["daily"]["total_cost"]


def get_monthly_total() -> float:
    return _ensure_current(load_tracker())["monthly"]["total_cost"]


def get_limits() -> dict:
    return load_tracker().get("limits", {})


def set_limits(daily_cap: float = None, monthly_cap: float = None):
    data = load_tracker()
    if daily_cap is not None:
        data["limits"]["daily_cost_cap"] = daily_cap
    if monthly_cap is not None:
        data["limits"]["monthly_cost_cap"] = monthly_cap
    save_tracker(data)
    print(f"[OK] 비용 상한: 일일 ${data['limits']['daily_cost_cap']}, 월간 ${data['limits']['monthly_cost_cap']}")


def get_status_summary() -> str:
    data = _ensure_current(load_tracker())
    lim = data["limits"]
    d = data["daily"]
    m = data["monthly"]
    return (
        f"  일일: ${d['total_cost']:.2f} / ${lim['daily_cost_cap']:.2f} "
        f"(Pro {d['pro_count']}장, Flash {d['flash_count']}장)\n"
        f"  월간: ${m['total_cost']:.2f} / ${lim['monthly_cost_cap']:.2f} "
        f"(Pro {m['pro_count']}장, Flash {m['flash_count']}장)"
    )
