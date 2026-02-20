#!/usr/bin/env python3
"""
나노바나나 에이전트 — 메인 실행 스크립트
사용: python run_session.py
"""
import json
import random
import sys
import time
from pathlib import Path

BASE_DIR = Path(__file__).parent

# sys.path 설정
SKILLS_DIR = BASE_DIR / ".claude" / "skills"
for skill in ["session-controller", "word-manager", "image-generator",
              "pin-fetcher", "pin-tracker", "drive-uploader",
              "session-reporter", "notifier"]:
    sys.path.insert(0, str(SKILLS_DIR / skill / "scripts"))


def load_boards() -> list:
    boards_file = BASE_DIR / "config" / "pinterest-boards.json"
    if not boards_file.exists():
        return []
    with open(boards_file, encoding="utf-8") as f:
        return json.load(f)


def load_board_cache(board_name: str) -> dict:
    cache = BASE_DIR / "config" / "boards" / f"{board_name}.json"
    if not cache.exists():
        return {}
    with open(cache, encoding="utf-8") as f:
        return json.load(f)


def select_boards(boards: list) -> list:
    """보드 선택 UI"""
    print(f"\n{'═'*40}")
    print("Pinterest 보드 목록")
    print(f"{'═'*40}")

    if not boards:
        print("[WARN] 보드 없음. list_boards.py 먼저 실행하세요.")
        board_name = input("보드 이름 직접 입력: ").strip()
        if not board_name:
            return []
        return [board_name]

    from datetime import datetime
    for i, b in enumerate(boards, 1):
        lock = "[P]" if b.get("is_private") else "[O]"
        cache = load_board_cache(b.get("board_name", ""))
        cache_status = ""
        if cache:
            ts = cache.get("last_incremental_update", "")
            cache_status = f"-- cached ({ts[:10]})"
        print(f"  {i}. {lock} {b.get('board_name', '?')} ({b.get('pin_count', 0)}핀) {cache_status}")
    print(f"{'═'*40}")

    while True:
        raw = input("레퍼런스 보드 선택 (번호, 복수는 쉼표 예: 1,3): ").strip()
        if not raw:
            continue
        try:
            indices = [int(x.strip()) - 1 for x in raw.split(",")]
            selected = [boards[i]["board_name"] for i in indices if 0 <= i < len(boards)]
            if selected:
                return selected
        except (ValueError, IndexError):
            print("[ERROR] 올바른 번호를 입력하세요.")


def get_session_settings() -> dict:
    """세션 설정 입력"""
    print(f"\n{'═'*40}")
    print("세션 설정")
    print(f"{'═'*40}")

    def get_int(prompt, default):
        raw = input(prompt).strip()
        if not raw or raw == "무제한":
            return default
        try:
            return int(raw)
        except ValueError:
            return default

    def get_float(prompt, default):
        raw = input(prompt).strip()
        if not raw:
            return default
        try:
            return float(raw)
        except ValueError:
            return default

    target = get_int("생성 수량 (Enter=무제한): ", -1)
    duration = get_float("실행 시간 시간 단위 (Enter=무제한): ", -1)
    session_cap = get_float("이 세션 비용 상한 $ (Enter=없음): ", None)

    return {
        "target_count": target,
        "max_duration_hours": duration,
        "session_cost_cap": session_cap
    }


