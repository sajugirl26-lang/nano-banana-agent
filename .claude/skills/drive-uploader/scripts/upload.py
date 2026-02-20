#!/usr/bin/env python3
"""Google Drive 업로드 — 단일 파일 즉시 업로드 + 공개 링크"""
import json
import sys
from pathlib import Path

CONFIG_DIR = Path(__file__).parents[4] / "config"
DRIVE_CONFIG_FILE = CONFIG_DIR / "drive-config.json"
TARGET_FOLDER_ID = "1t5isTXE_q-1EZl_6VcA6d2wzfI2GkPhJ"

sys.path.insert(0, str(Path(__file__).parent))

_service_cache = None
_folder_cache = {}


def load_drive_config() -> dict:
    if not DRIVE_CONFIG_FILE.exists():
        return {"use_drive": False}
    with open(DRIVE_CONFIG_FILE) as f:
        return json.load(f)


def _get_service():
    """Drive 서비스 싱글턴"""
    global _service_cache
    if _service_cache is None:
        from drive_setup import get_drive_service
        _service_cache = get_drive_service()
    return _service_cache


def _get_folder_id(date_str: str) -> str | None:
    """날짜별 Drive 폴더 ID (캐싱)"""
    if date_str in _folder_cache:
        return _folder_cache[date_str]
    service = _get_service()
    if not service:
        return None
    from drive_setup import get_or_create_folder
    folder_id = get_or_create_folder(service, date_str, TARGET_FOLDER_ID)
    _folder_cache[date_str] = folder_id
    return folder_id


def upload_single_image(file_path: str, metadata: dict, date_str: str) -> str | None:
    """이미지 1개를 Drive에 업로드하고 file_id 반환. 실패시 None"""
    cfg = load_drive_config()
    if not cfg.get("use_drive"):
        return None

    service = _get_service()
    if not service:
        return None

    folder_id = _get_folder_id(date_str)
    if not folder_id:
        return None

    try:
        from googleapiclient.http import MediaFileUpload
    except ImportError:
        return None

    path = Path(file_path)
    if not path.exists():
        return None

    mime = "image/png" if path.suffix == ".png" else "image/jpeg"

    file_meta = {
        "name": path.name,
        "parents": [folder_id]
    }
    media = MediaFileUpload(str(path), mimetype=mime, resumable=True)

    try:
        result = service.files().create(
            body=file_meta, media_body=media, fields="id"
        ).execute()
        return result.get("id")
    except Exception as e:
        print(f"  [DRIVE] 업로드 실패 {path.name}: {e}")
        return None


def get_drive_image_url(file_id: str) -> str:
    """Drive file_id → 이미지 직접 표시 URL"""
    return f"https://lh3.googleusercontent.com/d/{file_id}"


def upload_metadata_file(file_path: str) -> str | None:
    """metadata JSON을 Drive metadata 폴더에 업로드"""
    cfg = load_drive_config()
    if not cfg.get("use_drive"):
        return None

    service = _get_service()
    if not service:
        return None

    from drive_setup import get_or_create_folder
    meta_folder_id = get_or_create_folder(service, "metadata", TARGET_FOLDER_ID)

    try:
        from googleapiclient.http import MediaFileUpload
    except ImportError:
        return None

    path = Path(file_path)
    if not path.exists():
        return None

    # 기존 파일 삭제 후 재업로드 (덮어쓰기)
    existing = service.files().list(
        q=f"'{meta_folder_id}' in parents and name='{path.name}' and trashed=false",
        fields="files(id)"
    ).execute().get("files", [])
    for f in existing:
        service.files().delete(fileId=f["id"]).execute()

    file_meta = {"name": path.name, "parents": [meta_folder_id]}
    media = MediaFileUpload(str(path), mimetype="application/json", resumable=True)

    try:
        result = service.files().create(
            body=file_meta, media_body=media, fields="id"
        ).execute()
        return result.get("id")
    except Exception as e:
        print(f"  [DRIVE] metadata 업로드 실패: {e}")
        return None


def upload_html_file(file_path: str) -> str | None:
    """HTML 뷰어를 Drive html 폴더에 업로드"""
    cfg = load_drive_config()
    if not cfg.get("use_drive"):
        return None

    service = _get_service()
    if not service:
        return None

    from drive_setup import get_or_create_folder
    html_folder_id = get_or_create_folder(service, "html", TARGET_FOLDER_ID)

    try:
        from googleapiclient.http import MediaFileUpload
    except ImportError:
        return None

    path = Path(file_path)
    if not path.exists():
        return None

    # 기존 파일 삭제 후 재업로드
    existing = service.files().list(
        q=f"'{html_folder_id}' in parents and name='{path.name}' and trashed=false",
        fields="files(id)"
    ).execute().get("files", [])
    for f in existing:
        service.files().delete(fileId=f["id"]).execute()

    file_meta = {"name": path.name, "parents": [html_folder_id]}
    media = MediaFileUpload(str(path), mimetype="text/html", resumable=True)

    try:
        result = service.files().create(
            body=file_meta, media_body=media, fields="id"
        ).execute()
        return result.get("id")
    except Exception as e:
        print(f"  [DRIVE] HTML 업로드 실패: {e}")
        return None
