#!/usr/bin/env python3
"""
Phase 2 enhancements:
- Phase 3 #8: 좋아요 vs 안좋아요 비교
- Phase 4 #12: 개별 단어 조합 성공 패턴
- Phase 4 #9-10: 클러스터링 분석 (simplified)
- Improve Design Patterns insight
"""

import json
import os
import glob
import re
import math
from collections import Counter, defaultdict

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HTML_PATH = os.path.join(BASE, 'docs', 'analysis.html')

def load_metadata():
    all_meta = []
    for f in sorted(glob.glob(os.path.join(BASE, 'output', 'images', 'metadata', '26*_metadata.json'))):
        if 'backup' in f or 'bak' in f:
            continue
        with open(f, 'r', encoding='utf-8') as fh:
            all_meta.extend(json.load(fh))
    return all_meta

def load_liked_ids():
    liked_ids = set()
    for f in glob.glob(os.path.join(BASE, 'output', 'likes', '*.png')):
        parts = os.path.basename(f).replace('.png', '').split('_')
        if len(parts) >= 2:
            liked_ids.add(parts[0] + '_' + parts[1])
    return liked_ids

def load_word1_db():
    with open(os.path.join(BASE, 'config', 'word1-db.json'), 'r', encoding='utf-8') as f:
        w1db = json.load(f)
    word_to_cat = {}
    for cat, words in w1db.items():
        for w in words:
            if isinstance(w, dict):
                word_to_cat[w.get('word', '')] = cat
            elif isinstance(w, list) and len(w) >= 1:
                word_to_cat[w[0]] = cat
            elif isinstance(w, str):
                word_to_cat[w] = cat
    return word_to_cat

