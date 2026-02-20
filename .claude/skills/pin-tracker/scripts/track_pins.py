#!/usr/bin/env python3
"""핀 사용 추적 — 메타데이터 JSON 관리"""
import json
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).parents[4]
OUTPUT_DIR = BASE_DIR / "output" / "images"


METADATA_DIR = OUTPUT_DIR / "metadata"


def get_metadata_file(date_str: str = None) -> Path:
    if not date_str:
        date_str = datetime.now().strftime("%y%m%d")
    return METADATA_DIR / f"{date_str}_metadata.json"


def load_metadata(date_str: str = None) -> list:
    f = get_metadata_file(date_str)
    if not f.exists():
        return []
    with open(f, encoding="utf-8") as fp:
        return json.load(fp)


def save_metadata(entries: list, date_str: str = None):
    f = get_metadata_file(date_str)
    METADATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = f.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as fp:
        json.dump(entries, fp, ensure_ascii=False, indent=2)
    tmp.replace(f)


def append_entry(entry: dict, date_str: str = None):
    """메타데이터에 새 항목 추가"""
    entries = load_metadata(date_str)
    entries.append(entry)
    save_metadata(entries, date_str)


def update_drive_status(combo_id: str, drive_file_id: str, date_str: str = None):
    """Drive 업로드 완료 후 drive_file_id 업데이트"""
    entries = load_metadata(date_str)
    for e in entries:
        if e.get("combo_id") == combo_id:
            e["drive_uploaded"] = True
            e["drive_file_id"] = drive_file_id
            break
    save_metadata(entries, date_str)


def get_pin_usage_stats(date_str: str = None) -> dict:
    """핀 사용 통계 계산"""
    entries = load_metadata(date_str)
    pin_counts: dict = {}
    board_set: set = set()
    for entry in entries:
        for pin_url in entry.get("reference_pins", []):
            pin_counts[pin_url] = pin_counts.get(pin_url, 0) + 1
        board_set.update(entry.get("reference_boards", []))
    return {
        "total_entries": len(entries),
        "unique_pins_used": len(pin_counts),
        "boards_used": list(board_set),
        "top_pins": sorted(pin_counts.items(), key=lambda x: -x[1])[:20]
    }


def get_all_entries(date_str: str = None) -> list:
    return load_metadata(date_str)
