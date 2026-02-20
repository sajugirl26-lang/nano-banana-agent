#!/usr/bin/env python3
"""세션 완료 리포트 생성"""
import time
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).parents[4]
LOGS_DIR = BASE_DIR / "output" / "logs"


def generate_report(session: dict, start_time: float) -> str:
    """세션 완료 리포트 텍스트 생성"""
    prog = session.get("progress", {})
    settings = session.get("settings", {})
    boards = session.get("boards_used", [])
    stop_reason = session.get("stop_reason", "알 수 없음")

    elapsed = time.time() - start_time
    h = int(elapsed // 3600)
    m = int((elapsed % 3600) // 60)
    s = int(elapsed % 60)

    generated = prog.get("generated", 0)
    failed = prog.get("failed", 0)
    pro_count = prog.get("pro_count", 0)
    flash_count = prog.get("flash_count", 0)
    session_cost = prog.get("session_cost", 0.0)
    pro_cost = round(pro_count * 0.134, 2)
    flash_cost = round(flash_count * 0.039, 2)

    target = settings.get("target_count", "무제한")
    session_cap = settings.get("session_cost_cap")
    cap_str = f"${session_cap:.2f}" if session_cap else "미설정"

    report = f"""
{'='*52}
세션 완료
{'='*52}
• 세션 ID: {session['session_id']}
• 보드: {', '.join(boards)}
• 정지 사유: {stop_reason}

📊 생성 결과
├─ Pro  (2K): {pro_count:4d}장  — ${pro_cost:.2f}
├─ Flash(1K): {flash_count:4d}장  — ${flash_cost:.2f}
└─ 합계: {generated}장 성공 / {failed}장 실패  — ${session_cost:.2f}

💰 비용 현황
├─ 이 세션: ${session_cost:.2f} / {cap_str} 상한
└─ 설정: {target}장 목표

⏱ 소요: {h}시간 {m}분 {s}초
{'='*52}"""

    return report.strip()


def save_report(session: dict, report_text: str) -> str:
    """리포트 파일 저장"""
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    report_file = LOGS_DIR / f"report-{session['session_id']}.txt"
    with open(report_file, "w", encoding="utf-8") as f:
        f.write(report_text)
    print(f"[OK] 리포트 저장: {report_file}")
    return str(report_file)


def print_and_save_report(session: dict, start_time: float) -> str:
    """리포트 출력 + 저장 통합"""
    text = generate_report(session, start_time)
    print(text)
    return save_report(session, text)


if __name__ == "__main__":
    import json
    sample = {
        "session_id": "ses_test",
        "boards_used": ["aesthetic-mood"],
        "settings": {"target_count": 50},
        "progress": {"generated": 47, "failed": 3, "pro_count": 40, "flash_count": 7, "session_cost": 5.63},
        "stop_reason": "수량 도달"
    }
    print(generate_report(sample, time.time() - 3600))
