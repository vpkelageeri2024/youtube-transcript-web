// ── State ────────────────────────────────────────────────────────────────

let currentTranscript = null;
let currentVideoId = null;

// ── DOM Elements ─────────────────────────────────────────────────────────

const urlInput = document.getElementById('urlInput');
const langInput = document.getElementById('langInput');
const translateInput = document.getElementById('translateInput');
const formatSelect = document.getElementById('formatSelect');
const fetchBtn = document.getElementById('fetchBtn');
const langsBtn = document.getElementById('langsBtn');
const statusEl = document.getElementById('status');
const resultsEl = document.getElementById('results');
const langsPanelEl = document.getElementById('langsPanel');
const videoPreview = document.getElementById('videoPreview');
const toastEl = document.getElementById('toast');

// ── Video Preview ────────────────────────────────────────────────────────

function extractVideoId(url) {
    if (!url) return null;
    url = url.trim();

    // Plain video ID
    if (/^[A-Za-z0-9_-]{11}$/.test(url)) return url;

    try {
        const parsed = new URL(url);

        // youtu.be
        if (parsed.hostname === 'youtu.be') {
            return parsed.pathname.slice(1).split('/')[0].split('?')[0];
        }

        // youtube.com variants
        if (['www.youtube.com', 'youtube.com', 'm.youtube.com'].includes(parsed.hostname)) {
            if (parsed.pathname === '/watch') {
                return parsed.searchParams.get('v');
            }
            for (const prefix of ['/embed/', '/v/', '/shorts/', '/live/']) {
                if (parsed.pathname.startsWith(prefix)) {
                    return parsed.pathname.slice(prefix.length).split('/')[0].split('?')[0];
                }
            }
        }
    } catch (e) { }

    return null;
}

function updateVideoPreview() {
    const videoId = extractVideoId(urlInput.value);
    const thumbImg = document.getElementById('thumbImg');
    const videoIdLabel = document.getElementById('videoIdLabel');

    if (videoId) {
        thumbImg.src = `https://img.youtube.com/vi/${videoId}/maxresdefault.jpg`;
        thumbImg.onerror = () => {
            thumbImg.src = `https://img.youtube.com/vi/${videoId}/hqdefault.jpg`;
        };
        videoIdLabel.textContent = `ID: ${videoId}`;
        videoPreview.classList.add('video-preview--visible');
    } else {
        videoPreview.classList.remove('video-preview--visible');
    }
}

// Debounced preview
let previewTimeout;
urlInput.addEventListener('input', () => {
    clearTimeout(previewTimeout);
    previewTimeout = setTimeout(updateVideoPreview, 400);
});

// ── Status Messages ──────────────────────────────────────────────────────

function showStatus(message, type = 'info') {
    const icons = { error: '✕', success: '✓', info: '⟳' };
    statusEl.innerHTML = `<span>${icons[type] || ''}</span> ${message}`;
    statusEl.className = `status status--visible status--${type}`;
}

function hideStatus() {
    statusEl.className = 'status';
}

// ── Toast ─────────────────────────────────────────────────────────────────

function showToast(message) {
    toastEl.textContent = message;
    toastEl.classList.add('toast--visible');
    setTimeout(() => toastEl.classList.remove('toast--visible'), 2200);
}

// ── Format Timestamp ─────────────────────────────────────────────────────

function formatTime(seconds) {
    const total = Math.floor(seconds);
    const h = Math.floor(total / 3600);
    const m = Math.floor((total % 3600) / 60);
    const s = total % 60;
    if (h > 0) {
        return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
    }
    return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
}

// ── Usage Badge ──────────────────────────────────────────────────────────

function updateUsageBadge(remaining, total) {
    const badge = document.getElementById('usageBadge');
    const text = document.getElementById('usageText');
    if (!badge || !text) return;

    text.textContent = `${remaining}/${total} remaining`;
    badge.style.display = 'inline-flex';

    badge.classList.remove('usage-badge--warning', 'usage-badge--danger');
    const ratio = remaining / total;
    if (ratio <= 0.15) {
        badge.classList.add('usage-badge--danger');
    } else if (ratio <= 0.4) {
        badge.classList.add('usage-badge--warning');
    }
}

// ── Credit Badge ─────────────────────────────────────────────────────────

function updateCreditBadge(credits, dailyLimit) {
    const badge = document.getElementById('creditBadge');
    const count = document.getElementById('creditCount');
    if (!badge || !count) return;
    
    count.textContent = dailyLimit < 0 ? '∞' : credits;
    badge.classList.remove('credit-badge--ok', 'credit-badge--warning', 'credit-badge--danger');
    
    if (dailyLimit < 0) {
        badge.classList.add('credit-badge--ok');
    } else if (credits > 3) {
        badge.classList.add('credit-badge--ok');
    } else if (credits > 0) {
        badge.classList.add('credit-badge--warning');
    } else {
        badge.classList.add('credit-badge--danger');
    }
    
    badge.classList.add('credit-badge--pulse');
    setTimeout(() => badge.classList.remove('credit-badge--pulse'), 300);
}

