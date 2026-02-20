#!/usr/bin/env python3
"""Gemini Batch API를 이용한 대량 이미지 생성 (50% 할인)"""
import base64
import json
import io
import time
import sys
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
OUTPUT_DIR = Path(__file__).parents[4] / "output" / "images"
TMP_DIR = Path(__file__).parents[4] / "tmp"
SETTINGS_FILE = CONFIG_DIR / "settings.json"
API_KEYS_FILE = CONFIG_DIR / "api-keys.json"

sys.path.insert(0, str(Path(__file__).parent))
from prompt_builder import build_prompt, weighted_random_template

# 핀 이미지 캐시
_pin_cache: dict = {}


def _load_settings() -> dict:
    if SETTINGS_FILE.exists():
        with open(SETTINGS_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {}


def _load_batch_config() -> dict:
    s = _load_settings()
    return s.get("batch", {
        "poll_interval_seconds": 30,
        "poll_timeout_seconds": 7200,
        "max_batch_size": 200
    })


def _get_api_key() -> str:
    """첫 번째 API 키 반환 (배치 API는 키 1개로 충분)"""
    with open(API_KEYS_FILE, encoding="utf-8") as f:
        cfg = json.load(f)
    keys = cfg.get("keys", [])
    if not keys:
        raise ValueError("API 키가 없습니다")
    return keys[0]["api_key"]


def _download_pin_image(pin_url: str) -> tuple:
    """핀 이미지 다운로드 (캐시 사용). (bytes, mime) 반환"""
    if pin_url in _pin_cache:
        return _pin_cache[pin_url]
    resp = _requests.get(pin_url, timeout=15)
    resp.raise_for_status()
    img_data = resp.content
    mime = resp.headers.get("content-type", "image/jpeg").split(";")[0]
    _pin_cache[pin_url] = (img_data, mime)
    return img_data, mime


def select_reference_pins(board_names: list, recent_used: list) -> list:
    """보드 캐시에서 핀 URL 선택 (generate.py와 동일 로직)"""
    import random
    all_pins = []
    seen_urls = set()
    for name in board_names:
        cache = CONFIG_DIR / "boards" / f"{name}.json"
        if not cache.exists():
            continue
        with open(cache, encoding="utf-8") as f:
            bd = json.load(f)
        for pin in bd.get("pins", []):
            url = pin.get("image_url", "")
            if url and url not in seen_urls:
                seen_urls.add(url)
                all_pins.append((name, pin.get("pin_id", ""), url))
    recent_set = set(list(recent_used)[-50:])
    available = [p for p in all_pins if p[2] not in recent_set]
    if not available:
        available = all_pins
    if not available:
        return []
    count = min(random.randint(2, 4), len(available))
    return random.sample(available, count)


def prepare_batch_requests(
    pairs: list,
    board_names: list,
    recent_pins: list,
    model: str = None
) -> tuple:
    """배치 요청 JSONL 파일 생성.
    Returns: (jsonl_path, request_map)
    request_map: {combo_id: {word1, word2, prompt, template_id, ref_urls, ...}}
    """
    settings = _load_settings()
    if model is None:
        model = settings.get("model_pro", "gemini-3-pro-image-preview")

    TMP_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%y%m%d_%H%M%S")
    jsonl_path = TMP_DIR / f"batch_{timestamp}.jsonl"

    request_map = {}
    template_index = 0

    print(f"\n[BATCH] {len(pairs)}개 요청 준비 중...")

    with open(jsonl_path, "w", encoding="utf-8") as f:
        for i, pair in enumerate(pairs):
            combo_id = pair["combo_id"]
            word1 = pair["word1"]
            word1_en = pair["word1_en"]
            word2 = pair["word2"]
            word2_en = pair["word2_en"]

            # 프롬프트 생성
            template_id = weighted_random_template(template_index)
            template_index += 1
            try:
                prompt_text, used_template_id = build_prompt(
                    word1, word1_en, word2, word2_en, template_id
                )
            except Exception as e:
                print(f"  [{i+1}] {word1} x {word2} — 프롬프트 실패: {e}")
                continue

            # 레퍼런스 핀 선택 + 다운로드
            ref_pins = select_reference_pins(board_names, recent_pins)
            parts = [{"text": prompt_text}]
            used_ref_urls = []

            for board_name, pin_id, pin_url in ref_pins:
                try:
                    img_data, mime = _download_pin_image(pin_url)
                    b64 = base64.b64encode(img_data).decode("ascii")
                    parts.append({
                        "inlineData": {
                            "mimeType": mime,
                            "data": b64
                        }
                    })
                    used_ref_urls.append(pin_url)
                except Exception as e:
                    print(f"  [WARN] pin download failed: {e}")

            # JSONL 행 작성
            request_obj = {
                "key": combo_id,
                "request": {
                    "contents": [{"parts": parts}],
                    "generation_config": {
                        "responseModalities": ["TEXT", "IMAGE"]
                    }
                }
            }
            f.write(json.dumps(request_obj, ensure_ascii=False) + "\n")

            request_map[combo_id] = {
                "word1": word1, "word1_en": word1_en,
                "word2": word2, "word2_en": word2_en,
                "prompt": prompt_text,
                "template_id": used_template_id,
                "reference_pins": used_ref_urls,
                "reference_boards": board_names,
            }

            if (i + 1) % 10 == 0:
                print(f"  [{i+1}/{len(pairs)}] 준비 완료")

    print(f"[BATCH] JSONL 생성 완료: {jsonl_path} ({len(request_map)}개)")
    return jsonl_path, request_map


def submit_batch(jsonl_path: Path, model: str) -> str:
    """배치 작업 제출. batch_job_name 반환"""
    api_key = _get_api_key()
    client = genai.Client(api_key=api_key)

    print(f"[BATCH] JSONL 업로드 중...")
    uploaded_file = client.files.upload(
        file=str(jsonl_path),
        config=types.UploadFileConfig(
            display_name=jsonl_path.stem,
            mime_type="jsonl"
        ),
    )
    print(f"[BATCH] 업로드 완료: {uploaded_file.name}")

    print(f"[BATCH] 배치 작업 생성 중 (model: {model})...")
    batch_job = client.batches.create(
        model=model,
        src=uploaded_file.name,
        config={"display_name": f"nano-banana-{jsonl_path.stem}"},
    )
    print(f"[BATCH] 배치 제출 완료: {batch_job.name}")
    return batch_job.name


def poll_batch(batch_job_name: str, interval: int = 30, timeout: int = 7200) -> object:
    """배치 완료까지 polling"""
    api_key = _get_api_key()
    client = genai.Client(api_key=api_key)

    start = time.time()
    print(f"[BATCH] polling 시작 (간격 {interval}초, 타임아웃 {timeout}초)")

    while time.time() - start < timeout:
        batch_job = client.batches.get(name=batch_job_name)
        state = batch_job.state.name if hasattr(batch_job.state, 'name') else str(batch_job.state)

        elapsed = int(time.time() - start)
        print(f"  [{elapsed}s] 상태: {state}", flush=True)

        if state in ("JOB_STATE_SUCCEEDED", "SUCCEEDED"):
            print(f"[BATCH] 배치 완료!")
            return batch_job
        elif state in ("JOB_STATE_FAILED", "FAILED"):
            print(f"[BATCH] 배치 실패: {batch_job.error}")
            return batch_job
        elif state in ("JOB_STATE_CANCELLED", "CANCELLED"):
            print(f"[BATCH] 배치 취소됨")
            return batch_job

        time.sleep(interval)

    print(f"[BATCH] polling 타임아웃 ({timeout}초)")
    return None


def download_batch_results(
    batch_job,
    request_map: dict,
    model: str,
    is_batch: bool = True
) -> list:
    """배치 결과 다운로드 + 이미지 추출 + 로컬 저장"""
    api_key = _get_api_key()
    client = genai.Client(api_key=api_key)

    settings = _load_settings()
    if is_batch:
        cost_per_image = settings.get("price_pro_batch", 0.067)
    else:
        cost_per_image = settings.get("price_pro", 0.134)

    # 결과 파일 다운로드
    result_file_name = batch_job.dest.file_name
    print(f"[BATCH] 결과 다운로드: {result_file_name}")
    file_content_bytes = client.files.download(file=result_file_name)
    file_content = file_content_bytes.decode("utf-8")

    today = datetime.now().strftime("%y%m%d")
    out_dir = OUTPUT_DIR / today
    out_dir.mkdir(parents=True, exist_ok=True)

    results = []
    success_count = 0
    fail_count = 0

    for line in file_content.splitlines():
        if not line.strip():
            continue
        parsed = json.loads(line)
        combo_id = parsed.get("key", "unknown")
        meta = request_map.get(combo_id, {})

        if "error" in parsed and parsed["error"]:
            fail_count += 1
            results.append({
                "combo_id": combo_id,
                "status": "failed",
                "error": str(parsed["error"]),
                **meta
            })
            continue

        # 이미지 추출
        response = parsed.get("response", {})
        image_data = None

        for candidate in response.get("candidates", []):
            for part in candidate.get("content", {}).get("parts", []):
                if "inlineData" in part:
                    inline = part["inlineData"]
                    if inline.get("mimeType", "").startswith("image"):
                        image_data = base64.b64decode(inline["data"])
                        break
            if image_data:
                break

        if image_data is None:
            fail_count += 1
            results.append({
                "combo_id": combo_id,
                "status": "failed",
                "error": "응답에 이미지 없음",
                **meta
            })
            continue

        # 이미지 저장
        w1 = meta.get("word1", "")[:10].replace("/", "_")
        w2 = meta.get("word2", "")[:10].replace("/", "_")
        filename = f"{combo_id}_{w1}_{w2}.png"
        file_path = out_dir / filename

        with open(file_path, "wb") as f:
            f.write(image_data)

        resolution = "unknown"
        if HAS_PILLOW:
            try:
                img = Image.open(io.BytesIO(image_data))
                resolution = f"{img.width}x{img.height}"
            except Exception:
                pass

        success_count += 1
        results.append({
            "combo_id": combo_id,
            "word1": meta.get("word1", ""),
            "word1_en": meta.get("word1_en", ""),
            "word2": meta.get("word2", ""),
            "word2_en": meta.get("word2_en", ""),
            "model_used": model,
            "cost": cost_per_image,
            "reference_pins": meta.get("reference_pins", []),
            "reference_boards": meta.get("reference_boards", []),
            "template_id": meta.get("template_id", ""),
            "prompt": meta.get("prompt", ""),
            "api_key_used": "batch",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "file_path": str(file_path),
            "resolution": resolution,
            "drive_uploaded": False,
            "drive_file_id": None,
            "status": "success"
        })

    print(f"[BATCH] 결과 처리 완료: 성공 {success_count}, 실패 {fail_count}")
    return results


def save_batch_state(batch_job_name: str, request_map: dict, model: str):
    """배치 상태 저장 (polling 중단 후 재개용)"""
    state_file = TMP_DIR / "batch_state.json"
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    state = {
        "batch_job_name": batch_job_name,
        "model": model,
        "request_map": request_map,
        "submitted_at": datetime.now(timezone.utc).isoformat()
    }
    with open(state_file, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    print(f"[BATCH] 상태 저장: {state_file}")


def load_batch_state() -> dict | None:
    """저장된 배치 상태 로드"""
    state_file = TMP_DIR / "batch_state.json"
    if not state_file.exists():
        return None
    with open(state_file, encoding="utf-8") as f:
        return json.load(f)


def clear_batch_state():
    """배치 상태 파일 삭제"""
    state_file = TMP_DIR / "batch_state.json"
    state_file.unlink(missing_ok=True)
