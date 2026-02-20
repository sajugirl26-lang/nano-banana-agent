#!/usr/bin/env python3
"""Pinterest 핀 URL 수집 — 증분 갱신 포함"""
import json
import sys
import subprocess
from datetime import datetime, timezone
from pathlib import Path

CONFIG_DIR = Path(__file__).parents[4] / "config"
BOARDS_DIR = CONFIG_DIR / "boards"
CREDENTIALS_DIR = CONFIG_DIR / "credentials"
COOKIE_FILE = CREDENTIALS_DIR / "pinterest-cookies.json"


def load_board_cache(board_name: str) -> dict | None:
    cache_file = BOARDS_DIR / f"{board_name}.json"
    if cache_file.exists():
        with open(cache_file, encoding="utf-8") as f:
            return json.load(f)
    return None


def save_board_cache(board_name: str, data: dict):
    BOARDS_DIR.mkdir(parents=True, exist_ok=True)
    cache_file = BOARDS_DIR / f"{board_name}.json"
    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"[OK] 캐시 저장: {cache_file}")


def fetch_pins_via_cli(board_url: str) -> list:
    """pinterest-dl scrape --cache로 핀 URL 수집 (다운로드 없이)"""
    import shutil
    import tempfile
    pdl_cmd = shutil.which("pinterest-dl") or str(Path(sys.executable).parent / "Scripts" / "pinterest-dl.exe")

    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
        cache_path = tmp.name

    try:
        result = subprocess.run(
            [pdl_cmd, "scrape", board_url,
             "-c", str(COOKIE_FILE),
             "-n", "10000",
             "--cache", cache_path],
            capture_output=True, timeout=300
        )
        if result.returncode != 0:
            stderr = result.stderr.decode("utf-8", errors="replace")
            print(f"[WARN] pinterest-dl 실패: {stderr[:300]}")
            return []
        try:
            with open(cache_path, encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                # [{id, src, alt, origin, resolution}, ...] 형태
                pins = []
                for item in data:
                    pin_id = str(item.get("id", ""))
                    img_url = item.get("src", item.get("url", ""))
                    if not img_url:
                        continue
                    if not pin_id:
                        pin_id = img_url.split("/")[-1].split(".")[0].split("?")[0]
                    pins.append({
                        "pin_id": pin_id,
                        "image_url": img_url,
                        "description": item.get("alt", ""),
                    })
                return pins
        except Exception as e:
            print(f"[WARN] 캐시 파일 파싱 실패: {e}")
            return []
    finally:
        Path(cache_path).unlink(missing_ok=True)


def collect_board_urls(board_name: str, board_url: str, is_private: bool = False) -> dict:
    """보드 핀 URL 수집 (증분 갱신)"""
    now = datetime.now(timezone.utc).isoformat()
    cache = load_board_cache(board_name)

    print(f"\n[보드] {board_name} ({board_url})")

    if cache:
        cached_pin_ids = {p["pin_id"] for p in cache.get("pins", [])}
        print(f"  캐시 핀 수: {len(cached_pin_ids)}")
        print("  증분 갱신 중...")
    else:
        print("  신규 수집 시작...")
        cached_pin_ids = set()

    raw_pins = fetch_pins_via_cli(board_url)

    if not raw_pins:
        if cache:
            print("  [WARN] 새 핀 조회 실패 — 캐시 유지")
            return cache
        else:
            print("  [ERROR] 핀 조회 실패")
            return {}

    new_pins = []
    for p in raw_pins:
        pin_id = str(p.get("pin_id", p.get("id", "")))
        img_url = p.get("image_url", p.get("url", p.get("original_link", "")))
        if not pin_id or not img_url:
            continue
        new_pins.append({
            "pin_id": pin_id,
            "image_url": img_url,
            "description": p.get("description", p.get("alt_text", "")),
            "added_at": now,
            "local_cache": f"/tmp/pins/{board_name}/{pin_id}.jpg"
        })

    new_pin_ids = {p["pin_id"] for p in new_pins}
    added = new_pin_ids - cached_pin_ids
    removed = cached_pin_ids - new_pin_ids
    print(f"  추가: {len(added)}핀, 삭제: {len(removed)}핀, 총: {len(new_pins)}핀")

    board_data = {
        "board_name": board_name,
        "board_url": board_url,
        "is_private": is_private,
        "collected_at": cache["collected_at"] if cache else now,
        "last_incremental_update": now,
        "pin_count": len(new_pins),
        "pins": new_pins
    }

    save_board_cache(board_name, board_data)
    return board_data


def collect_urls(board_name: str, board_url: str, is_private: bool = False) -> dict:
    return collect_board_urls(board_name, board_url, is_private)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: collect_urls.py <board_name> <board_url> [--private]")
        sys.exit(1)
    private = "--private" in sys.argv
    collect_urls(sys.argv[1], sys.argv[2], private)
