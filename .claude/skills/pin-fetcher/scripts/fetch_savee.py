#!/usr/bin/env python3
"""Savee.com 이미지를 Pinterest 보드 캐시와 동일한 형식으로 저장
— config/boards/savee_{collection}.json 형태로 저장되어 기존 레퍼런스 시스템과 자동 호환
"""
import json
import sys
from pathlib import Path
from datetime import datetime, timezone

import requests

CONFIG_DIR = Path(__file__).parents[4] / "config"
BOARDS_DIR = CONFIG_DIR / "boards"
CREDENTIALS_DIR = CONFIG_DIR / "credentials"
TOKEN_FILE = CREDENTIALS_DIR / "savee-token.json"

GRAPHQL_URL = "https://savee.com/api/graphql"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Content-Type": "application/json",
    "Referer": "https://savee.com/",
    "Origin": "https://savee.com",
}
PAGE_SIZE = 40


def _load_token() -> dict:
    if not TOKEN_FILE.exists():
        print("[ERROR] Savee 토큰 없음. config/credentials/savee-token.json 필요")
        sys.exit(1)
    with open(TOKEN_FILE, encoding="utf-8") as f:
        return json.load(f)


def _session() -> requests.Session:
    token = _load_token()
    s = requests.Session()
    s.cookies.set("auth_token", token["auth_token"], domain="savee.com", path="/")
    if "sv_did" in token:
        s.cookies.set("sv_did", token["sv_did"], domain="savee.com", path="/")
    return s


def fetch_all_items(session: requests.Session) -> list:
    """전체 Savee 아이템을 가져옴 (이미지만, 비디오 제외)"""
    all_items = []
    cursor = None

    while True:
        if cursor:
            q = '{auth{user{items(limit:%d,cursor:"%s"){items{_id name sourceURL asset{type image{width height original}}} pageInfo{nextCursor}}}}}' % (PAGE_SIZE, cursor)
        else:
            q = '{auth{user{items(limit:%d){items{_id name sourceURL asset{type image{width height original}}} pageInfo{nextCursor}}}}}' % PAGE_SIZE

        resp = session.post(GRAPHQL_URL, json={"query": q}, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        user = data.get("data", {}).get("auth", {}).get("user")
        if not user:
            print("[ERROR] Savee 인증 실패. 토큰을 갱신하세요.")
            return []

        items_data = user.get("items", {})
        items = items_data.get("items", [])
        if not items:
            break

        for item in items:
            asset = item.get("asset", {})
            if asset.get("type") != "image":
                continue
            img = asset.get("image", {})
            original = img.get("original", "")
            if not original:
                continue
            all_items.append({
                "pin_id": f"savee_{item['_id']}",
                "image_url": original,
                "description": item.get("name", ""),
                "source_url": item.get("sourceURL", ""),
                "width": img.get("width", 0),
                "height": img.get("height", 0),
            })

        cursor = items_data.get("pageInfo", {}).get("nextCursor")
        if not cursor:
            break

        sys.stdout.write(f"\r  수집 중... {len(all_items)}개")
        sys.stdout.flush()

    if all_items:
        print(f"\r  수집 완료: {len(all_items)}개 이미지")
    return all_items


def save_as_board(items: list, board_name: str = "savee"):
    """Pinterest 보드 캐시와 동일한 형식으로 저장"""
    BOARDS_DIR.mkdir(parents=True, exist_ok=True)

    now = datetime.now(timezone.utc).isoformat()
    for item in items:
        item["added_at"] = now

    board_data = {
        "board_name": board_name,
        "board_url": "https://savee.com/",
        "is_private": True,
        "collected_at": now,
        "last_incremental_update": now,
        "pin_count": len(items),
        "pins": items,
    }

    out_path = BOARDS_DIR / f"{board_name}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(board_data, f, ensure_ascii=False, indent=2)

    print(f"[OK] {out_path.name} 저장 ({len(items)}개 이미지)")
    return out_path


def main():
    session = _session()

    # 유저 정보 확인
    resp = session.post(GRAPHQL_URL,
        json={"query": "{auth{user{username itemsCount}}}"},
        headers=HEADERS, timeout=15)
    user = resp.json().get("data", {}).get("auth", {}).get("user")
    if not user:
        print("[ERROR] Savee 인증 실패")
        sys.exit(1)

    print(f"[Savee] {user['username']} ({user['itemsCount']}개 아이템)")

    items = fetch_all_items(session)
    if not items:
        print("[WARN] 이미지 없음")
        return

    save_as_board(items, "savee")


if __name__ == "__main__":
    main()
