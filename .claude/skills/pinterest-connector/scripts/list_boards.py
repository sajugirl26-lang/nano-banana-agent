#!/usr/bin/env python3
"""Pinterest 보드 목록 조회 (비공개 포함)"""
import json
import sys
from pathlib import Path
import requests

CONFIG_DIR = Path(__file__).parents[4] / "config"
CREDENTIALS_DIR = CONFIG_DIR / "credentials"
COOKIE_FILE = CREDENTIALS_DIR / "pinterest-cookies.json"
BOARDS_FILE = CONFIG_DIR / "pinterest-boards.json"


def load_cookies() -> dict:
    if not COOKIE_FILE.exists():
        print("[ERROR] 쿠키 파일 없음. 먼저 login.py를 실행하세요.")
        sys.exit(1)
    with open(COOKIE_FILE) as f:
        raw = json.load(f)
    if isinstance(raw, list):
        # 도메인 무관하게 모든 쿠키를 name:value로 통합
        # (kr.pinterest.com / www.pinterest.com / .pinterest.com 모두 포함)
        cookies = {}
        for c in raw:
            if "name" in c and "value" in c:
                cookies[c["name"]] = c["value"]
        return cookies
    return raw


def _build_session(cookies: dict):
    """Pinterest API용 requests 세션 + 헤더 구성"""
    session = requests.Session()
    session.cookies.update(cookies)

    # /me/ 리다이렉트로 username 추출
    ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    username = ""
    try:
        resp = session.get("https://www.pinterest.com/me/",
                           headers={"User-Agent": ua}, allow_redirects=False, timeout=15)
        loc = resp.headers.get("Location", "")
        parts = [p for p in loc.strip("/").split("/") if p]
        if parts:
            username = parts[-1]
    except Exception:
        pass

    headers = {
        "User-Agent": ua,
        "X-Requested-With": "XMLHttpRequest",
        "X-CSRFToken": cookies.get("csrftoken", ""),
        "Accept": "application/json, text/javascript, */*, q=0.01",
        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
        "Referer": "https://www.pinterest.com/",
        "Origin": "https://www.pinterest.com",
        "X-Pinterest-AppState": "active",
        "X-Pinterest-Source-Url": f"/{username}/_saved/" if username else "/",
        "X-Pinterest-PWS-Handler": "www/[username]/_saved.js",
        "X-APP-VERSION": "e8144ac",
    }
    return session, headers, username


def fetch_boards_via_api(cookies: dict) -> list:
    """Pinterest API로 내 보드 목록 조회"""
    session, headers, username = _build_session(cookies)
    if not username:
        print("[WARN] Pinterest username 확인 불가 (쿠키 만료?)")
        return []

    url = "https://www.pinterest.com/resource/BoardsResource/get/"
    all_boards = []
    bookmark = None

    while True:
        options = {
            "username": username,
            "page_size": 25,
            "privacy_filter": "all",
            "sort": "alphabetical",
            "field_set_key": "profile_grid_item",
            "filter": "all",
        }
        if bookmark:
            options["bookmarks"] = [bookmark]

        params = {
            "source_url": f"/{username}/_saved/",
            "data": json.dumps({"options": options, "context": {}})
        }
        try:
            resp = session.get(url, params=params, headers=headers, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            raw_boards = data.get("resource_response", {}).get("data", [])
            if not raw_boards:
                break
            for b in raw_boards:
                all_boards.append({
                    "board_id": b.get("id", ""),
                    "board_name": b.get("name", ""),
                    "board_url": b.get("url", ""),
                    "is_private": b.get("privacy", "public") != "public",
                    "pin_count": b.get("pin_count", 0),
                    "description": b.get("description", "")
                })
            bookmark = data.get("resource_response", {}).get("bookmark")
            if not bookmark or bookmark == "-end-":
                break
        except Exception as e:
            print(f"[WARN] Pinterest API 직접 호출 실패: {e}")
            break

    return all_boards


def fetch_boards_via_playwright() -> list:
    """Playwright로 /me/boards/ 페이지 스크래핑"""
    try:
        from playwright.sync_api import sync_playwright
        from urllib.parse import urlparse
    except ImportError:
        print("[WARN] playwright 없음")
        return []

    SYSTEM_SLUGS = {"_saved", "_created", "pins", "following", "followers", "more_ideas"}

    with open(COOKIE_FILE) as f:
        raw = json.load(f)
    pw_cookies = raw if isinstance(raw, list) else [
        {"name": k, "value": v, "domain": ".pinterest.com", "path": "/"}
        for k, v in raw.items()
    ]

    boards = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context()
        context.add_cookies(pw_cookies)
        page = context.new_page()
        try:
            # 1단계: username 얻기
            page.goto("https://www.pinterest.com/me/boards/", wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(2000)
            current_url = page.url
            path_parts = [p for p in urlparse(current_url).path.strip("/").split("/") if p]
            username = path_parts[0] if path_parts else ""

            # 2단계: 실제 보드 그리드 페이지로 이동
            base = f"{urlparse(current_url).scheme}://{urlparse(current_url).netloc}"
            boards_url = f"{base}/{username}/_saved/"
            page.goto(boards_url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(3000)

            # 3단계: "Boards" 탭 클릭 (있을 경우)
            try:
                boards_tab = page.locator("a[href*='/_created/'], a[href*='/boards/']").first
                if boards_tab.count() == 0:
                    # 탭 텍스트로 찾기
                    boards_tab = page.get_by_role("tab", name="Boards")
                boards_tab.click(timeout=3000)
                page.wait_for_timeout(2000)
            except Exception:
                pass  # 탭 없으면 그냥 계속

            # 4단계: 무한 스크롤로 모든 보드 로드
            prev_count = 0
            for _ in range(30):
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                page.wait_for_timeout(1500)
                links_now = page.eval_on_selector_all("a[href]", "els => els.map(e => e.href)")
                board_links = [l for l in links_now if f"/{username}/" in l]
                if len(board_links) == prev_count:
                    break
                prev_count = len(board_links)

            links = page.eval_on_selector_all("a[href]", "els => els.map(e => e.href)")
            seen = set()
            for href in links:
                parts = [p for p in urlparse(href).path.strip("/").split("/") if p]
                if len(parts) == 2 and parts[0] == username and parts[1] not in SYSTEM_SLUGS:
                    slug = parts[1]
                    if slug not in seen:
                        seen.add(slug)
                        boards.append({
                            "board_name": slug.replace("-", " "),
                            "board_url": href.split("?")[0].rstrip("/") + "/",
                            "is_private": False,
                            "pin_count": 0
                        })
        except Exception as e:
            print(f"[WARN] Playwright 스크래핑 실패: {e}")
        finally:
            browser.close()
    return boards


def list_boards() -> list:
    cookies = load_cookies()
    boards = fetch_boards_via_api(cookies)
    if not boards:
        print("[INFO] Playwright로 보드 목록을 스크래핑합니다...")
        boards = fetch_boards_via_playwright()
    if not boards:
        print("[ERROR] 보드를 찾을 수 없습니다. 쿠키가 만료되었을 수 있습니다.")
        sys.exit(1)

    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(BOARDS_FILE, "w", encoding="utf-8") as f:
        json.dump(boards, f, ensure_ascii=False, indent=2)

    print(f"\n[OK] 보드 {len(boards)}개 조회 완료")
    for i, b in enumerate(boards, 1):
        lock = "[private]" if b.get("is_private") else "[public]"
        print(f"  {i}. {lock} {b['board_name']} ({b.get('pin_count', 0)}pin)")
    return boards


if __name__ == "__main__":
    list_boards()