def compute_all():
    all_meta = load_metadata()
    liked_ids = load_liked_ids()
    w1_cat_map = load_word1_db()

    # Filter out midjourney (no likes data)
    nano_meta = [m for m in all_meta if 'midjourney' not in m.get('model_used', '')]
    liked_meta = [m for m in nano_meta if m['combo_id'] in liked_ids]
    not_liked = [m for m in nano_meta if m['combo_id'] not in liked_ids]

    result = {}

    # ===== Phase 3 #8: 좋아요 vs 안좋아요 비교 =====
    print("=== Phase 3 #8: Liked vs Not-Liked ===")

    # Word1 distribution comparison
    liked_w1 = Counter(m.get('word1', '') for m in liked_meta if m.get('word1'))
    notliked_w1 = Counter(m.get('word1', '') for m in not_liked if m.get('word1'))

    # Get all words used at least 5 times total
    all_w1 = Counter(m.get('word1', '') for m in nano_meta if m.get('word1'))
    w1_comparison = []
    for w, total in all_w1.most_common():
        if total >= 5 and w:
            liked_c = liked_w1.get(w, 0)
            not_c = notliked_w1.get(w, 0)
            rate = round(liked_c / total * 100, 1)
            w1_comparison.append({
                'word': w, 'total': total, 'liked': liked_c, 'not_liked': not_c, 'rate': rate
            })
    w1_comparison.sort(key=lambda x: -x['rate'])

    # Word2 distribution comparison
    liked_w2 = Counter(m.get('word2', '') for m in liked_meta if m.get('word2'))
    notliked_w2 = Counter(m.get('word2', '') for m in not_liked if m.get('word2'))
    all_w2 = Counter(m.get('word2', '') for m in nano_meta if m.get('word2'))
    w2_comparison = []
    for w, total in all_w2.most_common():
        if total >= 5 and w:
            liked_c = liked_w2.get(w, 0)
            not_c = notliked_w2.get(w, 0)
            rate = round(liked_c / total * 100, 1)
            w2_comparison.append({
                'word': w, 'total': total, 'liked': liked_c, 'not_liked': not_c, 'rate': rate
            })
    w2_comparison.sort(key=lambda x: -x['rate'])

    # Category comparison
    liked_cats = Counter(w1_cat_map.get(m.get('word1', ''), 'unknown') for m in liked_meta)
    notliked_cats = Counter(w1_cat_map.get(m.get('word1', ''), 'unknown') for m in not_liked)
    all_cats = Counter(w1_cat_map.get(m.get('word1', ''), 'unknown') for m in nano_meta)
    cat_comparison = []
    for cat, total in all_cats.most_common():
        if total >= 10 and cat != 'unknown':
            liked_c = liked_cats.get(cat, 0)
            not_c = notliked_cats.get(cat, 0)
            rate = round(liked_c / total * 100, 1)
            cat_comparison.append({
                'cat': cat, 'total': total, 'liked': liked_c, 'not_liked': not_c, 'rate': rate
            })
    cat_comparison.sort(key=lambda x: -x['rate'])

    # Template comparison
    liked_tmpl = Counter(m.get('template_id', 'unknown') for m in liked_meta)
    notliked_tmpl = Counter(m.get('template_id', 'unknown') for m in not_liked)
    all_tmpl = Counter(m.get('template_id', 'unknown') for m in nano_meta)
    tmpl_comparison = []
    for t, total in all_tmpl.most_common():
        if total >= 10 and t:
            liked_c = liked_tmpl.get(t, 0)
            not_c = notliked_tmpl.get(t, 0)
            rate = round(liked_c / total * 100, 1)
            tmpl_comparison.append({
                'tmpl': t, 'total': total, 'liked': liked_c, 'not_liked': not_c, 'rate': rate
            })
    tmpl_comparison.sort(key=lambda x: -x['rate'])

    result['liked_vs_notliked'] = {
        'total_nano': len(nano_meta),
        'liked': len(liked_meta),
        'not_liked': len(not_liked),
        'overall_rate': round(len(liked_meta) / len(nano_meta) * 100, 1),
        'w1_top': w1_comparison[:15],
        'w1_bottom': [x for x in w1_comparison if x['rate'] == 0][:15],
        'w2_top': w2_comparison[:15],
        'w2_bottom': [x for x in w2_comparison if x['rate'] == 0][:15],
        'cat_comparison': cat_comparison,
        'tmpl_comparison': tmpl_comparison[:15],
    }
    print(f"  Nano total: {len(nano_meta)}, liked: {len(liked_meta)}")
    print(f"  W1 top: {w1_comparison[0]['word']} ({w1_comparison[0]['rate']}%)")
    print(f"  W1 zero-rate: {len([x for x in w1_comparison if x['rate'] == 0])}")

    # ===== Phase 4 #12: 개별 단어 조합 패턴 =====
    print("\n=== Phase 4 #12: Word Combination Patterns ===")

    combo_all = Counter()
    combo_liked_c = Counter()
    for m in nano_meta:
        w1 = m.get('word1', '')
        w2 = m.get('word2', '')
        if w1 and w2:
            key = f"{w1}×{w2}"
            combo_all[key] += 1
    for m in liked_meta:
        w1 = m.get('word1', '')
        w2 = m.get('word2', '')
        if w1 and w2:
            key = f"{w1}×{w2}"
            combo_liked_c[key] += 1

    combo_stats = []
    for combo, total in combo_all.most_common():
        if total >= 2:
            liked_c = combo_liked_c.get(combo, 0)
            rate = round(liked_c / total * 100, 1)
            parts = combo.split('×')
            combo_stats.append({
                'w1': parts[0], 'w2': parts[1],
                'total': total, 'liked': liked_c, 'rate': rate
            })
    combo_stats.sort(key=lambda x: (-x['rate'], -x['liked']))

    # Category x Category patterns (from metadata, not just likes)
    catcat_all = Counter()
    catcat_liked = Counter()
    for m in nano_meta:
        w1 = m.get('word1', '')
        w2 = m.get('word2', '')
        if w1 and w2:
            c1 = w1_cat_map.get(w1, 'unknown')
            # We don't have w2 category map, use a simple check
            catcat_all[c1] += 1
    # Already covered in cross-table, skip redundant

    # Filter out 0% combos from top list — they go into zero_combos
    positive_combos = [x for x in combo_stats if x['rate'] > 0]
    result['combo_patterns'] = {
        'top_combos': positive_combos[:30],
        'zero_combos': [x for x in combo_stats if x['rate'] == 0 and x['total'] >= 3][:20],
        'total_unique_combos': len(combo_all),
        'combos_with_likes': len([k for k, v in combo_liked_c.items() if v > 0]),
    }
    print(f"  Total unique combos: {len(combo_all)}")
    print(f"  Combos with likes: {len([k for k, v in combo_liked_c.items() if v > 0])}")
    print(f"  Top combo: {combo_stats[0]}")

    # ===== Phase 4 #9-10: Simplified Clustering =====
    print("\n=== Phase 4 #9-10: Clustering (simplified) ===")

    gpt_path = os.path.join(BASE, 'output', 'likes_analysis', 'extracted_gpt4o.json')
    gem_path = os.path.join(BASE, 'output', 'likes_analysis', 'extracted_gemini.json')
    with open(gpt_path, 'r', encoding='utf-8') as f:
        gpt_data = json.load(f)
    with open(gem_path, 'r', encoding='utf-8') as f:
        gem_data = json.load(f)

    # Instead of full K-means (needs numpy/sklearn), do manual "taste profile" clustering
    # based on dominant attributes
    # Cluster by: render_quality x color_temperature x emotional_appeal core

    # Extract core taste groups
    taste_groups = defaultdict(list)
    for entry in gpt_data:
        a = entry.get('analysis', entry)  # nested under 'analysis'
        rq = str(a.get('render_quality', '')).lower()
        ct = str(a.get('color_temperature', '')).lower()
        ea = str(a.get('emotional_appeal', '')).lower()

        # Simplify render quality
        if 'photo' in rq:
            rq_simple = 'photorealistic'
        else:
            rq_simple = 'stylized'

        # Simplify color temp
        if 'warm' in ct:
            ct_simple = 'warm'
        elif 'cool' in ct:
            ct_simple = 'cool'
        else:
            ct_simple = 'neutral'

        # Simplify emotional appeal
        if 'whimsical' in ea:
            ea_simple = 'whimsical'
        elif 'elegant' in ea:
            ea_simple = 'elegant'
        elif 'mysterious' in ea:
            ea_simple = 'mysterious'
        elif 'serene' in ea or 'calm' in ea or 'tranquil' in ea:
            ea_simple = 'serene'
        elif 'playful' in ea:
            ea_simple = 'playful'
        else:
            ea_simple = 'other'

        group_key = f"{rq_simple} / {ct_simple} / {ea_simple}"
        taste_groups[group_key].append(entry.get('id', ''))

    # Sort by count
    cluster_data = []
    for key, ids in sorted(taste_groups.items(), key=lambda x: -len(x[1])):
        parts = key.split(' / ')
        cluster_data.append({
            'render': parts[0],
            'temp': parts[1],
            'emotion': parts[2],
            'count': len(ids),
            'pct': round(len(ids) / len(gpt_data) * 100, 1),
        })

    # Also do it for Gemini
    gem_groups = defaultdict(list)
    for entry in gem_data:
        a = entry.get('analysis', entry)
        rq = str(a.get('render_quality', '')).lower()
        ct = str(a.get('color_temperature', '')).lower()
        ea = str(a.get('emotional_appeal', '')).lower()

        rq_simple = 'photorealistic' if 'photo' in rq or 'realistic' in rq else 'stylized'
        ct_simple = 'warm' if 'warm' in ct else ('cool' if 'cool' in ct else 'neutral')
        if 'whimsical' in ea:
            ea_simple = 'whimsical'
        elif 'elegant' in ea:
            ea_simple = 'elegant'
        elif 'mysterious' in ea:
            ea_simple = 'mysterious'
        elif 'serene' in ea or 'calm' in ea or 'tranquil' in ea:
            ea_simple = 'serene'
        elif 'playful' in ea:
            ea_simple = 'playful'
        else:
            ea_simple = 'other'

        group_key = f"{rq_simple} / {ct_simple} / {ea_simple}"
        gem_groups[group_key].append(entry.get('id', ''))

    gem_cluster_data = []
    for key, ids in sorted(gem_groups.items(), key=lambda x: -len(x[1])):
        parts = key.split(' / ')
        gem_cluster_data.append({
            'render': parts[0],
            'temp': parts[1],
            'emotion': parts[2],
            'count': len(ids),
            'pct': round(len(ids) / len(gem_data) * 100, 1),
        })

    result['clusters'] = {
        'gpt_clusters': cluster_data[:15],
        'gem_clusters': gem_cluster_data[:15],
        'gpt_total': len(gpt_data),
        'gem_total': len(gem_data),
    }
    print(f"  GPT clusters: {len(cluster_data)}, top: {cluster_data[0]}")
    print(f"  GEM clusters: {len(gem_cluster_data)}, top: {gem_cluster_data[0]}")

    # ===== Improved Design Patterns insight =====
    # Count dimension, depth_of_field, has_nature distributions
    dim_counts = Counter(str(e.get('analysis', e).get('dimension', '')).lower() for e in gpt_data)
    dof_counts = Counter(str(e.get('analysis', e).get('depth_of_field', '')).lower() for e in gpt_data)
    nature_count = sum(1 for e in gpt_data if str(e.get('analysis', e).get('has_nature', '')).lower() == 'true')
    arch_count = sum(1 for e in gpt_data if str(e.get('analysis', e).get('has_architecture', '')).lower() == 'true')
    char_count = sum(1 for e in gpt_data if str(e.get('analysis', e).get('has_character', '')).lower() == 'true')

    result['design_extra'] = {
        'dim_3d': dim_counts.get('3d', 0),
        'dim_total': len(gpt_data),
        'dof_deep': sum(v for k, v in dof_counts.items() if 'deep' in k),
        'dof_shallow': sum(v for k, v in dof_counts.items() if 'shallow' in k or 'bokeh' in k),
        'nature_count': nature_count,
        'arch_count': arch_count,
        'char_count': char_count,
        'nature_pct': round(nature_count / len(gpt_data) * 100, 1),
        'char_pct': round(char_count / len(gpt_data) * 100, 1),
    }

    return result

