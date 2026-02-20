#!/usr/bin/env python3
"""Google Drive 인증 설정"""
import json
import sys
from pathlib import Path

CONFIG_DIR = Path(__file__).parents[4] / "config"
CREDENTIALS_DIR = CONFIG_DIR / "credentials"
DRIVE_CONFIG_FILE = CONFIG_DIR / "drive-config.json"
TOKEN_FILE = CREDENTIALS_DIR / "token.pickle"
SA_FILE = CREDENTIALS_DIR / "drive-sa.json"
OAUTH_CLIENT_FILE = CREDENTIALS_DIR / "oauth-client.json"

SCOPES = ["https://www.googleapis.com/auth/drive.file"]


def setup_oauth():
    """OAuth 2.0 인증 (개인 계정)"""
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
        from google.auth.transport.requests import Request
        import pickle
    except ImportError:
        print("[ERROR] pip install google-auth google-auth-oauthlib google-api-python-client")
        return None

    creds = None
    if TOKEN_FILE.exists():
        with open(TOKEN_FILE, "rb") as f:
            import pickle
            creds = pickle.load(f)

    if creds and creds.valid:
        return creds

    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    else:
        if not OAUTH_CLIENT_FILE.exists():
            print(f"[ERROR] OAuth 클라이언트 파일 없음: {OAUTH_CLIENT_FILE}")
            print("Google Cloud Console → APIs & Services → Credentials → OAuth 2.0 Client ID 생성")
            return None
        flow = InstalledAppFlow.from_client_secrets_file(str(OAUTH_CLIENT_FILE), SCOPES)
        creds = flow.run_local_server(port=0)

    import pickle
    with open(TOKEN_FILE, "wb") as f:
        pickle.dump(creds, f)
    print(f"[OK] OAuth 토큰 저장: {TOKEN_FILE}")
    return creds


def setup_service_account():
    """Service Account 인증"""
    try:
        from google.oauth2 import service_account
    except ImportError:
        print("[ERROR] pip install google-auth")
        return None

    if not SA_FILE.exists():
        print(f"[ERROR] SA 파일 없음: {SA_FILE}")
        return None
    return service_account.Credentials.from_service_account_file(str(SA_FILE), scopes=SCOPES)


def get_drive_service():
    """Drive API 서비스 객체 반환"""
    try:
        from googleapiclient.discovery import build
    except ImportError:
        print("[ERROR] pip install google-api-python-client")
        return None

    # SA 우선, OAuth 폴백
    creds = None
    if SA_FILE.exists():
        creds = setup_service_account()
        if creds:
            print("[INFO] Service Account 인증 사용")
    if not creds:
        creds = setup_oauth()
        if creds:
            print("[INFO] OAuth 2.0 인증 사용")

    if not creds:
        return None

    return build("drive", "v3", credentials=creds)


def get_or_create_folder(service, name: str, parent_id: str = None) -> str:
    """폴더 생성 또는 기존 폴더 ID 반환"""
    query = f"name='{name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
    if parent_id:
        query += f" and '{parent_id}' in parents"

    results = service.files().list(q=query, fields="files(id, name)").execute()
    files = results.get("files", [])

    if files:
        return files[0]["id"]

    meta = {"name": name, "mimeType": "application/vnd.google-apps.folder"}
    if parent_id:
        meta["parents"] = [parent_id]

    folder = service.files().create(body=meta, fields="id").execute()
    print(f"[OK] Drive 폴더 생성: {name} (id={folder['id']})")
    return folder["id"]


def init_drive_config():
    """Drive 설정 초기화"""
    CREDENTIALS_DIR.mkdir(parents=True, exist_ok=True)
    service = get_drive_service()
    if not service:
        print("[WARN] Drive 연결 실패 — 로컬 저장만 사용")
        config = {"use_drive": False}
        with open(DRIVE_CONFIG_FILE, "w") as f:
            json.dump(config, f, indent=2)
        return

    root_id = get_or_create_folder(service, "nano-banana-output")
    config = {"use_drive": True, "root_folder_id": root_id}

    with open(DRIVE_CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)
    print(f"[OK] Drive 설정 저장: {DRIVE_CONFIG_FILE}")
    print(f"[OK] 루트 폴더: nano-banana-output (id={root_id})")


if __name__ == "__main__":
    init_drive_config()
