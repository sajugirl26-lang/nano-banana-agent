#!/usr/bin/env python3
"""Word1/Word2 랜덤 선택"""
import json
import random
from collections import Counter
from pathlib import Path

CONFIG_DIR = Path(__file__).parents[4] / "config"
SETTINGS_FILE = CONFIG_DIR / "settings.json"
WORD1_FILE = CONFIG_DIR / "word1-db.json"
WORD2_FILE = CONFIG_DIR / "word2-pool.json"
EXCLUDE_FILE = CONFIG_DIR / "exclude-words.json"


def _load_exclude_words() -> dict:
    """exclude-words.json에서 제외 단어 목록 로드"""
    if EXCLUDE_FILE.exists():
        with open(EXCLUDE_FILE, encoding="utf-8") as f:
            data = json.load(f)
        return {
            "word1": set(data.get("word1", [])),
            "word2": set(data.get("word2", []))
        }
    return {"word1": set(), "word2": set()}


def _load_word_repeat_limit() -> int:
    """settings.json에서 배치 내 단어 반복 상한 로드"""
    if SETTINGS_FILE.exists():
        with open(SETTINGS_FILE, encoding="utf-8") as f:
            s = json.load(f)
        return s.get("session", {}).get("word_repeat_max_per_batch", 2)
    return 2


def load_word1_db() -> dict:
    if not WORD1_FILE.exists():
        raise FileNotFoundError(f"word1-db.json 없음. init_words.py를 먼저 실행하세요.")
    with open(WORD1_FILE, encoding="utf-8") as f:
        db = json.load(f)
    exclude = _load_exclude_words()["word1"]
    if exclude:
        db = {cat: [w for w in words if w["word"] not in exclude] for cat, words in db.items()}
    return db


def load_word2_pool() -> list:
    if not WORD2_FILE.exists():
        raise FileNotFoundError(f"word2-pool.json 없음. init_words.py를 먼저 실행하세요.")
    with open(WORD2_FILE, encoding="utf-8") as f:
        pool = json.load(f)
    exclude = _load_exclude_words()["word2"]
    if exclude:
        pool = [w for w in pool if w["word"] not in exclude]
    return pool


def pick_word1(used_counts: Counter = None) -> dict:
    """Word1 랜덤 선택 (배치 내 반복 상한 적용)"""
    db = load_word1_db()
    repeat_limit = _load_word_repeat_limit()
    all_words = []
    for cat, words in db.items():
        for w in words:
            all_words.append({**w, "category": cat})

    if not all_words:
        raise ValueError("Word1 DB가 비어있습니다.")

    if used_counts:
        candidates = [w for w in all_words if used_counts.get(w["word"], 0) < repeat_limit]
        if candidates:
            return random.choice(candidates)
        # 모든 단어가 상한 도달 시 카운터 리셋 후 전체에서 선택
        used_counts.clear()

    return random.choice(all_words)


def pick_word2(used_counts: Counter = None) -> dict:
    """Word2 랜덤 선택 (배치 내 반복 상한 적용)"""
    pool = load_word2_pool()
    repeat_limit = _load_word_repeat_limit()
    if not pool:
        raise ValueError("Word2 풀이 비어있습니다.")

    if used_counts:
        candidates = [w for w in pool if used_counts.get(w["word"], 0) < repeat_limit]
        if candidates:
            return random.choice(candidates)
        used_counts.clear()

    return random.choice(pool)


def generate_word_pairs(count: int, recent_word1: list = None, fixed_word1: str = None) -> list:
    """count개의 단어 조합 사전 생성. count=-1이면 200개.
    배치 내 word1/word2 각각 word_repeat_max_per_batch 횟수까지만 중복 허용.
    fixed_word1이 지정되면 모든 조합에서 해당 word1을 고정 사용."""
    if count < 0:
        count = 200
    if recent_word1 is None:
        recent_word1 = []

    # fixed_word1 처리: word1-db에서 해당 단어 찾기
    fixed_w1 = None
    if fixed_word1:
        db = load_word1_db()
        for cat, words in db.items():
            for w in words:
                if w["word"] == fixed_word1:
                    fixed_w1 = {**w, "category": cat}
                    break
            if fixed_w1:
                break
        if not fixed_w1:
            raise ValueError(f"Word1 DB에서 '{fixed_word1}'을(를) 찾을 수 없습니다.")
        print(f"[WORD1 고정] {fixed_word1} ({fixed_w1['en'][:30]})")

    w1_counts: Counter = Counter()
    w2_counts: Counter = Counter()
    pairs = []
    for _ in range(count):
        w1 = fixed_w1 if fixed_w1 else pick_word1(w1_counts)
        w2 = pick_word2(w2_counts)
        w1_counts[w1["word"]] += 1
        w2_counts[w2["word"]] += 1
        recent_word1.append(w1["word"])
        pairs.append({
            "word1": w1["word"],
            "word1_en": w1["en"],
            "word2": w2["word"],
            "word2_en": w2["en"]
        })
    return pairs


if __name__ == "__main__":
    print("단어 조합 5개 샘플:")
    pairs = generate_word_pairs(5)
    for p in pairs:
        print(f"  {p['word1']}({p['word1_en'][:20]}...) × {p['word2']}({p['word2_en']})")
