# pin-tracker

핀 사용 추적, 메타데이터 기록, HTML 뷰어 생성

## 스크립트

### track_pins.py
메타데이터 JSON 관리
```python
from track_pins import append_entry, get_pin_usage_stats
append_entry(metadata_dict)        # 생성 완료 후 즉시 기록
stats = get_pin_usage_stats()      # 세션 완료 후 통계
```
- 파일: `/output/images/{date}/metadata.json`
- 각 항목: combo_id, word1/2, model, cost, reference_pins(URL), prompt, file_path 등

### generate_viewer.py
핀 추적 HTML 뷰어 생성
```python
from generate_viewer import generate_viewer
output_path = generate_viewer(session_id, date_str)
```
- 출력: `/output/images/{date}/session-{id}-pins.html`
- 기능:
  - 생성 이미지 + 참조 핀 5장 카드 형태 표시
  - 핀 클릭 → Pinterest 원본 새 탭
  - 단어 검색, 모델 필터, 정렬 기능
  - 비용 현황 요약 (상단 통계)

### pin_stats.py
핀 사용 통계
```python
from pin_stats import get_session_stats
stats = get_session_stats(session_id, date_str)
```

## 메타데이터 구조
```json
{
  "combo_id": "20260217_001",
  "word1": "사랑", "word1_en": "love, warmth",
  "word2": "톱니바퀴", "word2_en": "gear, mechanism",
  "model_used": "gemini-3-pro-image-preview",
  "cost": 0.134,
  "reference_pins": ["https://i.pinimg.com/..."],
  "reference_boards": ["aesthetic-mood"],
  "template_id": "fusion_01",
  "prompt": "...",
  "generated_at": "2026-02-17T10:30:00Z",
  "file_path": "/output/images/20260217/...",
  "resolution": "2048x2048",
  "drive_uploaded": false,
  "status": "success"
}
```
