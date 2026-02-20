#!/usr/bin/env python3
"""예약 배치: Pro 이미지 1장 테스트 → 성공 시 200장 배치 실행, 실패 시 중단"""
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / ".claude" / "skills" / "notifier" / "scripts"))
from slack_notify import send_slack

CONFIG_DIR = Path(__file__).parent / "config"
API_KEYS_FILE = CONFIG_DIR / "api-keys.json"
SETTINGS_FILE = CONFIG_DIR / "settings.json"


def test_pro_image():
    """Pro 모델로 이미지 1장 테스트 생성"""
    with open(API_KEYS_FILE, encoding="utf-8") as f:
        keys = json.load(f)["keys"]
    with open(SETTINGS_FILE, encoding="utf-8") as f:
        settings = json.load(f)

    api_key = keys[0]["api_key"]
    model = settings.get("model_pro", "gemini-3-pro-image-preview")

    print(f"[TEST] 모델: {model}")
    print(f"[TEST] Pro 이미지 1장 테스트 중...")

    try:
        from google import genai
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=model,
            contents="a cute cat, simple illustration",
            config=genai.types.GenerateContentConfig(
                response_modalities=["TEXT", "IMAGE"]
            ),
        )
        for part in response.candidates[0].content.parts:
            if part.inline_data:
                size = len(part.inline_data.data)
                print(f"[TEST] 성공! 이미지 생성됨 ({size:,} bytes)")
                return True
        print("[TEST] 실패 — 응답에 이미지 없음")
        return False
    except Exception as e:
        print(f"[TEST] 실패 — {e}")
        return False


def kill_existing_batch():
    """실행 중인 run_batch.py 프로세스 종료"""
    try:
        result = subprocess.run(
            ["wmic", "process", "where",
             "CommandLine like '%run_batch.py%' and Name like '%python%'",
             "get", "ProcessId"],
            capture_output=True, text=True, timeout=10
        )
        for line in result.stdout.strip().split("\n"):
            line = line.strip()
            if line.isdigit():
                pid = int(line)
                print(f"[KILL] 기존 프로세스 종료: PID {pid}")
                subprocess.run(["taskkill", "/PID", str(pid), "/F"],
                               capture_output=True, timeout=10)
    except Exception as e:
        print(f"[WARN] 프로세스 확인 실패: {e}")


def main():
    # 1. 기존 배치 프로세스 확인 + 종료
    kill_existing_batch()

    # 2. Pro 테스트
    if test_pro_image():
        send_slack("Pro 테스트 성공 — 200장 배치 시작합니다.", "🟢")
        print("\n[GO] Pro 정상 — 200장 배치 시작합니다.")
        subprocess.Popen(
            [sys.executable, "run_batch.py", "200"],
            cwd=str(Path(__file__).parent)
        )
    else:
        send_slack("Pro 테스트 실패 — 배치 실행하지 않습니다.", "🔴")
        print("\n[STOP] Pro 실패 — 배치 실행하지 않습니다.")
        kill_existing_batch()


if __name__ == "__main__":
    main()
