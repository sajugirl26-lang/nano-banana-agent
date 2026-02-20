#!/usr/bin/env python3
"""Pinterest 로그인 — pinterest-dl 라이브러리로 쿠키 저장"""
import subprocess
import sys
from pathlib import Path

CREDENTIALS_DIR = Path(__file__).parents[4] / "config" / "credentials"
COOKIE_FILE = CREDENTIALS_DIR / "pinterest-cookies.json"


def login():
    CREDENTIALS_DIR.mkdir(parents=True, exist_ok=True)
    print("Pinterest 로그인을 시작합니다.")
    print("브라우저가 열리면 Pinterest에 로그인 후 창을 닫으세요.\n")
    import shutil
    pdl_cmd = shutil.which("pinterest-dl")
    if not pdl_cmd:
        scripts_dir = Path(sys.executable).parent / "Scripts"
        pdl_cmd = str(scripts_dir / "pinterest-dl.exe")
    result = subprocess.run(
        [pdl_cmd, "login", "-o", str(COOKIE_FILE), "--headful", "--wait", "30"],
        capture_output=False
    )
    if result.returncode != 0:
        print(f"[ERROR] 로그인 실패 (returncode={result.returncode})")
        sys.exit(1)
    if not COOKIE_FILE.exists():
        print("[ERROR] 쿠키 파일이 생성되지 않았습니다.")
        sys.exit(1)
    print(f"\n[OK] 쿠키 저장 완료: {COOKIE_FILE}")
    return str(COOKIE_FILE)


if __name__ == "__main__":
    login()
