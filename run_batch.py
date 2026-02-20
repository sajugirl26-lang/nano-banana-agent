#!/usr/bin/env python3
"""
나노바나나 — 비대화형 배치 실행
사용: python run_batch.py [장수] (기본 999)
"""
import json
import random
import sys
import time
import atexit
from collections import deque
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).parent
SKILLS_DIR = BASE_DIR / ".claude" / "skills"
for skill in ["session-controller", "word-manager", "image-generator",
              "pin-fetcher", "pin-tracker", "drive-uploader",
              "session-reporter", "notifier", "pinterest-connector"]:
    sys.path.insert(0, str(SKILLS_DIR / skill / "scripts"))

from session_manager import create_new_session, get_pending_pairs, update_session_progress, close_session, check_resume, get_current_session
from generate import generate_image
from cost_tracker import add_cost, get_daily_total, get_monthly_total, get_limits, get_status_summary
from stop_checker import check_stop_conditions
from track_pins import append_entry
from slack_notify import notify_consecutive_errors, notify_model_switch, notify_cost_limit, notify_session_complete
from rate_limiter import get_rate_limiter
from upload import upload_single_image, upload_metadata_file, upload_html_file


LOCK_FILE = Path(__file__).parent / "output" / "logs" / "batch.lock"


def _find_existing_batch_processes():
    """현재 실행 중인 run_batch.py 프로세스 목록 (자기 자신 제외)"""
    import os, subprocess
    my_pid = os.getpid()
    try:
        result = subprocess.run(
            ['wmic', 'process', 'where',
             "CommandLine like '%run_batch.py%' and Name like '%python%'",
             'get', 'ProcessId'],
            capture_output=True, text=True, timeout=10
        )
        pids = []
        for line in result.stdout.strip().split('\n'):
            line = line.strip()
            if line.isdigit() and int(line) != my_pid:
                pids.append(int(line))
        return pids
    except Exception:
        return []


def acquire_lock():
    """프로세스 락 — 동시 실행 방지 (lock 파일 + 프로세스 직접 검사)"""
    import os

    # 1단계: lock 파일과 무관하게, run_batch.py 프로세스가 이미 있는지 직접 확인
    existing = _find_existing_batch_processes()
    if existing:
        print(f"[ERROR] run_batch.py가 이미 실행 중입니다 (PID: {existing})")
        print(f"  종료 후 다시 시도하세요.")
        sys.exit(1)

    # 2단계: lock 파일 확인 (프로세스가 없는데 lock만 남은 경우 = stale lock → 자동 정리)
    if LOCK_FILE.exists():
        try:
            old_pid = int(LOCK_FILE.read_text().strip())
            import subprocess
            result = subprocess.run(
                ['tasklist.exe', '/FI', f'PID eq {old_pid}', '/NH'],
                capture_output=True, text=True
            )
            if str(old_pid) in result.stdout:
                print(f"[ERROR] 이미 실행 중인 배치가 있습니다 (PID {old_pid})")
                sys.exit(1)
            else:
                print(f"[INFO] stale lock 정리 (PID {old_pid} 이미 종료됨)")
                LOCK_FILE.unlink(missing_ok=True)
        except Exception:
            print(f"[INFO] 깨진 lock 파일 정리")
            LOCK_FILE.unlink(missing_ok=True)

    LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    LOCK_FILE.write_text(str(os.getpid()))
    atexit.register(release_lock)


def release_lock():
    LOCK_FILE.unlink(missing_ok=True)


