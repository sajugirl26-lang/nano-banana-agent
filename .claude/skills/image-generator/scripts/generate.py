#!/usr/bin/env python3
"""이미지 생성 메인 스크립트 — google-genai SDK (Pro/Flash 전환 포함)"""
import json
import random
import time
import sys
import io
from pathlib import Path
from datetime import datetime, timezone

try:
    from google import genai
    from google.genai import types
except ImportError:
    print("[ERROR] pip install google-genai")
    sys.exit(1)

try:
    from PIL import Image
    HAS_PILLOW = True
except ImportError:
    HAS_PILLOW = False

import requests as _requests

CONFIG_DIR = Path(__file__).parents[4] / "config"
PINS_DIR = Path(__file__).parents[4] / "tmp" / "pins"
OUTPUT_DIR = Path(__file__).parents[4] / "output" / "images"

sys.path.insert(0, str(Path(__file__).parent))
from rate_limiter import get_rate_limiter
from prompt_builder import build_prompt, round_robin_template

PRICE_PRO = 0.134
PRICE_FLASH = 0.039
MAX_REF_IMAGES = 5
MAX_INLINE_BYTES = 20 * 1024 * 1024
MAX_RECENT_PINS = 50


def select_reference_pins(board_names: list, recent_used: list) -> list:
    """보드 캐시 JSON에서 핀 URL 선택 (로컬 파일 불필요)"""
    all_pins = []  # [(board_name, pin_id, image_url), ...]
    for name in board_names:
        cache = CONFIG_DIR / "boards" / f"{name}.json"
        if not cache.exists():
            continue
        with open(cache, encoding="utf-8") as f:
            bd = json.load(f)
        for pin in bd.get("pins", []):
            url = pin.get("image_url", "")
            if url:
                all_pins.append((name, pin.get("pin_id", ""), url))

    recent_set = set(recent_used[-MAX_RECENT_PINS:])
    available = [p for p in all_pins if p[2] not in recent_set]
    if not available:
        available = all_pins
    if not available:
        return []
    count = min(random.randint(2, 5), len(available))
    return random.sample(available, count)


def generate_image(
    word1: str, word1_en: str,
    word2: str, word2_en: str,
    board_names: list,
    combo_id: str,
    template_index: int = 0,
    recent_pins: list = None
) -> dict:
    """이미지 1장 생성. 메타데이터 dict 반환"""
    if recent_pins is None:
        recent_pins = []

    rl = get_rate_limiter()

    template_id = round_robin_template(template_index)
    try:
        prompt, used_template_id = build_prompt(word1, word1_en, word2, word2_en, template_id)
    except Exception as e:
        return {"status": "failed", "error": f"프롬프트 생성 실패: {e}", "combo_id": combo_id}

    ref_pins = select_reference_pins(board_names, recent_pins)  # [(board, pin_id, url), ...]
    if len(ref_pins) < 3:
        print(f"  [WARN] ref pins {len(ref_pins)} (min 3 recommended)")

    key = rl.wait_for_slot(timeout=180)
    if not key:
        return {"status": "failed", "error": "모든 API 키 소진", "combo_id": combo_id}

    model_name = rl.current_model
    cost = PRICE_PRO

    # 컨텐츠 구성: URL에서 직접 다운로드
    content_parts = [prompt]
    total_size = 0
    used_ref_urls = []

    for board_name, pin_id, pin_url in ref_pins:
        try:
            resp = _requests.get(pin_url, timeout=15)
            resp.raise_for_status()
            img_data = resp.content
            if total_size + len(img_data) > MAX_INLINE_BYTES:
                break
            mime = resp.headers.get("content-type", "image/jpeg").split(";")[0]
            content_parts.append(types.Part.from_bytes(
                data=img_data,
                mime_type=mime
            ))
            total_size += len(img_data)
            used_ref_urls.append(pin_url)
        except Exception as e:
            print(f"  [WARN] pin download failed {pin_url[:60]}: {e}")

    # API 호출 (재시도 포함)
    response = None
    for attempt in range(rl.max_retry):
        try:
            client = genai.Client(api_key=key["api_key"])
            rl.mark_used(key["id"])
            response = client.models.generate_content(
                model=model_name,
                contents=content_parts,
                config=types.GenerateContentConfig(
                    response_modalities=["IMAGE", "TEXT"]
                )
            )
            break
        except Exception as e:
            err_str = str(e)
            if "503" in err_str or "UNAVAILABLE" in err_str:
                # 서버 과부하는 재시도해도 낭비 — 즉시 실패 처리
                return {"status": "failed", "error": f"503 서버 과부하 (재시도 안함)", "combo_id": combo_id}
            elif "429" in err_str or "RESOURCE_EXHAUSTED" in err_str or "quota" in err_str.lower():
                rl.mark_rate_limited(key["id"])
                key = rl.wait_for_slot(timeout=120)
                if not key:
                    return {"status": "failed", "error": "Rate limit 소진", "combo_id": combo_id}
            elif attempt == rl.max_retry - 1:
                return {"status": "failed", "error": err_str, "combo_id": combo_id}
            else:
                time.sleep(20)

    if response is None:
        return {"status": "failed", "error": "응답 없음", "combo_id": combo_id}

    # 이미지 저장
    today = datetime.now().strftime("%y%m%d")
    out_dir = OUTPUT_DIR / today
    out_dir.mkdir(parents=True, exist_ok=True)
    safe_w1 = word1[:10].replace("/", "_")
    safe_w2 = word2[:10].replace("/", "_")
    filename = f"{combo_id}_{safe_w1}_{safe_w2}.png"
    file_path = out_dir / filename

    try:
        image_data = None
        for part in response.candidates[0].content.parts:
            if part.inline_data and part.inline_data.mime_type.startswith("image"):
                image_data = part.inline_data.data
                break
        if image_data is None:
            return {"status": "failed", "error": "응답에 이미지 없음", "combo_id": combo_id}

        with open(file_path, "wb") as f:
            f.write(image_data)

        resolution = "unknown"
        if HAS_PILLOW:
            img = Image.open(io.BytesIO(image_data))
            resolution = f"{img.width}x{img.height}"
    except Exception as e:
        return {"status": "failed", "error": f"저장 실패: {e}", "combo_id": combo_id}

    return {
        "combo_id": combo_id,
        "word1": word1, "word1_en": word1_en,
        "word2": word2, "word2_en": word2_en,
        "model_used": model_name,
        "cost": cost,
        "reference_pins": used_ref_urls,
        "reference_boards": board_names,
        "template_id": used_template_id,
        "prompt": prompt,
        "api_key_used": key["id"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "file_path": str(file_path),
        "resolution": resolution,
        "drive_uploaded": False,
        "drive_file_id": None,
        "status": "success"
    }


if __name__ == "__main__":
    result = generate_image(
        word1="사랑", word1_en="love, warmth",
        word2="톱니바퀴", word2_en="gear, mechanism",
        board_names=["aesthetic-mood"],
        combo_id="test_001",
        template_index=0
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
