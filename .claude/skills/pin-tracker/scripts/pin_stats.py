#!/usr/bin/env python3
"""핀 사용 통계"""
import json
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).parents[4]
OUTPUT_DIR = BASE_DIR / "output" / "images"


METADATA_DIR = OUTPUT_DIR / "metadata"


def get_session_stats(session_id: str, date_str: str = None) -> dict:
    if not date_str:
        date_str = datetime.now().strftime("%y%m%d")
    metadata_file = METADATA_DIR / f"{date_str}_metadata.json"
    if not metadata_file.exists():
        return {"session_id": session_id, "error": "metadata.json 없음"}

    with open(metadata_file, encoding="utf-8") as f:
        entries = json.load(f)

    pin_set = set()
    board_set = set()
    for e in entries:
        pin_set.update(e.get("reference_pins", []))
        board_set.update(e.get("reference_boards", []))

    success = [e for e in entries if e.get("status") == "success"]
    failed = [e for e in entries if e.get("status") != "success"]

    return {
        "session_id": session_id,
        "date": date_str,
        "total_images": len(entries),
        "success": len(success),
        "failed": len(failed),
        "unique_pins_used": len(pin_set),
        "boards_used": list(board_set),
        "total_cost": round(sum(e.get("cost", 0) for e in entries), 4),
        "pro_count": sum(1 for e in entries if "flash" not in e.get("model_used", "").lower()),
        "flash_count": sum(1 for e in entries if "flash" in e.get("model_used", "").lower())
    }
