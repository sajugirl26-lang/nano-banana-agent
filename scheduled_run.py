#!/usr/bin/env python3
"""예약 실행: 3시/5시/7시 테스트 후 200장 배치"""
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

BASE_CMD = [sys.executable, "run_batch.py"]
WORK_DIR = "d:/01/nano-banana-agent"

# Slack 알림용 import
sys.path.insert(0, str(Path(WORK_DIR) / ".claude" / "skills" / "notifier" / "scripts"))
from slack_notify import send_slack


def wait_until(hour):
    """지정 시각까지 대기"""
    now = datetime.now()
    target = now.replace(hour=hour, minute=0, second=0, microsecond=0)
    if now >= target:
        return
    diff = (target - now).total_seconds()
    print(f"[WAIT] {hour}시까지 대기 ({int(diff//60)}분 남음)...")
    send_slack(f"{hour}시까지 대기 중 ({int(diff//60)}분 남음)", "⏰")
    time.sleep(diff)


def run_test():
    """1장 테스트. 성공=True, 실패=False"""
    now_str = datetime.now().strftime('%H:%M:%S')
    print(f"\n[TEST] 1장 테스트 시작 ({now_str})")
    send_slack(f"1장 테스트 시작 ({now_str})", "🧪")

    result = subprocess.run(
        BASE_CMD + ["1", "--no-refresh"],
        cwd=WORK_DIR, capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=300
    )
    output = result.stdout + result.stderr

    if result.returncode == 0 and "[OK]" in output and "0/1" not in output:
        print("[TEST] 성공!")
        send_slack("1장 테스트 성공! 200장 배치를 시작합니다.", "✅")
        return True
    else:
        print("[TEST] 실패")
        send_slack("1장 테스트 실패 (503/API 에러). 다음 시간에 재시도합니다.", "❌")
        return False


def run_batch_200():
    """200장 배치 실행"""
    now_str = datetime.now().strftime('%H:%M:%S')
    print(f"\n[BATCH] 200장 배치 시작 ({now_str})")
    send_slack(f"200장 배치 시작 ({now_str})", "🚀")

    result = subprocess.run(
        BASE_CMD + ["200", "--no-refresh"],
        cwd=WORK_DIR, encoding="utf-8", errors="replace",
        timeout=600 * 60
    )
    print(f"[BATCH] 완료 (exit code: {result.returncode})")


def main():
    schedule = [3, 5, 7]
    send_slack(f"예약 실행 시작 - 스케줄: {schedule[0]}시/{schedule[1]}시/{schedule[2]}시", "📋")

    for i, hour in enumerate(schedule):
        wait_until(hour)
        if run_test():
            run_batch_200()
            return
        else:
            remaining = schedule[i+1:] if i+1 < len(schedule) else []
            if remaining:
                send_slack(f"다음 시도: {remaining[0]}시", "⏭️")
            print(f"[INFO] {hour}시 테스트 실패. 다음 시도로 넘어갑니다.")

    send_slack("3시/5시/7시 모두 실패. 예약 실행을 중단합니다.", "🛑")
    print("\n[STOP] 3시/5시/7시 모두 실패. 중단합니다.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        send_slack("예약 실행이 수동 중단되었습니다 (Ctrl+C)", "⛔")
        print("\n[STOP] Ctrl+C")
        sys.exit(0)
