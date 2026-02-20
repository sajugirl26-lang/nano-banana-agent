# image-generator

Gemini API로 이미지 생성 (Pro/Flash 전환 포함)

## 스크립트

### prompt_builder.py
고정 템플릿 + 문자열 치환으로 프롬프트 생성 (LLM 호출 없음)
```python
from prompt_builder import build_prompt, round_robin_template
prompt, template_id = build_prompt(word1, word1_en, word2, word2_en)
```
- `{word1}`, `{word1_en}`, `{word2}`, `{word2_en}` 4개 플레이스홀더 치환
- 템플릿 파일: `/config/prompt-templates.json`

### rate_limiter.py
API 키 로테이션 + Rate Limit 관리 + 모델 전환
```python
from rate_limiter import get_rate_limiter
rl = get_rate_limiter()
key = rl.get_available_key()
rl.mark_rate_limited(key_id)   # 429 발생 시
rl.switch_to_flash()            # Flash 전환
rl.try_switch_back_to_pro()     # Flash 10회마다 Pro 복귀 시도
```

**전환 로직:**
- Pro 모든 키 429 → Flash 자동 전환 + Slack 알림
- Flash 10회마다 Pro 키 쿨다운 해제 확인 → 복귀

### generate.py
이미지 1장 생성 메인 함수
```python
from generate import generate_image
metadata = generate_image(
    word1, word1_en, word2, word2_en,
    board_names, combo_id, template_index
)
```
- 로컬 핀 캐시에서 5장 랜덤 선택 (최근 N회 사용 제외)
- base64 인라인으로 API 전달 (총 < 20MB)
- 성공 시 metadata dict 반환 (status="success")
- 실패 시 metadata dict 반환 (status="failed")

## 모델 전환 정책
```
[1순위] gemini-3-pro-image-preview (Pro) — $0.134/장
   └─ 모든 키 429 → ↓
[2순위] gemini-2.5-flash-image (Flash) — $0.039/장
   ├─ 매 10회마다 Pro 복귀 시도
   └─ Flash도 전체 429 → 60초 대기 → Pro 재시도 → 실패 시 세션 종료
```

## 비용
- Pro (2K PNG): $0.134/장
- Flash (1K PNG): $0.039/장
