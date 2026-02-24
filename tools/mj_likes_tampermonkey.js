// ==UserScript==
// @name         MJ Likes Auto Collector
// @namespace    nano-banana
// @version      2.5
// @description  Midjourney Liked 이미지 자동 수집 (00:00, 12:00, 18:00)
// @match        https://www.midjourney.com/*
// @match        https://midjourney.com/*
// @run-at       document-idle
// @grant        GM_xmlhttpRequest
// @grant        GM_getValue
// @grant        GM_setValue
// @connect      127.0.0.1
// ==/UserScript==

(function() {
    'use strict';

    console.log('[MJ Likes] v2.5 loaded');

    const USER_ID = 'a0d2fe4b-1be4-4ef8-9316-71bacb306ef9';
    const SERVER_URL = 'http://127.0.0.1:7821/mj-likes';
    const SCHEDULE_HOURS = [0, 12, 18]; // KST
    const CHECK_INTERVAL_MS = 15 * 60 * 1000; // 15분마다 체크

    let collecting = false;

    function showStatus(text, color) {
        let el = document.getElementById('mj-auto-status');
        if (!el) {
            el = document.createElement('div');
            el.id = 'mj-auto-status';
            el.style.cssText = 'position:fixed;bottom:60px;right:20px;z-index:99999;padding:10px 16px;border-radius:8px;font:13px sans-serif;color:#fff;transition:opacity 0.5s;box-shadow:0 2px 10px rgba(0,0,0,0.3);';
            document.body.appendChild(el);
        }
        el.style.background = color || '#0f3460';
        el.textContent = text;
        el.style.opacity = '1';
        clearTimeout(el._timer);
        el._timer = setTimeout(() => { el.style.opacity = '0'; }, 10000);
    }

    function createButton() {
        const btn = document.createElement('div');
        btn.id = 'mj-collect-btn';
        btn.textContent = 'MJ Collect';
        btn.style.cssText = 'position:fixed;bottom:20px;right:20px;z-index:99999;padding:10px 20px;background:#e94560;color:#fff;border-radius:8px;font:bold 14px sans-serif;cursor:pointer;box-shadow:0 2px 10px rgba(0,0,0,0.3);user-select:none;';
        btn.addEventListener('click', async () => {
            if (collecting) return;
            console.log('[MJ Likes] Manual collect triggered');
            await GM_setValue('lastCollect', 0);
            await runCollection();
        });
        document.body.appendChild(btn);
        console.log('[MJ Likes] Button created');
    }

    function isLikedActive() {
        const btn = [...document.querySelectorAll('button')].find(b => b.textContent.trim() === 'Liked');
        return btn && !!btn.querySelector('svg');
    }

    function isScheduledWindow() {
        const hour = new Date().getHours();
        return SCHEDULE_HOURS.includes(hour);
    }

    async function shouldCollect() {
        if (!isScheduledWindow()) return false;
        const lastRun = await GM_getValue('lastCollect', 0);
        return (Date.now() - lastRun) >= 4 * 60 * 60 * 1000; // 4시간 경과
    }

    async function collectWithScroll() {
        const seen = new Set();
        const items = [];

        function scan() {
            document.querySelectorAll('img[src*="cdn.midjourney.com"]').forEach(img => {
                const m = img.src.match(/cdn\.midjourney\.com\/([a-f0-9-]+)\/([0-9]+_[0-9]+)/);
                if (m) {
                    const key = m[1] + '_' + m[2];
                    if (!seen.has(key)) {
                        seen.add(key);
                        items.push({ id: m[1], pos: m[2], url: img.src });
                    }
                }
            });
            return items.length;
        }

        const ob = new MutationObserver(scan);
        ob.observe(document.body, { childList: true, subtree: true, attributes: true, attributeFilter: ['src'] });
        scan();

        const containers = [...document.querySelectorAll('div')].filter(d => {
            const s = getComputedStyle(d);
            return d.scrollHeight > d.clientHeight + 200 &&
                   (s.overflowY === 'auto' || s.overflowY === 'scroll' || s.overflow === 'auto' || s.overflow === 'scroll');
        });
        const scroller = containers.length > 0 ? containers[containers.length - 1] : null;
        console.log('[MJ Likes] Scroller found:', !!scroller);

        if (scroller) {
            scroller.scrollTop = 0;
            await new Promise(r => setTimeout(r, 500));

            let prev = 0, stable = 0;
            for (let i = 0; i < 500; i++) {
                if (!isLikedActive()) {
                    console.log('[MJ Likes] Liked deactivated, stopping');
                    break;
                }
                scroller.scrollTop += 300;
                await new Promise(r => setTimeout(r, 300));
                const count = scan();
                showStatus(`MJ Likes: 수집 중... ${count}개`, '#0f3460');
                if (count === prev) { stable++; if (stable > 15) break; }
                else { stable = 0; prev = count; }
            }
        }

        ob.disconnect();
        return items;
    }

    async function collectPrompts(jobIds) {
        const prompts = {};

        // 1차: 내 생성 이미지에서 프롬프트 수집
        let cursor = '';
        let pages = 0;
        while (pages < 200) {
            let url = `/api/imagine?user_id=${USER_ID}&page_size=50` + (cursor ? `&cursor=${encodeURIComponent(cursor)}` : '');
            try {
                const r = await fetch(url, { headers: { 'x-csrf-protection': '1' } });
                const d = await r.json();
                if (!d.data || !d.data.length) break;
                d.data.forEach(j => {
                    if (jobIds.has(j.id)) prompts[j.id] = { prompt: j.full_command || '', width: j.width, height: j.height, time: j.enqueue_time };
                });
                cursor = d.cursor || '';
                if (!cursor || Object.keys(prompts).length >= jobIds.size) break;
                pages++;
                showStatus(`MJ Likes: 내 프롬프트 ${Object.keys(prompts).length}/${jobIds.size}...`, '#0f3460');
            } catch (e) { console.error('[MJ Likes] Prompt error:', e); break; }
        }

        // 2차: 못 찾은 job은 개별 조회 (다른 사람 이미지)
        const missing = [...jobIds].filter(id => !prompts[id]);
        if (missing.length > 0) {
            showStatus(`MJ Likes: 외부 프롬프트 ${missing.length}개 조회...`, '#0f3460');
            for (let i = 0; i < missing.length; i += 10) {
                const batch = missing.slice(i, i + 10);
                const params = batch.map(id => `jobIds[]=${id}`).join('&');
                try {
                    const r = await fetch(`/api/app/job-status/?${params}`, { headers: { 'x-csrf-protection': '1' } });
                    const d = await r.json();
                    if (d && typeof d === 'object') {
                        Object.entries(d).forEach(([id, j]) => {
                            if (j && jobIds.has(id)) {
                                prompts[id] = { prompt: j.full_command || j.prompt || '', width: j.width, height: j.height, time: j.enqueue_time || j.created_at || '' };
                            }
                        });
                    }
                    showStatus(`MJ Likes: 프롬프트 ${Object.keys(prompts).length}/${jobIds.size}...`, '#0f3460');
                    await new Promise(r => setTimeout(r, 200));
                } catch (e) { console.error('[MJ Likes] Job status error:', e); }
            }
        }

        return prompts;
    }

    function sendToServer(data) {
        return new Promise((resolve, reject) => {
            GM_xmlhttpRequest({
                method: 'POST',
                url: SERVER_URL,
                headers: { 'Content-Type': 'application/json' },
                data: JSON.stringify(data),
                onload: (resp) => resp.status === 200 ? resolve(JSON.parse(resp.responseText)) : reject(new Error('Server ' + resp.status)),
                onerror: () => reject(new Error('Connection failed'))
            });
        });
    }

    async function runCollection() {
        if (collecting) return;
        collecting = true;

        const btn = document.getElementById('mj-collect-btn');
        if (btn) { btn.textContent = '수집 중...'; btn.style.background = '#0f3460'; }

        try {
            if (!isLikedActive()) {
                showStatus('MJ Likes: Liked 필터를 켜주세요', '#e94560');
                return;
            }

            showStatus('MJ Likes: 수집 시작...', '#0f3460');
            await new Promise(r => setTimeout(r, 2000));

            const items = await collectWithScroll();
            console.log('[MJ Likes] Collected', items.length, 'images');

            if (items.length === 0) {
                showStatus('MJ Likes: 이미지 없음', '#e94560');
                return;
            }

            let existing = [];
            try { existing = JSON.parse(await GM_getValue('savedLikes', '[]')); } catch(e) {}
            const existingKeys = new Set(existing.map(e => e.id + '_' + (e.pos || '0_0')));
            let newCount = 0;
            for (const item of items) {
                if (!existingKeys.has(item.id + '_' + item.pos)) {
                    existing.push(item);
                    existingKeys.add(item.id + '_' + item.pos);
                    newCount++;
                }
            }

            const needPrompt = new Set();
            for (const item of existing) { if (!item.prompt) needPrompt.add(item.id); }
            let prompts = {};
            if (needPrompt.size > 0) {
                showStatus(`MJ Likes: 프롬프트 ${needPrompt.size}개...`, '#0f3460');
                prompts = await collectPrompts(needPrompt);
            }

            const final = existing.map(item => {
                const p = prompts[item.id] || {};
                return {
                    id: item.id, pos: item.pos || '0_0',
                    image_url: (item.image_url || item.url || '').split('?')[0].replace('_384_N', ''),
                    thumbnail_url: item.thumbnail_url || item.url || '',
                    prompt: item.prompt || p.prompt || '',
                    width: item.width || p.width || 0, height: item.height || p.height || 0,
                    time: item.time || p.time || ''
                };
            });

            await GM_setValue('savedLikes', JSON.stringify(final));

            showStatus(`MJ Likes: ${final.length}개 전송 중...`, '#0f3460');
            try {
                const result = await sendToServer(final);
                showStatus(`MJ Likes: 완료! 총 ${result.count}개 (새로 ${newCount}개)`, '#27ae60');
                await GM_setValue('lastCollect', Date.now());
            } catch (e) {
                showStatus('MJ Likes: 서버 없음 → JSON 다운로드', '#e67e22');
                const blob = new Blob([JSON.stringify(final, null, 2)], {type: 'application/json'});
                const a = document.createElement('a');
                a.href = URL.createObjectURL(blob);
                a.download = 'mj_likes_' + new Date().toISOString().slice(0, 10) + '.json';
                a.click();
                await GM_setValue('lastCollect', Date.now());
            }
        } finally {
            collecting = false;
            if (btn) { btn.textContent = 'MJ Collect'; btn.style.background = '#e94560'; }
        }
    }

    // 시작
    (async () => {
        await new Promise(r => setTimeout(r, 3000));
        createButton();
        showStatus('MJ Likes v2.5 (00:00/12:00/18:00)', '#27ae60');

        // 첫 실행: 스케줄 시간이면 자동 수집
        if (await shouldCollect()) {
            console.log('[MJ Likes] Scheduled auto collect');
            await runCollection();
        } else {
            const lastRun = await GM_getValue('lastCollect', 0);
            const mins = Math.round((Date.now() - lastRun) / 60000);
            console.log(`[MJ Likes] Next schedule: ${SCHEDULE_HOURS.join(', ')}시. Last: ${mins}분 전. Click button to collect now.`);
        }

        // 15분마다 스케줄 체크
        setInterval(async () => {
            if (await shouldCollect()) {
                console.log('[MJ Likes] Scheduled collection...');
                await runCollection();
            }
        }, CHECK_INTERVAL_MS);
    })();

})();
