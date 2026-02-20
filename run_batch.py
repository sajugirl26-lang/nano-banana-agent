#!/usr/bin/env python3
"""
나노바나나 — 비대화형 배치 실행
사용:
  python run_batch.py [장수]            # 일반모드 (1장씩 순차)
  python run_batch.py [장수] --batch    # Gemini Batch API 모드 (50% 할인)
"""
import argparse
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
from slack_notify import (
    notify_consecutive_errors, notify_model_switch, notify_cost_limit,
    notify_session_complete, notify_batch_submitted, notify_batch_complete
)
from rate_limiter import get_rate_limiter
from upload import upload_single_image, upload_metadata_file, upload_html_file
from batch_generator import (
    prepare_batch_requests, submit_batch, poll_batch,
    download_batch_results, save_batch_state, load_batch_state, clear_batch_state,
    _load_batch_config
)


LOCK_FILE = Path(__file__).parent / "output" / "logs" / "batch.lock"


def acquire_lock():
    """프로세스 락 — 동시 실행 방지 (lock 파일 + PID 생존 확인)"""
    import os

    if LOCK_FILE.exists():
        try:
            old_pid = int(LOCK_FILE.read_text().strip())
            import subprocess
            result = subprocess.run(
                ['tasklist.exe', '/FI', f'PID eq {old_pid}', '/NH'],
                capture_output=True, text=True, timeout=10
            )
            if f" {old_pid} " in result.stdout:
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


def refresh_savee():
    """Savee.com 이미지 최신 갱신"""
    print("\n[SAVEE REFRESH] Savee 이미지 갱신 시작...")
    try:
        from fetch_savee import _session, fetch_all_items, save_as_board, GRAPHQL_URL, HEADERS
        session = _session()

        # 유저 확인
        resp = session.post(GRAPHQL_URL,
            json={"query": "{auth{user{username itemsCount}}}"},
            headers=HEADERS, timeout=15)
        user = resp.json().get("data", {}).get("auth", {}).get("user")
        if not user:
            print("  [WARN] Savee 인증 실패 — 기존 캐시로 진행")
            return

        print(f"  Savee: {user['username']} ({user['itemsCount']}개 아이템)")
        items = fetch_all_items(session)
        if items:
            save_as_board(items, "savee")
        else:
            print("  [WARN] Savee 이미지 없음 — 기존 캐시로 진행")
    except Exception as e:
        print(f"  [WARN] Savee 갱신 실패 (기존 캐시 유지): {e}")


def refresh_pinterest():
    """Pinterest 보드 목록 + 핀 URL 갱신"""
    print("\n[PINTEREST REFRESH] 보드/핀 갱신 시작...")
    try:
        from list_boards import list_boards
        boards = list_boards()
        print(f"  보드 {len(boards)}개 확인")
    except SystemExit:
        print("  [WARN] Pinterest 쿠키 만료 - 기존 캐시로 진행합니다.")
        return
    except Exception as e:
        print(f"  [WARN] 보드 목록 갱신 실패 (기존 유지): {e}")

    boards_file = BASE_DIR / "config" / "pinterest-boards.json"
    if not boards_file.exists():
        print(f"  [WARN] pinterest-boards.json 없음 — 핀 갱신 건너뜀")
        return

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
        print(f"[PINTEREST REFRESH] 완료 — 총 {total_new}핀")
    except SystemExit:
        print("  [WARN] 핀 URL 수집 중 종료 시그널 - 기존 캐시로 진행")
    except Exception as e:
        print(f"  [WARN] 핀 URL 갱신 실패 (기존 캐시 유지): {e}")


def refresh_pins():
    """배치 시작 전 Savee + Pinterest 레퍼런스 이미지 갱신"""
    print("\n" + "=" * 55)
    print("[REFRESH] 레퍼런스 이미지 갱신 (Savee + Pinterest)")
    print("=" * 55)
    refresh_savee()
    refresh_pinterest()
    print("\n[REFRESH] 갱신 완료\n")


