#!/usr/bin/env python3
"""Slack 웹훅 알림"""
import json
from pathlib import Path

import requests

CONFIG_DIR = Path(__file__).parents[4] / "config"
SETTINGS_FILE = CONFIG_DIR / "settings.json"


SECRETS_FILE = CONFIG_DIR / "secrets.json"


def get_webhook_url() -> str | None:
    # secrets.json 우선, 없으면 settings.json fallback
    if SECRETS_FILE.exists():
        with open(SECRETS_FILE, encoding="utf-8") as f:
            s = json.load(f)
        url = s.get("slack_webhook_url", "")
        if url and "YOUR/WEBHOOK" not in url:
            return url
    if not SETTINGS_FILE.exists():
        return None
    with open(SETTINGS_FILE, encoding="utf-8") as f:
        s = json.load(f)
    url = s.get("notifications", {}).get("slack_webhook_url", "")
    if not url or "YOUR/WEBHOOK" in url or "__see_" in url:
        return None
    return url


def send_slack(message: str, emoji: str = "📢", retries: int = 2) -> bool:
    """Slack 웹훅으로 메시지 전송. 실패 시 재시도."""
    import time
    url = get_webhook_url()
    if not url:
        return False
    payload = {"text": f"{emoji} {message}"}
    for attempt in range(retries + 1):
        try:
            resp = requests.post(url, json=payload, timeout=10)
            resp.raise_for_status()
            return True
        except Exception as e:
            if attempt < retries:
                time.sleep(2 ** attempt)
            else:
                print(f"[WARN] Slack 알림 실패 ({retries+1}회 시도): {e}")
                return False


def notify_session_complete(
    session_id: str, pro_count: int, flash_count: int,
    total_cost: float, drive_ok: int, total: int, stop_reason: str
) -> bool:
    is_abnormal = "과사용" in stop_reason or "비용" in stop_reason or "cost" in stop_reason.lower() or "한도" in stop_reason
    label = "세션 중단" if is_abnormal else "세션 완료"
    emoji = "🚨" if is_abnormal else "✅"
    msg = (
        f"{label} ({stop_reason})\n"
        f"Pro {pro_count}장 + Flash {flash_count}장 = ${total_cost:.2f}\n"
        f"Drive 업로드 {drive_ok}/{total} 완료"
    )
    return send_slack(msg, emoji)


def notify_model_switch(from_model: str = "Pro", to_model: str = "Flash", reason: str = "") -> bool:
    msg = f"Flash로 전환 — {reason or '키 429'}. 매 10회마다 Pro 복귀 시도"
    return send_slack(msg, "⚡")


def notify_consecutive_errors(error_count: int, last_error: str) -> bool:
    msg = f"연속 {error_count}회 실패 — {last_error[:100]}. 30초 대기 후 재시도"
    return send_slack(msg, "⚠️")


def notify_cost_limit(limit_type: str, limit_val: float, current: float) -> bool:
    msg = (
        f"{limit_type} 비용 상한 도달\n"
        f"• 상한: ${limit_val:.2f}\n"
        f"• 현재: ${current:.2f}\n"
        f"• 세션 자동 정지"
    )
    return send_slack(msg, "⚠️")


def notify_batch_submitted(count: int, estimated_cost: float, model: str) -> bool:
    msg = (
        f"Gemini Batch 제출 완료\n"
        f"• {count}장 요청 (모델: {model})\n"
        f"• 예상 비용: ${estimated_cost:.2f} (50% 할인 적용)"
    )
    return send_slack(msg, "📦")


def notify_batch_complete(
    success: int, fail: int, total_cost: float,
    drive_ok: int, elapsed_min: int
) -> bool:
    msg = (
        f"Gemini Batch 완료\n"
        f"• 성공 {success}장 / 실패 {fail}장\n"
        f"• 비용: ${total_cost:.2f}\n"
        f"• Drive 업로드: {drive_ok}장\n"
        f"• 소요 시간: {elapsed_min}분"
    )
    return send_slack(msg, "✅")


if __name__ == "__main__":
    print("Slack 알림 테스트...")
    result = send_slack("테스트 메시지", "🔔")
    print(f"결과: {'성공' if result else '설정 없음 또는 실패'}")