def inject_html(data):
    with open(HTML_PATH, 'r', encoding='utf-8') as f:
        html = f.read()

    # === 1. Add Liked vs Not-Liked section ===
    lvn_html = '''
<!-- Section: Liked vs Not-Liked Comparison -->
<div class="section" id="s-lvn">
  <h2>좋아요 vs 안좋아요 비교 <span class="sub-note">(Phase 3 #8)</span></h2>
  <p class="insight" id="lvn-insight"></p>
  <div class="chart-row">
    <div class="chart-box"><h3>카테고리별 좋아요율</h3><canvas id="chart-lvn-cat"></canvas></div>
    <div class="chart-box"><h3>템플릿별 좋아요율</h3><canvas id="chart-lvn-tmpl"></canvas></div>
  </div>
  <h3 style="margin-top:16px">Word1 Top 15 vs Bottom 15</h3>
  <div class="chart-row">
    <div class="chart-box" style="min-height:450px"><h3>Word1 Best (좋아요율 높음)</h3><canvas id="chart-lvn-w1top"></canvas></div>
    <div class="chart-box" style="min-height:450px"><h3>Word1 Worst (좋아요율 0%)</h3><canvas id="chart-lvn-w1bot"></canvas></div>
  </div>
  <div class="chart-row">
    <div class="chart-box" style="min-height:450px"><h3>Word2 Best (좋아요율 높음)</h3><canvas id="chart-lvn-w2top"></canvas></div>
    <div class="chart-box" style="min-height:450px"><h3>Word2 Worst (좋아요율 0%)</h3><canvas id="chart-lvn-w2bot"></canvas></div>
  </div>
</div>
'''

    # === 2. Add Word Combo Patterns section ===
    combo_html = '''
<!-- Section: Word Combination Patterns -->
<div class="section" id="s-combos">
  <h2>단어 조합 성공 패턴 <span class="sub-note">(Phase 4 #12)</span></h2>
  <p class="insight" id="combo-insight2"></p>
  <div class="chart-row">
    <div class="chart-box full" style="min-height:500px"><h3>Top 30 조합 (좋아요율 기준)</h3><canvas id="chart-combo-top"></canvas></div>
  </div>
  <h3 style="margin-top:16px">실패한 조합 (0% 좋아요, 3회 이상 사용)</h3>
  <table id="combo-zero-table"></table>
</div>
'''

    # === 3. Add Clustering section ===
    cluster_html = '''
<!-- Section: Taste Clustering -->
<div class="section" id="s-clusters">
  <h2>취향 클러스터 분석 <span class="sub-note">(Phase 4 #9-10)</span></h2>
  <p class="insight" id="cluster-insight"></p>
  <div class="chart-row">
    <div class="chart-box"><h3>GPT-4o 기반 클러스터</h3><canvas id="chart-cluster-gpt"></canvas></div>
    <div class="chart-box"><h3>Gemini 기반 클러스터</h3><canvas id="chart-cluster-gem"></canvas></div>
  </div>
  <h3 style="margin-top:16px">클러스터 상세 비교</h3>
  <table id="cluster-table"></table>
</div>
'''

    # Insert before the deep analysis sections
    marker = '<!-- ═══ DEEP ANALYSIS START ═══ -->'
    html = html.replace(marker, lvn_html + '\n' + combo_html + '\n' + cluster_html + '\n' + marker)

    # === 4. Inject JS ===
    p2_data = json.dumps(data, ensure_ascii=False)

    js_code = f'''
// ═══ PHASE 2 ENHANCEMENT JS START ═══
var P2 = {p2_data};

// Liked vs Not-Liked
(function(){{
  var lvn = P2.liked_vs_notliked;
  document.getElementById('lvn-insight').innerHTML =
    'Nano-banana 전체 <em>'+lvn.total_nano+'</em>개 중 <strong>'+lvn.liked+'</strong>개 좋아요 (<em>'+lvn.overall_rate+'%</em>). ' +
    '좋아요율 0%인 Word1이 <strong>'+lvn.w1_bottom.length+'</strong>개, Word2가 <strong>'+lvn.w2_bottom.length+'</strong>개 — ' +
    '이 단어들을 제거하면 효율 향상 가능.';

  // Category chart
  var cats = lvn.cat_comparison;
  new Chart(document.getElementById('chart-lvn-cat'),{{
    type:'bar',
    data:{{
      labels:cats.map(function(x){{return x.cat}}),
      datasets:[
        {{label:'Liked',data:cats.map(function(x){{return x.liked}}),backgroundColor:GREEN+'88',borderColor:GREEN,borderWidth:1}},
        {{label:'Not Liked',data:cats.map(function(x){{return x.not_liked}}),backgroundColor:RED+'44',borderColor:RED,borderWidth:1}}
      ]
    }},
    options:{{responsive:true,plugins:{{legend:{{labels:{{boxWidth:12}}}},tooltip:{{callbacks:{{afterLabel:function(ctx){{var c=cats[ctx.dataIndex];return 'Rate: '+c.rate+'%'}}}}}}}},scales:{{y:{{stacked:true,grid:{{color:'#222'}}}},x:{{stacked:true,grid:{{display:false}}}}}}}}
  }});

  // Template chart
  var tmpls = lvn.tmpl_comparison;
  new Chart(document.getElementById('chart-lvn-tmpl'),{{
    type:'bar',
    data:{{
      labels:tmpls.map(function(x){{return x.tmpl}}),
      datasets:[{{
        label:'Like Rate %',data:tmpls.map(function(x){{return x.rate}}),
        backgroundColor:tmpls.map(function(x){{return x.rate>=15?GREEN+'88':(x.rate>=10?GOLD+'88':RED+'88')}}),
        borderColor:tmpls.map(function(x){{return x.rate>=15?GREEN:(x.rate>=10?GOLD:RED)}}),borderWidth:1
      }}]
    }},
    options:{{indexAxis:'y',responsive:true,plugins:{{legend:{{display:false}},tooltip:{{callbacks:{{afterLabel:function(ctx){{var t=tmpls[ctx.dataIndex];return 'Used: '+t.total+', Liked: '+t.liked}}}}}}}},scales:{{x:{{grid:{{color:'#222'}}}},y:{{grid:{{display:false}}}}}}}}
  }});

  // W1 top/bottom charts
  function lvnChart(id,data,color){{
    new Chart(document.getElementById(id),{{
      type:'bar',
      data:{{
        labels:data.map(function(x){{return x.word}}),
        datasets:[{{
          label:'Like Rate %',data:data.map(function(x){{return x.rate}}),
          backgroundColor:color+'88',borderColor:color,borderWidth:1
        }}]
      }},
      options:{{indexAxis:'y',responsive:true,plugins:{{legend:{{display:false}},tooltip:{{callbacks:{{afterLabel:function(ctx){{var d=data[ctx.dataIndex];return 'Total: '+d.total+', Liked: '+d.liked}}}}}}}},scales:{{x:{{grid:{{color:'#222'}},title:{{display:true,text:'Like Rate %'}}}},y:{{grid:{{display:false}}}}}}}}
    }});
  }}
  lvnChart('chart-lvn-w1top',lvn.w1_top,GREEN);
  lvnChart('chart-lvn-w1bot',lvn.w1_bottom,RED);
  lvnChart('chart-lvn-w2top',lvn.w2_top,GREEN);
  lvnChart('chart-lvn-w2bot',lvn.w2_bottom,RED);
}})();

// Word Combination Patterns
(function(){{
  var cp = P2.combo_patterns;
  document.getElementById('combo-insight2').innerHTML =
    '총 <em>'+cp.total_unique_combos+'</em>개 고유 조합 중 <strong>'+cp.combos_with_likes+'</strong>개만 좋아요 획득 ('+Math.round(cp.combos_with_likes/cp.total_unique_combos*100)+'%). ' +
    '대부분의 조합은 1회 사용 — 반복 사용되면서 좋아요도 받은 조합이 진정한 "황금 조합".';

  var top = cp.top_combos;
  new Chart(document.getElementById('chart-combo-top'),{{
    type:'bar',
    data:{{
      labels:top.map(function(x){{return x.w1+' × '+x.w2}}),
      datasets:[{{
        label:'Like Rate %',data:top.map(function(x){{return x.rate}}),
        backgroundColor:top.map(function(x){{return x.rate>=50?GREEN+'88':(x.rate>=25?GOLD+'88':BLUE+'88')}}),
        borderColor:top.map(function(x){{return x.rate>=50?GREEN:(x.rate>=25?GOLD:BLUE)}}),borderWidth:1
      }}]
    }},
    options:{{indexAxis:'y',responsive:true,plugins:{{legend:{{display:false}},tooltip:{{callbacks:{{afterLabel:function(ctx){{var d=top[ctx.dataIndex];return 'Used: '+d.total+', Liked: '+d.liked}}}}}}}},scales:{{x:{{grid:{{color:'#222'}},title:{{display:true,text:'Like Rate %'}}}},y:{{grid:{{display:false}},ticks:{{font:{{size:10}}}}}}}}}}
  }});

  // Zero-rate combos table
  var zero = cp.zero_combos;
  if(zero.length){{
    var rows = zero.map(function(x,i){{
      return '<tr><td>'+(i+1)+'</td><td>'+x.w1+'</td><td>'+x.w2+'</td><td>'+x.total+'</td><td style="color:#ff4757">0%</td></tr>';
    }}).join('');
    document.getElementById('combo-zero-table').innerHTML =
      '<thead><tr><th>#</th><th>Word1</th><th>Word2</th><th>Used</th><th>Rate</th></tr></thead><tbody>'+rows+'</tbody>';
  }}
}})();

// Clustering
(function(){{
  var cl = P2.clusters;
  var gTop = cl.gpt_clusters[0];
  var gemTop = cl.gem_clusters[0];
  document.getElementById('cluster-insight').innerHTML =
    '좋아요 이미지를 <strong>Render × Color Temp × Emotion</strong> 3축으로 클러스터링. ' +
    'GPT-4o 기준 최대 클러스터: <strong>'+gTop.render+' / '+gTop.temp+' / '+gTop.emotion+'</strong> ('+gTop.count+'개, '+gTop.pct+'%). ' +
    'Gemini 기준: <strong>'+gemTop.render+' / '+gemTop.temp+' / '+gemTop.emotion+'</strong> ('+gemTop.count+'개, '+gemTop.pct+'%).';

  function clusterChart(id,data,colors){{
    var labels = data.map(function(x){{return x.render+'/'+x.temp+'/'+x.emotion}});
    new Chart(document.getElementById(id),{{
      type:'bar',
      data:{{
        labels:labels,
        datasets:[{{
          label:'Count',data:data.map(function(x){{return x.count}}),
          backgroundColor:data.map(function(x,i){{return colors[i%colors.length]+'88'}}),
          borderColor:data.map(function(x,i){{return colors[i%colors.length]}}),borderWidth:1
        }}]
      }},
      options:{{indexAxis:'y',responsive:true,plugins:{{legend:{{display:false}},tooltip:{{callbacks:{{afterLabel:function(ctx){{return data[ctx.dataIndex].pct+'% of total'}}}}}}}},scales:{{x:{{grid:{{color:'#222'}}}},y:{{grid:{{display:false}},ticks:{{font:{{size:9}}}}}}}}}}
    }});
  }}
  clusterChart('chart-cluster-gpt',cl.gpt_clusters.slice(0,12),[GOLD,BLUE,GREEN,PURPLE,RED,ORANGE,'#00bcd4','#e91e63','#8bc34a','#ff9800','#9c27b0','#03a9f4']);
  clusterChart('chart-cluster-gem',cl.gem_clusters.slice(0,12),[PURPLE,GREEN,BLUE,GOLD,RED,ORANGE,'#00bcd4','#e91e63','#8bc34a','#ff9800','#9c27b0','#03a9f4']);

  // Cluster comparison table
  var allKeys = {{}};
  cl.gpt_clusters.forEach(function(x){{allKeys[x.render+'/'+x.temp+'/'+x.emotion]=true}});
  cl.gem_clusters.forEach(function(x){{allKeys[x.render+'/'+x.temp+'/'+x.emotion]=true}});
  var keys = Object.keys(allKeys).sort();
  var rows = keys.slice(0,20).map(function(k){{
    var gpt = cl.gpt_clusters.find(function(x){{return x.render+'/'+x.temp+'/'+x.emotion===k}});
    var gem = cl.gem_clusters.find(function(x){{return x.render+'/'+x.temp+'/'+x.emotion===k}});
    var gC = gpt?gpt.count:0;
    var eC = gem?gem.count:0;
    var diff = gC-eC;
    var diffStr = diff>0?'+'+diff:(diff<0?''+diff:'=');
    return '<tr><td style="font-size:0.73rem">'+k+'</td><td>'+gC+'</td><td>'+eC+'</td><td style="color:'+(diff>2?GREEN:(diff<-2?RED:'#888'))+'">'+diffStr+'</td></tr>';
  }}).join('');
  document.getElementById('cluster-table').innerHTML =
    '<thead><tr><th>Cluster</th><th>GPT</th><th>Gemini</th><th>Diff</th></tr></thead><tbody>'+rows+'</tbody>';
}})();

// Improved Design Patterns insight
(function(){{
  var de = P2.design_extra;
  var di = D.design.total + '개 좋아요 이미지 GPT-4o 분석: ';
  di += '<strong>3D</strong> '+Math.round(de.dim_3d/de.dim_total*100)+'% 압도적 — 2D는 거의 선호하지 않음. ';
  di += '자연 요소 <strong>'+de.nature_pct+'%</strong>, 건축 요소 <strong>'+Math.round(de.arch_count/de.dim_total*100)+'%</strong>, 캐릭터 <strong>'+de.char_pct+'%</strong>. ';
  di += 'DOF: deep focus <strong>'+de.dof_deep+'</strong>개 vs shallow bokeh <strong>'+de.dof_shallow+'</strong>개 — 전체가 또렷한 deep focus 선호. ';
  di += '결론: <strong>3D 포토리얼 + soft lighting + 자연 요소 포함 + deep focus</strong>가 핵심 레시피.';
  document.getElementById('design-insight').innerHTML = di;
}})();

// ═══ PHASE 2 ENHANCEMENT JS END ═══
'''

    # Insert before closing </script>
    html = html.replace('</script>\n</body>', js_code + '\n</script>\n</body>')

    return html

def main():
    print("=== Computing Phase 2 data ===")
    data = compute_all()

    print(f"\n=== Injecting into HTML ===")
    html = inject_html(data)

    with open(HTML_PATH, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"  Saved: {HTML_PATH}")

    out_copy = os.path.join(BASE, 'output', 'images', 'html', 'analysis.html')
    if os.path.exists(os.path.dirname(out_copy)):
        with open(out_copy, 'w', encoding='utf-8') as f:
            f.write(html)
        print(f"  Saved: {out_copy}")

    print("\n=== Phase 2 Done! ===")

if __name__ == '__main__':
    main()
