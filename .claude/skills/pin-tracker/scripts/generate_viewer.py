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
        try:
            with open(meta_file, encoding="utf-8") as f:
                entries = json.load(f)
            if isinstance(entries, list):
                all_entries.extend(entries)
            else:
                print(f"  [WARN] 메타데이터 형식 오류 (list 아님): {meta_file.name}")
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            print(f"  [WARN] 깨진 메타데이터 건너뜀: {meta_file.name} ({e})")
    return all_entries


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

    # MJ 항목 제외 (미드저니는 웹 뷰어에 표시하지 않음)
    entries = [e for e in entries if "midjourney" not in e.get("model_used", "").lower()]

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

        combo_id = entry.get('combo_id', '').replace('/', '_').replace('.', '_')
        html_cards += f"""
  <div class="card{card_cls}"
       data-id="{combo_id}"
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
.controls {{ margin-bottom: 16px; display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }}
.controls input, .controls select {{ background: #1a1a1a; border: 1px solid #333; color: #e0e0e0; padding: 6px 10px; border-radius: 6px; font-size: 0.85rem; }}
.controls input[type="text"] {{ width: 180px; }}
.controls label {{ font-size: 0.85rem; color: #aaa; cursor: pointer; }}
.controls label input {{ margin-right: 4px; }}
.date-filters {{ display: flex; gap: 8px; align-items: center; }}
.date-filters label {{ font-size: 0.85rem; color: #aaa; cursor: pointer; }}
.date-filters label input {{ margin-right: 3px; }}
#count {{ color: #888; font-size: 0.8rem; }}
.grid {{ display: flex; gap: 12px; align-items: flex-start; }}
.grid-col {{ flex: 1; display: flex; flex-direction: column; gap: 12px; min-width: 0; }}
.card {{ background: #1a1a1a; border-radius: 8px; overflow: hidden; }}
.card-img-wrap {{ position: relative; }}
.card-img {{ width: 100%; display: block; background: #222; }}
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
.memo-area {{ margin-top: 6px; }}
.memo-text {{ font-size: 0.75rem; color: #f0c040; background: #222; border-radius: 4px; padding: 4px 8px; white-space: pre-wrap; word-break: break-word; cursor: pointer; }}
.memo-text:empty {{ display: none; }}
.memo-btn {{ background: none; border: 1px solid #333; color: #666; font-size: 0.75rem; cursor: pointer; padding: 2px 8px; border-radius: 4px; }}
.memo-btn:hover {{ color: #f0c040; border-color: #f0c040; }}
.memo-text:not(:empty) ~ .memo-btn {{ display: none; }}
.memo-edit {{ width: 100%; background: #222; border: 1px solid #f0c040; border-radius: 4px; color: #f0c040; font-size: 0.75rem; padding: 4px 8px; resize: vertical; min-height: 32px; font-family: inherit; }}
.failed {{ opacity: 0.4; }}
.load-more-btn {{ display: block; margin: 20px auto; padding: 10px 40px; background: #333; color: #e0e0e0; border: 1px solid #555; border-radius: 8px; font-size: 0.9rem; cursor: pointer; }}
.load-more-btn:hover {{ background: #444; }}
</style>
</head>
<body>
<h1>BOKBOK STUDIO</h1>
<div class="stats">
  <div class="stat"><div class="stat-val">{len(entries)}</div><div class="stat-lbl">Total</div></div>
  <div class="stat"><div class="stat-val" id="liked-stat">0</div><div class="stat-lbl">Liked</div></div>
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
const memosRef = db.ref('memos');

const grid = document.getElementById('grid');
const cards = [...grid.children];
const likedSet = new Set();
const cardMap = {{}};
const oldKeyToNew = {{}};

cards.forEach(c => {{
  const newKey = c.dataset.id;
  c.dataset.key = newKey;
  if (newKey) cardMap[newKey] = c;
  // 이전 키 형식 매핑 (word1_word2_time → combo_id)
  const oldKey = (c.dataset.word1 + '_' + c.dataset.word2 + '_' + c.dataset.time).replace(/[.#$/\\[\\]]/g, '_');
  oldKeyToNew[oldKey] = newKey;
}});

// Firebase에서 하트 데이터 실시간 수신 + 이전 키 마이그레이션
let migrated = false;
likesRef.on('value', snap => {{
  const data = snap.val() || {{}};
  likedSet.clear();
  cards.forEach(c => {{
    c.dataset.liked = 'false';
    c.querySelector('.heart-btn').classList.remove('liked');
    c.querySelector('.heart-btn').innerHTML = '\\u2661';
  }});
  const toMigrate = {{}};
  Object.keys(data).forEach(key => {{
    let target = cardMap[key];
    if (target) {{
      // 새 키 형식 매칭
      likedSet.add(key);
      target.dataset.liked = 'true';
      target.querySelector('.heart-btn').classList.add('liked');
      target.querySelector('.heart-btn').innerHTML = '\\u2665';
    }} else if (oldKeyToNew[key] && cardMap[oldKeyToNew[key]]) {{
      // 이전 키 → 새 키로 마이그레이션
      const nk = oldKeyToNew[key];
      likedSet.add(nk);
      cardMap[nk].dataset.liked = 'true';
      cardMap[nk].querySelector('.heart-btn').classList.add('liked');
      cardMap[nk].querySelector('.heart-btn').innerHTML = '\\u2665';
      if (!migrated) toMigrate[key] = nk;
    }}
  }});
  // 이전 키를 새 키로 한번만 마이그레이션
  if (!migrated && Object.keys(toMigrate).length > 0) {{
    migrated = true;
    const updates = {{}};
    Object.entries(toMigrate).forEach(([oldK, newK]) => {{
      updates[oldK] = null;
      updates[newK] = true;
    }});
    likesRef.update(updates);
  }}
  updateLikedCounts();
  if (document.getElementById('liked-only').checked) filterCards(false);
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

function updateLikedCounts() {{
  const dates = getSelectedDates();
  const dateLiked = cards.filter(c => c.dataset.liked === 'true' && (dates.length === 0 || dates.includes(c.dataset.date))).length;
  const totalLiked = cards.filter(c => c.dataset.liked === 'true').length;
  document.getElementById('liked-stat').textContent = totalLiked;
  const lo = document.getElementById('liked-only').checked;
  document.getElementById('count').textContent = lo ? dateLiked + ' liked' : '';
}}
function filterCards(resetPage) {{
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
  if (resetPage !== false) currentPage = 1;
  updateLikedCounts();
  renderPage();
}}
function getColCount() {{
  if (window.innerWidth <= 768) return 2;
  if (window.innerWidth <= 1200) return 3;
  return 5;
}}
function renderPage() {{
  const scrollY = window.scrollY;
  const end = currentPage * PAGE_SIZE;
  const colCount = getColCount();
  while (grid.firstChild) grid.removeChild(grid.firstChild);
  const cols = [];
  for (let i = 0; i < colCount; i++) {{
    const col = document.createElement('div');
    col.className = 'grid-col';
    grid.appendChild(col);
    cols.push(col);
  }}
  const visible = filteredCards.slice(0, end);
  visible.forEach((card, i) => {{
    card.style.display = '';
    cols[i % colCount].appendChild(card);
  }});
  const btn = document.getElementById('load-more');
  btn.style.display = end < filteredCards.length ? '' : 'none';
  requestAnimationFrame(() => window.scrollTo(0, scrollY));
}}
function loadMore() {{
  currentPage++;
  renderPage();
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
// 메모 기능 — Firebase 실시간
memosRef.on('value', snap => {{
  const data = snap.val() || {{}};
  document.querySelectorAll('.memo-area').forEach(area => {{
    const mid = area.dataset.memoId;
    const textEl = area.querySelector('.memo-text');
    if (data[mid]) {{
      textEl.textContent = data[mid];
    }} else {{
      textEl.textContent = '';
    }}
  }});
}});
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
  function save() {{
    const val = ta.value.trim();
    ta.remove();
    textEl.style.display = '';
    if (val) {{
      memosRef.child(mid).set(val);
    }} else {{
      memosRef.child(mid).remove();
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
    if (s === 'oldest') return a.dataset.time.localeCompare(b.dataset.time);
    return b.dataset.time.localeCompare(a.dataset.time);
  }});
  filterCards();
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
