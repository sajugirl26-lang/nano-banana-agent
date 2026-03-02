#!/usr/bin/env python3
"""통합 HTML 뷰어 — Gemini + MJ Likes, Drive/CDN URL 이미지, 프롬프트, 날짜필터, 하트, 5열"""
import sys, io

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

KST = timezone(timedelta(hours=9))

BASE_DIR = Path(__file__).parents[4]
OUTPUT_DIR = BASE_DIR / "output" / "images"
METADATA_DIR = OUTPUT_DIR / "metadata"
HTML_DIR = OUTPUT_DIR / "html"
SECRETS_FILE = BASE_DIR / "config" / "secrets.json"
MJ_LIKES_FILE = BASE_DIR / "config" / "mj_likes_final.json"


def _load_firebase_config() -> dict:
    """secrets.json에서 Firebase 설정 로드"""
    default = {
        "apiKey": "", "authDomain": "",
        "databaseURL": "", "projectId": ""
    }
    if SECRETS_FILE.exists():
        with open(SECRETS_FILE, encoding="utf-8") as f:
            s = json.load(f)
        return s.get("firebase", default)
    return default


def _to_kst_date(generated_at: str) -> str:
    """generated_at ISO string -> KST 날짜 (YYYY-MM-DD)"""
    if not generated_at:
        return ""
    try:
        dt = datetime.fromisoformat(generated_at)
        if dt.tzinfo is not None:
            dt = dt.astimezone(KST)
        else:
            dt = dt.replace(tzinfo=KST)
        return dt.strftime("%Y-%m-%d")
    except Exception:
        return generated_at[:10]


def _load_all_metadata() -> list:
    """모든 날짜의 metadata를 합쳐서 반환 (combo_id 중복 제거)"""
    all_entries = []
    if not METADATA_DIR.exists():
        return all_entries
    for meta_file in sorted(METADATA_DIR.glob("*_metadata.json")):
        if "backup" in meta_file.name:
            continue
        try:
            with open(meta_file, encoding="utf-8") as f:
                entries = json.load(f)
            if isinstance(entries, list):
                all_entries.extend(entries)
            else:
                print(f"  [WARN] 메타데이터 형식 오류 (list 아님): {meta_file.name}")
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            print(f"  [WARN] 깨진 메타데이터 건너뜀: {meta_file.name} ({e})")
    # combo_id 기준 중복 제거 (첫 번째 항목 유지)
    seen = set()
    unique = []
    for e in all_entries:
        cid = e.get("combo_id")
        if cid and cid in seen:
            continue
        if cid:
            seen.add(cid)
        unique.append(e)
    if len(unique) < len(all_entries):
        print(f"  [DEDUP] 중복 제거: {len(all_entries)} → {len(unique)} ({len(all_entries) - len(unique)}개 제거)")
    return unique


def _parse_mj_prompt(prompt: str):
    """MJ 프롬프트에서 클린 텍스트 + sref URL 추출"""
    if not prompt:
        return "", []
    sref_urls = []
    sref_match = re.search(r'--sref\s+(.*?)$', prompt)
    if sref_match:
        sref_urls = re.findall(r'https?://\S+', sref_match.group(1))
    clean = re.sub(r'--sref\s+.*$', '', prompt).strip()
    clean = re.sub(r'--\w+\s+\S+', '', clean).strip()
    clean = re.sub(r'\s+', ' ', clean)
    return clean, sref_urls


def _esc(s: str) -> str:
    return (s.replace("&", "&amp;").replace("<", "&lt;")
             .replace(">", "&gt;").replace('"', "&quot;")
             .replace("'", "&#39;"))


