#!/usr/bin/env python3
"""실패한 Drive 업로드 재시도"""
import json
import sys
from pathlib import Path

CONFIG_DIR = Path(__file__).parents[4] / "config"
FAILED_FILE = CONFIG_DIR / "failed-uploads.json"
sys.path.insert(0, str(Path(__file__).parent))


def retry_failed():
    if not FAILED_FILE.exists():
        print("[INFO] 재시도할 실패 파일 없음")
        return

    with open(FAILED_FILE) as f:
        failed = json.load(f)

    if not failed:
        print("[INFO] 실패 목록 비어있음")
        return

    print(f"[INFO] {len(failed)}개 파일 재업로드 시도...")

    try:
        from drive_setup import get_drive_service, get_or_create_folder
        from upload import upload_file, load_drive_config
    except Exception as e:
        print(f"[ERROR] Drive 모듈 로드 실패: {e}")
        return

    cfg = load_drive_config()
    if not cfg.get("use_drive"):
        print("[INFO] Drive 비활성화")
        return

    service = get_drive_service()
    if not service:
        print("[ERROR] Drive 서비스 초기화 실패")
        return

    root_id = cfg.get("root_folder_id")
    still_failed = []

    for fp in failed:
        path = Path(fp)
        if not path.exists():
            print(f"  [SKIP] 파일 없음: {fp}")
            continue
        date_str = path.parent.name
        folder_id = get_or_create_folder(service, date_str, root_id)
        file_id = upload_file(service, fp, {}, folder_id)
        if file_id:
            print(f"  [OK] 재업로드 성공: {path.name}")
        else:
            print(f"  [FAIL] 재업로드 실패: {path.name}")
            still_failed.append(fp)

    with open(FAILED_FILE, "w") as f:
        json.dump(still_failed, f, indent=2)

    print(f"[OK] 완료. 여전히 실패: {len(still_failed)}개")


if __name__ == "__main__":
    retry_failed()
