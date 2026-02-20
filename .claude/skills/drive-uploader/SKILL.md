# drive-uploader

Google Drive 업로드 (별도 계정 지원, description 메타데이터 포함)

## 인증 방식

| 방식 | 시나리오 | 파일 |
|------|---------|------|
| OAuth 2.0 | 별도 개인 계정 | `credentials/oauth-client.json` → `credentials/token.pickle` |
| Service Account | 같은 GCP 프로젝트 | `credentials/drive-sa.json` |

## 스크립트

### drive_setup.py
Drive 인증 초기화
```bash
python .claude/skills/drive-uploader/scripts/drive_setup.py
```
- 브라우저 1회 인증 (OAuth) 또는 SA 자동 인증
- 루트 폴더 `nano-banana-output` 생성
- 출력: `/config/drive-config.json` (root_folder_id 저장)

### upload.py
세션 전체 파일 업로드
```python
from upload import upload_session
results = upload_session(date_str, session_id, metadata_list)
# results: {"uploaded": 225, "failed": 0}
```
- Drive 파일 description: `word1, word2, board, date` (Drive 내 검색 가능)
- 업로드 후 metadata 항목의 `drive_uploaded`, `drive_file_id` 업데이트

### retry_failed.py
실패한 업로드 재시도
```bash
python .claude/skills/drive-uploader/scripts/retry_failed.py
```

## 폴더 구조 (Drive)
```
nano-banana-output/
└── 20260217/
    ├── 20260217_0001_사랑_톱니바퀴.png
    ├── 20260217_0002_달_우산.png
    ├── metadata.json
    └── session-ses_20260217_103000-pins.html
```

## 에러 처리
- Drive 설정 없으면 로컬만 저장 (세션 진행에 영향 없음)
- 개별 파일 업로드 실패 → `failed-uploads.json` 기록 → 다음 세션 시작 시 재시도
