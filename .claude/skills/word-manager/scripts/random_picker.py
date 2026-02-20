#!/usr/bin/env python3
"""Word1/Word2 랜덤 선택"""
import json
import random
from pathlib import Path

CONFIG_DIR = Path(__file__).parents[4] / "config"
WORD1_FILE = CONFIG_DIR / "word1-db.json"
WORD2_FILE = CONFIG_DIR / "word2-pool.json"


def load_word1_db() -> dict:
    if not WORD1_FILE.exists():
        raise FileNotFoundError(f"word1-db.json 없음. init_words.py를 먼저 실행하세요.")
    with open(WORD1_FILE, encoding="utf-8") as f:
        return json.load(f)


def load_word2_pool() -> list:
    if not WORD2_FILE.exists():
        raise FileNotFoundError(f"word2-pool.json 없음. init_words.py를 먼저 실행하세요.")
    with open(WORD2_FILE, encoding="utf-8") as f:
        return json.load(f)


def pick_word1(recent_words: list = None) -> dict:
    """Word1 랜덤 선택 (동일 단어 연속 3회 방지)"""
    db = load_word1_db()
    all_words = []
    for cat, words in db.items():
        for w in words:
            all_words.append({**w, "category": cat})

    if not all_words:
        raise ValueError("Word1 DB가 비어있습니다.")

    if recent_words and len(recent_words) >= 3:
        last_three = recent_words[-3:]
        if len(set(last_three)) == 1:
            blocked = last_three[0]
            candidates = [w for w in all_words if w["word"] != blocked]
            if candidates:
                return random.choice(candidates)

    return random.choice(all_words)


def pick_word2() -> dict:
    """Word2 완전 랜덤 선택"""
    pool = load_word2_pool()
    if not pool:
        raise ValueError("Word2 풀이 비어있습니다.")
    return random.choice(pool)


def generate_word_pairs(count: int, recent_word1: list = None) -> list:
    """count개의 단어 조합 사전 생성. count=-1이면 200개"""
    if count < 0:
        count = 200
    if recent_word1 is None:
        recent_word1 = []
    pairs = []
    for _ in range(count):
        w1 = pick_word1(recent_word1)
        w2 = pick_word2()
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
