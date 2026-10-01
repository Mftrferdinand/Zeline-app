/* Zeline FE — part 1: state, API client, utils, modal, toast */
'use strict';

const DEV_SESSION_KEYS = ['zeline.connection', 'zeline.account', 'zeline.token', 'zeline.gatewayToken'];

let API = '/api/v1';
const LS_TOKEN = 'zeline.token';
const LS_ACTIVE_AGENT = 'zeline.activeAgent';
const LS_ACTIVE_SESSION = 'zeline.activeSession';
const LS_ACTIVE_ROOM = 'zeline.activeRoom';
const LS_REGISTRATION_PENDING = 'zeline.registrationPending';
const LS_AGENT_CACHE = 'zeline.agentCache';
const LS_SESSION_CACHE = 'zeline.sessionCache';
const LS_MESSAGE_CACHE_PREFIX = 'zeline.messageCache.';
const ZELINE_CHAT_AVATAR = 'assets/zeline-chat-avatar.png?v=2';
const fixedChatAvatar = (alt = 'Zeline') => `<img class="fixed-chat-avatar" src="${ZELINE_CHAT_AVATAR}" alt="${esc(alt)}" draggable="false">`;

const S = {
  token: localStorage.getItem(LS_TOKEN) || '',
  agents: [], providers: [], sessions: [], messages: [],
  agentId: localStorage.getItem(LS_ACTIVE_AGENT),
  sessionId: localStorage.getItem(LS_ACTIVE_SESSION), model: null,
  chatMode: 'general',
  attachments: [],
  streaming: false, abort: null, health: null, status: null,
  roomLoadVersion: 0,
  opt: {
    autoScroll: true, toolOpen: false, compact: false,
    ...JSON.parse(localStorage.getItem('zeline.opt') || '{}')
  },
  page: 'chat', filterAgent: 'all', q: ''
};

const $ = (id) => document.getElementById(id);
const el = (tag, cls, html) => {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (html != null) n.innerHTML = html;
  return n;
};
const esc = (s) => String(s == null ? '' : s)
  .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

const saveOpt = () => localStorage.setItem('zeline.opt', JSON.stringify(S.opt));

function readAgentCache() {
  try {
    const cached = JSON.parse(localStorage.getItem(LS_AGENT_CACHE) || '[]');
    return Array.isArray(cached) ? cached.filter(agent => agent && agent.id && agent.name) : [];
  } catch (_) { return []; }
}
function hydrateAgentCache() {
  if (!S.agents.length) S.agents = readAgentCache();
  return S.agents;
}
function saveAgentCache(agents) {
  const safe = Array.isArray(agents) ? agents.filter(agent => agent && agent.id && agent.name) : [];
  localStorage.setItem(LS_AGENT_CACHE, JSON.stringify(safe));
}
function readSessionCache() {
  try {
    const cached = JSON.parse(localStorage.getItem(LS_SESSION_CACHE) || '[]');
    return Array.isArray(cached) ? cached.filter(session => session && session.id && session.agent_id) : [];
  } catch (_) { return []; }
}
function hydrateSessionCache() {
  if (!S.sessions.length) S.sessions = readSessionCache();
  return S.sessions;
}
function saveSessionCache(sessions) {
  const safe = Array.isArray(sessions) ? sessions.filter(session => session && session.id && session.agent_id) : [];
  localStorage.setItem(LS_SESSION_CACHE, JSON.stringify(safe));
}
function messageCacheKey(sessionId) { return LS_MESSAGE_CACHE_PREFIX + String(sessionId || ''); }
function readMessageCache(sessionId) {
  if (!sessionId) return [];
  try {
    const cached = JSON.parse(localStorage.getItem(messageCacheKey(sessionId)) || '[]');
    return Array.isArray(cached) ? cached : [];
  } catch (_) { return []; }
}
function saveMessageCache(sessionId, messages) {
  if (!sessionId || !Array.isArray(messages)) return;
  // Bound storage while keeping the most recent visible history available offline.
  const safe = messages.slice(-300);
  try { localStorage.setItem(messageCacheKey(sessionId), JSON.stringify(safe)); }
  catch (_) { /* cache is best-effort; runtime persistence remains authoritative */ }
}
function reconcileMessageHistory(sessionId, fetched, hint = null) {
  const incoming = Array.isArray(fetched) ? fetched : [];
  const cached = readMessageCache(sessionId);
  const byId = new Map(cached.filter(message => message?.id).map(message => [message.id, message]));
  const cachedAssistants = cached.filter(message => message?.role === 'assistant');
  let assistantIndex = 0;
  /* The live turn's activity log lives on the optimistic (local) assistant and is
     handed in as `hint`. Attach it to the LAST assistant of the incoming batch so
     the finished message keeps every step even when ids don't line up. */
  const lastAssistantId = (() => {
    for (let i = incoming.length - 1; i >= 0; i--) if (incoming[i].role === 'assistant') return incoming[i].id;
    return null;
  })();
  const hintEvents = hint?.metadata?.activity_events || [];
  const hintHistory = hint?.metadata?.activity_history || [];
  const merged = incoming.map(message => {
    const local = byId.get(message.id) || (message.role === 'assistant' ? cachedAssistants[assistantIndex++] : null);
    let activity = local?.metadata?.activity_events;
    let history = local?.metadata?.activity_history;
    if (message.role === 'assistant' && message.id === lastAssistantId && (hintEvents.length || hintHistory.length)) {
      activity = hintEvents.length ? hintEvents : activity;
      history = hintHistory.length ? hintHistory : history;
    }
    if (!activity?.length && !history?.length) return message;
    return { ...message, metadata: { ...(message.metadata || {}), activity_events: activity || [], activity_history: history || [] } };
  });
  const pendingLocal = cached.filter(message => String(message?.id || '').startsWith('local_') && ['sending', 'streaming'].includes(message.status));
  const authoritativeKeys = new Set(incoming.map(message => `${message.role}\u0000${String(message.content || '').trim()}`));
  const unresolved = pendingLocal.filter(message => {
    const key = `${message.role}\u0000${String(message.content || '').trim()}`;
    if (message.role === 'user') return !authoritativeKeys.has(key);
    const localAt = Date.parse(message.created_at || '') || 0;
    return !incoming.some(item => item.role === 'assistant' && (Date.parse(item.created_at || '') || 0) >= localAt);
  });
  return [...merged, ...unresolved].sort((a, b) => (Date.parse(a.created_at || '') || 0) - (Date.parse(b.created_at || '') || 0));
}
function clearMessageCache(sessionId) {
  if (sessionId) localStorage.removeItem(messageCacheKey(sessionId));
}