async function fetchCredits() {
    try {
        const res = await fetch('/api/credits');
        if (res.ok) {
            const data = await res.json();
            updateCreditBadge(data.credits, data.daily_limit);
        }
    } catch (err) {
        // Silently fail — credit badge is non-critical
    }
}

// ── Upgrade Modal ────────────────────────────────────────────────────────

function showUpgradeModal() {
    // Remove existing modal if any
    const existing = document.querySelector('.modal-overlay');
    if (existing) existing.remove();

    const overlay = document.createElement('div');
    overlay.className = 'modal-overlay';
    overlay.innerHTML = `
        <div class="modal">
            <div class="modal__icon">🪙</div>
            <h2 class="modal__title">Out of Credits</h2>
            <p class="modal__text">You've used all your credits for today. Each transcript costs 1 credit. Upgrade your plan to get more daily credits and unlock premium features.</p>
            <a href="/pricing" class="modal__btn-primary">💎 Get More Credits</a>
            <button class="modal__btn-dismiss" onclick="this.closest('.modal-overlay').remove()">Maybe Later</button>
        </div>
    `;

    // Dismiss on backdrop click
    overlay.addEventListener('click', (e) => {
        if (e.target === overlay) overlay.remove();
    });

    document.body.appendChild(overlay);
}

// ── Render Transcript ────────────────────────────────────────────────────

function renderTranscript(data) {
    currentTranscript = data;
    currentVideoId = data.video_id;

    // Update meta
    const langLabel = data.language ? ` · ${data.language}` : '';
    document.getElementById('segmentCount').textContent = `${data.segments} segments${langLabel}`;

    // Timestamped view
    const segmentsContainer = document.getElementById('timestampedView');
    segmentsContainer.innerHTML = data.transcript.map(entry => `
        <div class="segment">
            <span class="segment__time">${formatTime(entry.start)}</span>
            <span class="segment__text">${escapeHtml(entry.text)}</span>
        </div>
    `).join('');

    // Plain text view
    document.getElementById('textView').textContent = data.text;

    // SRT view
    document.getElementById('srtView').textContent = data.srt;

    // JSON view
    document.getElementById('jsonView').textContent = JSON.stringify(data.transcript, null, 2);

    // Show results
    resultsEl.classList.add('results--visible');
    langsPanelEl.classList.remove('langs-panel--visible');

    // Switch to default tab
    switchTab('timestamped');


    // Show affiliate section
    loadAffiliateTools();

    // Scroll to results
    setTimeout(() => {
        resultsEl.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }, 100);
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// ── View Tabs ────────────────────────────────────────────────────────────

function switchTab(tab) {
    // Update tab buttons
    document.querySelectorAll('.view-tab').forEach(el => {
        el.classList.toggle('view-tab--active', el.dataset.tab === tab);
    });

    // Update views
    document.querySelectorAll('.transcript-view').forEach(el => {
        el.classList.toggle('transcript-view--active', el.dataset.view === tab);
    });
}

document.querySelectorAll('.view-tab').forEach(tab => {
    tab.addEventListener('click', () => switchTab(tab.dataset.tab));
});

// ── Fetch Transcript ─────────────────────────────────────────────────────

async function fetchTranscript() {
    const url = urlInput.value.trim();
    if (!url) {
        showStatus('Please enter a YouTube URL.', 'error');
        urlInput.focus();
        return;
    }

    // UI loading state
    fetchBtn.classList.add('btn--loading');
    fetchBtn.disabled = true;
    hideStatus();
    resultsEl.classList.remove('results--visible');
    langsPanelEl.classList.remove('langs-panel--visible');

    try {
        const body = { url };
        if (langInput.value.trim()) body.lang = langInput.value.trim();
        if (translateInput.value.trim()) body.translate = translateInput.value.trim();

        const res = await fetch('/api/transcript', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });

        const data = await res.json();

        if (!res.ok) {
            if (res.status === 429) {
                showStatus(data.error || 'Out of credits.', 'error');
                showUpgradeModal();
            } else {
                showStatus(data.error || 'Something went wrong.', 'error');
            }
            return;
        }

        showStatus(`Fetched ${data.segments} segments for video ${data.video_id}`, 'success');
        renderTranscript(data);

        // Update credit badge from response
        if (data.remaining !== undefined && data.daily_limit !== undefined) {
            updateCreditBadge(data.remaining, data.daily_limit);
        }

    } catch (err) {
        showStatus(`Network error: ${err.message}`, 'error');
    } finally {
        fetchBtn.classList.remove('btn--loading');
        fetchBtn.disabled = false;
    }
}

fetchBtn.addEventListener('click', fetchTranscript);

// Enter key to submit
urlInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') fetchTranscript();
});

// ── Fetch Languages ──────────────────────────────────────────────────────

