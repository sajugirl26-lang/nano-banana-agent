#!/usr/bin/env python3
"""프롬프트 빌더 — 고정 템플릿 + 문자열 치환 (LLM 호출 없음)"""
import json
import random
from pathlib import Path

CONFIG_DIR = Path(__file__).parents[4] / "config"
TEMPLATES_FILE = CONFIG_DIR / "prompt-templates.json"


def load_templates() -> list:
    if not TEMPLATES_FILE.exists():
        raise FileNotFoundError(f"템플릿 파일 없음: {TEMPLATES_FILE}")
    with open(TEMPLATES_FILE, encoding="utf-8") as f:
        data = json.load(f)
    return data.get("templates", [])


def build_prompt(word1: str, word1_en: str, word2: str, word2_en: str,
                 template_id: str = None) -> tuple:
    """프롬프트 생성. (prompt_text, template_id) 반환"""
    templates = load_templates()
    if not templates:
        raise ValueError("템플릿이 없습니다.")

    if template_id:
        tpl = next((t for t in templates if t["id"] == template_id), None)
        if not tpl:
            tpl = random.choice(templates)
    else:
        tpl = random.choice(templates)

    prompt = tpl["text"]
    prompt = prompt.replace("{word1}", word1)
    prompt = prompt.replace("{word1_en}", word1_en)
    prompt = prompt.replace("{word2}", word2)
    prompt = prompt.replace("{word2_en}", word2_en)

    for ph in ["{word1}", "{word1_en}", "{word2}", "{word2_en}"]:
        if ph in prompt:
            raise ValueError(f"플레이스홀더 미치환: {ph}")

    return prompt, tpl["id"]


def round_robin_template(index: int) -> str:
    """랜덤 템플릿 선택 (12종 중 무작위)"""
    templates = load_templates()
    if not templates:
        return None
    return random.choice(templates)["id"]


if __name__ == "__main__":
    p, tid = build_prompt("사랑", "love, warmth", "톱니바퀴", "gear, mechanism")
    print(f"Template: {tid}")
    print(f"Prompt: {p}")