/* Fill any static [data-zi] placeholder in index.html with its Cupertino SVG.
   Runs once at boot; dynamic UI uses ZI() inline. */
function hydrateStaticIcons(root = document) {
  root.querySelectorAll('[data-zi]').forEach(node => {
    const name = node.getAttribute('data-zi');
    if (name && typeof ZI === 'function') node.innerHTML = ZI(name);
  });
}
if (typeof window !== 'undefined') window.hydrateStaticIcons = hydrateStaticIcons;

/* ─────────────────────── Agent status vocabulary ───────────────────────
   Canonical activity/connection labels grouped into 5 colour tones. The tone
   drives the dot colour (green/blue/yellow/red/white) everywhere the status is
   shown (agent cards + chat room head). statusTone(label) resolves any label to
   its tone; unknown labels fall back to 'green'. */
const STATUS_TONE = {
  // Green — connected / thinking
  'Connected': 'green', 'Thinking...': 'green', 'Analyzing...': 'green', 'Processing...': 'green',
  // Blue — execution
  'Searching...': 'blue', 'Browsing...': 'blue', 'Reading...': 'blue', 'Reading data...': 'blue',
  'Reading skill...': 'blue', 'Self Improvement...': 'blue', 'Cron Job...': 'blue',
  'Writing...': 'blue', 'Coding...': 'blue', 'Editing...': 'blue',
  'Running...': 'blue', 'Generating...': 'blue',
  // Yellow — waiting / connection
  'Waiting...': 'yellow', 'Reconnecting...': 'yellow',
  // Red — error
  'Disconnected': 'red', 'Provider error': 'red', 'Rate limited': 'red', 'Raye limited': 'red', 'Failed': 'red',
  // White — neutral
  'Paused': 'white', 'Completed': 'white', 'Cancelled': 'white'
};
function statusTone(label) { return STATUS_TONE[label] || 'green'; }
if (typeof window !== 'undefined') { window.STATUS_TONE = STATUS_TONE; window.statusTone = statusTone; }

function connectionConfig() {
  try { return JSON.parse(localStorage.getItem('zeline.connection') || 'null'); }
  catch (_) { return null; }
}
function clearPendingRegistrationState() {
  localStorage.removeItem(LS_REGISTRATION_PENDING);
  localStorage.removeItem('zeline.connection');
  localStorage.removeItem('zeline.account');
  localStorage.removeItem(LS_TOKEN);
  S.token = '';
}