def _load_mj_likes() -> list:
    """MJ Likes 데이터를 metadata 호환 형식으로 변환"""
    if not MJ_LIKES_FILE.exists():
        return []
    try:
        with open(MJ_LIKES_FILE, encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return []

    entries = []
    for item in data:
        clean_prompt, sref_urls = _parse_mj_prompt(item.get("prompt", ""))
        entries.append({
            "combo_id": f"mj_{item['id']}_{item.get('pos', '0_0')}",
            "word1": clean_prompt[:80] if clean_prompt else "MJ",
            "word2": "",
            "model_used": "midjourney",
            "cost": 0,
            "reference_pins": sref_urls,
            "prompt": item.get("prompt", ""),
            "generated_at": item.get("time", ""),
            "status": "success",
            "_mj_image_url": item.get("image_url", "") or item.get("thumbnail_url", ""),
            "_mj_thumb_url": item.get("thumbnail_url", ""),
        })
    return entries


def generate_viewer(session_id: str = None, date_str: str = None) -> Path | None:
    if date_str:
        meta_file = METADATA_DIR / f"{date_str}_metadata.json"
        if not meta_file.exists():
            print(f"[ERROR] metadata 없음: {meta_file}")
            return None
        try:
            with open(meta_file, encoding="utf-8") as f:
                entries = json.load(f)
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            print(f"[ERROR] 깨진 metadata: {meta_file} ({e})")
            return None
    else:
        entries = _load_all_metadata()

    # Gemini 항목만 (MJ generated 제외, MJ likes는 별도 로드)
    entries = [e for e in entries if "midjourney" not in e.get("model_used", "").lower()]

    # MJ Likes 병합
    mj_entries = _load_mj_likes()
    entries.extend(mj_entries)
    mj_count = len(mj_entries)

    if not entries:
        print("[ERROR] metadata 항목 없음")
        return None

    HTML_DIR.mkdir(parents=True, exist_ok=True)
    output_file = HTML_DIR / "nano-banana-viewer.html"

    success = [e for e in entries if e.get("status") == "success"]
    total_cost = sum(e.get("cost", 0) for e in entries)

    dates = sorted(set(
        _to_kst_date(e.get("generated_at", "")) for e in entries if e.get("generated_at")
    ) - {""}, reverse=True)

    # 최신순 정렬 (combo_id 순번 기준 — 번호가 클수록 최신)
    def _sort_key(e):
        cid = e.get("combo_id", "")
        # MJ 항목은 generated_at 사용
        if cid.startswith("mj_"):
            return (0, e.get("generated_at", ""))
        # Gemini: combo_id = "YYMMDD_NNNN" → (날짜, 순번) 역순
        parts = cid.split("_", 1)
        if len(parts) == 2 and parts[1].isdigit():
            return (1, parts[0], int(parts[1]))
        return (0, e.get("generated_at", ""))

    entries.sort(key=_sort_key, reverse=True)

    html_cards = ""
    for entry in entries:
        is_mj = entry.get("model_used", "").lower() == "midjourney"
        is_success = entry.get("status") == "success"
        model = entry.get("model_used", "")

        if is_mj:
            model_cls = "model-mj"
            model_label = "MJ"
            img_url = entry.get("_mj_image_url", "")
            data_model = "mj"
        else:
            is_pro = "flash" not in model.lower()
            model_cls = "model-pro" if is_pro else "model-flash"
            model_label = "Pro" if is_pro else "Flash"
            fid = entry.get("drive_file_id")
            img_url = f"https://lh3.googleusercontent.com/d/{fid}" if fid else ""
            data_model = "pro" if is_pro else "flash"

        date_val = _to_kst_date(entry.get("generated_at", ""))
        if is_mj:
            clean_p, _ = _parse_mj_prompt(entry.get("prompt", ""))
            prompt_text = _esc(clean_p)
        else:
            prompt_text = _esc(entry.get("prompt", ""))

        card_cls = "" if is_success else " failed"
        if img_url and is_success:
            esc_url = _esc(img_url)
            img_html = f'<img class="card-img" src="{esc_url}" loading="lazy" onclick="showPinPopup(\'{esc_url}\')" style="cursor:pointer">'
        else:
            img_html = '<div class="card-img-placeholder">No Image</div>'

        pins_html = ""
        for pin_url in entry.get("reference_pins", []):
            if pin_url.startswith("http"):
                esc_pin = _esc(pin_url)
                onerror = ' onerror="this.style.display=\'none\'"' if is_mj else ""
                pins_html += (
                    f'<img class="pin-thumb" src="{esc_pin}" loading="lazy" '
                    f'onclick="showPinPopup(\'{esc_pin}\')"{onerror}>'
                )

        combo_id = entry.get('combo_id', '')
        for ch in ['/', '.', '$', '#', '[', ']']:
            combo_id = combo_id.replace(ch, '_')

        # Words 영역: MJ는 프롬프트, Gemini는 word1 x word2, free는 템플릿명
        w1 = _esc(entry.get('word1', ''))
        w2 = _esc(entry.get('word2', ''))
        tpl_id = entry.get('template_id', '')
        free_label = ''
        if tpl_id and tpl_id.startswith('free_'):
            _free_labels = {
                'free_01': '스타일전이형_01', 'free_02': '스타일전이형_02',
                'free_03': '스타일전이형_03', 'free_04': '스타일전이형_04',
                'free_05': '무드보드확장형_05', 'free_06': '무드보드확장형_06',
                'free_07': '무드보드확장형_07', 'free_08': '무드보드확장형_08',
            }
            free_label = _free_labels.get(tpl_id, tpl_id)
            words_html = f'<span class="w1">{free_label}</span>'
        elif tpl_id and tpl_id.startswith('deep_'):
            free_label = tpl_id
            words_html = f'<span class="w1">{tpl_id}</span>'
        elif w2:
            words_html = f'<span class="w1">{w1}</span> x <span class="w2">{w2}</span>'
        else:
            words_html = f'<span class="w1">{w1}</span>'

        # Meta 영역
        if is_mj:
            meta_html = f'<span class="{model_cls}">MJ</span> · {date_val}'
        else:
            sub_label = "Pro" if is_pro else "Flash"
            sub_cls = "model-pro" if is_pro else "model-flash"
            meta_html = (
                f'<span class="model-nb">NB</span> · <span class="{sub_cls}">{sub_label}</span> · '
                f'${entry.get("cost", 0):.3f} · '
                f'{entry.get("combo_id", "")} · '
                f'{date_val}'
            )

        heart_html = '' if is_mj else '<button class="heart-btn" title="Like">&#9825;</button>'
        mj_liked = 'true' if is_mj else 'false'
        html_cards += f"""
  <div class="card{card_cls}"
       data-id="{combo_id}"
       data-word1="{free_label if free_label else w1}"
       data-word2="{'' if free_label else w2}"
       data-cost="{entry.get('cost', 0)}"
       data-model="{data_model}"
       data-date="{date_val}"
       data-time="{entry.get('generated_at', '')}"
       data-liked="{mj_liked}">
    <div class="card-img-wrap">
      {img_html}
      {heart_html}
    </div>
    <div class="card-body">
      <div class="words">{words_html}</div>
      <div class="meta">{meta_html}</div>
      <div class="prompt">{prompt_text}</div>
      <div class="pins">{pins_html}</div>
      <div class="memo-area" data-memo-id="{combo_id}">
        <div class="memo-text" onclick="editMemo(this)"></div>
        <button class="memo-btn" onclick="editMemo(this.parentElement.querySelector('.memo-text'))" title="메모">&#9998;</button>
      </div>
    </div>
  </div>"""

    date_checkboxes = '<label><input type="checkbox" id="date-all" checked onchange="toggleAllDates(this)"> All</label>'
    date_checkboxes += ''.join(
        f'<label><input type="checkbox" class="date-cb" value="{d}" checked onchange="onDateCbChange()"> {d[5:]}</label>'
        for d in dates
    )

    gemini_count = len(entries) - mj_count

    html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>BOKBOK STUDIO</title>
<style>
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ font-family: -apple-system, sans-serif; background: #0a0a0a; color: #e0e0e0; padding: 20px; }}
h1 {{ font-size: 1.4rem; color: #f0c040; margin-bottom: 8px; }}
.stats {{ background: #1a1a1a; border-radius: 8px; padding: 12px 16px; margin-bottom: 16px; display: flex; gap: 24px; flex-wrap: wrap; }}
.stat {{ text-align: center; }}
.stat-val {{ font-size: 1.5rem; font-weight: bold; color: #f0c040; }}
.stat-lbl {{ font-size: 0.7rem; color: #888; }}
.src-btn {{ padding: 6px 16px; border-radius: 6px; border: 1px solid #333; background: #1a1a1a; color: #666; font-size: 0.85rem; cursor: pointer; transition: all 0.2s; user-select: none; }}
.src-btn:hover {{ border-color: #555; color: #aaa; }}
.src-btn.nb.active {{ border-color: #22c55e; color: #22c55e; background: #0a2a10; }}
.src-btn.mj.active {{ border-color: #a855f7; color: #a855f7; background: #1a0a2a; }}
.src-btn.liked-btn.active {{ border-color: #ff4757; color: #ff4757; background: #2a0a0a; }}
.controls {{ margin-bottom: 16px; display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }}
.controls input, .controls select {{ background: #1a1a1a; border: 1px solid #333; color: #e0e0e0; padding: 6px 10px; border-radius: 6px; font-size: 0.85rem; }}
.controls input[type="text"] {{ width: 180px; }}
.controls label {{ font-size: 0.85rem; color: #aaa; cursor: pointer; }}
.controls label input {{ margin-right: 4px; }}
.date-filters {{ display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }}
.date-filters label {{ font-size: 0.85rem; color: #aaa; cursor: pointer; }}
.date-filters label input {{ margin-right: 3px; }}
#count {{ color: #f0c040; font-size: 0.85rem; font-weight: bold; margin-left: 4px; }}
.grid {{ position: relative; }}
.card {{ background: #1a1a1a; border-radius: 8px; overflow: hidden; }}
.card-img-wrap {{ position: relative; }}
.card-img {{ width: 100%; display: block; background: #222; }}
.card-img-placeholder {{ width: 100%; aspect-ratio: 1; background: #222; display: flex; align-items: center; justify-content: center; color: #444; font-size: 0.75rem; }}
.heart-btn {{ position: absolute; top: 6px; right: 6px; background: rgba(0,0,0,0.5); border: none; color: #888; font-size: 1.5rem; cursor: pointer; border-radius: 50%; width: 40px; height: 40px; display: flex; align-items: center; justify-content: center; transition: color 0.2s, transform 0.15s; line-height: 1; z-index: 10; -webkit-tap-highlight-color: transparent; touch-action: manipulation; }}
.heart-btn:hover {{ color: #ff6b6b; }}
.heart-btn:active {{ transform: scale(0.85); }}
.heart-btn.liked {{ color: #ff4757; }}
.heart-btn.saving {{ pointer-events: none; opacity: 0.6; }}
@keyframes heart-pop {{ 0%{{ transform: scale(1); }} 50%{{ transform: scale(1.3); }} 100%{{ transform: scale(1); }} }}
.heart-btn.pop {{ animation: heart-pop 0.3s ease; }}
.card-body {{ padding: 8px 10px; }}
.words {{ font-size: 0.9rem; font-weight: bold; margin-bottom: 4px; }}
.w1 {{ color: #7eb8f7; }}
.w2 {{ color: #f0c040; }}
.meta {{ font-size: 0.65rem; color: #888; margin-bottom: 4px; }}
.model-pro {{ color: #7eb8f7; }}
.model-flash {{ color: #f09040; }}
.model-nb {{ color: #22c55e; font-weight: bold; }}
.model-mj {{ color: #a855f7; font-weight: bold; }}
.prompt {{ font-size: 0.75rem; color: #999; margin-bottom: 6px; line-height: 1.4; }}
.pins {{ display: flex; gap: 3px; flex-wrap: wrap; }}
.pin-thumb {{ width: 72px; height: 72px; object-fit: cover; border-radius: 4px; cursor: pointer; border: 1px solid #333; }}
.pin-popup-overlay {{ position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.85); display: flex; align-items: center; justify-content: center; z-index: 1000; }}
.pin-popup {{ position: relative; max-width: 90vw; max-height: 90vh; }}
.pin-popup img {{ max-width: 90vw; max-height: 85vh; object-fit: contain; border-radius: 8px; }}
.pin-popup-close {{ position: absolute; top: -12px; right: -12px; background: #333; color: #fff; border: none; font-size: 1.2rem; width: 32px; height: 32px; border-radius: 50%; cursor: pointer; display: flex; align-items: center; justify-content: center; }}
.pin-popup-close:hover {{ background: #ff4757; }}
.memo-area {{ margin-top: 6px; }}
.memo-text {{ font-size: 0.75rem; color: #f0c040; background: #222; border-radius: 4px; padding: 4px 8px; white-space: pre-wrap; word-break: break-word; cursor: pointer; }}
.memo-text:empty {{ display: none; }}
.memo-btn {{ background: none; border: 1px solid #333; color: #666; font-size: 0.75rem; cursor: pointer; padding: 2px 8px; border-radius: 4px; }}
.memo-btn:hover {{ color: #f0c040; border-color: #f0c040; }}
.memo-text:not(:empty) ~ .memo-btn {{ display: none; }}
.memo-edit {{ width: 100%; background: #222; border: 1px solid #f0c040; border-radius: 4px; color: #f0c040; font-size: 0.75rem; padding: 4px 8px; resize: vertical; min-height: 32px; font-family: inherit; }}
.failed {{ opacity: 0.4; }}
.loading-spinner {{ text-align: center; color: #888; padding: 20px; font-size: 0.85rem; }}
</style>
</head>
<body>
<div style="display:flex;align-items:center;gap:12px;margin-bottom:8px">
<h1 style="margin-bottom:0">BOKBOK STUDIO</h1>
<a href="analysis.html" class="src-btn" style="text-decoration:none;padding:4px 12px;font-size:0.75rem;border-color:#f0c040;color:#f0c040;background:#1a1a0a">프롬프트 분석</a>
</div>
<div class="stats">
  <div class="stat"><div class="stat-val">{len(entries)}</div><div class="stat-lbl">Total</div></div>
  <div class="stat"><div class="stat-val">${total_cost:.2f}</div><div class="stat-lbl">Cost</div></div>
  <div class="stat"><div class="stat-val" id="nb-liked-stat">0</div><div class="stat-lbl">NB LIKED</div></div>
  <div class="stat"><div class="stat-val">{mj_count}</div><div class="stat-lbl">MJ LIKED</div></div>
  <div class="stat"><div class="stat-val" id="all-liked-stat">0</div><div class="stat-lbl">ALL LIKED</div></div>
</div>
<div class="controls">
  <input type="text" id="search" placeholder="Search..." oninput="filterCards()">
  <span class="date-filters">{date_checkboxes}</span>
  <select id="sort" onchange="sortCards()">
    <option value="newest">Newest</option>
    <option value="oldest">Oldest</option>
    <option value="cost-high">Cost High</option>
    <option value="cost-low">Cost Low</option>
  </select>
  <select id="model-filter" onchange="filterCards()">
    <option value="all">All models</option>
    <option value="pro">Pro</option>
    <option value="flash">Flash</option>
  </select>
  <button id="filter-nb" class="src-btn nb active" onclick="toggleSource('nb')">NanoBanana</button>
  <button id="filter-mj" class="src-btn mj active" onclick="toggleSource('mj')">Midjourney</button>
  <button id="filter-liked" class="src-btn liked-btn" onclick="toggleLiked()">Liked Only</button>
  <span id="count"></span>
</div>
<div class="grid" id="grid">
{html_cards}
</div>
<div id="scroll-sentinel" style="height:1px"></div>
<script src="https://www.gstatic.com/firebasejs/9.23.0/firebase-app-compat.js"></script>
<script src="https://www.gstatic.com/firebasejs/9.23.0/firebase-database-compat.js"></script>
<script src="https://www.gstatic.com/firebasejs/9.23.0/firebase-auth-compat.js"></script>
<script>
firebase.initializeApp({{
  apiKey: "{_load_firebase_config()['apiKey']}",
  authDomain: "{_load_firebase_config()['authDomain']}",
  databaseURL: "{_load_firebase_config()['databaseURL']}",
  projectId: "{_load_firebase_config()['projectId']}"
}});
const db = firebase.database();
const likesRef = db.ref('likes');
const memosRef = db.ref('memos');

const grid = document.getElementById('grid');
const cards = [...grid.children];
const likedSet = new Set();
const cardMap = {{}};
const oldKeyToNew = {{}};
let firebaseOk = false;
const LS_LIKES = 'bokbok_likes';
const LS_MEMOS = 'bokbok_memos';
const pendingWrites = new Map(); // key → true(like) or false(unlike)

function getLocalLikes() {{
  try {{ return JSON.parse(localStorage.getItem(LS_LIKES) || '{{}}'); }} catch(e) {{ return {{}}; }}
}}
function saveLocalLikes(data) {{
  try {{ localStorage.setItem(LS_LIKES, JSON.stringify(data)); }} catch(e) {{}}
}}
function getLocalMemos() {{
  try {{ return JSON.parse(localStorage.getItem(LS_MEMOS) || '{{}}'); }} catch(e) {{ return {{}}; }}
}}
function saveLocalMemos(data) {{
  try {{ localStorage.setItem(LS_MEMOS, JSON.stringify(data)); }} catch(e) {{}}
}}

cards.forEach(c => {{
  const newKey = c.dataset.id;
  c.dataset.key = newKey;
  if (newKey) cardMap[newKey] = c;
  const oldKey = (c.dataset.word1 + '_' + c.dataset.word2 + '_' + c.dataset.time).replace(/[.#$/\\[\\]]/g, '_');
  oldKeyToNew[oldKey] = newKey;
}});

function setHeartUI(card, liked) {{
  card.dataset.liked = liked ? 'true' : 'false';
  const hb = card.querySelector('.heart-btn');
  if (hb) {{
    hb.classList.toggle('liked', liked);
    hb.innerHTML = liked ? '\\u2665' : '\\u2661';
  }}
}}

function applyLikesData(data) {{
  likedSet.clear();
  cards.forEach(c => {{
    if (c.dataset.model === 'mj') return;
    const k = c.dataset.key;
    // pendingWrites 중인 키는 optimistic update 방향대로 보존
    if (pendingWrites.has(k)) {{
      if (pendingWrites.get(k)) likedSet.add(k);
      return;
    }}
    c.dataset.liked = 'false';
    const hb = c.querySelector('.heart-btn');
    if (hb) {{ hb.classList.remove('liked'); hb.innerHTML = '\\u2661'; }}
  }});
  Object.keys(data).forEach(key => {{
    let target = cardMap[key];
    if (!target && oldKeyToNew[key]) target = cardMap[oldKeyToNew[key]];
    if (target && !pendingWrites.has(target.dataset.key || key)) {{
      const k = target.dataset.key;
      likedSet.add(k);
      setHeartUI(target, true);
    }}
  }});
  updateLikedCounts();
  if (document.getElementById('filter-liked').classList.contains('active')) filterCards(false);
}}

function setupFirebaseListeners() {{
  let migrated = false;
  likesRef.on('value', snap => {{
    firebaseOk = true;
    const data = snap.val() || {{}};
    saveLocalLikes(data);
    applyLikesData(data);
    const toMigrate = {{}};
    Object.keys(data).forEach(key => {{
      if (!cardMap[key] && oldKeyToNew[key] && cardMap[oldKeyToNew[key]]) {{
        if (!migrated) toMigrate[key] = oldKeyToNew[key];
      }}
    }});
    if (!migrated && Object.keys(toMigrate).length > 0) {{
      migrated = true;
      const updates = {{}};
      Object.entries(toMigrate).forEach(([oldK, newK]) => {{
        updates[oldK] = null;
        updates[newK] = true;
      }});
      likesRef.update(updates);
    }}
  }}, err => {{
    console.warn('[LIKES] Firebase read failed:', err.message);
    applyLikesData(getLocalLikes());
  }});
  memosRef.on('value', snap => {{
    memoData = snap.val() || {{}};
    saveLocalMemos(memoData);
    applyMemos();
  }}, err => {{
    console.warn('[MEMOS] Firebase read failed:', err.message);
    memoData = getLocalMemos();
    applyMemos();
  }});
}}

// 익명 인증 시도 후 리스너 설정
firebase.auth().signInAnonymously()
  .then(() => {{ setupFirebaseListeners(); }})
  .catch(err => {{
    console.warn('[AUTH] Anonymous auth failed:', err.message, '- trying without auth');
    setupFirebaseListeners();
  }});

// 3초 내 Firebase 응답 없으면 localStorage fallback
setTimeout(() => {{
  if (!firebaseOk) {{
    console.warn('[FALLBACK] Firebase timeout - using localStorage');
    applyLikesData(getLocalLikes());
    memoData = getLocalMemos();
    applyMemos();
  }}
}}, 3000);

// 이벤트 위임으로 하트 클릭 처리
document.getElementById('grid').addEventListener('click', function(e) {{
  const btn = e.target.closest('.heart-btn');
  if (!btn) return;
  e.stopPropagation();
  e.preventDefault();
  toggleHeart(btn);
}});

function toggleHeart(btn) {{
  const card = btn.closest('.card');
  const key = card.dataset.key;
  if (!key) return;

  // 이미 저장 중이면 무시 (중복 클릭 방지)
  if (pendingWrites.has(key)) return;

  const isLiked = card.dataset.liked === 'true';
  const newLiked = !isLiked;

  // pendingWrites에 방향과 함께 등록 (Firebase listener가 덮어쓰지 못하게)
  pendingWrites.set(key, newLiked);
  btn.classList.add('saving');

  // 즉시 UI 반영 (optimistic update)
  setHeartUI(card, newLiked);
  if (newLiked) {{ likedSet.add(key); btn.classList.add('pop'); }}
  else likedSet.delete(key);
  updateLikedCounts();

  // localStorage 저장
  const local = getLocalLikes();
  if (newLiked) local[key] = true; else delete local[key];
  saveLocalLikes(local);

  // Firebase 저장 시도
  likesRef.child(key).set(newLiked ? true : null)
    .then(() => {{
      pendingWrites.delete(key);
      btn.classList.remove('saving');
      btn.classList.remove('pop');
    }})
    .catch(err => {{
      console.warn('[HEART] Firebase write failed:', err.message);
      pendingWrites.delete(key);
      btn.classList.remove('saving');
      btn.classList.remove('pop');
      // Firebase 실패 시 rollback
      setHeartUI(card, isLiked);
      if (isLiked) likedSet.add(key); else likedSet.delete(key);
      updateLikedCounts();
      const rl = getLocalLikes();
      if (isLiked) rl[key] = true; else delete rl[key];
      saveLocalLikes(rl);
    }});
}}
function toggleAllDates(allCb) {{
  document.querySelectorAll('.date-cb').forEach(cb => {{ cb.checked = allCb.checked; }});
  filterCards();
}}
function onDateCbChange() {{
  const cbs = document.querySelectorAll('.date-cb');
  const allChecked = [...cbs].every(cb => cb.checked);
  document.getElementById('date-all').checked = allChecked;
  filterCards();
}}
function getSelectedDates() {{
  const cbs = document.querySelectorAll('.date-cb');
  const selected = [];
  cbs.forEach(cb => {{ if (cb.checked) selected.push(cb.value); }});
  return selected;
}}
const PAGE_SIZE = 50;
let currentPage = 1;
let filteredCards = [];

function toggleSource(src) {{
  const btn = document.getElementById('filter-' + src);
  btn.classList.toggle('active');
  filterCards();
}}
function toggleLiked() {{
  const btn = document.getElementById('filter-liked');
  btn.classList.toggle('active');
  filterCards();
}}
function updateLikedCounts() {{
  const nbLiked = cards.filter(c => c.dataset.liked === 'true' && c.dataset.model !== 'mj').length;
  const mjLiked = cards.filter(c => c.dataset.model === 'mj').length;
  document.getElementById('nb-liked-stat').textContent = nbLiked;
  document.getElementById('all-liked-stat').textContent = nbLiked + mjLiked;
}}
function filterCards(resetPage) {{
  const q = document.getElementById('search').value.toLowerCase();
  const dates = getSelectedDates();
  const nbOn = document.getElementById('filter-nb').classList.contains('active');
  const mjOn = document.getElementById('filter-mj').classList.contains('active');
  const lo = document.getElementById('filter-liked').classList.contains('active');
  const mf = document.getElementById('model-filter').value;
  const prevLen = filteredCards.length;
  filteredCards = cards.filter(c => {{
    const w = (c.dataset.word1 + ' ' + c.dataset.word2).toLowerCase();
    const p = (c.querySelector('.prompt')?.textContent || '').toLowerCase();
    const isMj = c.dataset.model === 'mj';
    const srcOk = (isMj && mjOn) || (!isMj && nbOn);
    const modelOk = mf === 'all' || isMj || c.dataset.model === mf;
    const dateOk = !c.dataset.date || dates.includes(c.dataset.date);
    return srcOk
      && modelOk
      && (w.includes(q) || p.includes(q))
      && dateOk
      && (!lo || c.dataset.liked === 'true');
  }});
  if (resetPage !== false && filteredCards.length !== prevLen) currentPage = 1;
  updateLikedCounts();
  document.getElementById('count').textContent = filteredCards.length;
  renderPage();
}}
function getColCount() {{
  const w = window.innerWidth;
  if (w <= 640) return 2;
  if (w <= 1024) return 3;
  if (w <= 1440) return 4;
  if (w <= 1920) return 5;
  if (w <= 2560) return 6;
  return 7;
}}
function layoutCards(visible, colCount, colWidth, gap) {{
  const colHeights = new Array(colCount).fill(0);
  visible.forEach((card, i) => {{
    const col = i % colCount;
    const h = card.offsetHeight;
    card.style.cssText = 'position:absolute;width:' + colWidth + 'px;left:' + (col * (colWidth + gap)) + 'px;top:' + colHeights[col] + 'px';
    colHeights[col] += h + gap;
  }});
  grid.style.height = Math.max(...colHeights) + 'px';
}}
let _relayoutTimer;
function renderPage(isAppend) {{
  const end = currentPage * PAGE_SIZE;
  const visible = filteredCards.slice(0, end);
  const gap = 12;
  const colCount = getColCount();
  const gridWidth = grid.clientWidth || grid.parentElement.clientWidth;
  const colWidth = (gridWidth - gap * (colCount - 1)) / colCount;
  if (!isAppend) {{
    while (grid.firstChild) grid.removeChild(grid.firstChild);
    visible.forEach(card => {{
      card.style.cssText = 'position:absolute;visibility:hidden;width:' + colWidth + 'px';
      grid.appendChild(card);
    }});
  }} else {{
    const inGrid = new Set([...grid.children]);
    visible.forEach(card => {{
      if (!inGrid.has(card)) {{
        card.style.cssText = 'position:absolute;visibility:hidden;width:' + colWidth + 'px';
        grid.appendChild(card);
      }} else {{
        card.style.width = colWidth + 'px';
      }}
    }});
  }}
  layoutCards(visible, colCount, colWidth, gap);
  let pending = 0;
  visible.forEach(card => {{
    const img = card.querySelector('.card-img');
    if (img && !img.complete) {{
      pending++;
      img.onload = img.onerror = () => {{
        pending--;
        clearTimeout(_relayoutTimer);
        _relayoutTimer = setTimeout(() => layoutCards(visible, colCount, colWidth, gap), pending > 0 ? 50 : 0);
      }};
    }}
  }});
}}
function loadMore() {{
  currentPage++;
  renderPage(true);
}}
let resizeTimer;
window.addEventListener('resize', () => {{
  clearTimeout(resizeTimer);
  resizeTimer = setTimeout(renderPage, 200);
}});
function showPinPopup(url) {{
  const overlay = document.createElement('div');
  overlay.className = 'pin-popup-overlay';
  overlay.innerHTML = '<div class="pin-popup"><button class="pin-popup-close" onclick="this.closest(\\'.pin-popup-overlay\\').remove()">X</button><img src="' + url + '"></div>';
  overlay.addEventListener('click', function(e) {{ if (e.target === overlay) overlay.remove(); }});
  document.body.appendChild(overlay);
}}
let memoData = {{}};
function applyMemos() {{
  cards.forEach(c => {{
    const area = c.querySelector('.memo-area');
    if (!area) return;
    const mid = area.dataset.memoId;
    const textEl = area.querySelector('.memo-text');
    if (memoData[mid]) {{
      textEl.textContent = memoData[mid];
    }} else {{
      textEl.textContent = '';
    }}
  }});
}}
function editMemo(textEl) {{
  const area = textEl.closest('.memo-area');
  const mid = area.dataset.memoId;
  const current = textEl.textContent || '';
  const ta = document.createElement('textarea');
  ta.className = 'memo-edit';
  ta.value = current;
  ta.placeholder = '메모 입력...';
  textEl.style.display = 'none';
  area.querySelector('.memo-btn').style.display = 'none';
  area.appendChild(ta);
  ta.focus();
  let saved = false;
  function save() {{
    if (saved) return;
    saved = true;
    const val = ta.value.trim();
    ta.remove();
    textEl.textContent = val;
    textEl.style.display = '';
    const btn = area.querySelector('.memo-btn');
    if (btn) btn.style.display = '';
    // localStorage 저장
    const localM = getLocalMemos();
    if (val) {{ localM[mid] = val; }} else {{ delete localM[mid]; }}
    saveLocalMemos(localM);
    // Firebase 저장 시도
    if (val) {{
      memosRef.child(mid).set(val).catch(err => console.warn('[MEMO] Firebase write failed:', err.message));
    }} else {{
      memosRef.child(mid).remove().catch(err => console.warn('[MEMO] Firebase remove failed:', err.message));
    }}
  }}
  ta.addEventListener('blur', save);
  ta.addEventListener('keydown', function(e) {{
    if (e.key === 'Enter' && !e.shiftKey) {{ e.preventDefault(); save(); }}
    if (e.key === 'Escape') {{ ta.value = current; save(); }}
  }});
}}
function sortCards() {{
  const s = document.getElementById('sort').value;
  cards.sort((a, b) => {{
    if (s === 'cost-high') return parseFloat(b.dataset.cost) - parseFloat(a.dataset.cost);
    if (s === 'cost-low') return parseFloat(a.dataset.cost) - parseFloat(b.dataset.cost);
    if (s === 'oldest') return (a.dataset.time || '').localeCompare(b.dataset.time || '');
    return (b.dataset.time || '').localeCompare(a.dataset.time || '');
  }});
  filterCards();
}}
filterCards();
// Infinite scroll
(function() {{
  const sentinel = document.getElementById('scroll-sentinel');
  if (!sentinel) return;
  const obs = new IntersectionObserver(entries => {{
    if (entries[0].isIntersecting && currentPage * PAGE_SIZE < filteredCards.length) {{
      loadMore();
    }}
  }}, {{ rootMargin: '800px' }});
  obs.observe(sentinel);
}})();
</script>
</body>
</html>"""

    with open(output_file, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"[OK] HTML 뷰어 생성: {output_file} (Gemini: {gemini_count}, MJ: {mj_count})")
    return output_file


if __name__ == "__main__":
    generate_viewer()
