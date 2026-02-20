#!/usr/bin/env python3
"""세션 관리 — Resume 감지, 세션 초기화, active-session.json 관리"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).parents[4]
LOGS_DIR = BASE_DIR / "output" / "logs"
ACTIVE_SESSION_FILE = LOGS_DIR / "active-session.json"

sys.path.insert(0, str(BASE_DIR / ".claude" / "skills" / "word-manager" / "scripts"))


def check_resume() -> dict | None:
    """중단된 세션 감지. 있으면 dict, 없으면 None"""
    if not ACTIVE_SESSION_FILE.exists():
        return None
    try:
        with open(ACTIVE_SESSION_FILE, encoding="utf-8") as f:
            session = json.load(f)
    except Exception:
        return None
    pending = [wp for wp in session.get("word_pairs", []) if wp.get("status") == "pending"]
    return session if pending else None


def display_resume_prompt(session: dict) -> bool:
    """Resume 여부 사용자에게 확인. True=이어서, False=새 세션"""
    prog = session.get("progress", {})
    settings = session.get("settings", {})
    print(f"\n{'='*50}")
    print(f"이전 세션 발견: {session['session_id']}")
    print(f"시작: {session.get('started_at', 'N/A')}")
    print(f"보드: {', '.join(session.get('boards_used', []))}")
    print(f"진행: {prog.get('generated', 0)}/{settings.get('target_count', '?')}장 완료")
    print(f"비용: ${prog.get('session_cost', 0):.2f} 사용")
    print(f"{'='*50}")
    try:
        ans = input("이어서 진행하시겠습니까? (y/n): ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        ans = "n"
    return ans == "y"


def archive_old_session(session: dict):
    """이전 세션을 archived 처리"""
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    archive_file = LOGS_DIR / f"session-{session['session_id']}-archived.json"
    session["stop_reason"] = "abandoned"
    session["archived_at"] = datetime.now(timezone.utc).isoformat()
    with open(archive_file, "w", encoding="utf-8") as f:
        json.dump(session, f, ensure_ascii=False, indent=2)
    ACTIVE_SESSION_FILE.unlink(missing_ok=True)
    print(f"[OK] 이전 세션 archived: {archive_file.name}")


def _get_next_image_number(date_str: str) -> int:
    """오늘 날짜 폴더에서 YYMMDD_NNNN 형식의 최대 번호 + 1 반환"""
    import re
    output_dir = BASE_DIR / "output" / "images" / date_str
    if not output_dir.exists():
        return 1
    max_num = 0
    pattern = re.compile(rf"^{date_str}_(\d{{4}})_")
    for f in output_dir.iterdir():
        m = pattern.match(f.name)
        if m:
            n = int(m.group(1))
            if n > max_num:
                max_num = n
    return max_num + 1


def create_new_session(boards: list, settings: dict) -> dict:
    """새 세션 생성 + active-session.json 저장"""
    from random_picker import generate_word_pairs
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now()
    session_id = f"ses_{now.strftime('%y%m%d_%H%M%S')}"
    target = settings.get("target_count", 50)

    word_pairs = generate_word_pairs(target)
    date_str = now.strftime("%y%m%d")
    start_num = _get_next_image_number(date_str)
    for i, pair in enumerate(word_pairs, 0):
        pair["combo_id"] = f"{date_str}_{start_num + i:04d}"
        pair["template_id"] = None
        pair["status"] = "pending"

    session = {
        "session_id": session_id,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "boards_used": boards,
        "settings": settings,
        "word_pairs": word_pairs,
        "progress": {
            "generated": 0,
            "failed": 0,
            "pro_count": 0,
            "flash_count": 0,
            "session_cost": 0.0
        },
        "stop_reason": None
    }

    with open(ACTIVE_SESSION_FILE, "w", encoding="utf-8") as f:
        json.dump(session, f, ensure_ascii=False, indent=2)

    print(f"[OK] 새 세션 생성: {session_id} ({len(word_pairs)}쌍)")
    return session


def update_session_progress(combo_id: str, status: str, cost: float, is_flash: bool, error: str = ""):
    """combo_id 상태 업데이트 + 진행 카운터"""
    if not ACTIVE_SESSION_FILE.exists():
        return
    with open(ACTIVE_SESSION_FILE, encoding="utf-8") as f:
        session = json.load(f)

    for pair in session["word_pairs"]:
        if pair["combo_id"] == combo_id:
            pair["status"] = status
            if error:
                pair["error"] = error[:200]
            break

    prog = session["progress"]
    if status == "done":
        prog["generated"] += 1
        prog["session_cost"] = round(prog["session_cost"] + cost, 4)
        if is_flash:
            prog["flash_count"] += 1
        else:
            prog["pro_count"] += 1
    elif status == "failed":
        prog["failed"] += 1

    with open(ACTIVE_SESSION_FILE, "w", encoding="utf-8") as f:
        json.dump(session, f, ensure_ascii=False, indent=2)


def close_session(stop_reason: str, total_api_calls: int = 0) -> dict | None:
    """세션 정상 종료 — active-session.json 삭제 + 로그 저장"""
    if not ACTIVE_SESSION_FILE.exists():
        return None
    with open(ACTIVE_SESSION_FILE, encoding="utf-8") as f:
        session = json.load(f)

    session["stop_reason"] = stop_reason
    session["ended_at"] = datetime.now(timezone.utc).isoformat()
    if total_api_calls > 0:
        session["total_api_calls"] = total_api_calls

    archive_file = LOGS_DIR / f"session-{session['session_id']}.json"
    with open(archive_file, "w", encoding="utf-8") as f:
        json.dump(session, f, ensure_ascii=False, indent=2)

    ACTIVE_SESSION_FILE.unlink(missing_ok=True)
    print(f"[OK] 세션 완료: {archive_file.name}")
    return session


def get_pending_pairs() -> list:
    """pending 상태 combo 목록 반환"""
    if not ACTIVE_SESSION_FILE.exists():
        return []
    with open(ACTIVE_SESSION_FILE, encoding="utf-8") as f:
        session = json.load(f)
    return [p for p in session.get("word_pairs", []) if p.get("status") == "pending"]


def get_current_session() -> dict | None:
    """현재 세션 데이터 반환"""
    if not ACTIVE_SESSION_FILE.exists():
        return None
    with open(ACTIVE_SESSION_FILE, encoding="utf-8") as f:
        return json.load(f)