def run_batch_mode(target, board_names, session, global_start_time=None):
    """Gemini Batch API 모드 — 50% 할인"""
    from stop_checker import PRICE_PRO_BATCH
    start_time = global_start_time or time.time()
    today_date = datetime.now().strftime("%y%m%d")

    settings_file = BASE_DIR / "config" / "settings.json"
    with open(settings_file, encoding="utf-8") as f:
        settings = json.load(f)
    model = settings.get("model_pro", "gemini-3-pro-image-preview")
    batch_cfg = _load_batch_config()
    cost_per_image = settings.get("price_pro_batch", 0.067)

    # pending pairs 가져오기
    pending = get_pending_pairs()
    if not pending:
        print("[BATCH] 처리할 항목이 없습니다.")
        close_session("no pending pairs", 0)
        return

    pairs = pending[:target]
    print(f"\n[Nano-Banana] Gemini Batch API Mode (50% 할인)")
    print(f"  요청: {len(pairs)}장")
    print(f"  모델: {model}")
    print(f"  예상 비용: ${len(pairs) * cost_per_image:.2f}")
    print("=" * 50)

    # 비용 상한 사전 체크
    estimated_cost = len(pairs) * cost_per_image
    limits = get_limits()
    daily_total = get_daily_total()
    monthly_total = get_monthly_total()

    if limits.get("daily_cost_cap", 0) > 0 and daily_total + estimated_cost > limits["daily_cost_cap"]:
        print(f"[STOP] 일일 비용 상한 초과 예상 (현재 ${daily_total:.2f} + 예상 ${estimated_cost:.2f} > 한도 ${limits['daily_cost_cap']:.2f})")
        close_session("일일 비용 상한 (배치 사전 체크)", 0)
        return

    if limits.get("monthly_cost_cap", 0) > 0 and monthly_total + estimated_cost > limits["monthly_cost_cap"]:
        print(f"[STOP] 월간 비용 상한 초과 예상")
        close_session("월간 비용 상한 (배치 사전 체크)", 0)
        return

    # JSONL 생성
    recent_pins = deque(maxlen=50)
    jsonl_path, request_map = prepare_batch_requests(
        pairs, board_names, list(recent_pins), model
    )

    if not request_map:
        print("[BATCH] 유효한 요청이 없습니다.")
        close_session("no valid requests", 0)
        return

    # 배치 제출
    batch_job_name = submit_batch(jsonl_path, model)
    save_batch_state(batch_job_name, request_map, model)
    notify_batch_submitted(len(request_map), len(request_map) * cost_per_image, model)

    # polling
    poll_interval = batch_cfg.get("poll_interval_seconds", 30)
    poll_timeout = batch_cfg.get("poll_timeout_seconds", 7200)

    try:
        batch_job = poll_batch(batch_job_name, poll_interval, poll_timeout)
    except KeyboardInterrupt:
        print(f"\n[BATCH] Ctrl+C — 배치 작업은 계속 실행 중입니다.")
        print(f"  batch_job_name: {batch_job_name}")
        print(f"  나중에 결과를 수거하려면 batch_state.json을 참고하세요.")
        return

    if batch_job is None:
        print("[BATCH] polling 타임아웃. batch_state.json에 상태 저장됨.")
        return

    state = batch_job.state.name if hasattr(batch_job.state, 'name') else str(batch_job.state)
    if state not in ("JOB_STATE_SUCCEEDED", "SUCCEEDED"):
        print(f"[BATCH] 배치 실패/취소: {state}")
        close_session(f"batch {state}", 0)
        clear_batch_state()
        return

    # 결과 다운로드 + 이미지 저장
    results = download_batch_results(batch_job, request_map, model, is_batch=True)
    clear_batch_state()

    # 결과 처리
    generated = 0
    failed_count = 0
    drive_ok = 0
    session_cost = 0.0

    for r in results:
        if r.get("status") == "success":
            cost = r.get("cost", cost_per_image)
            add_cost(cost, False)
            session_cost = round(session_cost + cost, 4)
            generated += 1
            update_session_progress(r["combo_id"], "done", cost, False)

            # Drive 업로드
            drive_id = upload_single_image(r.get("file_path", ""), r, today_date)
            if drive_id:
                r["drive_uploaded"] = True
                r["drive_file_id"] = drive_id
                drive_ok += 1

            append_entry(r, today_date)
            print(f"  [OK] {r.get('word1', '')} x {r.get('word2', '')} — ${cost:.3f} ({r.get('resolution', '?')})"
                  + (" [DRIVE]" if r.get("drive_uploaded") else ""))
        else:
            failed_count += 1
            update_session_progress(r.get("combo_id", ""), "failed", 0, False, error=r.get("error", "unknown"))
            print(f"  [FAIL] {r.get('combo_id', '')} — {r.get('error', 'unknown')[:60]}")

    close_session("batch complete", len(request_map))

    # 보고
    elapsed = time.time() - start_time
    elapsed_min = int(elapsed / 60)
    print(f"\n{'=' * 55}")
    print(f"[BATCH COMPLETE]")
    print(f"  성공: {generated}장 / 실패: {failed_count}장")
    print(f"  비용: ${session_cost:.2f} (배치 50% 할인 적용)")
    print(f"  Drive 업로드: {drive_ok}장")
    print(f"  소요: {elapsed_min}분")
    print(f"{'=' * 55}\n")

    # HTML viewer + GitHub Pages
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
    notify_batch_complete(generated, failed_count, session_cost, drive_ok, elapsed_min)


