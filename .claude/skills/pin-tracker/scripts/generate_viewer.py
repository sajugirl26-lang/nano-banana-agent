#!/usr/bin/env python3
"""통합 HTML 뷰어 — 모든 날짜, Drive URL 이미지, 프롬프트, 날짜필터, 하트, 5열"""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

KST = timezone(timedelta(hours=9))

BASE_DIR = Path(__file__).parents[4]
OUTPUT_DIR = BASE_DIR / "output" / "images"
METADATA_DIR = OUTPUT_DIR / "metadata"
HTML_DIR = OUTPUT_DIR / "html"
SECRETS_FILE = BASE_DIR / "config" / "secrets.json"


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
    """모든 날짜의 metadata를 합쳐서 반환"""
    all_entries = []
    if not METADATA_DIR.exists():
        return all_entries
    for meta_file in sorted(METADATA_DIR.glob("*_metadata.json")):
        if "backup" in meta_file.name:
            continue
        with open(meta_file, encoding="utf-8") as f:
            entries = json.load(f)
        all_entries.extend(entries)
    return all_entries


def generate_viewer(session_id: str = None, date_str: str = None) -> Path | None:
    if date_str:
        meta_file = METADATA_DIR / f"{date_str}_metadata.json"
        if not meta_file.exists():
            print(f"[ERROR] metadata 없음: {meta_file}")
            return None
        with open(meta_file, encoding="utf-8") as f:
            entries = json.load(f)
    else:
        entries = _load_all_metadata()

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

    # 최신순 정렬 (generated_at 역순, 없으면 combo_id 역순)
    entries.sort(key=lambda e: e.get("generated_at", e.get("combo_id", "")), reverse=True)

    html_cards = ""
    for entry in entries:
        is_success = entry.get("status") == "success"
        model = entry.get("model_used", "")
        is_pro = "flash" not in model.lower()
        model_cls = "model-pro" if is_pro else "model-flash"
        model_label = "Pro" if is_pro else "Flash"

        fid = entry.get("drive_file_id")
        img_url = f"https://lh3.googleusercontent.com/d/{fid}" if fid else ""
        date_val = _to_kst_date(entry.get("generated_at", ""))
        prompt_text = entry.get("prompt", "")

        card_cls = "" if is_success else " failed"
        if img_url and is_success:
            img_html = f'<img class="card-img" src="{img_url}" loading="lazy" onclick="showPinPopup(\'{img_url}\')" style="cursor:pointer">'
        else:
            img_html = '<div class="card-img-placeholder">No Image</div>'

        pins_html = ""
        for pin_url in entry.get("reference_pins", []):
            if pin_url.startswith("http"):
                pins_html += (
                    f'<img class="pin-thumb" src="{pin_url}" loading="lazy" '
                    f'onclick="showPinPopup(\'{pin_url}\')">'
                )

        html_cards += f"""
  <div class="card{card_cls}"
       data-word1="{entry.get('word1','')}"
       data-word2="{entry.get('word2','')}"
       data-cost="{entry.get('cost', 0)}"
       data-model="{'pro' if is_pro else 'flash'}"
       data-date="{date_val}"
       data-time="{entry.get('generated_at', '')}"
       data-liked="false">
    <div class="card-img-wrap">
      {img_html}
      <button class="heart-btn" onclick="toggleHeart(this)" title="Like">&#9825;</button>
    </div>
    <div class="card-body">
      <div class="words">
        <span class="w1">{entry.get('word1','')}</span> x
        <span class="w2">{entry.get('word2','')}</span>
      </div>
      <div class="meta">
        <span class="{model_cls}">{model_label}</span> ·
        ${entry.get('cost', 0):.3f} ·
        {entry.get('combo_id', '')} ·
        {date_val}
      </div>
      <div class="prompt">{prompt_text}</div>
      <div class="pins">{pins_html}</div>
    </div>
  </div>"""

    date_checkboxes = '<label><input type="checkbox" id="date-all" checked onchange="toggleAllDates(this)"> All</label>'
    date_checkboxes += ''.join(
        f'<label><input type="checkbox" class="date-cb" value="{d}" checked onchange="onDateCbChange()"> {d[5:]}</label>'
        for d in dates
    )

    html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Nano Banana Viewer</title>
