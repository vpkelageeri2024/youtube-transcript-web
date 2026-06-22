// ── State ────────────────────────────────────────────────────────────────

let currentTranscript = null;
let currentVideoId = null;
let googleClientId = null;

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
const searchInput = document.getElementById('searchInput');

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

function formatTimeVtt(seconds) {
    const total = Math.floor(seconds);
    const ms = Math.floor((seconds - total) * 1000);
    const h = Math.floor(total / 3600);
    const m = Math.floor((total % 3600) / 60);
    const s = total % 60;
    return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}.${String(ms).padStart(3, '0')}`;
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

    // VTT view
    let vttContent = "WEBVTT\n\n";
    vttContent += data.transcript.map(entry => {
        const start = formatTimeVtt(entry.start);
        const end = formatTimeVtt(entry.start + entry.duration);
        return `${start} --> ${end}\n${entry.text}\n`;
    }).join('\n');
    document.getElementById('vttView').textContent = vttContent;
    currentTranscript.vtt = vttContent;

    // MD view
    const mdContent = `# Transcript for ${data.video_id}\n\n` + data.transcript.map(entry => {
        return `**[${formatTime(entry.start)}]** ${entry.text}`;
    }).join('\n\n');
    document.getElementById('mdView').textContent = mdContent;
    currentTranscript.md = mdContent;

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

function escapeRegExp(string) {
    return string.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

if (searchInput) {
    searchInput.addEventListener('input', (e) => {
        const query = e.target.value.toLowerCase();
        
        // Highlight in timestamped view
        const segments = document.querySelectorAll('.segment');
        segments.forEach(seg => {
            const textEl = seg.querySelector('.segment__text');
            const originalText = textEl.dataset.original || textEl.textContent;
            if (!textEl.dataset.original) {
                textEl.dataset.original = originalText;
            }
            
            if (query) {
                const safeQuery = escapeRegExp(query);
                const regex = new RegExp(`(${safeQuery})`, 'gi');
                const highlighted = escapeHtml(originalText).replace(regex, '<mark>$1</mark>');
                textEl.innerHTML = highlighted;
                
                // hide/show segment based on match
                if (originalText.toLowerCase().includes(query)) {
                    seg.style.display = '';
                } else {
                    seg.style.display = 'none';
                }
            } else {
                textEl.innerHTML = escapeHtml(originalText);
                seg.style.display = '';
            }
        });
    });
}

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
    if (tab === 'vtt') return currentTranscript?.vtt || '';
    if (tab === 'md') return currentTranscript?.md || '';
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
    const extMap = { timestamped: 'txt', text: 'txt', srt: 'srt', vtt: 'vtt', md: 'md', json: 'json' };
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

// ── Google Auth ──────────────────────────────────────────────────────────

async function initAuth() {
    try {
        const res = await fetch('/api/config');
        if (res.ok) {
            const config = await res.json();
            googleClientId = config.google_client_id;
        }
    } catch (e) {}

    fetchMe();
}

async function fetchMe() {
    try {
        const res = await fetch('/api/auth/me');
        if (res.ok) {
            const data = await res.json();
            if (data.user) {
                renderUser(data.user);
            } else {
                renderGoogleButton();
            }
        }
    } catch (err) {}
}

function renderGoogleButton() {
    const authContainer = document.getElementById('userAuth');
    if (!authContainer) return;
    
    // We must wait for `google` to be available
    if (typeof google === 'undefined' || !googleClientId) {
        setTimeout(renderGoogleButton, 500);
        return;
    }
    
    authContainer.innerHTML = '<div id="googleButtonDiv"></div>';
    
    google.accounts.id.initialize({
        client_id: googleClientId,
        callback: handleCredentialResponse
    });
    
    google.accounts.id.renderButton(
        document.getElementById("googleButtonDiv"),
        { theme: "outline", size: "large", shape: "pill" }
    );
}

async function handleCredentialResponse(response) {
    try {
        const res = await fetch('/api/auth/google', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ credential: response.credential })
        });
        if (res.ok) {
            const data = await res.json();
            renderUser(data.user);
            fetchCredits(); 
            showToast("Successfully logged in!");
        } else {
            showStatus("Login failed.", "error");
        }
    } catch (e) {
        showStatus("Network error during login.", "error");
    }
}

function renderUser(user) {
    const authContainer = document.getElementById('userAuth');
    if (!authContainer) return;
    
    authContainer.innerHTML = `
        <div class="user-profile">
            <img src="${user.picture}" alt="Profile" class="user-profile__img" referrerpolicy="no-referrer">
            <span class="user-profile__name">${escapeHtml(user.name)}</span>
            <button onclick="showHistory()" class="btn btn--secondary" style="padding: 4px 10px; font-size: 0.8rem; border-radius: 999px;">History</button>
            <button onclick="logout()" class="btn btn--secondary" style="padding: 4px 10px; font-size: 0.8rem; border-radius: 999px;">Logout</button>
        </div>
    `;
}

async function logout() {
    try {
        await fetch('/api/auth/logout', { method: 'POST' });
        renderGoogleButton();
        fetchCredits(); 
        showToast("Logged out");
    } catch (e) {}
}

// ── History Modal ────────────────────────────────────────────────────────

async function showHistory() {
    const existing = document.querySelector('.modal-overlay');
    if (existing) existing.remove();

    const overlay = document.createElement('div');
    overlay.className = 'modal-overlay';
    overlay.innerHTML = `
        <div class="modal" style="max-width: 600px; width: 90%; max-height: 80vh; overflow-y: auto;">
            <div class="modal__icon">🕒</div>
            <h2 class="modal__title">Your History</h2>
            <div id="historyList" style="text-align: left; margin: 15px 0;">Loading...</div>
            <button class="btn btn--secondary" onclick="this.closest('.modal-overlay').remove()">Close</button>
        </div>
    `;

    overlay.addEventListener('click', (e) => {
        if (e.target === overlay) overlay.remove();
    });

    document.body.appendChild(overlay);

    try {
        const res = await fetch('/api/auth/history');
        const data = await res.json();
        
        const listEl = document.getElementById('historyList');
        if (!res.ok) {
            listEl.innerHTML = \`<p style="color: var(--danger)">Error: \${escapeHtml(data.error || 'Could not fetch history')}</p>\`;
            return;
        }

        if (!data.history || data.history.length === 0) {
            listEl.innerHTML = '<p>No history found.</p>';
            return;
        }

        listEl.innerHTML = data.history.map(item => \`
            <div style="background: var(--bg-card); padding: 10px; margin-bottom: 10px; border-radius: 8px; cursor: pointer; border: 1px solid var(--border);" onclick="loadHistoryItem('\${item.video_id}', '\${item.language || ''}')">
                <div style="font-weight: 500; margin-bottom: 4px;">Video ID: \${item.video_id}</div>
                <div style="font-size: 0.85rem; color: var(--text-muted); display: flex; justify-content: space-between;">
                    <span>Language: \${item.language || 'Default'}</span>
                    <span>\${new Date(item.created_at).toLocaleString()}</span>
                </div>
            </div>
        \`).join('');

    } catch (err) {
        document.getElementById('historyList').innerHTML = '<p style="color: var(--danger)">Network error.</p>';
    }
}

function loadHistoryItem(videoId, lang) {
    document.querySelector('.modal-overlay')?.remove();
    urlInput.value = \`https://www.youtube.com/watch?v=\${videoId}\`;
    langInput.value = lang || '';
    fetchTranscript();
}

// ── Init ─────────────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
    // Fetch credit balance on page load
    fetchCredits();
    initAuth();
});