def run_normal_mode(target, board_names, session, global_start_time=None):
    """기존 일반모드 — 1장씩 순차 API 호출"""
    start_time = global_start_time or time.time()

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
            is_flash = rl.is_flash_mode
            add_cost(cost, is_flash)
            session_cost = round(session_cost + cost, 4)
            generated += 1
            if is_flash:
                flash_count += 1
            else:
                pro_count += 1
            consecutive_errors = 0
            update_session_progress(pair["combo_id"], "done", cost, is_flash)

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
                print(f"\n  [EMERGENCY] 연속 {consecutive_errors}회 실패 - 프로세스를 자동 중단합니다.")
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


def main():
    global_start_time = time.time()  # 전체 시작 시점 (Slack 알림용)

    parser = argparse.ArgumentParser(description="나노바나나 — 이미지 생성 배치 실행")
    parser.add_argument("count", nargs="?", type=int, default=999, help="생성할 이미지 수 (기본 999)")
    parser.add_argument("--batch", action="store_true", help="Gemini Batch API 사용 (50%% 할인)")
    parser.add_argument("--no-refresh", action="store_true", help="Pinterest 핀 갱신 건너뛰기")
    args = parser.parse_args()

    acquire_lock()
    target = args.count

    # 배치 시작 전 핀 갱신
    if args.no_refresh:
        print("\n[PIN REFRESH] --no-refresh: 건너뜀 (기존 캐시 사용)")
    else:
        refresh_pins()

    # 모든 보드 사용 (Pinterest + Savee)
    boards_file = BASE_DIR / "config" / "pinterest-boards.json"
    with open(boards_file, encoding="utf-8") as f:
        all_boards = json.load(f)
    board_names = [b["board_name"] for b in all_boards]

    # Savee 보드 추가 (savee.json이 있으면 자동 포함)
    savee_board = BASE_DIR / "config" / "boards" / "savee.json"
    if savee_board.exists() and "savee" not in board_names:
        board_names.append("savee")

    mode_label = "Gemini Batch API (50% 할인)" if args.batch else "일반 (순차)"
    print(f"\n[Nano-Banana] {mode_label}")
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

    if args.batch:
        run_batch_mode(target, board_names, session, global_start_time)
    else:
        run_normal_mode(target, board_names, session, global_start_time)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n[STOP] Ctrl+C. active-session.json preserved for resume.")
        sys.exit(0)