<style>
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ font-family: -apple-system, sans-serif; background: #0a0a0a; color: #e0e0e0; padding: 20px; }}
h1 {{ font-size: 1.4rem; color: #f0c040; margin-bottom: 8px; }}
.stats {{ background: #1a1a1a; border-radius: 8px; padding: 12px 16px; margin-bottom: 16px; display: flex; gap: 24px; flex-wrap: wrap; }}
.stat {{ text-align: center; }}
.stat-val {{ font-size: 1.5rem; font-weight: bold; color: #f0c040; }}
.stat-lbl {{ font-size: 0.7rem; color: #888; }}
.controls {{ margin-bottom: 16px; display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }}
.controls input, .controls select {{ background: #1a1a1a; border: 1px solid #333; color: #e0e0e0; padding: 6px 10px; border-radius: 6px; font-size: 0.85rem; }}
.controls input[type="text"] {{ width: 180px; }}
.controls label {{ font-size: 0.85rem; color: #aaa; cursor: pointer; }}
.controls label input {{ margin-right: 4px; }}
.date-filters {{ display: flex; gap: 8px; align-items: center; }}
.date-filters label {{ font-size: 0.85rem; color: #aaa; cursor: pointer; }}
.date-filters label input {{ margin-right: 3px; }}
#count {{ color: #888; font-size: 0.8rem; }}
.grid {{ display: grid; grid-template-columns: repeat(5, 1fr); gap: 12px; }}
.card {{ background: #1a1a1a; border-radius: 8px; overflow: hidden; }}
.card-img-wrap {{ position: relative; }}
.card-img {{ width: 100%; aspect-ratio: 1; object-fit: cover; display: block; background: #222; }}
.card-img-placeholder {{ width: 100%; aspect-ratio: 1; background: #222; display: flex; align-items: center; justify-content: center; color: #444; font-size: 0.75rem; }}
.heart-btn {{ position: absolute; top: 6px; right: 6px; background: rgba(0,0,0,0.5); border: none; color: #888; font-size: 1.4rem; cursor: pointer; border-radius: 50%; width: 32px; height: 32px; display: flex; align-items: center; justify-content: center; transition: color 0.2s; line-height: 1; }}
.heart-btn:hover {{ color: #ff6b6b; }}
.heart-btn.liked {{ color: #ff4757; }}
.card-body {{ padding: 8px 10px; }}
.words {{ font-size: 0.9rem; font-weight: bold; margin-bottom: 4px; }}
.w1 {{ color: #7eb8f7; }}
.w2 {{ color: #f0c040; }}
.meta {{ font-size: 0.65rem; color: #888; margin-bottom: 4px; }}
.model-pro {{ color: #7eb8f7; }}
.model-flash {{ color: #f09040; }}
.prompt {{ font-size: 0.75rem; color: #999; margin-bottom: 6px; line-height: 1.4; }}
.pins {{ display: flex; gap: 3px; flex-wrap: wrap; }}
.pin-thumb {{ width: 72px; height: 72px; object-fit: cover; border-radius: 4px; cursor: pointer; border: 1px solid #333; }}
.pin-popup-overlay {{ position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.85); display: flex; align-items: center; justify-content: center; z-index: 1000; }}
.pin-popup {{ position: relative; max-width: 90vw; max-height: 90vh; }}
.pin-popup img {{ max-width: 90vw; max-height: 85vh; object-fit: contain; border-radius: 8px; }}
.pin-popup-close {{ position: absolute; top: -12px; right: -12px; background: #333; color: #fff; border: none; font-size: 1.2rem; width: 32px; height: 32px; border-radius: 50%; cursor: pointer; display: flex; align-items: center; justify-content: center; }}
.pin-popup-close:hover {{ background: #ff4757; }}
.failed {{ opacity: 0.4; }}
.load-more-btn {{ display: block; margin: 20px auto; padding: 10px 40px; background: #333; color: #e0e0e0; border: 1px solid #555; border-radius: 8px; font-size: 0.9rem; cursor: pointer; }}
.load-more-btn:hover {{ background: #444; }}
@media (max-width: 1200px) {{ .grid {{ grid-template-columns: repeat(3, 1fr); }} }}
@media (max-width: 768px) {{ .grid {{ grid-template-columns: repeat(2, 1fr); }} }}
</style>
</head>
<body>
<h1>Nano Banana Viewer</h1>
<div class="stats">
  <div class="stat"><div class="stat-val">{len(entries)}</div><div class="stat-lbl">Total</div></div>
  <div class="stat"><div class="stat-val">{len(success)}</div><div class="stat-lbl">Success</div></div>
  <div class="stat"><div class="stat-val">{len(entries)-len(success)}</div><div class="stat-lbl">Failed</div></div>
  <div class="stat"><div class="stat-val">${total_cost:.2f}</div><div class="stat-lbl">Cost</div></div>
</div>
<div class="controls">
  <input type="text" id="search" placeholder="Search..." oninput="filterCards()">
  <span class="date-filters">{date_checkboxes}</span>
  <select id="model-filter" onchange="filterCards()">
    <option value="all">All models</option>
    <option value="pro">Pro</option>
    <option value="flash">Flash</option>
  </select>
  <select id="sort" onchange="sortCards()">
    <option value="newest">Newest</option>
    <option value="oldest">Oldest</option>
    <option value="cost-high">Cost High</option>
    <option value="cost-low">Cost Low</option>
  </select>
  <label><input type="checkbox" id="liked-only" onchange="filterCards()"> Liked only</label>
  <span id="count"></span>
</div>
<div class="grid" id="grid">
{html_cards}
</div>
<button id="load-more" class="load-more-btn" onclick="loadMore()" style="display:none">Load More</button>
<script src="https://www.gstatic.com/firebasejs/9.23.0/firebase-app-compat.js"></script>
<script src="https://www.gstatic.com/firebasejs/9.23.0/firebase-database-compat.js"></script>
<script>
firebase.initializeApp({{
  apiKey: "{_load_firebase_config()['apiKey']}",
  authDomain: "{_load_firebase_config()['authDomain']}",
  databaseURL: "{_load_firebase_config()['databaseURL']}",
  projectId: "{_load_firebase_config()['projectId']}"
}});
const db = firebase.database();
const likesRef = db.ref('likes');

const grid = document.getElementById('grid');
const cards = [...grid.children];
const likedSet = new Set();
const cardMap = {{}};

cards.forEach(c => {{
  const key = (c.dataset.word1 + '_' + c.dataset.word2 + '_' + c.dataset.time).replace(/[.#$/\\[\\]]/g, '_');
  c.dataset.key = key;
  cardMap[key] = c;
}});

// Firebase에서 하트 데이터 실시간 수신
likesRef.on('value', snap => {{
  const data = snap.val() || {{}};
  likedSet.clear();
  cards.forEach(c => {{
    c.dataset.liked = 'false';
    c.querySelector('.heart-btn').classList.remove('liked');
    c.querySelector('.heart-btn').innerHTML = '\\u2661';
  }});
  Object.keys(data).forEach(key => {{
    if (data[key] && cardMap[key]) {{
      likedSet.add(key);
      cardMap[key].dataset.liked = 'true';
      cardMap[key].querySelector('.heart-btn').classList.add('liked');
      cardMap[key].querySelector('.heart-btn').innerHTML = '\\u2665';
    }}
  }});
  filterCards();
}});

function toggleHeart(btn) {{
  const card = btn.closest('.card');
  const key = card.dataset.key;
  const isLiked = card.dataset.liked === 'true';
  likesRef.child(key).set(isLiked ? null : true);
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

function filterCards() {{
  const q = document.getElementById('search').value.toLowerCase();
  const dates = getSelectedDates();
  const mf = document.getElementById('model-filter').value;
  const lo = document.getElementById('liked-only').checked;
  filteredCards = cards.filter(c => {{
    const w = (c.dataset.word1 + ' ' + c.dataset.word2).toLowerCase();
    return w.includes(q)
      && (dates.length === 0 || dates.includes(c.dataset.date))
      && (mf === 'all' || c.dataset.model === mf)
      && (!lo || c.dataset.liked === 'true');
  }});
  currentPage = 1;
  renderPage();
}}
function renderPage() {{
  const end = currentPage * PAGE_SIZE;
  cards.forEach(c => c.style.display = 'none');
  filteredCards.slice(0, end).forEach(c => c.style.display = '');
  document.getElementById('count').textContent = Math.min(end, filteredCards.length) + '/' + filteredCards.length + ' shown';
  const btn = document.getElementById('load-more');
  btn.style.display = end < filteredCards.length ? '' : 'none';
}}
function loadMore() {{
  currentPage++;
  renderPage();
}}
function showPinPopup(url) {{
  const overlay = document.createElement('div');
  overlay.className = 'pin-popup-overlay';
  overlay.innerHTML = '<div class="pin-popup"><button class="pin-popup-close" onclick="this.closest(\\'.pin-popup-overlay\\').remove()">X</button><img src="' + url + '"></div>';
  overlay.addEventListener('click', function(e) {{ if (e.target === overlay) overlay.remove(); }});
  document.body.appendChild(overlay);
}}
function sortCards() {{
  const s = document.getElementById('sort').value;
  [...cards].sort((a, b) => {{
    if (s === 'cost-high') return parseFloat(b.dataset.cost) - parseFloat(a.dataset.cost);
    if (s === 'cost-low') return parseFloat(a.dataset.cost) - parseFloat(b.dataset.cost);
    if (s === 'oldest') return a.dataset.time.localeCompare(b.dataset.time);
    return b.dataset.time.localeCompare(a.dataset.time);
  }}).forEach(c => grid.appendChild(c));
}}
filterCards();
</script>
</body>
</html>"""

    with open(output_file, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"[OK] HTML 뷰어 생성: {output_file}")
    return output_file


if __name__ == "__main__":
    generate_viewer()