async function fetchLanguages() {
    const url = urlInput.value.trim();
    if (!url) {
        showStatus('Please enter a YouTube URL first.', 'error');
        urlInput.focus();
        return;
    }

    langsBtn.classList.add('btn--loading');
    langsBtn.disabled = true;
    hideStatus();

    try {
        const res = await fetch('/api/languages', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url }),
        });

        const data = await res.json();

        if (!res.ok) {
            showStatus(data.error || 'Something went wrong.', 'error');
            return;
        }

        renderLanguages(data);

    } catch (err) {
        showStatus(`Network error: ${err.message}`, 'error');
    } finally {
        langsBtn.classList.remove('btn--loading');
        langsBtn.disabled = false;
    }
}

function renderLanguages(data) {
    const manualList = document.getElementById('manualLangs');
    const generatedList = document.getElementById('generatedLangs');

    if (data.manual.length === 0) {
        manualList.innerHTML = '<span class="lang-chip lang-chip--empty">None available</span>';
    } else {
        manualList.innerHTML = data.manual.map(l =>
            `<span class="lang-chip" onclick="selectLang('${l.code}')">${l.language} <span class="lang-chip__code">${l.code}</span></span>`
        ).join('');
    }

    if (data.generated.length === 0) {
        generatedList.innerHTML = '<span class="lang-chip lang-chip--empty">None available</span>';
    } else {
        generatedList.innerHTML = data.generated.map(l =>
            `<span class="lang-chip" onclick="selectLang('${l.code}')">${l.language} <span class="lang-chip__code">${l.code}</span></span>`
        ).join('');
    }

    langsPanelEl.classList.add('langs-panel--visible');
    resultsEl.classList.remove('results--visible');

    setTimeout(() => {
        langsPanelEl.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }, 100);
}

function selectLang(code) {
    langInput.value = code;
    showToast(`Language set to "${code}" — click Generate to fetch`);
}

langsBtn.addEventListener('click', fetchLanguages);

// ── Copy & Download ──────────────────────────────────────────────────────

function getActiveContent() {
    const activeView = document.querySelector('.transcript-view--active');
    if (!activeView) return '';

    const tab = activeView.dataset.view;

    if (tab === 'timestamped' && currentTranscript) {
        return currentTranscript.transcript.map(e =>
            `[${formatTime(e.start)}]  ${e.text}`
        ).join('\n');
    }

    if (tab === 'text') return currentTranscript?.text || '';
    if (tab === 'srt') return currentTranscript?.srt || '';
    if (tab === 'json') return JSON.stringify(currentTranscript?.transcript, null, 2);

    return '';
}

function copyTranscript() {
    const content = getActiveContent();
    if (!content) return;

    navigator.clipboard.writeText(content).then(() => {
        const btn = document.getElementById('copyBtn');
        btn.classList.add('copied');
        btn.innerHTML = '✓ Copied';
        showToast('Transcript copied to clipboard');

        setTimeout(() => {
            btn.classList.remove('copied');
            btn.innerHTML = '📋 Copy';
        }, 2000);
    });
}

function downloadTranscript() {
    const content = getActiveContent();
    if (!content) return;

    const activeView = document.querySelector('.transcript-view--active');
    const tab = activeView?.dataset.view || 'text';
    const extMap = { timestamped: 'txt', text: 'txt', srt: 'srt', json: 'json' };
    const ext = extMap[tab] || 'txt';

    const blob = new Blob([content], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `transcript_${currentVideoId || 'video'}.${ext}`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);

    showToast(`Downloaded as .${ext}`);
}

// ── Mouse tracking for glow effect ───────────────────────────────────────

const inputCard = document.querySelector('.input-card');
if (inputCard) {
    inputCard.addEventListener('mousemove', (e) => {
        const rect = inputCard.getBoundingClientRect();
        inputCard.style.setProperty('--mouse-x', `${e.clientX - rect.left}px`);
        inputCard.style.setProperty('--mouse-y', `${e.clientY - rect.top}px`);
    });
}


// ── Affiliate Section ────────────────────────────────────────────────────

async function loadAffiliateTools() {
    const section = document.getElementById('affiliateSection');
    if (!section) return;

    try {
        const res = await fetch('/api/config');
        const config = await res.json();

        if (config.affiliate_tools && config.affiliate_tools.length > 0) {
            section.innerHTML = `
                <h2 class="docs-section__title" style="font-size: 1.1rem; margin-bottom: 16px;">
                    <span>🛠</span> Recommended Tools
                </h2>
                <div class="affiliate-grid">
                    ${config.affiliate_tools.map(tool => `
                        <a href="${tool.url}" target="_blank" rel="noopener noreferrer" class="affiliate-card">
                            <span class="affiliate-card__icon">${tool.icon || '🔧'}</span>
                            <span class="affiliate-card__name">${escapeHtml(tool.name)}</span>
                            <span class="affiliate-card__desc">${escapeHtml(tool.description)}</span>
                            <span class="affiliate-card__cta">Try it →</span>
                        </a>
                    `).join('')}
                </div>
            `;
            section.style.display = 'block';
        }
    } catch (err) {
        // Silently fail — affiliate section is non-critical
    }
}

// ── Init ─────────────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
    // Fetch credit balance on page load
    fetchCredits();
});