function initOnboarding() {
  /* Never hijack the screen once the user is already inside the app. The boot
     sequence (`startZelineApp` -> `initOnboarding_ifNeeded`) can finish AFTER
     the user has tapped a shortcut on the home hub — and this function used to
     force `hidden = false` unconditionally, throwing a full-screen black
     onboarding overlay over the page they had just navigated to. That is the
     "tap Providers and it snaps back to the welcome/home screen" bug: the page
     DID change underneath, it was just covered. */
  if (window.__zelineAppEntered || (typeof S !== 'undefined' && S && S.page && S.page !== 'chat')) return false;
  if (window.__zelineOnboardingShown) return true;
  const root = $('onboarding'); if (!root) return false; root.hidden = false;
  window.__zelineOnboardingShown = true;
  const showProfile = () => {
    $('authOptions').hidden = true;
    $('connectForm').hidden = true;
    $('profileForm').hidden = false;
    $('onboardingTitle').textContent = 'Name for your agent';
    $('onboardingDescription').textContent = 'Tell Zeline what to call you.';
    $('profileName').focus();
  };
  const showAuth = () => {
    $('authOptions').hidden = false;
    $('connectForm').hidden = true;
    $('profileForm').hidden = true;
    $('onboardingTitle').textContent = 'Welcome to Zeline';
    $('onboardingDescription').textContent = 'Chat with your agents from anywhere. Connect your account and sync your Zeline runtimes.';
  };
  const showConnect = () => {
    $('authOptions').hidden = true;
    $('profileForm').hidden = true;
    $('connectForm').hidden = false;
    $('onboardingTitle').textContent = 'Connect to your runtime';
    $('onboardingDescription').textContent = 'Paste the access token from your Zeline CLI runtime to connect this app.';
    $('connectToken').focus();
  };
  showAuth();
  document.querySelectorAll('[data-auth]').forEach(btn => btn.onclick = () => {
    if (btn.dataset.auth === 'google') {
      localStorage.setItem(LS_REGISTRATION_PENDING, 'google');
      showProfile();
    } else if (btn.dataset.auth === 'agent') {
      showConnect();
    } else toast('GitHub sign-in will be connected here', 'info', 2800);
  });
  $('connectBack').onclick = showAuth;
  $('connectForm').onsubmit = async (e) => {
    e.preventDefault();
    const rawUrl = $('connectUrl').value.trim() || 'localhost:8082';
    const token = $('connectToken').value.trim();
    if (!token) return;
    const apiBase = normalizeGatewayBase(rawUrl);
    // The runtime access token is the gateway credential. Exchange it for the
    // short-lived Bearer session before calling /agents; an agent token is a
    // different credential and must not be presented as the app gateway token.
    const prevApi = API, prevToken = S.token;
    API = apiBase; S.token = '';
    try {
      const auth = await api('/auth/login', {
        method: 'POST', body: { gateway_token: token }, timeoutMs: 10000
      });
      if (!auth?.access_token) throw new Error('Runtime tidak mengembalikan access session');
      S.token = auth.access_token;
      const data = await api('/agents');
      const agent = (data.agents || [])[0];
      if (!agent) throw new Error('Token is valid but the runtime has no agent');
      localStorage.setItem('zeline.connection', JSON.stringify({ configured: true, kind: 'gateway', apiBase }));
      localStorage.setItem('zeline.gatewayToken', token);
      localStorage.setItem(LS_TOKEN, S.token);
      localStorage.setItem('zeline.account', JSON.stringify({ id: agent.id, name: agent.name || 'Zeline', kind: 'gateway', profile_complete: true }));
      localStorage.removeItem(LS_REGISTRATION_PENDING);
      root.hidden = true;
      window.startZelineApp?.({ restoreConversation: false });
    } catch (err) {
      API = prevApi; S.token = prevToken;
      toast(err.code === 'UNAUTHORIZED' || err.code === 'INVALID_TOKEN'
        ? 'Agent token rejected — check the token again' : (err.message || 'Connection failed'), 'err', 5000);
    }
  };
  $('profileForm').onsubmit = (e) => {
    e.preventDefault();
    const name = $('profileName').value.trim();
    if (!name) return;
    localStorage.setItem('zeline.connection', JSON.stringify({ configured: true, kind: 'account', provider: 'google', apiBase: '/api/v1' }));
    localStorage.setItem('zeline.account', JSON.stringify({ id: 'demo_google_user', name, agent_call_name: name, provider: 'google', demo: true, language: $('profileLanguage').value, profile_complete: true }));
    localStorage.removeItem(LS_REGISTRATION_PENDING);
    root.hidden = true;
    window.startZelineApp?.({ restoreConversation: false });
  };
  return true;
};

/* Turn a user-typed gateway address into an /api/v1 base URL.
   'localhost:8082' → 'http://localhost:8082/api/v1'; a full URL is respected. */
