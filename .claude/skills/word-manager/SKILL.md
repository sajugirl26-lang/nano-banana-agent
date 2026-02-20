# word-manager

단어 DB 초기화 및 Word1/Word2 랜덤 선택

## 스크립트

### init_words.py
Word DB 초기 생성 (1회성)
```bash
python .claude/skills/word-manager/scripts/init_words.py
```
- 출력: `/config/word1-db.json` (카테고리별 에보케이티브 단어, en 필드 포함)
- 출력: `/config/word2-pool.json` (200개 이상 수식어 풀, en 필드 포함)

### random_picker.py
Word1/Word2 랜덤 선택
```python
from random_picker import pick_word1, pick_word2, generate_word_pairs
pairs = generate_word_pairs(count=50)
```

**Word1 선택 규칙:**
- 동일 단어 연속 3회 이상 금지
- 카테고리 구분 없이 전체 풀에서 랜덤

**Word2 선택 규칙:**
- 완전 랜덤 (제한 없음)

## DB 구조

### word1-db.json
```json
{
  "감정": [{"word": "사랑", "en": "love, tender warmth, longing"}, ...],
  "자연": [...],
  "판타지": [...],
  "일상": [...],
  "추상": [...]
}
```

### word2-pool.json
```json
[{"word": "우산", "en": "umbrella, shelter from storm"}, ...]
```

## 성공 기준
- Word1: 카테고리 5개 이상, 각 20개 이상, 모든 단어에 en 필드
- Word2: 200개 이상, 모든 단어에 en 필드