def print_report(report_type, session_id, generated, failed_count, pro_count, flash_count, session_cost, start_time, target):
    """진행 상황 보고"""
    elapsed = time.time() - start_time
    hours = int(elapsed // 3600)
    mins = int((elapsed % 3600) // 60)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    pending = target - generated - failed_count

    print(f"\n{'=' * 55}")
    if report_type == "start":
        print(f"[REPORT] 배치 시작 | {now}")
    elif report_type == "hourly":
        print(f"[REPORT] 1시간 경과 보고 | {now}")
    elif report_type == "complete":
        print(f"[REPORT] 배치 완료 | {now}")

    print(f"  세션: {session_id}")
    print(f"  진행: {generated}/{target} 완료 | {failed_count} 실패 | {pending} 남음")
    from stop_checker import PRICE_PRO, PRICE_FLASH
    print(f"  모델: Pro {pro_count}장 (${pro_count * PRICE_PRO:.2f}) | Flash {flash_count}장 (${flash_count * PRICE_FLASH:.2f})")
    print(f"  API 호출: 총 {pro_count + flash_count + failed_count}회 (성공 {generated}, 실패 {failed_count})")
    print(f"  비용: ${session_cost:.2f} (세션) | {get_status_summary()}")
    print(f"  시간: {hours}h {mins}m 경과")
    print(f"{'=' * 55}\n", flush=True)


def deploy_to_github_pages(html_path):
    """뷰어 HTML을 docs/index.html로 복사 후 GitHub에 push"""
    import shutil, subprocess
    try:
        docs_dir = BASE_DIR / "docs"
        docs_dir.mkdir(exist_ok=True)
        dest = docs_dir / "index.html"
        shutil.copy2(str(html_path), str(dest))
        print(f"[DEPLOY] docs/index.html 업데이트")

        now = datetime.now().strftime("%m/%d %H:%M")
        subprocess.run(["git", "add", "docs/index.html"], cwd=str(BASE_DIR), timeout=30)
        subprocess.run(
            ["git", "commit", "-m", f"Update viewer {now}"],
            cwd=str(BASE_DIR), capture_output=True, timeout=30
        )
        result = subprocess.run(
            ["git", "push"], cwd=str(BASE_DIR),
            capture_output=True, text=True, timeout=60
        )
        if result.returncode == 0:
            print(f"[DEPLOY] GitHub Pages 배포 완료")
        else:
            print(f"[WARN] git push 실패: {result.stderr[:200]}")
    except Exception as e:
        print(f"[WARN] GitHub Pages 배포 실패: {e}")


def refresh_pins():
    """배치 시작 전 보드 목록 + 핀 URL 갱신"""
    print("\n[PIN REFRESH] 보드/핀 갱신 시작...")
    try:
        from list_boards import list_boards
        boards = list_boards()
        print(f"  보드 {len(boards)}개 확인")
    except Exception as e:
        print(f"  [WARN] 보드 목록 갱신 실패 (기존 유지): {e}")
        boards = None

    boards_file = BASE_DIR / "config" / "pinterest-boards.json"
    with open(boards_file, encoding="utf-8") as f:
        all_boards = json.load(f)

    try:
        from collect_urls import collect_board_urls
        total_new = 0
        for b in all_boards:
            result = collect_board_urls(b["board_name"], b["board_url"], b.get("is_private", False))
            if result:
                old_count = len(result.get("pins", []))
                total_new += old_count
        print(f"[PIN REFRESH] 완료 — 총 {total_new}핀")
    except Exception as e:
        print(f"  [WARN] 핀 URL 갱신 실패 (기존 캐시 유지): {e}")


def main():
    acquire_lock()
    target = int(sys.argv[1]) if len(sys.argv) > 1 else 999

    # 배치 시작 전 핀 갱신
    refresh_pins()

    # 모든 보드 사용
    boards_file = BASE_DIR / "config" / "pinterest-boards.json"
    with open(boards_file, encoding="utf-8") as f:
        all_boards = json.load(f)
    board_names = [b["board_name"] for b in all_boards]

    print(f"\n[Nano-Banana] Batch Mode")
    print(f"  target: {target}")
    print(f"  boards: {len(board_names)}")
    print("=" * 50)

    # 기존 세션 resume 또는 새 세션 생성
    existing = check_resume()
    if existing:
        session = existing
        done = sum(1 for p in session["word_pairs"] if p["status"] == "done")
        print(f"[RESUME] session {session['session_id']} ({done} done, resuming...)")
    else:
        settings = {
            "target_count": target,
            "max_duration_hours": -1,
            "session_cost_cap": None
        }
        session = create_new_session(board_names, settings)
    start_time = time.time()

    rl = get_rate_limiter()
    consecutive_errors = 0
    template_index = 0
    recent_pins = deque(maxlen=50)
    generated = 0
    failed_count = 0
    pro_count = 0
    flash_count = 0
    drive_ok = 0
    session_cost = 0.0
    today_date = datetime.now().strftime("%y%m%d")
    last_report_time = time.time()

    stop_reason = "batch complete"

    print(f"\n[START] session {session['session_id']}")
    print_report("start", session["session_id"], generated, failed_count, pro_count, flash_count, session_cost, start_time, target)

    while True:
        pending = get_pending_pairs()
        if not pending:
            close_session("batch complete", rl.get_total_api_calls())
            break

        pair = pending[0]
        limits = get_limits()
        daily_total = get_daily_total()
        monthly_total = get_monthly_total()

        should_stop, reason = check_stop_conditions(
            generated=generated,
            failed=failed_count,
            target_count=target,
            start_time=start_time,
            max_duration_hours=-1,
            session_cost=session_cost,
            session_cost_cap=None,
            daily_total=daily_total,
            daily_cap=limits.get("daily_cost_cap", 0),
            monthly_total=monthly_total,
            monthly_cap=limits.get("monthly_cost_cap", 0),
            all_models_exhausted=rl.all_keys_rate_limited(),
            next_is_flash=rl.is_flash_mode
        )

        if should_stop:
            print(f"\n[STOP] {reason}")
            stop_reason = reason
            if "cost" in reason.lower() or "비용" in reason:
                notify_cost_limit(reason, limits.get("daily_cost_cap", 0), daily_total)
            close_session(reason, rl.get_total_api_calls())
            break

        print(f"\n[{generated+1}/{target}] {pair['word1']} x {pair['word2']}", end="", flush=True)

        result = generate_image(
            word1=pair["word1"], word1_en=pair["word1_en"],
            word2=pair["word2"], word2_en=pair["word2_en"],
            board_names=board_names,
            combo_id=pair["combo_id"],
            template_index=template_index,
            recent_pins=recent_pins
        )
        template_index += 1

        if result.get("status") == "success":
            cost = result.get("cost", 0)
            add_cost(cost, False)
            session_cost = round(session_cost + cost, 4)
            generated += 1
            pro_count += 1
            consecutive_errors = 0
            update_session_progress(pair["combo_id"], "done", cost, False)

            # Drive 업로드
            drive_id = upload_single_image(result.get("file_path", ""), result, today_date)
            if drive_id:
                result["drive_uploaded"] = True
                result["drive_file_id"] = drive_id
                drive_ok += 1
                print(f" [OK] ${cost:.3f} ({result.get('resolution', '?')}) [DRIVE OK]")
            else:
                print(f" [OK] ${cost:.3f} ({result.get('resolution', '?')})")

            append_entry(result, today_date)
            recent_pins.append(result.get("file_path", ""))
        else:
            failed_count += 1
            consecutive_errors += 1
            update_session_progress(pair["combo_id"], "failed", 0, False, error=result.get("error", "unknown"))
            print(f" [FAIL] {result.get('error', 'unknown')[:50]}")

            if consecutive_errors >= 5:
                notify_consecutive_errors(consecutive_errors, result.get("error", ""))
                print(f"\n  [EMERGENCY] 연속 {consecutive_errors}회 실패 — 프로세스를 자동 중단합니다.")
                stop_reason = f"연속 {consecutive_errors}회 실패 자동 중단"
                close_session(stop_reason, rl.get_total_api_calls())
                break

        # API 과사용 실시간 감지 (10장 이상 시도 후부터 체크)
        total_attempts = generated + failed_count
        if total_attempts >= 10:
            total_api_calls = rl.get_total_api_calls()
            overhead = total_api_calls - total_attempts
            if overhead > total_attempts * 0.5:
                print(f"\n  [EMERGENCY] API 과사용 감지! 호출 {total_api_calls}회 vs 시도 {total_attempts}회 (초과 {overhead}회)")
                print(f"  프로세스를 자동 중단합니다.")
                stop_reason = f"API 과사용 자동 중단 (초과 {overhead}회/{total_attempts}회)"
                close_session(stop_reason, rl.get_total_api_calls())
                break

        # random delay 30~60s
        wait_sec = random.randint(30, 60)
        print(f"  [WAIT] {wait_sec}s ...", end="", flush=True)
        time.sleep(wait_sec)
        print(" OK")

        # 1시간마다 진행 보고
        if time.time() - last_report_time >= 3600:
            print_report("hourly", session["session_id"], generated, failed_count, pro_count, flash_count, session_cost, start_time, target)
            last_report_time = time.time()

    # 완료 보고
    print_report("complete", session["session_id"], generated, failed_count, pro_count, flash_count, session_cost, start_time, target)

    # HTML viewer 생성 + Drive 업로드 + GitHub Pages 배포
    try:
        from generate_viewer import generate_viewer
        html_path = generate_viewer(session["session_id"])
        if html_path:
            upload_html_file(str(html_path))
            deploy_to_github_pages(html_path)
    except Exception as e:
        print(f"[WARN] viewer: {e}")

    # metadata Drive 업로드
    try:
        from track_pins import get_metadata_file
        meta_path = get_metadata_file(today_date)
        if meta_path.exists():
            upload_metadata_file(str(meta_path))
    except Exception as e:
        print(f"[WARN] metadata upload: {e}")

    # Slack
    notify_session_complete(
        session["session_id"],
        pro_count,
        flash_count,
        session_cost, drive_ok, generated, stop_reason
    )

    # API 과사용 검증
    total_api_calls = rl.get_total_api_calls()
    expected_calls = generated + failed_count
    overhead = total_api_calls - expected_calls
    print(f"\n{'=' * 55}")
    print(f"[API 사용량 검증]")
    print(f"  생성 성공: {generated}장")
    print(f"  생성 실패: {failed_count}장")
    print(f"  예상 API 호출: {expected_calls}회")
    print(f"  실제 API 호출: {total_api_calls}회")
    print(f"  초과 호출 (재시도): {overhead}회")
    if overhead > expected_calls * 0.5:
        print(f"  [WARN] 과사용 감지! 초과 호출이 예상의 50% 초과 ({overhead}/{expected_calls})")
    else:
        print(f"  [OK] 정상 범위")
    print(f"{'=' * 55}\n")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n[STOP] Ctrl+C. active-session.json preserved for resume.")
        sys.exit(0)