function normalizeGatewayBase(raw) {
  let s = String(raw || '').trim().replace(/\/+$/, '');
  if (!/^https?:\/\//i.test(s)) s = 'http://' + s;
  if (!/\/api\/v\d+$/.test(s)) s += '/api/v1';
  return s;
}
if (typeof window !== 'undefined') window.normalizeGatewayBase = normalizeGatewayBase;

/* Decide at boot whether to show onboarding. A returning user with a saved,
   configured connection (agent-token or account) skips straight into the app;
   otherwise onboarding runs. Returns true when onboarding took over the screen. */
function initOnboarding_ifNeeded() {
  // An interrupted Google profile registration is never a valid signed-in state.
  // Restart from the provider choice instead of resuming an ambiguous half-profile.
  if (localStorage.getItem(LS_REGISTRATION_PENDING)) {
    clearPendingRegistrationState();
    return initOnboarding();
  }
  const conn = connectionConfig();
  const account = (() => { try { return JSON.parse(localStorage.getItem('zeline.account') || 'null'); } catch (_) { return null; } })();
  const ready = conn && conn.configured && (conn.kind === 'agent' ? Boolean(S.token) : account && account.profile_complete);
  if (ready) { $('onboarding').hidden = true; return false; }
  return initOnboarding();
}
if (typeof window !== 'undefined') window.initOnboarding_ifNeeded = initOnboarding_ifNeeded;

function timeAgo(iso) {
  const t = Date.parse(iso);
  if (!t) return '—';
  const d = (Date.now() - t) / 1000;
  if (d < 60) return 'baru saja';
  if (d < 3600) return Math.floor(d / 60) + 'm lalu';
  if (d < 86400) return Math.floor(d / 3600) + 'j lalu';
  return Math.floor(d / 86400) + 'h lalu';
}

function clock(iso) {
  const t = new Date(iso || Date.now());
  return isNaN(t) ? '' : t.toTimeString().slice(0, 5);
}

/* Links become plain blue inline anchors (NO card/bubble). Handles both
   markdown links [label](url) and bare http(s) URLs. Runs only on text OUTSIDE
   <code>/<pre> so URLs inside real code blocks stay literal. Called after
   code/bold.
   EXCEPTION: agents very often wrap a URL in `backticks`, which md() already
   turned into a <code> card. A code span whose ONLY content is a URL is NOT
   real code — it's a link the model mono-styled — so we unwrap it to a plain
   blue anchor instead of leaving it as a card. */
function linkify(s) {
  // First: any <code>…</code> that contains nothing but a URL → inline link,
  // not a card. (Uses &amp; because esc() already ran.) <pre> blocks are left
  // alone — multi-line code is real code.
  s = s.replace(/<code>\s*((?:https?:\/\/|www\.)[^<\s]+?)\s*<\/code>/gi, (_, raw) => {
    const href = (/^https?:\/\//i.test(raw) ? raw : 'https://' + raw).replace(/&amp;/g, '&');
    return `<a class="msg-link" href="${href.replace(/&/g, '&amp;')}" target="_blank" rel="noopener noreferrer">${raw}</a>`;
  });
  // Next: a <code>owner/repo</code> GitHub slug → blue link to the repo, NOT a
  // code card. The model very often backticks a repo name (e.g.
  // `Mftrferdinand/Zeline-MCP`) and it was left as a grey card. We convert it to
  // github.com/owner/repo. EXCLUDE known model-provider prefixes so a model id
  // like `anthropic/claude-sonnet-4` or `google/gemini-2.5-pro` STAYS a code
  // span (those are not repos). Slug = two path segments, no spaces, and NOT
  // containing a version-y colon.
  const MODEL_VENDORS = /^(anthropic|openai|google|meta-llama|mistralai|x-ai|xai|deepseek|qwen|cohere|perplexity|groq|together|fireworks|hcn|gr|glm|cbai|cb|ag|nousresearch)$/i;
  s = s.replace(/<code>\s*([A-Za-z0-9][\w.-]*)\/([A-Za-z0-9][\w.-]*)\s*<\/code>/g, (whole, owner, repo) => {
    if (MODEL_VENDORS.test(owner)) return whole;   // model id → keep as code
    const slug = `${owner}/${repo}`;
    return `<a class="msg-link" href="https://github.com/${slug}" target="_blank" rel="noopener noreferrer">${slug}</a>`;
  });
  // Split on the remaining code/pre spans; only the even (non-code) segments get linked.
  return s.split(/(<pre[\s\S]*?<\/pre>|<code>[\s\S]*?<\/code>)/g).map((seg, i) => {
    if (i % 2) return seg; // odd = a code/pre chunk, leave untouched
    // 1) markdown links [label](url) — the label is shown, the url is HIDDEN
    //    behind it (masked link). URL may itself be wrapped in the code span we
    //    just unwrapped, so accept an optional surrounding anchor too.
    seg = seg.replace(/\[([^\]]+)\]\(\s*(?:<a[^>]*href="([^"]+)"[^>]*>[^<]*<\/a>|((?:https?:\/\/|www\.)[^\s)]+))\s*\)/g,
      (_, label, hrefAnchor, hrefBare) => {
        const raw = hrefAnchor || hrefBare || '';
        const href = /^https?:\/\//i.test(raw) ? raw : 'https://' + raw;
        return `<a class="msg-link" href="${href}" target="_blank" rel="noopener noreferrer">${label}</a>`;
      });
    // 2) bare URLs not already inside an href="..." or an anchor's text
    seg = seg.replace(/(^|[\s(])(https?:\/\/[^\s<)]+)/g,
      (_, pre, url) => `${pre}<a class="msg-link" href="${url}" target="_blank" rel="noopener noreferrer">${url}</a>`);
    // 3) bare GitHub owner/repo slug in plain prose (not backticked, not a URL).
    //    Same model-vendor exclusion. Requires a leading boundary so paths inside
    //    words are ignored.
    seg = seg.replace(/(^|[\s(])([A-Za-z0-9][\w.-]*)\/([A-Za-z0-9][\w.-]*)(?=[\s.,;:)!?]|$)/g,
      (whole, pre, owner, repo) => {
        if (MODEL_VENDORS.test(owner)) return whole;
        // Skip if it's clearly a path fragment (has another slash right after).
        const slug = `${owner}/${repo}`;
        return `${pre}<a class="msg-link" href="https://github.com/${slug}" target="_blank" rel="noopener noreferrer">${slug}</a>`;
      });
    return seg;
  }).join('');
}

/* markdown parser: heading, bold, italic, strikethrough, list (ul/ol),
   tabel, blockquote, hr, image, link, inline & block code, newline.
   Aman: esc() dijalankan LEBIH DULU, jadi semua konten sudah di-escape;
   markup HTML yang kita tambahkan sendiri yang aktif. */
function md(src) {
  const raw = String(src == null ? '' : src);

  // 1) Lindungi block code ```…``` dulu (sebelum esc/parsing) pakai placeholder.
  const codeBlocks = [];
  let s = raw.replace(/```(\w*)\n?([\s\S]*?)```/g, (_, lang, body) => {
    const idx = codeBlocks.length;
    const cls = lang ? ` class="lang-${esc(lang)}"` : '';
    codeBlocks.push(`<pre><code${cls}>${esc(body.replace(/\n$/, ''))}</code></pre>`);
    return `\u0000CB${idx}\u0000`;
  });

  // 2) Lindungi inline code `…` juga.
  const inlineCodes = [];
  s = s.replace(/`([^`\n]+)`/g, (_, body) => {
    const idx = inlineCodes.length;
    inlineCodes.push(`<code>${esc(body)}</code>`);
    return `\u0000IC${idx}\u0000`;
  });

  // 3) Escape sisanya (teks biasa).
  s = esc(s);

  // 4) Inline formatting (bold/italic/strikethrough/image/link) — dipakai per-baris.
  const inline = (t) => {
    // image ![alt](url) — HARUS sebelum link
    t = t.replace(/!\[([^\]]*)\]\(\s*([^)\s]+)(?:\s+"[^"]*")?\s*\)/g,
      (_, alt, url) => {
        const safe = /^(https?:|data:)/i.test(url) ? url : '';
        return safe
          ? `<img class="msg-img" src="${safe.replace(/"/g,'&quot;')}" alt="${alt}" loading="lazy">`
          : alt;
      });
    // link [label](url)
    t = t.replace(/\[([^\]]+)\]\(\s*([^)\s]+)(?:\s+"[^"]*")?\s*\)/g,
      (_, label, url) => {
        const href = /^https?:\/\//i.test(url) ? url : (/^(mailto:|tel:|#|\/)/i.test(url) ? url : 'https://' + url);
        return `<a class="msg-link" href="${href.replace(/"/g,'&quot;')}" target="_blank" rel="noopener noreferrer">${label}</a>`;
      });
    // bold **x** atau __x__  (non-greedy, boleh ada * tunggal di dalam)
    t = t.replace(/\*\*([\s\S]+?)\*\*/g, '<strong>$1</strong>');
    t = t.replace(/__([^_\n]+?)__/g, '<strong>$1</strong>');
    // italic *x* atau _x_  (hindari ** yang sudah jadi strong)
    t = t.replace(/(^|[^*])\*([^*\n]+?)\*(?!\*)/g, '$1<em>$2</em>');
    t = t.replace(/(^|[^_])_([^_\n]+?)_(?!_)/g, '$1<em>$2</em>');
    // strikethrough ~~x~~
    t = t.replace(/~~([\s\S]+?)~~/g, '<del>$1</del>');
    return t;
  };

  // 5) Parse blok baris-per-baris: heading, hr, tabel, list, blockquote, paragraf.
  const lines = s.split('\n');
  const out = [];
  let i = 0;

  const isTableSep = (l) => /^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)+\|?\s*$/.test(l);
  const splitRow = (l) => l.replace(/^\s*\|/, '').replace(/\|\s*$/, '').split('|').map(c => c.trim());

  while (i < lines.length) {
    let line = lines[i];

    // baris kosong → skip (pemisah blok)
    if (/^\s*$/.test(line)) { i++; continue; }

    // horizontal rule
    if (/^\s*(---|\*\*\*|___)\s*$/.test(line)) { out.push('<hr>'); i++; continue; }

    // heading  # .. ######
    const h = line.match(/^\s*(#{1,6})\s+(.*)$/);
    if (h) { out.push(`<h${h[1].length}>${inline(h[2].trim())}</h${h[1].length}>`); i++; continue; }

    // TABEL: header row + separator row
    if (/\|/.test(line) && i + 1 < lines.length && isTableSep(lines[i + 1])) {
      const header = splitRow(line);
      i += 2; // lewati header + separator
      const rows = [];
      while (i < lines.length && /\|/.test(lines[i]) && !/^\s*$/.test(lines[i])) {
        rows.push(splitRow(lines[i])); i++;
      }
      let html = '<div class="md-table-wrap"><table class="md-table"><thead><tr>';
      html += header.map(c => `<th>${inline(c)}</th>`).join('');
      html += '</tr></thead><tbody>';
      html += rows.map(r => '<tr>' + header.map((_, ci) => `<td>${inline((r[ci] || '').trim())}</td>`).join('') + '</tr>').join('');
      html += '</tbody></table></div>';
      out.push(html);
      continue;
    }

    // blockquote  > ...  (esc sudah ubah '>' jadi '&gt;')
    if (/^\s*&gt;\s?/.test(line)) {
      const buf = [];
      while (i < lines.length && /^\s*&gt;\s?/.test(lines[i])) {
        buf.push(lines[i].replace(/^\s*&gt;\s?/, '')); i++;
      }
      out.push(`<blockquote>${buf.map(b => inline(b)).join('<br>')}</blockquote>`);
      continue;
    }

    // unordered list  - / * / +
    if (/^\s*[-*+]\s+/.test(line)) {
      const items = [];
      while (i < lines.length && /^\s*[-*+]\s+/.test(lines[i])) {
        items.push(inline(lines[i].replace(/^\s*[-*+]\s+/, ''))); i++;
      }
      out.push('<ul>' + items.map(it => `<li>${it}</li>`).join('') + '</ul>');
      continue;
    }

    // ordered list  1. 2. 3.
    if (/^\s*\d+\.\s+/.test(line)) {
      const items = [];
      while (i < lines.length && /^\s*\d+\.\s+/.test(lines[i])) {
        items.push(inline(lines[i].replace(/^\s*\d+\.\s+/, ''))); i++;
      }
      out.push('<ol>' + items.map(it => `<li>${it}</li>`).join('') + '</ol>');
      continue;
    }

    // paragraf: kumpulkan baris berturut sampai baris kosong / blok lain
    const para = [];
    while (i < lines.length && !/^\s*$/.test(lines[i])
           && !/^\s*(#{1,6})\s+/.test(lines[i])
           && !/^\s*(---|\*\*\*|___)\s*$/.test(lines[i])
           && !/^\s*&gt;\s?/.test(lines[i])
           && !/^\s*[-*+]\s+/.test(lines[i])
           && !/^\s*\d+\.\s+/.test(lines[i])
           && !(/\|/.test(lines[i]) && i + 1 < lines.length && isTableSep(lines[i + 1]))) {
      para.push(lines[i]); i++;
    }
    if (para.length) {
      const joined = para.join('\n');
      // Kalau paragraf ISINYA cuma placeholder block-code, jangan bungkus <p>.
      if (/^\s*\u0000CB\d+\u0000\s*$/.test(joined)) {
        out.push(joined.trim());
      } else {
        out.push(`<p>${inline(joined).replace(/\n/g, '<br>')}</p>`);
      }
    }
  }

  let html = out.join('');

  // 6) linkify bare URL / github slug pada hasil (tidak menyentuh code/pre).
  html = linkify(html);

  // 7) kembalikan placeholder code.
  html = html.replace(/\u0000CB(\d+)\u0000/g, (_, n) => codeBlocks[+n] || '');
  html = html.replace(/\u0000IC(\d+)\u0000/g, (_, n) => inlineCodes[+n] || '');
  return html;
}

/* ───────────────────────── toast ───────────────────────── */
function toast(msg, kind = 'info', ms = 3200) {
  const t = el('div', 'toast ' + kind, `<span class="bar"></span><span>${esc(msg)}</span>`);
  $('toasts').appendChild(t);
  setTimeout(() => { t.style.opacity = '0'; setTimeout(() => t.remove(), 220); }, ms);
}

/* ───────────────────────── modal ───────────────────────── */
function wireModalAction(button, action) {
  button.onclick = async () => {
    if (!action.onClick) return closeModal();
    if (button.disabled) return;
    const label = button.textContent;
    button.disabled = true;
    button.setAttribute('aria-busy', 'true');
    button.textContent = action.pendingLabel || 'Please wait…';
    try {
      await action.onClick(closeModal);
    } catch (error) {
      toast(error?.message || 'Action failed', 'err');
    } finally {
      if (button.isConnected) {
        /* Restore the label, but do NOT force-enable: a handler may have
           deliberately locked a *different* button (or this one) as part of a
           gate — e.g. Create stays disabled until a Check passes. `is-locked`
           is the marker for "something owns this button's disabled state". */
        button.removeAttribute('aria-busy');
        button.textContent = label;
        if (!button.classList.contains('is-locked')) button.disabled = false;
      }
    }
  };
}

function modal({ title, subtitle, body, actions, compact = false, footerActions = false,
                popup = false }) {
  const shell = document.querySelector('.modal');
  const root = $('modalRoot');
  // Workspace search lives in the reusable modal header. Remove it before a
  // different screen reuses this shell so it can never leak into another modal.
  shell.querySelector('.modal-workspace-search')?.remove();
  shell.className = 'modal' + (compact ? ' compact-confirm-modal' : '')
    + (popup ? ' popup-sheet' : '');
  /* `popup` marks a centred dialog over the current screen rather than a
     full-screen Android takeover. It is a real class on the root, not a
     `:has()` guess, so the two can never disagree about which shape is
     wanted — and the flag is reset on every open. */
  root.classList.toggle('is-popup', popup);
  $('modalTitle').textContent = title;
  /* Optional one-line explanation under the title — 9Router's Add-Provider
     screen leads with one ("Configure a new AI provider to use with your
     applications."). Recreated each call so a previous subtitle can't leak
     into the next modal. */
  document.querySelector('.modal-head-subtitle')?.remove();
  if (subtitle) {
    const sub = el('p', 'modal-head-subtitle', esc(subtitle));
    $('modalTitle').insertAdjacentElement('afterend', sub);
  }
  const b = $('modalBody'); b.innerHTML = '';
  b.appendChild(typeof body === 'string' ? el('div', '', body) : body);
  const f = $('modalFoot'); f.innerHTML = '';
  const headAction = $('modalHeadAction');
  headAction.hidden = true;
  headAction.className = 'modal-head-action';
  headAction.onclick = null;
  const searchAction = $('modalSearchAction');
  if (searchAction) {
    searchAction.hidden = true;
    searchAction.className = 'modal-search-action';
    searchAction.innerHTML = '';
    searchAction.onclick = null;
  }

  const list = actions || [];
  /* `footerActions` keeps every button in the bottom bar instead of promoting
     the primary into the header. Screens with a real form (Add Provider) want
     the confirm action next to the fields it submits, not above them. */
  const primaryIndex = (compact || footerActions)
    ? -1
    : list.findLastIndex(action => action.kind === 'primary' || action.kind === 'danger');
  list.forEach((action, index) => {
    if (index === primaryIndex) {
      headAction.textContent = action.label;
      headAction.classList.toggle('danger', action.kind === 'danger');
      headAction.hidden = false;
      wireModalAction(headAction, action);
      return;
    }
    // Full-screen Android surfaces use the left Back control for dismiss; only
    // compact confirmations and explicit footerActions keep footer choices.
    if (!compact && !footerActions && !action.onClick) return;
    const button = el('button', 'btn ' + (action.kind || 'ghost'), esc(action.label));
    wireModalAction(button, action);
    f.appendChild(button);
  });
  $('modalRoot').hidden = false;
  document.body.classList.add('modal-open');
}
function closeModal() {
  $('modalRoot').hidden = true;
  $('modalRoot').classList.remove('is-popup');
  $('modalHeadAction').hidden = true;
  const searchAction = $('modalSearchAction');
  if (searchAction) {
    searchAction.hidden = true;
    searchAction.onclick = null;
    searchAction.innerHTML = '';
  }
  document.body.classList.remove('modal-open');
}

function field(label, id, opts = {}) {
  const w = el('div', 'field');
  const lab = el('label', '', esc(label));
  lab.setAttribute('for', id);
  // A visible marker on required fields, same convention 9Router uses.
  if (opts.required) lab.insertAdjacentHTML('beforeend', ' <b class="field-req">*</b>');
  w.appendChild(lab);
  /* `desc` sits BETWEEN the label and the control — title, description, then
     the input. `hint` keeps the older below-the-control placement so existing
     screens are untouched. */
  if (opts.desc) w.appendChild(el('small', 'field-desc', esc(opts.desc)));
  let inp;
  if (opts.tag === 'textarea') { inp = el('textarea'); inp.rows = opts.rows || 4; }
  else if (opts.tag === 'select') {
    inp = el('select');
    (opts.options || []).forEach(o => {
      const op = el('option', '', esc(o.label));
      op.value = o.value; inp.appendChild(op);
    });
  } else { inp = el('input'); inp.type = opts.type || 'text'; }
  inp.id = id;
  // `value` must be applied AFTER the options exist, or a <select> silently
  // falls back to its first option.
  if (opts.value != null) inp.value = opts.value;
  if (opts.placeholder) inp.placeholder = opts.placeholder;
  if (opts.disabled) inp.disabled = true;
  w.appendChild(inp);
  if (opts.hint) w.appendChild(el('small', '', esc(opts.hint)));
  return w;
}

function checkGrid(items, selected) {
  const g = el('div', 'check-grid');
  items.forEach(it => {
    const l = el('label', 'check');
    const cb = el('input'); cb.type = 'checkbox'; cb.value = it;
    cb.checked = (selected || []).includes(it);
    l.appendChild(cb); l.appendChild(el('span', '', esc(it)));
    g.appendChild(l);
  });
  return g;
}
const checked = (root) =>
  [...root.querySelectorAll('.check input:checked')].map(i => i.value);

function normalizeAgentName(value) {
  return String(value || '').replace(/[^A-Za-z0-9 ]/g, '').replace(/\s+/g, ' ').trimStart().slice(0, 25);
}

function wireAgentNameInput(input) {
  if (!input) return input;
  input.maxLength = 25;
  input.inputMode = 'text';
  input.pattern = '[A-Za-z0-9 ]{1,25}';
  input.oninput = () => {
    const next = normalizeAgentName(input.value);
    if (input.value !== next) input.value = next;
  };
  return input;
}

function validAgentName(value) {
  return /^[A-Za-z0-9](?:[A-Za-z0-9 ]{0,24})$/.test(String(value || '').trim());
}

/* ───────────────────────── API ───────────────────────── */
async function api(path, { method = 'GET', body, raw, timeoutMs = 0 } = {}) {
  const headers = { 'Content-Type': 'application/json' };
  if (S.token) headers.Authorization = 'Bearer ' + S.token;
  const controller = timeoutMs ? new AbortController() : null;
  const timeout = controller ? setTimeout(() => controller.abort(), timeoutMs) : null;
  let res;
  try {
    res = await fetch(API + path, {
      method, headers, body: body ? JSON.stringify(body) : undefined,
      signal: controller?.signal
    });
  } catch (error) {
    if (error?.name === 'AbortError') throw new Error(`Request timed out after ${Math.ceil(timeoutMs / 1000)}s`);
    throw error;
  } finally {
    if (timeout) clearTimeout(timeout);
  }
  if (raw) return res;
  const j = await res.json().catch(() => ({}));
  if (!res.ok || j.error) {
    const e = new Error(j.error?.message || 'HTTP ' + res.status);
    e.code = j.error?.code || 'INTERNAL_ERROR';
    throw e;
  }
  return j.data;
}

async function login() {
  // Token gateway diambil dari dev server (env ZELINE_APP_TOKEN), bukan hardcode.
  let gatewayToken = localStorage.getItem('zeline.gatewayToken') || 'dev-local-gateway-token';
  try {
    const cfg = await fetch('/__dev/config').then(r => r.ok ? r.json() : null);
    if (cfg && cfg.gateway_token) gatewayToken = cfg.gateway_token;
    if (cfg) S.devMode = cfg.mode;
  } catch (_) { /* dev config opsional */ }
  const d = await api('/auth/login', {
    method: 'POST', body: { gateway_token: gatewayToken }, timeoutMs: 10000
  });
  S.token = d.access_token;
  S.authMeta = d;
  localStorage.setItem(LS_TOKEN, S.token);
  return d;
}

async function ensureAuth() {
  // A saved gateway connection already has a short-lived Bearer session.
  // Reuse it first; login() below re-exchanges the stored runtime access token
  // only when the session has expired.
  const conn = connectionConfig();
  if (conn && conn.kind === 'gateway' && S.token) {
    try { await api('/agents', { timeoutMs: 10000 }); return; }
    catch (e) { if (e.code !== 'UNAUTHORIZED' && e.code !== 'INVALID_TOKEN') throw e; }
  }
  if (!S.token) await login();
  try { await api('/agents', { timeoutMs: 10000 }); }
  catch (e) { if (e.code === 'UNAUTHORIZED' || e.code === 'INVALID_TOKEN') await login(); }
}

