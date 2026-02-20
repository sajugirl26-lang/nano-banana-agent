#!/usr/bin/env python3
"""
나노바나나 에이전트 — 초기 설정 스크립트 (1회 실행)
사용: python setup.py
"""
import json
import subprocess
import sys
from pathlib import Path

BASE_DIR = Path(__file__).parent
SKILLS_DIR = BASE_DIR / ".claude" / "skills"
sys.path.insert(0, str(SKILLS_DIR / "word-manager" / "scripts"))
sys.path.insert(0, str(SKILLS_DIR / "session-controller" / "scripts"))
sys.path.insert(0, str(SKILLS_DIR / "drive-uploader" / "scripts"))


def check_dependencies():
    """필수 패키지 설치 확인"""
    required = [
        "pinterest-dl", "pillow", "requests",
        "google-generativeai", "google-auth",
        "google-auth-oauthlib", "google-api-python-client"
    ]
    missing = []
    for pkg in required:
        try:
            __import__(pkg.replace("-", "_").replace("google_generativeai", "google.generativeai"))
        except ImportError:
            missing.append(pkg)

    if missing:
        print(f"[WARN] 미설치 패키지: {', '.join(missing)}")
        ans = input("지금 설치하시겠습니까? (y/n): ").strip().lower()
        if ans == "y":
            subprocess.run([sys.executable, "-m", "pip", "install"] + missing)
    else:
        print("[OK] 모든 필수 패키지 설치됨")


def setup_api_keys():
    """API 키 설정"""
    api_file = BASE_DIR / "config" / "api-keys.json"
    with open(api_file, encoding="utf-8") as f:
        config = json.load(f)

    print("\n[Gemini API 키 설정]")
    print("현재 키 목록:")
    for k in config["keys"]:
        masked = k["api_key"][:8] + "..." if len(k["api_key"]) > 8 else k["api_key"]
        print(f"  - {k['id']}: {masked}")

    ans = input("API 키를 추가/수정하시겠습니까? (y/n): ").strip().lower()
    if ans == "y":
        key_val = input("API 키 값: ").strip()
        if key_val:
            project = input("프로젝트 이름 (예: my-project): ").strip() or "my-project"
            new_id = f"key_{len(config['keys']) + 1}"
            config["keys"].append({
                "id": new_id,
                "project": project,
                "api_key": key_val,
                "daily_limit": 40
            })
            with open(api_file, "w", encoding="utf-8") as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
            print(f"[OK] 키 추가: {new_id}")


def setup_cost_limits():
    """비용 상한 설정"""
    from cost_tracker import set_limits, load_tracker
    current = load_tracker()["limits"]
    print(f"\n[비용 상한 설정]")
    print(f"현재: 일일 ${current['daily_cost_cap']}, 월간 ${current['monthly_cost_cap']}")

    try:
        daily = float(input("일일 비용 상한 $ (Enter=유지): ").strip() or current["daily_cost_cap"])
        monthly = float(input("월간 비용 상한 $ (Enter=유지): ").strip() or current["monthly_cost_cap"])
    except ValueError:
        print("[WARN] 잘못된 입력. 기존값 유지")
        return

    set_limits(daily, monthly)


def setup_word_db():
    """단어 DB 초기화"""
    word1_file = BASE_DIR / "config" / "word1-db.json"
    word2_file = BASE_DIR / "config" / "word2-pool.json"

    if word1_file.exists() and word2_file.exists():
        ans = input("\n단어 DB가 이미 있습니다. 재생성하시겠습니까? (y/n): ").strip().lower()
        if ans != "y":
            print("[SKIP] 단어 DB 유지")
            return

    print("\n[단어 DB 초기화 중...]")
    from init_words import init_word_db
    init_word_db()


def setup_pinterest():
    """Pinterest 로그인"""
    cookie_file = BASE_DIR / "config" / "credentials" / "pinterest-cookies.json"
    if cookie_file.exists():
        ans = input("\nPinterest 쿠키가 이미 있습니다. 재로그인하시겠습니까? (y/n): ").strip().lower()
        if ans != "y":
            print("[SKIP] 기존 쿠키 유지")
        else:
            subprocess.run([sys.executable,
                           str(SKILLS_DIR / "pinterest-connector" / "scripts" / "login.py")])
    else:
        print("\n[Pinterest 로그인]")
        subprocess.run([sys.executable,
                       str(SKILLS_DIR / "pinterest-connector" / "scripts" / "login.py")])

    if cookie_file.exists():
        print("[INFO] 보드 목록 조회 중...")
        subprocess.run([sys.executable,
                       str(SKILLS_DIR / "pinterest-connector" / "scripts" / "list_boards.py")])


def setup_drive():
    """Google Drive 설정 (선택)"""
    ans = input("\nGoogle Drive 설정을 진행하시겠습니까? (y/n): ").strip().lower()
    if ans != "y":
        print("[SKIP] Drive 설정 건너뜀 (로컬 저장만 사용)")
        return
    from drive_setup import init_drive_config
    init_drive_config()


def setup_slack():
    """Slack 알림 설정 (선택)"""
    settings_file = BASE_DIR / "config" / "settings.json"
    with open(settings_file, encoding="utf-8") as f:
        settings = json.load(f)

    current_url = settings.get("notifications", {}).get("slack_webhook_url", "")
    ans = input("\nSlack 웹훅 URL 설정하시겠습니까? (y/n): ").strip().lower()
    if ans != "y":
        print("[SKIP] Slack 알림 비활성화")
        return

    url = input("Slack Incoming Webhook URL: ").strip()
    if url:
        settings["notifications"]["slack_webhook_url"] = url
        with open(settings_file, "w", encoding="utf-8") as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)
        print("[OK] Slack 웹훅 URL 저장됨")


def main():
    print("[나노바나나] 에이전트 초기 설정")
    print("=" * 50)

    steps = [
        ("패키지 확인", check_dependencies),
        ("API 키 설정", setup_api_keys),
        ("비용 상한 설정", setup_cost_limits),
        ("단어 DB 초기화", setup_word_db),
        ("Pinterest 로그인", setup_pinterest),
        ("Google Drive 설정", setup_drive),
        ("Slack 알림 설정", setup_slack),
    ]

    for name, func in steps:
        print(f"\n{'─'*50}")
        print(f"단계: {name}")
        print(f"{'─'*50}")
        try:
            func()
        except KeyboardInterrupt:
            print("\n[중단] 설정 중단됨")
            break
        except Exception as e:
            print(f"[ERROR] {name} 실패: {e}")

    print(f"\n{'='*50}")
    print("초기 설정 완료!")
    print("세션 시작: python run_session.py")
    print(f"{'='*50}")


if __name__ == "__main__":
    main()