def run_generation_session(session: dict, start_time: float):
    """이미지 생성 세션 루프"""
    from session_manager import get_pending_pairs, update_session_progress, close_session
    from generate import generate_image
    from cost_tracker import add_cost, get_daily_total, get_monthly_total, get_limits
    from stop_checker import check_stop_conditions, format_elapsed
    from track_pins import append_entry
    from slack_notify import notify_consecutive_errors, notify_model_switch, notify_cost_limit
    from rate_limiter import get_rate_limiter

    settings = session["settings"]
    boards = session["boards_used"]

    rl = get_rate_limiter()
    consecutive_errors = 0
    template_index = 0
    recent_pins = []

    print(f"\n[시작] 세션 {session['session_id']}")
    print(f"  보드: {', '.join(boards)}")
    print(f"  목표: {settings.get('target_count', '무제한')}장")

    today_date = __import__("datetime").datetime.now().strftime("%y%m%d")
    prog = session.get("progress", {})
    generated = prog.get("generated", 0)
    failed_count = prog.get("failed", 0)
    session_cost = prog.get("session_cost", 0.0)

    while True:
        pending = get_pending_pairs()
        if not pending:
            close_session("완료 — 모든 조합 생성")
            break

        pair = pending[0]
        limits = get_limits()
        daily_total = get_daily_total()
        monthly_total = get_monthly_total()

        should_stop, reason = check_stop_conditions(
            generated=generated,
            failed=failed_count,
            target_count=settings.get("target_count", -1),
            start_time=start_time,
            max_duration_hours=settings.get("max_duration_hours", -1),
            session_cost=session_cost,
            session_cost_cap=settings.get("session_cost_cap"),
            daily_total=daily_total,
            daily_cap=limits.get("daily_cost_cap", 0),
            monthly_total=monthly_total,
            monthly_cap=limits.get("monthly_cost_cap", 0),
            all_models_exhausted=rl.all_keys_rate_limited(),
            next_is_flash=False
        )

        if should_stop:
            print(f"\n[정지] {reason}")
            if "비용" in reason:
                notify_cost_limit(reason, limits.get("daily_cost_cap", 0), daily_total)
            close_session(reason)
            break

        print(f"\n[{generated+1}] {pair['word1']} × {pair['word2']}", end="", flush=True)

        result = generate_image(
            word1=pair["word1"], word1_en=pair["word1_en"],
            word2=pair["word2"], word2_en=pair["word2_en"],
            board_names=boards,
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
            consecutive_errors = 0
            update_session_progress(pair["combo_id"], "done", cost, False)
            append_entry(result, today_date)
            print(f" [OK] ${cost:.3f} ({result.get('resolution', '?')})")
            recent_pins.append(result.get("file_path", ""))
        else:
            failed_count += 1
            consecutive_errors += 1
            update_session_progress(pair["combo_id"], "failed", 0, False)
            print(f" [FAIL] {result.get('error', 'unknown')[:50]}")

            if consecutive_errors >= 5:
                notify_consecutive_errors(consecutive_errors, result.get("error", ""))
                print(f"  [WARN] 연속 {consecutive_errors}회 실패. 30초 대기...")
                time.sleep(30)
                consecutive_errors = 0

        # 랜덤 대기 (30초~120초) — 밴 방지
        wait_sec = random.randint(30, 120)
        print(f"  [WAIT] {wait_sec}s ...", end="", flush=True)
        time.sleep(wait_sec)
        print(" OK")

    return generated, failed_count, session_cost


def main():
    from session_manager import check_resume, display_resume_prompt, archive_old_session, create_new_session, close_session
    from cost_tracker import get_daily_total, get_monthly_total, get_status_summary
    from track_pins import get_pin_usage_stats
    from generate_viewer import generate_viewer
    from report import print_and_save_report
    from slack_notify import notify_session_complete

    print("\n[Nano-Banana] Pro Inspiration Generator Agent")
    print("=" * 50)

    # Resume 체크
    existing = check_resume()
    if existing:
        if display_resume_prompt(existing):
            session = existing
            start_time = time.time()
        else:
            archive_old_session(existing)
            session = None
    else:
        session = None

    if session is None:
        # 새 세션 설정
        boards = load_boards()
        selected_boards = select_boards(boards)
        if not selected_boards:
            print("[ERROR] 보드 선택 취소")
            return

        # 핀 사전 다운로드 확인
        pins_dir = BASE_DIR / "tmp" / "pins"
        for board_name in selected_boards:
            board_pins = list((pins_dir / board_name).glob("*.jpg")) if (pins_dir / board_name).exists() else []
            cache_file = BASE_DIR / "config" / "boards" / f"{board_name}.json"
            expected = 0
            if cache_file.exists():
                with open(cache_file) as f:
                    bd = json.load(f)
                expected = bd.get("pin_count", 0)
            if expected > 0 and len(board_pins) < expected * 0.8:
                print(f"\n[INFO] {board_name} 핀 이미지 부족 ({len(board_pins)}/{expected}). 사전 다운로드 시작...")
                from prefetch_pins import prefetch_board
                prefetch_board(board_name)

        settings = get_session_settings()
        session = create_new_session(selected_boards, settings)
        start_time = time.time()

    # 생성 루프
    generated, failed, session_cost = run_generation_session(session, start_time)

    # 세션 완료 처리
    today_date = __import__("datetime").datetime.now().strftime("%y%m%d")
    print(f"\n[완료] 생성 {generated}장, 실패 {failed}장, 비용 ${session_cost:.2f}")
    print("\n[Cost]:")
    print(get_status_summary())

    # HTML 뷰어 생성
    print("\n[HTML 뷰어 생성 중...]")
    generate_viewer(session["session_id"], today_date)

    # Drive 업로드
    try:
        from upload import upload_session
        from track_pins import get_all_entries
        entries = get_all_entries(today_date)
        print("\n[Drive 업로드 중...]")
        drive_result = upload_session(today_date, session["session_id"], entries)
        drive_ok = drive_result.get("uploaded", 0)
    except Exception as e:
        print(f"[WARN] Drive 업로드 실패: {e}")
        drive_ok = 0

    # 리포트
    final_session = session.copy()
    final_session["progress"]["generated"] = generated
    final_session["progress"]["session_cost"] = session_cost
    print_and_save_report(final_session, start_time)

    # Slack 알림
    notify_session_complete(
        session["session_id"],
        final_session["progress"].get("pro_count", 0),
        final_session["progress"].get("flash_count", 0),
        session_cost,
        drive_ok,
        generated,
        final_session.get("stop_reason", "완료")
    )


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n[중단] Ctrl+C로 종료. active-session.json이 유지됩니다. 다음 실행 시 Resume 가능.")
        sys.exit(0)
