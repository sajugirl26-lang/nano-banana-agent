#!/usr/bin/env python3
"""핀 이미지 사전 다운로드 — /tmp/pins/{board-name}/{pin_id}.jpg"""
import json
import sys
import io
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

try:
    from PIL import Image
    HAS_PILLOW = True
except ImportError:
    HAS_PILLOW = False
    print("[WARN] Pillow 미설치. 리사이즈 기능 비활성화.")

CONFIG_DIR = Path(__file__).parents[4] / "config"
BOARDS_DIR = CONFIG_DIR / "boards"
BASE_DIR = Path(__file__).parents[4]
PINS_DIR = BASE_DIR / "tmp" / "pins"
CREDENTIALS_DIR = CONFIG_DIR / "credentials"
COOKIE_FILE = CREDENTIALS_DIR / "pinterest-cookies.json"

MAX_FILE_SIZE_BYTES = 3 * 1024 * 1024  # 3MB
MAX_DIMENSION = 1500
JPEG_QUALITY = 80
MAX_WORKERS = 8
SUCCESS_THRESHOLD = 0.80


def load_cookies() -> dict:
    if not COOKIE_FILE.exists():
        return {}
    with open(COOKIE_FILE) as f:
        raw = json.load(f)
    if isinstance(raw, list):
        return {c["name"]: c["value"] for c in raw if "name" in c}
    return raw


def download_pin(pin: dict, board_name: str, session: requests.Session) -> tuple:
    """단일 핀 이미지 다운로드. (pin_id, success, local_path)"""
    pin_id = pin["pin_id"]
    img_url = pin.get("image_url", "")
    if not img_url:
        return pin_id, False, "URL 없음"

    dest_dir = PINS_DIR / board_name
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / f"{pin_id}.jpg"

    if dest_path.exists() and dest_path.stat().st_size > 0:
        return pin_id, True, str(dest_path)

    try:
        resp = session.get(img_url, timeout=30, stream=True)
        resp.raise_for_status()
        raw_data = resp.content

        if HAS_PILLOW and len(raw_data) > MAX_FILE_SIZE_BYTES:
            img = Image.open(io.BytesIO(raw_data))
            img.thumbnail((MAX_DIMENSION, MAX_DIMENSION), Image.LANCZOS)
            buf = io.BytesIO()
            img.convert("RGB").save(buf, format="JPEG", quality=JPEG_QUALITY)
            raw_data = buf.getvalue()

        with open(dest_path, "wb") as f:
            f.write(raw_data)
        return pin_id, True, str(dest_path)

    except Exception as e:
        return pin_id, False, str(e)


def prefetch_board(board_name: str) -> dict:
    """보드의 모든 핀 이미지 사전 다운로드"""
    cache_file = BOARDS_DIR / f"{board_name}.json"
    if not cache_file.exists():
        print(f"[ERROR] 보드 캐시 없음: {cache_file}")
        return {"success": 0, "failed": 0}

    with open(cache_file, encoding="utf-8") as f:
        board_data = json.load(f)

    pins = board_data.get("pins", [])
    if not pins:
        print(f"[WARN] {board_name}: 핀 없음")
        return {"success": 0, "failed": 0}

    print(f"\n[{board_name}] {len(pins)}핀 사전 다운로드 시작...")
    cookies = load_cookies()
    session = requests.Session()
    session.cookies.update(cookies)
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://www.pinterest.com/"
    })

    results = {"success": 0, "failed": 0}
    updated_pins = list(pins)

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(download_pin, pin, board_name, session): i
                   for i, pin in enumerate(pins)}
        completed = 0
        for future in as_completed(futures):
            pin_id, success, path = future.result()
            idx = futures[future]
            if success:
                updated_pins[idx]["local_cache"] = path
                results["success"] += 1
            else:
                results["failed"] += 1
            completed += 1
            if completed % 20 == 0:
                pct = results["success"] / completed * 100
                print(f"  진행: {completed}/{len(pins)} ({pct:.0f}% 성공)")

    board_data["pins"] = updated_pins
    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump(board_data, f, ensure_ascii=False, indent=2)

    total = len(pins)
    rate = results["success"] / total if total > 0 else 0
    print(f"  결과: 성공 {results['success']}, 실패 {results['failed']} (성공률 {rate:.0%})")
    if rate < SUCCESS_THRESHOLD:
        print(f"  [WARN] 성공률 {rate:.0%} < {SUCCESS_THRESHOLD:.0%} 기준 미달")
    return results


def prefetch_boards(board_names: list) -> dict:
    """복수 보드 사전 다운로드"""
    total = {"success": 0, "failed": 0}
    for name in board_names:
        r = prefetch_board(name)
        total["success"] += r["success"]
        total["failed"] += r["failed"]
    print(f"\n[전체] 성공 {total['success']}, 실패 {total['failed']}")
    return total


def get_local_pins(board_names: list) -> list:
    """세션에서 사용할 로컬 핀 경로 목록 반환"""
    paths = []
    for name in board_names:
        board_dir = PINS_DIR / name
        if board_dir.exists():
            paths.extend([str(p) for p in board_dir.glob("*.jpg")
                          if p.stat().st_size > 0])
    return paths


if __name__ == "__main__":
    boards = sys.argv[1:] if len(sys.argv) > 1 else []
    if not boards:
        print("Usage: prefetch_pins.py <board_name1> [board_name2 ...]")
        sys.exit(1)
    prefetch_boards(boards)
