/* Zeline FE — part 3: pages (sessions, agents, providers, settings) */
'use strict';

const expandedAgentSessions = new Set();
const SESSION_READ_KEY = 'zeline.sessionReadAt';
const WORKSPACE_KIND_KEY = 'zeline.workspaceKind';

// One chat engine, four user-visible workspace contexts. Older browser caches
// and API records used `saved` / `cron`; normalize them at this boundary so a
// legacy conversation stays intact while all new UI/API calls use canonical
// names.
const WORKSPACE_KINDS = ['session', 'project', 'cronjob', 'workflow'];
const WORKSPACE_KIND_ALIASES = {
  saved: 'session', sessions: 'session',
  cron: 'cronjob', 'cron-job': 'cronjob', cron_job: 'cronjob', cronjobs: 'cronjob',
  projects: 'project', workflows: 'workflow',
};
function canonicalWorkspaceKind(value, fallback = 'session') {
  const raw = String(value || '').trim().toLowerCase().replace(/_/g, '-');
  if (raw === 'general') return 'general';
  const kind = WORKSPACE_KIND_ALIASES[raw] || raw;
  return WORKSPACE_KINDS.includes(kind) ? kind : fallback;
}
const storedWorkspaceKind = canonicalWorkspaceKind(localStorage.getItem(WORKSPACE_KIND_KEY), 'session');
let activeWorkspaceKind = WORKSPACE_KINDS.includes(storedWorkspaceKind) ? storedWorkspaceKind : 'session';
localStorage.setItem(WORKSPACE_KIND_KEY, activeWorkspaceKind);
const isGeneralSession = session => session?.kind === 'general' || String(session?.title || '').startsWith('__general__');
function workspaceKindOf(session) {
  const kind = canonicalWorkspaceKind(session?.kind, 'session');
  if (session && kind !== 'general' && session.kind !== kind) session.kind = kind;
  return kind === 'general' ? 'session' : kind;
}

function sessionReadState() {
  try { return JSON.parse(localStorage.getItem(SESSION_READ_KEY) || '{}'); }
  catch { return {}; }
}

function markSessionRead(sessionId) {
  const state = sessionReadState();
  const session = S.sessions.find(item => item.id === sessionId);
  const now = new Date().toISOString();
  state[sessionId] = String(session?.updated_at || '') > now ? String(session.updated_at) : now;
  localStorage.setItem(SESSION_READ_KEY, JSON.stringify(state));
}

/* Real, content-backed unread: count assistant messages in a session that
   arrived AFTER the read cursor. An agent that never replied has 0 — no fake
   badge. Reading the room (markSessionRead) pushes the cursor to now → 0. */
function sessionUnreadCount(session) {
  if (!session?.id) return 0;
  const readAt = sessionReadState()[session.id] || '';
  return readMessageCache(session.id)
    .filter(m => m && m.role === 'assistant' && String(m.created_at || '') > readAt).length;
}

function sessionHasUnread(session) {
  return sessionUnreadCount(session) > 0;
}

const agentUnreadCount = agentId => S.sessions
  .filter(session => session.agent_id === agentId)
  .filter(isGeneralSession)
  .reduce((sum, session) => sum + sessionUnreadCount(session), 0);

/* Connection = which agent is ACTUALLY bound to this gateway via its agent
   token. Only the profile whose token authed this session (backend flag
   `is_connected_agent`) is Connected — every other profile is Unconnected, even
   though it has a provider+model configured. Having a provider/model only means
   the agent COULD run, not that it's linked to the running Termux gateway.
   Offline / failed health on the bound agent → Reconnected (retrying). */
function agentConnectionPresentation(agent) {
  const bound = Boolean(agent?.is_connected_agent);
  if (!bound) return { label: 'Unconnected', tone: 'red' };
  if (navigator.onLine === false || S.health?.ok === false) return { label: 'Reconnected', tone: 'yellow' };
  return { label: 'Connected', tone: 'green' };
}

/* INTERFACE card status — ZEROLINEAR ↔ Zeline Gateway connection (from /health +
   bound-agent flag). Vocabulary: Connected / Disconnected / Connecting… /
   Unauthorized / Connection failed. */
function interfaceStatus() {
  const hc = S.hc || {};
  if (hc.gateway === 'checking') return { label: 'Connecting…', tone: 'yellow' };
  const agent = S.agents[0] || null;
  const conn = agent ? agentConnectionPresentation(agent) : { label: 'Unconnected', tone: 'red' };
  if (hc.gateway === 'down') return { label: S.__ifReason || 'Connection failed', tone: 'red' };
  if (conn.label === 'Connected') return { label: 'Connected', tone: 'green' };
  if (conn.label === 'Reconnected') return { label: 'Connecting…', tone: 'yellow' };
  return { label: 'Disconnected', tone: 'red' };
}

/* GATEWAY card status — is the Zeline Gateway (runtime) up on the host? Sourced
   from the /system probe. Vocabulary: Running / Stopped / Checking… / Failed. */
function gatewayRunStatus() {
  const hc = S.hc || {};
  if (hc.environment === 'checking') return { label: 'Checking…', tone: 'yellow' };
  if (hc.environment === 'down') return { label: 'Failed', tone: 'red' };
  if (hc.environment === 'ok') return { label: 'Running', tone: 'green' };
  // idle / before any manual recheck → infer from the boot /system snapshot.
  return S.system ? { label: 'Running', tone: 'green' } : { label: 'Stopped', tone: 'red' };
}

function refreshAgentStatusesInPlace() {
  S.agents.forEach(agent => updateAgentCardStatusInPlace(agent.id));
}

const agentLiveActivity = new Map();

/* Session dot lifecycle: white pulse while the agent works, blue only after it
   settles. The settle delay absorbs slow networks so a stream that resumes
   typing keeps the dot white instead of flickering to blue and back. */
const SESSION_SETTLE_MS = 2600;
const liveSessions = new Set();
const sessionSettleTimers = new Map();

function clearSessionSettleTimer(sessionId) {
  const timer = sessionSettleTimers.get(sessionId);
  if (timer) clearTimeout(timer);
  sessionSettleTimers.delete(sessionId);
}

function setSessionLive(sessionId, live) {
  if (!sessionId) return;
  clearSessionSettleTimer(sessionId);
  if (live) {
    const changed = !liveSessions.has(sessionId);
    liveSessions.add(sessionId);
    if (changed) renderAgentHome();
    return;
  }
  if (!liveSessions.has(sessionId)) return;
  sessionSettleTimers.set(sessionId, setTimeout(() => {
    sessionSettleTimers.delete(sessionId);
    liveSessions.delete(sessionId);
    renderAgentHome();
  }, SESSION_SETTLE_MS));
}

function sessionIsLive(sessionId) {
  return liveSessions.has(sessionId);
}

/* Saved Session pins live in the SAME store as Agent pins — one pin feature, not
   two. Agent ids and session ids never collide, so a single `pinned` array holds
   both and a Session pin is a first-class main pin. */
function sessionIsPinned(sessionId) {
  return agentFlags().pinned.includes(sessionId);
}

function toggleSessionPin(session) {
  if (!session?.id) return false;
  const pinned = agentFlags().pinned.includes(session.id);
  pinned ? removePins([session.id]) : promotePins([session.id]);
  renderAgentHome();
  return !pinned;
}

function prunePinnedSession(sessionId) {
  removePins([sessionId]);
}

/* One-time migration from the short-lived separate Session pin store. */
function migrateLegacySessionPins() {
  const legacyRaw = localStorage.getItem('zeline.sessionFlags');
  if (!legacyRaw) return;
  try {
    const legacy = JSON.parse(legacyRaw);
    const ids = Array.isArray(legacy?.pinned) ? legacy.pinned : [];
    if (ids.length) {
      const flags = agentFlags();
      flags.pinned = [...ids.filter(id => !flags.pinned.includes(id)), ...flags.pinned];
      saveAgentFlags(flags);
    }
  } catch { /* discard unreadable legacy state */ }
  localStorage.removeItem('zeline.sessionFlags');
}

function setConversationLiveActivity(agentId, sessionId, label = '') {
  if (!agentId || !sessionId) return;
  const session = S.sessions.find(item => item.id === sessionId);
  const general = isGeneralSession(session);
  if (!general) return;
  if (label) agentLiveActivity.set(agentId, label);
  else agentLiveActivity.delete(agentId);
  // Smooth in-place update of just this agent's status pill (crossfade the label +
  // dot tone) instead of re-rendering the whole list, which would hard-swap and
  // flicker. Fall back to a full render only if the card isn't on screen yet.
  updateHubDmStatusInPlace(agentId);
  if (updateAgentCardStatusInPlace(agentId)) return;
  renderAgentHome();
}

/* Update one agent card's status label + tone with a soft crossfade. Returns true
   if the card was found and updated in place. */
function updateAgentCardStatusInPlace(agentId) {
  const card = document.querySelector(`.agent-card[data-agent-id="${agentId}"]`);
  const statusEl = card?.querySelector('.agent-card-status');
  if (!statusEl) return false;
  const agent = agentById(agentId);
  const liveLabel = agentLiveActivity.get(agentId);
  // Line 2 mirrors renderAgentHome: live action label while busy, else the
  // agent's latest chat preview, else the connection state.
  const connection = agentConnectionPresentation(agent);
  const general = generalSessionForAgent(agentId);
  const preview = String(general?.last_preview || '').replace(/\s+/g, ' ').trim();
  const label = liveLabel || preview || connection.label;
  const tone = liveLabel ? statusTone(liveLabel) : (preview ? 'white' : connection.tone);
  if (statusEl.dataset.label === label) return true;   // no change → no flicker
  // Crossfade: fade out, swap text/tone/classes, fade back in.
  statusEl.classList.add('status-swapping');
  setTimeout(() => {
    statusEl.className = 'agent-card-status tone-' + tone + (liveLabel ? ' busy' : '');
    statusEl.dataset.label = label;
    const labelNode = statusEl.childNodes[statusEl.childNodes.length - 1];
    if (labelNode && labelNode.nodeType === 3) labelNode.textContent = label;
    else statusEl.textContent = label;
    requestAnimationFrame(() => statusEl.classList.remove('status-swapping'));
  }, 130);
  return true;
}

/* The home DM card mirrors the existing general-room live activity. Keep this
   paint-only so starting/stopping a stream never rebuilds the hub. */
function updateHubDmStatusInPlace(agentId) {
  const card = document.querySelector('.hub-dm-card');
  const preview = card?.querySelector('.hub-dm-preview');
  if (!card || !preview) return false;
  const agent = agentById(agentId);
  if (!agent || agent.id !== S.agents[0]?.id) return false;
  const typing = agentLiveActivity.has(agentId);
  const rooms = S.sessions.filter(session => session.agent_id === agentId)
    .sort((a, b) => String(b.updated_at || '').localeCompare(String(a.updated_at || '')));
  const general = generalSessionForAgent(agentId);
  const latestRoom = rooms.find(room => String(room?.last_preview || '').trim()) || rooms[0] || null;
  const fallback = String(general?.last_preview || latestRoom?.last_preview || '')
    .replace(/\s+/g, ' ').trim() || 'Start a conversation with Zeline';
  preview.innerHTML = typing ? 'Typing...' : agentPreviewMarkup(fallback);
  preview.classList.toggle('typing', typing);
  return true;
}

function agentPreviewMarkup(value) {
  // Plain-text preview: strip markdown tokens entirely so no visible quotes,
  // model-name ticks, or link fragments leak into the home card.
  return esc(String(value || 'No messages yet').replace(/\s+/g, ' ').trim()
    .replace(/\[([^\]]*)\]\(([^)]*)\)/g, '$1')   // [text](link) → text
    .replace(/`([^`]*)`/g, '$1')                 // `code` → code
    .replace(/\*\*([^*]*)\*\*/g, '$1')           // **bold** → bold
    .replace(/__([^_]*)__/g, '$1')
    .replace(/(^|\s)[*_~#>`]+/g, '$1'));
}

/* Pin order is recency-based: the most recently pinned id sits at index 0 of the
   shared `pinned` array, so a lower index must sort higher. Unpinned ids get
   Infinity and fall through to the normal ordering. */
function pinRankMap() {
  const pinned = agentFlags().pinned;
  const rank = new Map();
  pinned.forEach((id, index) => { if (!rank.has(id)) rank.set(id, index); });
  return rank;
}

const pinRankOf = (rank, id) => (rank.has(id) ? rank.get(id) : Infinity);

function sessionsForAgent(agentId) {
  const rank = pinRankMap();
  return S.sessions.filter(session => session.agent_id === agentId && !isGeneralSession(session))
    .sort((left, right) => {
      const byPin = pinRankOf(rank, left.id) - pinRankOf(rank, right.id);
      if (byPin) return byPin;
      return String(right.updated_at || '').localeCompare(String(left.updated_at || ''));
    });
}

function allConversationsForAgent(agentId) {
  return S.sessions.filter(session => session.agent_id === agentId)
    .sort((left, right) => String(right.updated_at || '').localeCompare(String(left.updated_at || '')));
}

function generalSessionForAgent(agentId) {
  return S.sessions.find(session => session.agent_id === agentId && isGeneralSession(session)) || null;
}

/* ───────────────── sidebar recent ───────────────── */
function renderRecent() {
  const box = $('recentList');
  // The sidebar is rebuilt as a profile sheet on boot, which drops this node.
  // A missing container is a valid state, not a reason to abort the remaining
  // page renders — an exception here used to strand the Provider page blank.
  if (!box) return;
  box.innerHTML = '';
  [...S.sessions].filter(session => !isGeneralSession(session))
    .sort((a, b) => b.updated_at.localeCompare(a.updated_at))
    .slice(0, 8)
    .forEach(s => {
      const a = agentById(s.agent_id);
      const b = el('button', 'recent' + (s.id === S.sessionId ? ' active' : ''));
      const dot = el('span', 'recent-dot');
      dot.style.background = a?.accent || 'var(--text-3)';
      const main = el('div', 'recent-main');
      main.innerHTML = `<div class="recent-title">${esc(s.title)}</div>
        <div class="recent-sub">${esc(a?.name || '—')} · ${timeAgo(s.updated_at)}</div>`;
      b.appendChild(dot); b.appendChild(main);
      b.onclick = () => openSession(s.id);
      box.appendChild(b);
    });
}

/* ───────────────── sessions page ───────────────── */
function renderSessionFilter() {
  const box = $('sessionFilter');
  if (!box) return;
  box.innerHTML = '';
  const mk = (id, label) => {
    const c = el('button', 'chip' + (S.filterAgent === id ? ' on' : ''), esc(label));
    c.onclick = () => { S.filterAgent = id; renderSessionFilter(); renderSessions(); };
    box.appendChild(c);
  };
  mk('all', 'Semua');
  S.agents.forEach(a => mk(a.id, a.name));
}

function renderSessions() {
  const box = $('sessionList');
  if (!box) return;
  box.innerHTML = '';
  const items = S.sessions.filter(session => !isGeneralSession(session))
    .filter(s => S.filterAgent === 'all' || s.agent_id === S.filterAgent)
    .filter(s => !S.q || (s.title + s.last_preview).toLowerCase().includes(S.q))
    .sort((a, b) => b.updated_at.localeCompare(a.updated_at));

  if (!items.length) {
    box.appendChild(el('div', 'note', 'No matching sessions yet.'));
    return;
  }
  items.forEach(s => {
    const a = agentById(s.agent_id);
    const r = el('button', 'row');
    const ic = el('div', 'row-ic', ZI('agentchip'));
    ic.style.color = a?.accent || 'var(--accent)';
    ic.style.background = (a?.accent || '#6EA8FF') + '1F';
    const main = el('div', 'row-main');
    main.innerHTML = `<div class="row-title">${esc(s.title)}</div>
      <div class="row-sub">${esc(s.last_preview || 'no messages yet')}</div>`;
    const side = el('div', 'row-side');
    side.innerHTML = `<span class="pill mono">${s.message_count} msg</span>
      <span class="row-time">${timeAgo(s.updated_at)}</span>`;
    r.appendChild(ic); r.appendChild(main); r.appendChild(side);
    r.onclick = () => { openSession(s.id); go('chat'); };
    box.appendChild(r);
  });
}

/* ───────────────── agents page ───────────────── */
function renderAgents() {
  const g = $('agentGrid');
  if (!g) return;
  g.innerHTML = '';

  const add = el('button', 'card click');
  add.style.alignItems = 'center';
  add.style.justifyContent = 'center';
  add.style.minHeight = '168px';
  add.style.borderStyle = 'dashed';
  add.innerHTML = `<div class="card-ic" style="background:var(--accent-soft);color:var(--accent)">${ZI('plus')}</div>
    <h3 style="margin:0">Agent baru</h3>
    <p class="card-desc" style="text-align:center">Provider, model, prompt, tools, skills</p>`;
  add.onclick = agentModal;
  g.appendChild(add);

  S.agents.forEach(a => {
    const pr = S.providers.find(p => p.id === a.provider_id);
    const c = el('div', 'card');
    const head = el('div', 'card-head');
    const ic = el('div', 'card-ic', esc(a.icon));
    ic.style.color = a.accent; ic.style.background = a.accent + '1F';
    head.appendChild(ic);
    head.appendChild(el('h3', '', esc(a.name)));
    head.appendChild(el('span', 'pill ' + (a.memory_enabled ? 'ok' : ''),
      a.memory_enabled ? 'memory' : 'no memory'));
    c.appendChild(head);
    c.appendChild(el('p', 'card-desc', esc(a.description || '—')));

    const kv = el('div', 'kv');
    kv.innerHTML = `
      <div class="kv-row"><span>Provider</span><span>${esc(pr ? providerDisplayName(pr) : a.provider_id)}</span></div>
      <div class="kv-row"><span>Model</span><span class="mono">${esc(a.model)}</span></div>
      <div class="kv-row"><span>Diperbarui</span><span>${timeAgo(a.updated_at)}</span></div>`;
    c.appendChild(kv);

    if (a.enabled_tools.length) {
      const t = el('div', 'tags');
      a.enabled_tools.slice(0, 6).forEach(x => t.appendChild(el('span', 'tag', esc(x))));
      c.appendChild(t);
    }

    const act = el('div', 'card-actions');
    const chat = el('button', 'btn primary sm', 'Chat');
    chat.onclick = async () => {
      S.agentId = a.id; S.model = a.model;
      S.sessionId = null; S.messages = [];
      await syncAgentSelect(); go('chat'); showConversation(); renderEmpty(); persistActiveConversation();
    };
    const edit = el('button', 'btn ghost sm', 'Edit');
    edit.onclick = () => agentModal(a);
    const del = el('button', 'btn ghost danger sm', 'Delete');
    del.onclick = () => modal({
      title: 'Delete agent?',
      body: `<p class="note">Agent <strong>${esc(a.name)}</strong> akan dihapus.
             Sesi lamanya tetap tersimpan.</p>`,
      actions: [
        { label: 'Cancel' },
        {
          label: 'Delete', kind: 'ghost danger', onClick: async (close) => {
            try {
              await api('/agents/' + a.id, { method: 'DELETE' });
              toast('Agent dihapus', 'ok'); close(); await refreshAll();
            } catch (e) { toast(e.message, 'err'); }
          }
        }
      ]
    });
    act.appendChild(chat); act.appendChild(edit); act.appendChild(del);
    c.appendChild(act);
    g.appendChild(c);
  });
}

const ALL_TOOLS = ['terminal', 'file', 'patch', 'code_exec', 'web_search',
  'web_fetch', 'memory', 'delegation', 'vision'];
const ALL_SKILLS = ['zeline-development', 'local-dev-servers', 'market-analysis',
  'temp-email-automation'];

function agentModal(a) {
  if (!a && S.agents.length >= 5) { toast('Maximum 5 agent profiles', 'warn'); return; }
  const provider = S.providers.find(p => p.is_active) || S.providers[0] || {};
  const body = el('div', 'agent-simple-form create-agent-flow');
  body.innerHTML = `
    <div class="create-agent-steps" aria-label="Create agent steps">
      <span class="active"><b>1</b>Profile</span><i></i><span><b>2</b>Runtime</span><i></i><span><b>3</b>Security</span>
    </div>
    <section class="create-agent-step">
      <small>STEP 1 · PROFILE</small>
      <label class="create-agent-field"><span>Agent name</span><input id="fName" value="${esc(a?.name || '')}" placeholder="Agent name" maxlength="25" autocomplete="off"></label>
    </section>
    <section class="create-agent-step">
      <small>STEP 2 · RUNTIME</small>
      <div class="create-agent-runtime"><span>${ZI('gateway')}<small>Gateway</small><b>${navigator.onLine !== false ? 'Ready' : 'Offline'}</b></span><span>${ZI('provider')}<small>Provider</small><b>${esc(providerDisplayName(provider) || 'Not configured')}</b></span></div>
    </section>
    <section class="create-agent-step security">
      <small>STEP 3 · SECURITY</small>
      <strong>${ZI('key')}Save your agent key</strong>
      <p>The token is shown once after creation. Never share this token with anyone. Anyone with the key can control this agent.</p>
    </section>`;
  const input = body.querySelector('#fName');
  wireAgentNameInput(input);
  modal({
    title: a ? 'Edit Agent' : 'Create Agent', body,
    actions: [
      { label: 'Cancel' },
      { label: a ? 'Save' : 'Create Agent', kind: 'primary', onClick: async close => {
        const name = normalizeAgentName(input.value).trim();
        if (!validAgentName(name)) { toast('Use 1–25 letters, numbers, or spaces', 'err'); return; }
        const payload = {
          name, avatar: ZELINE_CHAT_AVATAR, icon: 'windowsgrid', description: '',
          provider_id: a?.provider_id || provider.id || '',
          model: a?.model || provider.models?.[0] || '',
          system_instructions: a?.system_instructions || '',
          enabled_tools: [...ALL_TOOLS], enabled_skills: [...ALL_SKILLS], memory_enabled: true
        };
        try {
          if (a) {
            const updated = await api('/agents/' + a.id, { method: 'PUT', body: payload });
            Object.assign(a, updated); saveAgentCache(S.agents); close(); renderAgentHome();
            toast('Agent updated', 'ok');
          } else {
            const created = await api('/agents', { method: 'POST', body: payload });
            if (!S.agents.some(item => item.id === created.id)) S.agents.push(created);
            saveAgentCache(S.agents); close(); renderAgentHome(); showAgentToken(created, true);
            toast('Agent created', 'ok');
          }
        } catch (e) { toast(e.message, 'err'); }
      } }
    ]
  });
  document.querySelector('.modal')?.classList.add('create-agent-modal-premium');
}

/* ───────────────── providers page ───────────────── */
/* Provider dashboard laid out like the reference: a Custom section with two
   full-width Add buttons, then single-row cards (icon left, name + status
   stacked center, a toggle on the right when connected). Every preset and
   saved connection is a card; unconfigured ones read "No connections". */
const PV_GROUP_META = {
  'openai-compatible': { label: 'Custom Providers', sub: 'OpenAI/Anthropic Compatible' },
  // Every non-custom provider. The label names what the section holds at its
  // top: the providers that already carry an API key / OAuth.
  available: { label: 'Api Key / OAuth Providers', sub: 'Connect providers using API keys or OAuth' },
};
// The catalog groups a provider can belong to are `oauth` / `free` / `apikey`;
// they are no longer folded into a single display bucket, so no constant is
// needed here.
const PV_GROUP_ORDER = ['openai-compatible', 'available'];
const PV_HEALTH_LABEL = {
  connected: 'Connected', failed: 'Failed',
  missing_credentials: 'No key', untested: 'Untested'
};

let providerState = { data: null, loading: false, error: null };
let providerDisabled = JSON.parse(localStorage.getItem('zeline.providerDisabled') || '[]');
// Provider page app bar: query owned by this page (never the global chat search).
let providerQuery = '';
let providerSearchOpen = false;

function pvProviderIcon(p, plain = false) {
  /* A custom endpoint (id `openai-compatible-chat-<uuid>`) has no artwork of its
     own, and borrowing the OpenAI/Anthropic mark would be wrong — it is the
     user's own provider ("Vantis", "JustWoker"), not that vendor. Give it the
     first two letters of its NAME instead, drawn at the same size as every
     other logo so the rows stay uniform. Real catalog providers keep their PNG. */
  const idRaw = String(p.id || '');
  const isCustomEndpoint = /^(openai|anthropic)-compatible/i.test(idRaw);
  const url = isCustomEndpoint ? '' : `/assets/providers/${encodeURIComponent(idRaw)}.png`;
  /* Two-letter fallback for any provider without artwork (custom endpoints, new
     upstreams). `Zeline Router` -> `ZR`, `My Gateway` -> `MY`. The blue fill is
     applied by `.pv-icon-text` in CSS, not inline, so it can't be clobbered.
     The inline background here is only the neutral plate BEHIND a real logo —
     it is cleared on the fallback path so the blue shows through.

     `plain` drops that plate entirely (no square, no fill) for the provider
     detail header, where the logo should sit on the page as bare artwork. The
     list cards keep the plate, so this is opt-in and defaults off. */
  const initials = esc(providerDisplayName(p).slice(0, 2).toUpperCase());
  /* A custom endpoint skips the <img> entirely: there is nothing to request, so
     the letter tile is the first and only paint (no broken-image flash). */
  if (isCustomEndpoint) {
    return `<span class="pv-icon pv-icon-text${plain ? ' pv-icon-plain' : ''}">${initials}</span>`;
  }
  return `<span class="pv-icon${plain ? ' pv-icon-plain' : ''}"${plain ? '' : ' style="background:#1d1d22"'}>
    <img src="${url}" alt="" loading="lazy" decoding="async" draggable="false"
         onerror="var w=this.closest('.pv-icon');w.innerHTML='${initials}';w.classList.add('pv-icon-text');w.style.background='';">
  </span>`;
}

/* ── Display name for a provider ─────────────────────────────────────────
   The center catalog hands back raw ids/names that do not match what the user
   sees inside the provider, so every user-facing name is resolved here:

     1. A known gateway id ('9router') is renamed to the app's own name
        ("OpenAI Codex") — that internal id must never reach the screen.
     2. Otherwise the name is derived from the MODELS the provider actually
        serves, because that is what the user recognises: a card full of
        `claude-*` models reads "Claude", one full of `gpt-*`/`o*` reads
        "OpenAI". This keeps a generic catalog label ("Anthropic") from
        disagreeing with the API behind it.
     3. Failing that, the catalog name is used as-is.

   Route EVERY user-facing provider name through here so the list, the detail
   header and the usage rows can never disagree. */
const PROVIDER_DISPLAY_NAMES = { '9router': 'OpenAI Codex' };
/* Resolve a provider's real name from the runtime, keyed by its model prefix.
   Two sources, in order:
     1. `routerModelOwners` — the /v1/models `owned_by` map (authoritative; this
        is the name the user gave the endpoint when they added it).
     2. The provider's own model ids, whose prefix is that same owner key.
   Returns '' when neither yields a name, so the caller falls back to the
   catalog label. */
function pvRouterOwnerFor(p) {
  if (!p) return '';
  /* `routerModelOwners` is declared further down the file, so read it through a
     typeof guard — calling this before that `let` initialises would otherwise
     throw a TDZ ReferenceError. */
  const owners = (typeof routerModelOwners === 'object' && routerModelOwners) || {};
  const models = Array.isArray(p.models) ? p.models
    : Array.isArray(p.model_ids) ? p.model_ids : [];
  /* 1. The prefix of any model this provider serves names its owner directly. */
  for (const m of models) {
    const s = String(m);
    const prefix = s.includes('/') ? s.split('/')[0] : '';
    if (prefix && owners[prefix]) return owners[prefix];
  }
  /* 2. Fall back to matching the provider id/name against the owner keys. */
  const idKey = String(p.id || '').toLowerCase();
  const nameKey = String(p.name || '').toLowerCase();
  for (const [prefix, owner] of Object.entries(owners)) {
    const pk = String(prefix).toLowerCase();
    if (pk === idKey || pk === nameKey) return owner;
  }
  return '';
}
function providerDisplayName(p) {
  if (!p) return '';
  const idKey = String(p.id || '').toLowerCase();
  if (PROVIDER_DISPLAY_NAMES[idKey]) return PROVIDER_DISPLAY_NAMES[idKey];
  /* The gateway is recognised by id OR by its raw catalog name. */
  if (pvIsCodexGateway(p)) return PROVIDER_DISPLAY_NAMES['9router'];
  /* What the user actually named this provider, read from the runtime's own
     model list: a custom endpoint added as "Vantis" / "b.ai" reports that name
     as `owned_by` on every model it serves. This beats the catalog label, which
     only knows the dialect ("OpenAI" / "Anthropic") and is exactly the mismatch
     the user reported. Matched on the model prefix first (authoritative), then
     on the provider id. */
  const owner = pvRouterOwnerFor(p);
  if (owner) return owner;
  const raw = String(p.name || '');
  if (PROVIDER_DISPLAY_NAMES[raw.toLowerCase()]) return PROVIDER_DISPLAY_NAMES[raw.toLowerCase()];
  return raw || String(p.id || '');
}

/* Official links for the local Codex gateway. The backend usually sends these,
   but when it does not the old code fell back to a bare '#', which rendered a
   dead link that looked clickable and did nothing. Fall back to the real
   OpenAI pages instead, keyed off the same id/name the display helper uses. */
function pvIsCodexGateway(p) {
  if (!p) return false;
  const id = String(p.id || '').toLowerCase();
  const nm = String(p.name || '').toLowerCase();
  return id === '9router' || nm === '9router' || id === 'codex' || id === 'cx';
}
function pvProviderSignupUrl(p) {
  if (p && p.signup_url) return p.signup_url;
  if (pvIsCodexGateway(p)) return 'https://chatgpt.com/';
  return (p && p.base_url) || '#';
}
function pvProviderDocsUrl(p) {
  if (p && p.docs_url) return p.docs_url;
  if (pvIsCodexGateway(p)) return 'https://platform.openai.com/docs/';
  return (p && p.signup_url) || (p && p.base_url) || '#';
}

/* Every router row that belongs to this provider, keyed off the catalog id but
   tolerant of the broker spelling the same provider differently (case, or a
   `-cli`/alias suffix on one side). ONE accessor so the connected test, the
   toggle and the detail screen can never disagree about which rows are "this
   provider's". Exact/alias keys from routerProviderKeys win; the tolerant scan
   only widens the set when that came back empty. */
function pvRouterRowsFor(p) {
  if (!p) return [];
  const exact = typeof routerProviderRows === 'function' ? routerProviderRows(p.id) : [];
  if (exact.length) return exact;
  const want = String(p.id || '').toLowerCase();
  if (!want || !routerConnections || !routerConnections.byProvider) return [];
  const out = [];
  const seen = new Set();
  for (const key of Object.keys(routerConnections.byProvider)) {
    const k = String(key).toLowerCase();
    const rows = routerConnections.byProvider[key];
    if (!Array.isArray(rows) || !rows.length) continue;
    /* Match on an alias boundary only: identical, or one side extends the other
       with `-`/`_` (e.g. `antigravity` vs `antigravity-cli`). A bare prefix like
       `code` matching `codex` is deliberately NOT allowed. */
    const aliasLike = k === want
      || k.startsWith(want + '-') || k.startsWith(want + '_')
      || want.startsWith(k + '-') || want.startsWith(k + '_');
    if (!aliasLike) continue;
    rows.forEach(r => { if (r && !seen.has(r.id)) { seen.add(r.id); out.push(r); } });
  }
  return out;
}

function pvIsConnected(p) {
  if (!p) return false;
  /* The local gateway is never a "connected provider": it holds no upstream
     credential of its own — it is the door to the router, and its key hint is
     the app's own gateway token, not a provider key. It belongs with the
     available/unconfigured entries, not in the Api Key / OAuth list. */
  if (pvIsCodexGateway(p)) return false;
  /* The backend's own `connected` flag is authoritative now: the center payload
     merges the router's live connections, so a custom endpoint the user added
     (Vantis, JustWoker) comes back `connected: true` while a bare catalog entry
     comes back false. Fall back to reading the router rows directly only when
     the field is absent (an older gateway). */
  if (typeof p.connected === 'boolean') return p.connected;
  return pvRouterRowsFor(p).length > 0;
}

function pvIsDisabled(p) {
  if (!pvIsConnected(p)) return false;
  /* The router is the source of truth: a provider is off when EVERY one of its
     connections reports `active: false`. Only fall back to the browser-local
     list when the router rows are not loaded yet, so a stale localStorage from
     another device can no longer show a switch that disagrees with routing. */
  const conns = typeof routerProviderRows === 'function' ? routerProviderRows(p.id) : [];
  if (conns.length) return conns.every(c => !c.active);
  return providerDisabled.includes(p.id);
}

function pvCardStatus(p) {
  if (pvIsDisabled(p)) {
    return { text: 'Disabled', cls: 'off', pill: '' };
  }
  if (!pvIsConnected(p)) {
    return { text: 'No connections', cls: 'idle', pill: '' };
  }
  const protocol = p.protocol === 'anthropic' ? 'Messages' : 'Chat';
  /* No latency on the local gateway: its "ping" is a loopback call to the broker
     on this same device, so an ms figure there measures nothing real and just
     litters the card (it was a stale 691ms reading). Only a real remote endpoint
     gets a latency. */
  const showLatency = !pvIsCodexGateway(p);
  if (p.health?.status === 'connected') {
    const latency = showLatency && Number.isFinite(p.health.latency_ms)
      ? ` · ${p.health.latency_ms}ms` : '';
    return { text: 'Connected' + latency, cls: 'ok', pill: protocol };
  }
  if (p.health?.status === 'failed') {
    return { text: 'Error' + (p.health.error ? ' (' + p.health.error + ')' : ''), cls: 'err', pill: protocol };
  }
  return { text: 'Connected', cls: 'ok', pill: protocol };
}

function pvProviderCard(p) {
  const connected = pvIsConnected(p);
  const disabled = pvIsDisabled(p);
  const status = pvCardStatus(p);
  const card = el('article', 'pv-card'
    + (connected ? ' is-connected' : '')
    + (disabled ? ' is-disabled' : ''));
  card.innerHTML = `
    <div class="pv-card-row">
      ${pvProviderIcon(p)}
      <div class="pv-card-copy">
        <div class="pv-name" title="${esc(providerDisplayName(p))}">${esc(providerDisplayName(p))}</div>
        <div class="pv-status-line">
          <span class="pv-status ${status.cls}"><span class="pv-dot"></span>${esc(status.text)}</span>
          ${status.pill ? `<span class="pv-pill">${esc(status.pill)}</span>` : ''}
        </div>
      </div>
      <div class="pv-card-side">
        ${connected && !pvIsCodexGateway(p) ? `
          <button class="pv-toggle ${disabled ? 'off' : 'on'}" data-pv-toggle aria-pressed="${!disabled}" title="${disabled ? 'Enable' : 'Disable'}">
            <span class="pv-toggle-knob"></span>
          </button>` : ''}
      </div>
    </div>`;

  const toggle = card.querySelector('[data-pv-toggle]');
  if (toggle) toggle.onclick = async (e) => {
    e.stopPropagation();
    e.preventDefault();
    if (toggle.dataset.busy === '1') return;
    /* Read the CURRENT state, not the `disabled` captured at render time.
       The old code closed over the render-time value, so a second tap
       re-derived the same `nowDisabled` and the switch never flipped back. */
    const nowDisabled = !pvIsDisabled(p);

    /* The toggle must change ROUTING, not just a browser-local list. A
       provider is only ever "off" in the router when every one of its
       connections is inactive, so this writes `active` to each of them through
       the same per-connection endpoint the detail screen uses. The
       localStorage mirror stays so the card renders the right state before the
       router round-trips. */
    const conns = pvRouterRowsFor(p);
    if (!conns.length) {
      /* The router connection list had not loaded (or this provider truly has
         no rows). Persisting the flip locally would make the card claim a
         state the router never agreed to, so say so and stop. */
      toast('Router connections not loaded — reopen Providers and try again', 'err');
      return;
    }
    {
      toggle.dataset.busy = '1';
      card.classList.add('is-busy');
      const results = await Promise.allSettled(conns.map(c =>
        api(`/providers/connection/${encodeURIComponent(c.id)}/toggle`, {
          method: 'POST', body: { active: !nowDisabled }, timeoutMs: 25000,
        })));
      delete toggle.dataset.busy;
      card.classList.remove('is-busy');
      const failed = results.filter(r => r.status === 'rejected').length;
      if (failed) {
        /* Only record the flip locally when the router actually accepted it —
           otherwise the card would claim the opposite of what the router does. */
        toast(`Could not ${nowDisabled ? 'disable' : 'enable'} ${failed} of ${conns.length} account(s)`, 'err');
        await refreshConns();
        return;
      }
    }

    if (nowDisabled) {
      if (!providerDisabled.includes(p.id)) providerDisabled.push(p.id);
    } else {
      providerDisabled = providerDisabled.filter(x => x !== p.id);
    }
    localStorage.setItem('zeline.providerDisabled', JSON.stringify(providerDisabled));

    /* Mirror the accepted flip into the in-memory router rows, so pvIsDisabled
       / pvCardStatus read the NEW state straight away. Without this the switch
       would be repainted from the stale rows and snap back to its old position
       on the next repaint. `conns` is the exact set the request was sent for. */
    conns.forEach(c => { c.active = !nowDisabled; });

    toast(nowDisabled
      ? `${providerDisplayName(p)} disabled`
      : `${providerDisplayName(p)} enabled`, 'ok', 1600);

    /* Flip the switch IN PLACE instead of re-rendering the list.
       A full re-render rebuilt every `.pv-card` from scratch, so each
       provider <img> was destroyed and re-requested — the logo visibly
       blanked and repainted (the "error flash") on every tap. Mutating the
       nodes we already hold keeps the icons untouched.
       Guarded because the card can be detached by a concurrent list render
       while this handler is still queued. */
    if (!card.isConnected) return;
    card.classList.toggle('is-disabled', nowDisabled);
    toggle.classList.toggle('off', nowDisabled);
    toggle.classList.toggle('on', !nowDisabled);
    toggle.setAttribute('aria-pressed', String(!nowDisabled));
    toggle.title = nowDisabled ? 'Enable' : 'Disable';

    const statusEl = card.querySelector('.pv-status');
    if (statusEl) {
      const st = pvCardStatus(p);
      statusEl.className = 'pv-status ' + st.cls;
      statusEl.innerHTML = `<span class="pv-dot"></span>${esc(st.text)}`;
      const line = card.querySelector('.pv-status-line');
      const oldPill = line?.querySelector('.pv-pill');
      if (st.pill) {
        if (oldPill) oldPill.textContent = st.pill;
        else if (line) line.insertAdjacentHTML('beforeend', `<span class="pv-pill">${esc(st.pill)}</span>`);
      } else if (oldPill) {
        oldPill.remove();
      }
    }
  };

  card.onclick = () => openProviderDetail(p.id);
  return card;
}

/* ─────────────── provider detail (dashboard-style) ─────────────── */
/* A full-screen view of one connection: its identity, a credential action
   (Add API key / OAuth), the model list with add/hide/test, and a provider
   connection test. Everything reads from the runtime; nothing is invented. */
/* `mtest` holds the per-model test verdict ('ok' | 'error') so a card can show a
   live check/cancel icon like the router does, instead of a toast that vanishes.
   `thinking` is the reasoning level applied to copied model names. */
let providerDetailState = { open: false, provider: null, models: null, testing: null,
                            thinking: 'auto', thinkingLevels: [], mtest: {}, copied: '',
                            /* Per-account test verdicts, keyed by connection id:
                               'queued' | 'testing' | 'ok' | 'error'. Kept here so
                               the badge survives the row re-render. */
                            connTest: {},
                            /* The message from a FAILED probe, keyed by
                               connection id. A pass stores '' so a stale reason
                               can never outlive the failure it described. */
                            connTestError: {},
                            /* Live run bookkeeping for the batch tester. `null`
                               means no run is in flight. */
                            connRun: null,
                            /* Hand-picked connection ids. The bulk actions only
                               ever send what is in here. */
                            selected: [],
                            /* Select mode. Off = cards are inert and a tap does
                               nothing; on = a tap anywhere in a card picks it.
                               Selection is shown by a soft blue ring on the
                               card, with no number badge. The router's order is
                               read-only on this screen. */
                            selectMode: false,
                            strategy: { round_robin: false, sticky: 3, loaded: false },
                            /* Auto-ping (quota warming), read from the router.
                               Shape: {"codex": {enabled: bool, connections: {"<id>": bool}}}
                               Only providers that support the feature appear here,
                               so the row decides whether to draw its pin button by
                               looking the provider up in this map. */
                            autoPing: { loaded: false, providers: {} },
                            /* When a finished run's summary should stop being
                               shown. The info panel lingers for 10s after the
                               run ends, then hides itself — the user asked for
                               it to clear on its own rather than sit there. */
                            runHideAt: 0,
                            adding: false };

async function openProviderDetail(id) {
  const p = (providerState.data?.providers || []).find(x => x.id === id);
  if (!p) return;
  /* Paint immediately so a tap feels instant — waiting for the model list
     (a multi-second broker round-trip) before showing ANYTHING made the card
     feel dead. The header, identity and account rows are all local, so they go
     up on this frame; the model block paints its skeleton and is filled in
     place when the list lands, which avoids the "models pop in" flash without
     blocking the open. Strategy and auto-ping load in parallel. */
  providerDetailState = { open: true, provider: p, models: null, testing: null,
                          thinking: 'auto', thinkingLevels: [], mtest: {}, copied: '',
                          connTest: {}, connTestError: {}, connRun: null,
                          selected: [], selectMode: false,
                          strategy: { round_robin: false, sticky: 3, loaded: false },
                          autoPing: { loaded: false, providers: {} },
                          adding: false };
  renderProviderDetail();
  // The rotation strategy lives on the router, so it is read, not assumed.
  loadProviderStrategy(id);
  // Same for auto-ping: the router holds the opt-in, so the pin button shows
  // what the router will actually do rather than a local guess.
  loadAutoPing();
  /* Models load AFTER the panel is up. The repaint on arrival is cheap and the
     scroll offset is preserved, so the block just fills in. */
  try {
    const d = await apiWhenAuthed(`/providers/${encodeURIComponent(id)}/models`);
    if (providerDetailState.provider?.id !== id) return;
    providerDetailState.models = d.models || [];
    providerDetailState.thinkingLevels = d.thinking_levels || [];
    providerDetailState.thinking = d.thinking || 'auto';
  } catch (e) {
    if (providerDetailState.provider?.id !== id) return;
    /* Keep `null` so the block shows its skeleton — the fetch failed and the
       list is genuinely unknown, which is different from "no models". */
    providerDetailState.models = null;
  }
  renderProviderDetail();
}

function closeProviderDetail() {
  // Stop any run still in flight so its loop does not keep writing into a
  // screen the user has already left (and does not burn quota silently).
  if (providerDetailState.connRun) providerDetailState.connRun.cancelled = true;
  providerDetailState.connRun = null;
  providerDetailState.open = false;
  renderProviderDetail();
}

/* Round robin + sticky, read from the router. The router owns this decision —
   it is the thing that actually picks which account answers — so the switch
   reflects its settings rather than a local flag the router would ignore. */
async function loadProviderStrategy(providerId) {
  try {
    const d = await apiWhenAuthed(`/providers/${encodeURIComponent(providerId)}/strategy`);
    if (providerDetailState.provider?.id !== providerId) return;
    providerDetailState.strategy = {
      round_robin: Boolean(d.round_robin),
      sticky: Number.isFinite(d.sticky) ? d.sticky : 3,
      loaded: true,
    };
    if (providerDetailState.open) renderProviderDetail();
  } catch (_) {
    providerDetailState.strategy.loaded = true;
  }
}

async function setProviderStrategy(patch, okMsg) {
  const p = providerDetailState.provider;
  if (!p) return;
  const previous = { ...providerDetailState.strategy };
  // Optimistic: the switch must feel instant, and the read-back below is what
  // makes the final state honest if the router disagrees.
  providerDetailState.strategy = { ...previous, ...patch, loaded: true };
  renderProviderDetail();
  try {
    const d = await apiWhenAuthed(`/providers/${encodeURIComponent(p.id)}/strategy`, {
      method: 'POST',
      body: { round_robin: patch.round_robin, sticky: patch.sticky },
    });
    providerDetailState.strategy = {
      round_robin: Boolean(d.round_robin),
      sticky: Number.isFinite(d.sticky) ? d.sticky : previous.sticky,
      loaded: true,
    };
    if (providerDetailState.open) renderProviderDetail();
    if (okMsg) toast(okMsg, 'ok', 1600);
  } catch (err) {
    providerDetailState.strategy = previous;
    if (providerDetailState.open) renderProviderDetail();
    toast(`${err.code || ''} ${err.message}`.trim() || 'Failed to save strategy', 'err');
  }
}

/* Auto-ping (quota warming), read from the router.

   The router owns the opt-in — it is the thing that actually sends the warm-up
   request — so the pin button reflects its settings instead of a local flag the
   router would ignore. Only providers the router reports support the feature,
   which is what keeps the button off an account where it would do nothing. */
async function loadAutoPing() {
  try {
    const d = await apiWhenAuthed('/providers/auto-ping');
    providerDetailState.autoPing = { loaded: true, providers: d.providers || d || {} };
  } catch (_) {
    // A router that cannot answer leaves the button hidden rather than showing
    // a switch whose state is unknown.
    providerDetailState.autoPing = { loaded: true, providers: {} };
  }
  if (providerDetailState.open) renderProviderDetail();
}

/* Flip auto-ping for one account (connectionId set) or for a whole provider.

   Optimistic: the pin must feel instant, and the read-back below is what makes
   the final state honest if the router disagrees. */
async function setAutoPing(provider, on, connectionId, okMsg) {
  const previous = providerDetailState.autoPing;
  const providers = { ...(previous.providers || {}) };
  const row = { enabled: false, connections: {}, ...(providers[provider] || {}) };
  if (connectionId) {
    row.connections = { ...(row.connections || {}), [String(connectionId)]: Boolean(on) };
    if (on) row.enabled = true;
  } else {
    row.enabled = Boolean(on);
  }
  providers[provider] = row;
  providerDetailState.autoPing = { ...previous, providers };
  renderProviderDetail();
  try {
    const body = connectionId
      ? { provider, connection_id: String(connectionId), on: Boolean(on) }
      : { provider, enabled: Boolean(on) };
    const d = await apiWhenAuthed('/providers/auto-ping', { method: 'POST', body });
    providerDetailState.autoPing = { loaded: true, providers: d.providers || d || {} };
    if (providerDetailState.open) renderProviderDetail();
    if (okMsg) toast(okMsg, 'ok', 1600);
  } catch (err) {
    providerDetailState.autoPing = previous;
    if (providerDetailState.open) renderProviderDetail();
    toast(`${err.code || ''} ${err.message}`.trim() || 'Failed to save auto-ping', 'err');
  }
}

/* (Model cards show the raw id only — one label per model. A pretty-name second
   line was removed because it repeated the same model in two spellings.) */

/* Which model to probe an account with.

   Two facts decide this. The router routes by model prefix, so probing a
   `cbai/` account with an `ag/` model fails for a reason that has nothing to do
   with the account. And within one provider accounts differ: a Codex ChatGPT
   plan answers `gpt-5.6-luna` but rejects `gpt-5.5-image`. So the connection's
   OWN history wins — the router records every model it has served through that
   connection — and only then does the prefix match come into play.

   Module scope on purpose: this is the decision the whole per-account test
   rests on, so it has to be inspectable (and testable) from outside the render
   pass rather than trapped in a closure. */
const PV_PROVIDER_PREFIX = {
  codex: 'cx/', cx: 'cx/',
  'codebuddy-intl': 'cbai/', 'codebuddy-cn': 'cbcn/',
  antigravity: 'ag/', 'gemini-cli': 'gc/', xai: 'gb/',
  kimi: 'kr/', kilocode: 'kc/', cline: 'cl/', iflow: 'if/',
  github: 'gh/', gitlab: 'gl/', qoder: 'qd/',
};
const pvBareModel = mid => String(mid || '').split('/').pop();

function pvProbeCandidates(conn) {
  const all = providerDetailState.models || [];
  const list = all.filter(m => !m.hidden).length ? all.filter(m => !m.hidden) : all;
  const ids = list.map(m => String(m.id));
  const seen = (conn?.models_seen || []).map(String);
  const pref = PV_PROVIDER_PREFIX[String(conn?.provider || '')] || '';
  const out = [];
  const push = mid => { if (mid && !out.includes(mid)) out.push(mid); };

  // 1. A model this connection has served AND the visible list carries. The
  //    list is the authoritative spelling (it carries the routing prefix).
  seen.forEach(mid => { if (ids.includes(mid)) push(mid); });
  // 2. A served model that only differs by the routing prefix.
  seen.forEach(mid => {
    const hit = ids.find(id => pvBareModel(id) === pvBareModel(mid));
    if (hit) push(hit);
    else if (pref) push(pref + pvBareModel(mid));
  });
  // 3. Any visible model belonging to this connection's provider.
  if (pref) list.filter(m => String(m.id).startsWith(pref)).forEach(m => push(m.id));
  // 4. Last resort: the first visible model at all.
  list.forEach(m => push(m.id));
  return out.slice(0, 6);
}

/* Probe one account, trying the candidate models in order.

   One model name is not enough: a served model may be one this account no
   longer supports, and the router's list spells names with a routing prefix the
   history does not carry. So each candidate is tried until one answers — the
   account is only "failed" when every candidate was rejected, which is the same
   bar the router's own dashboard applies. */
async function pvTestOneConnection(id, models, active = true) {
  /* A disabled account cannot be probed: the router refuses to route through
     it, so the probe would answer "no active credentials" and the badge would
     blame the credential for a switch the user turned off. Reporting it as `off`
     is the honest verdict and it points at the fix (enable it first). */
  if (!active) {
    providerDetailState.connTest[id] = 'off';
    providerDetailState.connTestError[id] = null;
    if (providerDetailState.open) renderProviderDetail();
    return { valid: false, error: 'Account is disabled', disabled: true };
  }
  const candidates = (Array.isArray(models) ? models : [models]).filter(Boolean);
  if (!candidates.length) {
    providerDetailState.connTest[id] = 'error';
    providerDetailState.connTestError[id] = { code: '', message: 'No model to test' };
    if (providerDetailState.open) renderProviderDetail();
    return { valid: false, error: 'No model to test' };
  }
  providerDetailState.connTest[id] = 'testing';
  /* The stored failure from a previous run is cleared the moment a new probe
     starts: while the row says "Testing", an old error underneath it describes
     a state that is no longer known to be true. */
  providerDetailState.connTestError[id] = null;
  if (providerDetailState.open) renderProviderDetail();
  let last = { valid: false, error: 'invalid' };
  for (const model of candidates) {
    try {
      last = await api(`/providers/connection/${encodeURIComponent(id)}/test`, {
        method: 'POST', body: { model }, timeoutMs: 60000,
      });
    } catch (err) {
      last = { valid: false, error: `${err.code || ''} ${err.message}`.trim() };
    }
    if (last.valid) break;
  }
  providerDetailState.connTest[id] = last.valid ? 'ok' : 'error';
  /* Only a failure carries a message. A pass clears it, so a healthy account
     never keeps a stale reason from the run before. The status code travels
     with it so the card can show the same "404 : reason" lead-in the stored
     router error gets. */
  providerDetailState.connTestError[id] = last.valid
    ? null
    : { code: last.status || '', message: String(last.error || '') };
  if (providerDetailState.open) renderProviderDetail();
  return last;
}

/* Split a connection's failure into the two lines the card shows: a readable
   message and the raw HTTP status.

   The router stores the status twice — once as `errorCode` and again as the
   `[400]:` prefix on `lastError` — so pasting both produced `[400] [400]: …`.
   The router's own `[provider/model]` prefix is also dropped, because the card
   already names the account.

   When the payload is a JSON error envelope (`{"detail":"…"}` /
   `{"error":{"message":"…"}}`) the human string is lifted out of it, so the
   card reads "Connection timeout" instead of a wall of braces. Anything that
   cannot be parsed is shown verbatim — never hidden. */
function pvConnErrorParts(conn) {
  const code = String(conn?.error_code || '').trim();
  let text = String(conn?.last_error || '').trim();
  // `message` is what the live probe records; `last_error` is the router's own
  // stored string. Either may be present.
  if (!text) text = String(conn?.message || '').trim();
  // Strip a leading `[provider/model]` and/or `[400]:` wrapper, and the
  // `HTTP 404:` form the probe's own transport error arrives in.
  text = text.replace(/^(?:\[[^\]]{0,120}\]\s*)*\[\d{3}\]:\s*/, '');
  text = text.replace(/^HTTP\s+\d{3}\s*:\s*/i, '');
  // Unwrap a JSON error envelope down to its message.
  if (/^[[{]/.test(text)) {
    let pick = '';
    try {
      const j = JSON.parse(text);
      pick = j?.detail ?? j?.error?.message ?? j?.error?.msg ?? j?.message ?? j?.msg;
    } catch (_) {
      /* The router truncates long payloads, so the JSON is often unterminated
         and JSON.parse throws. Fall back to lifting the first string value out
         of the envelope with a regex — better a readable message than a wall of
         braces. */
      const m = text.match(/"(?:detail|message|msg)"\s*:\s*"((?:[^"\\]|\\.)*)/);
      if (m) pick = m[1];
    }
    if (typeof pick === 'string' && pick.trim()) {
      text = pick.trim().replace(/\\"/g, '"').replace(/\\n/g, ' ').replace(/\s+/g, ' ');
    }
  }
  if (text.length > 400) text = text.slice(0, 397).trimEnd() + '…';
  /* The row shows the whole failure on ONE line, so the message is flattened:
     newlines and runs of spaces collapse to single spaces, and a trailing
     period is dropped so the code chip in front reads as the lead-in. */
  text = text.replace(/\s+/g, ' ').trim().replace(/[.\s]+$/, '');
  return {
    message: text || 'Connection failed',
    /* Bare status number — the row renders it as its own red chip in front of
       the message ("502 The usage limit has been reached"), not "HTTP 502". */
    code: code || String(conn?.code || '').trim() || '',
  };
}

/* One-line form, kept for callers that want the whole thing in a string. */
function pvConnError(conn) {
  const p = pvConnErrorParts(conn);
  return p.code ? `${p.code} ${p.message}` : p.message;
}

/* The auth type as the row's badge shows it. The router stores a lowercase
   machine token ('oauth', 'apikey'); the badge shows the words its own
   dashboard uses — "OAuth" and "API Key". */
function pvAuthLabel(authType) {
  const s = String(authType || '').toLowerCase().replace(/[\s_-]/g, '');
  if (s === 'apikey' || s === 'apikeys' || s === 'key' || s === 'token') return 'API Key';
  if (s === 'oauth' || s === 'oauth2') return 'OAuth';
  return authType ? String(authType) : 'OAuth';
}

/* The auth badge is ICON ONLY: a padlock for an OAuth session, a key for a
   plain API key. The pair is unambiguous once you know it, and the words cost
   the width of an email address on a phone. The label survives as the tooltip
   and the accessible name, so nothing is actually lost. */
function pvAuthIcon(authType) {
  return pvAuthLabel(authType) === 'API Key' ? ZI('key') : ZI('lock');
}

function renderProviderDetail() {
  /* Nothing to show and no overlay exists yet → do not create one. Creating the
     fixed full-screen node just to hide it is what could cover the next tap for
     a frame; not creating it at all removes that class of bug entirely. */
  let host = $('providerDetail');
  if (!host) {
    if (!providerDetailState.open || !providerDetailState.provider) return;
    host = el('div', 'provider-detail');
    host.id = 'providerDetail';
    document.body.appendChild(host);
  }
  if (!providerDetailState.open || !providerDetailState.provider) {
    host.hidden = true;
    return;
  }
  /* This render REPLACES the whole panel via innerHTML, so the scroll container
     is a brand-new node with scrollTop 0. Every test / hide / toggle that wants
     to refresh the screen therefore threw the user back to the top mid-scroll.
     Capture the old offset and reapply it after the shell is rebuilt. */
  const prevScroller = host.querySelector('.pv-detail-body');
  const prevScrollTop = prevScroller ? prevScroller.scrollTop : 0;
  const p = providerDetailState.provider;
  const detailName = providerDisplayName(p);
  host.hidden = false;
  const hasKey = p.credential_status === 'configured';
  // Connections held by the local router for this provider. These are the ones
  // that actually route traffic; Zeline's own config only holds API-key entries.
  // Same tolerant accessor the list card uses, so both screens count the SAME
  // accounts even when the catalog id and the broker key are spelled differently.
  const routerRows = pvRouterRowsFor(p);
  const routerCount = routerRows.length;
  const isOAuth = p.auth?.includes('oauth') || p.group === 'oauth'
    || (p.id === '9router' && routerRows.some(c => c.auth_type === 'oauth'));

  const models = providerDetailState.models;
  const visible = (models || []).filter(m => !m.hidden);
  const hiddenModels = (models || []).filter(m => m.hidden);
  const activeCount = routerRows.filter(c => c.active).length;
  const strategy = providerDetailState.strategy || { round_robin: false, sticky: 3 };
  const selectedCount = providerDetailState.selected
    .filter(id => routerRows.some(c => String(c.id) === String(id))).length;
  const selectMode = Boolean(providerDetailState.selectMode);
  /* "All picked" lights the Select-all control. Computed once here and reused
     by both the markup and paintSelectMode(), so the button's lit state can
     never disagree with the count. */
  const allPicked = routerCount > 0 && selectedCount === routerCount;

  /* The run object drives the progress grid AND the Test-all button's label. */
  const run = providerDetailState.connRun;
  const runActive = Boolean(run && !run.cancelled && run.done < run.total);
  const runCurrent = run && run.current
    ? (routerRows.find(c => String(c.id) === String(run.current)) || {})
    : {};
  const runWho = runCurrent.email || runCurrent.name || runCurrent.provider || '';
  /* A finished run's summary is transient: once `runHideAt` passes, the panel
     disappears. While the run is live there is no hide time yet. */
  const runExpired = Boolean(run) && !runActive
    && providerDetailState.runHideAt > 0 && Date.now() >= providerDetailState.runHideAt;
  const showRunBar = Boolean(run) && !runExpired;

  /* Live batch-test progress. Five figures on ONE line (Total, Completed,
     Passed, Failed, Skipped) with Running alone on the second — the counts are
     the scan line, the account being probed is a different kind of fact. The
     font is deliberately small and the row never wraps or ellipsises: every
     label must stay readable at 360px. No title — the button above names the
     action, so the bar is pure information. */
  const runStat = (label, val, cls) =>
    `<span class="pv-run-stat"><span class="pv-run-lbl">${label}:</span>`
    + `<b class="${cls || ''}">${val}</b></span>`;
  const connRunBar = showRunBar ? `
    <div class="pv-runbar ${runActive ? 'is-live' : ''}">
      <div class="pv-run-line">
        ${runStat('Total', run.total)}
        ${runStat('Completed', run.done)}
        ${runStat('Passed', run.passed, 'ok')}
        ${runStat('Failed', run.failed, run.failed ? 'err' : '')}
        ${runStat('Skipped', run.skipped)}
      </div>
      <div class="pv-run-line pv-run-line2">
        ${runStat('Running', esc(runWho || '—'), 'who')}
      </div>
    </div>` : '';

  /* Model card: raw id with a live toggle, the pretty name underneath, and the
     quick actions. Two columns, matching the router dashboard's own grid.
     A hand-added model also gets a real delete button — base models only get
     the toggle, because they belong to the runtime config. */
  /* Model card, matching the router's own: a live status glyph on the left
     (robot → check → cancel as a test resolves), the raw id, then the three
     actions it actually supports — Test, Copy, and disable/remove.

     The copy button appends the chosen thinking level as `id(level)`, but only
     when THIS model accepts that level; the backend reports the per-model
     ladder, so a model without reasoning copies its plain id. */
  const thinkLevel = providerDetailState.thinking || 'auto';
  const copySuffix = m => (thinkLevel !== 'auto'
    && (m.thinking_levels || []).includes(thinkLevel)) ? `(${thinkLevel})` : '';

  const modelCard = m => {
    const verdict = providerDetailState.mtest[m.id] || '';
    const copyId = `${m.id}${copySuffix(m)}`;
    const justCopied = providerDetailState.copied === m.id;
    /* The vendor mark for this model family, round. Falls back to the robot
       glyph so an unrecognised family still shows something. */
    const logo = pvModelLogoAsset(m.id);
    const mark = logo
      ? `<span class="pv-mlogo"><img src="assets/provider-logos/${esc(logo)}.svg?v=8" alt="" draggable="false"></span>`
      : `<span class="pv-mlogo is-fallback">${ZI('agentchip')}</span>`;
    return `
    <div class="pv-mcard ${m.hidden ? 'is-off' : ''} ${verdict ? 've-' + verdict : ''}" data-model="${esc(m.id)}">
      ${mark}
      <code class="pv-mcard-id" title="${esc(m.id)}">${esc(m.id)}</code>
      <div class="pv-mcard-acts">
        ${m.custom ? '<span class="pv-mcard-tag">custom</span>' : ''}
        <button class="pv-icon-btn is-act" data-mtest="${esc(m.id)}"
                title="Test ${esc(m.id)}" aria-label="Test ${esc(m.id)}">${ZI('spark')}</button>
        <button class="pv-icon-btn is-act ${justCopied ? 'is-done' : ''}" data-mcopy="${esc(copyId)}"
                title="Copy ${esc(copyId)}" aria-label="Copy ${esc(copyId)}">${ZI(justCopied ? 'check' : 'copy')}</button>
        <button class="pv-icon-btn danger" data-mdel="${esc(m.id)}"
                title="Hapus ${esc(m.id)}" aria-label="Hapus ${esc(m.id)}">${ZI('close')}</button>
      </div>
    </div>`;
  };

  /* `null` = fetch failed / not in hand (skeleton); an array = the real list. */
  const modelRows = models === null
    ? '<div class="pv-skeleton"></div><div class="pv-skeleton"></div>'
    : visible.length === 0
      ? '<div class="pv-empty">No models detected yet. Test the provider to load its model list.</div>'
      : `<div class="pv-model-list">${visible.map(modelCard).join('')}</div>`;

  /* Models the user removed from rotation. They are NOT deleted — the card
     moves down here so the list stays honest about what the provider actually
     offers. Each one keeps a "restore" control to bring it back up. */
  const unusedModels = models === null ? '' : (() => {
    const rows = hiddenModels.length
      ? hiddenModels.map(m => {
          const logo = pvModelLogoAsset(m.id);
          const mark = logo
            ? `<span class="pv-mlogo"><img src="assets/provider-logos/${esc(logo)}.svg?v=8" alt="" draggable="false"></span>`
            : `<span class="pv-mlogo is-fallback">${ZI('agentchip')}</span>`;
          return `
        <div class="pv-mcard is-off" data-model="${esc(m.id)}">
          ${mark}
          <code class="pv-mcard-id" title="${esc(m.id)}">${esc(m.id)}</code>
          <div class="pv-mcard-acts">
            <button class="pv-icon-btn is-act" data-mhide="${esc(m.id)}" data-hidden="1"
                    title="Pakai lagi: ${esc(m.id)}" aria-label="Pakai lagi ${esc(m.id)}">${ZI('plus')}</button>
          </div>
        </div>`;
        }).join('')
      : '';
    return `
    <div class="pv-models-block">
      <div class="pv-models-head">
        <span class="pv-models-title">Tidak dipakai <span>(${hiddenModels.length})</span></span>
      </div>
      <div class="pv-model-list">${rows || '<div class="pv-empty">Belum ada model yang dihapus.</div>'}</div>
    </div>`;
  })();

  /* One connection row: identity, state, rotation index, and the same actions
     the dashboard exposes. There is no tick box any more — while Select mode is
     on, a tap ANYWHERE on the card picks it, and the whole card carries the
     picked styling so the hit target and the feedback are the same rectangle.
     Order is no longer changed with ↑/↓ arrows: a long press turns on Select
     mode and arms a drag, and the card is dropped into its new slot. */
  /* The status pill under an account's email. 'queued' and 'testing' are live
     run states; 'success' and 'failed' are the verdict of the last probe. The
     router's own dashboard shows exactly this ladder, so the wording matches. */
  /* The status pill under an account's email.

     A live verdict from this session wins ('queued' / 'testing' / 'ok' /
     'error' / 'off'). Before any test has run, the router's OWN last-known
     status is shown instead — it is the same signal its dashboard displays, and
     it means the list says which accounts are healthy without the user having
     to press Test first. `testStatus` is 'active' for a healthy connection,
     'unavailable'/'error' for one the upstream rejected. */
  const connTestBadge = (id, conn) => {
    let v = providerDetailState.connTest[id];
    if (!v) {
      if (!conn?.active) return '';
      const st = String(conn.status || '');
      if (st === 'active') v = 'ok';
      else if (st === 'error' || st === 'unavailable') v = 'error';
      else return '';
    }
    /* `off` means the account is switched off. The state pill already spells
       that out as "Disable", so a second badge saying the same thing is noise —
       the test badge only ever reports a probe verdict. */
    if (v === 'off') return '';
    /* ICON ONLY, no words. Three verdicts, three shapes that are readable at a
       glance and at any language: a tick for a pass, a cross for a failure, a
       spinning ring while the probe is in flight. 'queued' shares the spinner
       (it is waiting on the same run, so a different glyph would imply a
       difference that is not there). The label survives as the tooltip and the
       accessible name.
       The chip itself is WHITE in every live state and only the glyph carries
       the colour (see the CSS), so the running state reads as "white chip, dark
       ring turning" and a pass as "white chip, blue tick" — exactly the two
       states the user asked for. */
    const label = v === 'ok' ? 'Success' : v === 'error' ? 'Failed'
      : v === 'testing' ? 'Testing' : 'Queued';
    const ico = v === 'ok' ? ZI('check')
      : v === 'error' ? ZI('close')
      : ZI('spinner');
    const spin = (v === 'testing' || v === 'queued') ? ' is-spin' : '';
    return `<span class="pv-crow-test is-${v}${spin}" title="${label}"
      aria-label="${label}" role="img"><span class="pv-crow-test-ico"
      aria-hidden="true">${ico}</span></span>`;
  };

  /* One connection row, two tight lines:
       line 1  #N <full email on ONE line>              [enable/disable switch]
       line 2  Active  🔒  ✓                            [bolt][refresh][edit][trash]
     The switch rides on the name line and the icon cluster rides on the status
     line, so the card is only as tall as those two rows. Nothing is truncated:
     the email is nowrap at a size that fits a real address, and the status row
     is a single line of pills. The auth and test pills are ICON ONLY (padlock =
     OAuth, key = API key; tick = pass, cross = fail, spinner = in flight), which
     is what keeps the row short enough for the email to breathe.

     The order is fixed here: it is read from the router and shown as the #N
     index, but it cannot be changed from this card any more. The ↑/↓ arrows
     and the drag path that replaced them are both gone — the router's order is
     read-only on this screen.

     A failure is drawn INSIDE the same card, on its own third line directly
     under the status pills, separated by a hairline rule. A healthy account
     simply omits that line, so the card only grows for a broken one and the
     error never detaches from the account it belongs to. The wrapper is the
     `[data-conn-row]` hit target, and it is only a hit target in Select mode.

     WHICH error is shown follows the live verdict, because the stored one goes
     stale the moment a probe runs:
       - 'testing' / 'queued' -> nothing. The row is mid-probe; an old reason
         underneath it would describe a state that is no longer known true.
       - 'ok'                  -> nothing. A pass is not a failure.
       - 'error'               -> the message from THIS probe.
       - no verdict yet        -> the router's own last-known failure, which is
         what lets a fresh screen show why an account is already red. */
  const connRow = (c, i) => {
    const picked = providerDetailState.selected.some(x => String(x) === String(c.id));
    const verdict = providerDetailState.connTest[String(c.id)];
    /* The failure line, gated on the live verdict — see the block comment
       above. `pvConnErrorParts` needs a {error_code,last_error} shape, so the
       probe's own message is fed through it as a last_error. */
    const err = verdict === 'testing' || verdict === 'queued' || verdict === 'ok'
      ? null
      : verdict === 'error'
        ? pvConnErrorParts(providerDetailState.connTestError[String(c.id)] || {})
        : (c.error_code || c.last_error ? pvConnErrorParts(c) : null);
    /* Auto-ping is a real router opt-in, and only for the providers that
       support it AND for OAuth accounts — the router's own dashboard gates it
       exactly this way, because warming a quota window is meaningless for a
       plain API key. A button that did nothing would be worse than no button.

       The glyph is a lightning bolt: this control is a short periodic burst
       that keeps the quota window warm, and a bolt reads as exactly that.
       (The earlier pin glyph suggested "pin to top", a different idea.) */
    const pingRow = providerDetailState.autoPing.providers?.[c.provider];
    const pingSupported = Boolean(pingRow) && String(c.auth_type || '').toLowerCase() === 'oauth';
    const pingOn = Boolean(pingRow?.connections?.[String(c.id)]);
    return `
    <div class="pv-crow-wrap ${c.active ? '' : 'is-off'} ${picked ? 'is-picked' : ''}"
         data-conn="${esc(c.id)}" data-conn-row
         ${selectMode ? 'data-selectable="1" role="checkbox" aria-checked="' + (picked ? 'true' : 'false') + '" tabindex="0"' : ''}>
      <div class="pv-crow">
        <div class="pv-crow-r1">
          <strong class="pv-crow-name"><span class="pv-crow-pri">#${i + 1}</span>${esc(c.email || c.name || c.provider)}</strong>
        </div>
        <div class="pv-crow-r2">
          <div class="pv-crow-meta">
            <span class="pv-crow-state ${c.active ? 'on' : 'off'}">
              <span class="pv-crow-state-dot" aria-hidden="true"></span>${c.active ? 'Active' : 'Disable'}</span>
            <span class="pv-crow-badge" title="${esc(pvAuthLabel(c.auth_type))}"
                  aria-label="${esc(pvAuthLabel(c.auth_type))}" role="img">
              <span class="pv-crow-badge-ico" aria-hidden="true">${pvAuthIcon(c.auth_type)}</span></span>
            ${connTestBadge(String(c.id), c)}
          </div>
          <div class="pv-crow-acts">
            ${pingSupported ? `
            <button class="pv-act pv-ping ${pingOn ? 'is-on' : ''}" data-conn-ping="${esc(c.id)}"
                    data-on="${pingOn ? 1 : 0}" role="switch" aria-checked="${pingOn ? 'true' : 'false'}"
                    title="Auto-ping ${pingOn ? 'on — warms the quota window after reset' : 'off'}"
                    aria-label="Auto-ping ${pingOn ? 'on' : 'off'}">${ZI('bolt')}</button>` : ''}
            <button class="pv-act ${providerDetailState.connTest[String(c.id)] === 'testing' ? 'is-busy' : ''}"
                    data-conn-test="${esc(c.id)}" title="Test this account (sends 1 real request)"
                    aria-label="Test account">${ZI('restart')}</button>
            <button class="pv-act" data-conn-edit="${esc(c.id)}" title="Edit account"
                    aria-label="Edit account">${ZI('pencil')}</button>
            <button class="pv-act danger" data-conn-del="${esc(c.id)}" title="Delete account"
                    aria-label="Delete account">${ZI('trash')}</button>
            <!-- The enable/disable switch lives at the far right of the action
                 cluster, AFTER delete — the same order the router's own card
                 uses (Proxy · Auto-ping · Edit · Delete · switch). It reads as
                 the card's master control rather than a stray toggle up on the
                 name line, and it keeps every account control on one row. -->
            <button class="pv-switch ${c.active ? 'on' : ''}" data-conn-toggle="${esc(c.id)}"
                    data-active="${c.active ? 1 : 0}" role="switch" aria-checked="${c.active ? 'true' : 'false'}"
                    title="${c.active ? 'Disable account' : 'Enable account'}"
                    aria-label="${c.active ? 'Disable account' : 'Enable account'}"><i></i></button>
          </div>
        </div>
        ${err ? `<div class="pv-crow-error">
          <span class="pv-crow-error-ico" aria-hidden="true">${ZI('warning')}</span>
          ${err.code ? `<span class="pv-crow-error-code">${esc(err.code)} :</span>` : ''}
          <span class="pv-crow-error-msg">${esc(err.message)}</span>
        </div>` : ''}
      </div>
    </div>`;
  };

  const connRows = routerRows.length
    ? routerRows.map(connRow).join('')
    : '<div class="pv-empty">No accounts yet. Click Connect OAuth to add one.</div>';

  host.innerHTML = `
    <div class="pv-detail-panel">
      <div class="pv-topbar">
        <button class="pv-topbar-back" data-pd-back type="button"
                aria-label="Kembali ke Providers" title="Kembali">
          ${ZI('chevleft')}
        </button>
        <span class="pv-topbar-title" role="heading" aria-level="1">${esc(detailName)}</span>
        <!-- Same width as the back button, so the title lands on the exact
             centre of the bar rather than being nudged by the button's width. -->
        <span class="pv-topbar-pad" aria-hidden="true"></span>
      </div>
      <div class="pv-detail-body">
        <div class="pv-detail-sheet">
        <div class="pv-identity">
          ${pvProviderIcon(p, true)}
          <div class="pv-identity-copy">
            <strong>${esc(detailName)}</strong>
            <span class="pv-identity-links">
              <a href="${esc(pvProviderSignupUrl(p))}" target="_blank" rel="noopener noreferrer">Sign up</a>
              <span>/</span>
              <a href="${esc(pvProviderDocsUrl(p))}" target="_blank" rel="noopener noreferrer">Learn more</a>
            </span>
          </div>
        </div>

        ${isOAuth ? `
        <div class="pv-risk">
          <span class="pv-risk-icon">!</span>
          <div>
            <strong>Risk Notice:</strong> This provider uses a subscription/OAuth session that
            is not officially licensed for proxy/router use. Your account may be restricted or
            banned. Use at your own risk.
          </div>
        </div>` : ''}

        <div class="pv-conns">
          <div class="pv-conns-head">
            <span class="pv-conns-title">Connections <span>(${routerCount})</span></span>
            <span class="pv-conns-sticky">${activeCount}/${routerCount} active</span>
          </div>
          ${routerCount ? `<div class="pv-connbar">
            <!-- The batch test sits ABOVE the Round Robin line: it is the action
                 you reach for first when a provider misbehaves, so it gets the
                 top slot, and the Round Robin row below it is a setting rather
                 than a button. The live counts (Total/Completed/…) render BELOW
                 this button, not above it, so the eye goes button → progress →
                 the list it is walking. -->
            <button class="pv-mini pv-testall-btn" data-conn-testall ${!runActive ? '' : 'disabled'}>
              Testing Connection One-by-one</button>
          </div>` : ''}
          ${connRunBar}
          <div class="pv-conns-tools pv-rr-row ${selectMode ? 'is-select' : ''}">
            <!-- ONE icon does the whole job. It used to be the word "Select"
                 plus a separate select-all control, which asked the user to
                 understand a mode before they could use it. Now the icon IS the
                 select-all: press it and every card is picked at once, and the
                 glyph flips to an X so the same button undoes it.
                 The icon is nudged right to sit on the same column as the pick
                 number each card shows, so the control and the numbers it
                 governs line up.
                 Delete is a WORD, not a glyph: a trash can at this small scale
                 read as just another icon and hid what it did; "Delete" says
                 exactly what pressing it will do. -->
            ${routerCount ? `<span class="pv-selhead">
              <button class="pv-selall-toggle ${allPicked ? 'is-on' : ''}" data-conn-selectall
                      type="button" aria-pressed="${allPicked ? 'true' : 'false'}"
                      title="${allPicked ? 'Deselect all' : 'Select all'}"
                      aria-label="${allPicked ? 'Deselect all' : 'Select all'}">${ZI(allPicked ? 'close' : 'checklist')}</button>
              <button class="pv-selicon danger" data-conn-bulk="delete"
                      title="Delete selected" aria-label="Delete selected">Delete</button>
            </span>` : ''}
            <!-- Round Robin and Sticky are ONE control in two states, and the
                 whole cluster is pushed to the RIGHT edge so its switch lands on
                 the exact same column as the per-account enable/disable switch
                 below it. The switch is the SAME 32×18 box the account rows
                 use, so "on" looks identical wherever it appears.
                 The label is the state readout: it says "Round Robin" while the
                 strategy is off, and the word "Sticky" once it is on — at which
                 point the Sticky limit box appears beside it. Pressing EITHER
                 the label or the switch toggles the strategy, so the whole
                 cluster is one big hit target. -->
            <div class="pv-rr-tail">
              <button class="pv-rr-lab ${strategy.round_robin ? 'is-on' : ''}" data-conn-rr
                      type="button"
                      title="${strategy.round_robin ? 'Round Robin is on — press to turn it off' : 'Spread the load across all accounts in turn'}"
                      aria-label="${strategy.round_robin ? 'Sticky' : 'Round Robin'}">${strategy.round_robin ? 'Sticky' : 'Round Robin'}</button>
              ${strategy.round_robin ? `
              <label class="pv-rr-sticky" title="How many consecutive requests reuse the same account">
                <input class="pv-rr-input" type="number" min="1" max="99" inputmode="numeric"
                       data-conn-sticky value="${esc(String(strategy.sticky))}"
                       aria-label="Sticky limit">
              </label>` : ''}
              <button class="pv-switch ${strategy.round_robin ? 'on' : ''}" data-conn-rr-switch
                      role="switch" aria-checked="${strategy.round_robin ? 'true' : 'false'}"
                      title="${strategy.round_robin ? 'Turn round robin off' : 'Turn round robin on'}"
                      aria-label="Round Robin"><i></i></button>
            </div>
          </div>
          <div class="pv-crow-list">${connRows}</div>
          <div class="pv-conns-foot">
            <button class="pv-action primary" data-pd-addkey>+ Add API Key</button>
            ${isOAuth ? `<button class="pv-action" data-pd-oauth>Connect OAuth</button>` : ''}
          </div>
        </div>

        <div class="pv-models">
          <div class="pv-models-head">
            <span class="pv-models-title">Available Models <span>(${visible.length}/${(models || []).length})</span></span>
            ${(providerDetailState.thinkingLevels || []).length ? `
            <select class="pv-think-select" data-thinking
                    title="Appends (level) suffix to copied model names"
                    aria-label="Thinking level">
              ${providerDetailState.thinkingLevels.map(lvl => `
                <option value="${esc(lvl)}" ${thinkLevel === lvl ? 'selected' : ''}>Thinking: ${esc(lvl.charAt(0).toUpperCase() + lvl.slice(1))}</option>`).join('')}
            </select>` : ''}
          </div>
          <div class="pv-model-list">${modelRows}</div>
          <button class="pv-add-model" type="button" data-pd-addmodel>
            <span class="pv-add-model-glyph">${ZI('agentchip')}</span>
            <span>Add Model</span>
          </button>
          ${unusedModels}
        </div>
        </div>
      </div>
    </div>`;

  host.querySelector('[data-pd-back]').onclick = closeProviderDetail;

  /* Put the scroll back where it was before this render wiped the panel. Done
     after the shell exists and BEFORE the pull-nudge wiring, so the restored
     offset is the one the gesture will start from. */
  if (prevScrollTop) {
    const newScroller = host.querySelector('.pv-detail-body');
    if (newScroller) newScroller.scrollTop = prevScrollTop;
  }

  /* Pull nudge — the exact gesture the Providers list uses, so the detail screen
     feels identical. `.pv-detail-body` is the native scroller; the inner
     `.pv-detail-sheet` is what actually moves, which is what lets the static grid
     behind it show through the revealed gap instead of a bare strip.
     Workspace gestures are disabled below 961px, so this is gated the same way. */
  if (window.matchMedia('(max-width: 960px)').matches) {
    const scroller = host.querySelector('.pv-detail-body');
    const sheetEl = host.querySelector('.pv-detail-sheet');
    if (typeof wireWorkspacePullNudge === 'function') wireWorkspacePullNudge(scroller, sheetEl);
  }

  const connAction = async (id, action, body, okMsg) => {
    try {
      await api(`/providers/connection/${encodeURIComponent(id)}/${action}`, {
        method: 'POST', body: body || {}, timeoutMs: 25000,
      });
      await refreshConns();
      if (okMsg) toast(okMsg, 'ok');
    } catch (err) {
      toast(`${err.code || ''} ${err.message}`.trim() || 'Action failed', 'err');
    }
  };

  // Enable / disable one connection.
  host.querySelectorAll('[data-conn-toggle]').forEach(btn => btn.addEventListener('click', () => {
    const id = btn.dataset.connToggle;
    const next = btn.dataset.active !== '1';
    connAction(id, 'toggle', { active: next }, next ? 'Connection enabled' : 'Connection disabled');
  }));

  /* Auto-ping per account. The write goes straight to the router's own
     settings, so the pin shows what the router will actually do. */
  host.querySelectorAll('[data-conn-ping]').forEach(btn => btn.addEventListener('click', () => {
    const id = btn.dataset.connPing;
    const conn = routerRows.find(c => String(c.id) === String(id)) || {};
    const next = btn.dataset.on !== '1';
    setAutoPing(conn.provider, next, id,
      next ? 'Auto-ping on — quota window will be warmed after reset'
           : 'Auto-ping off');
  }));

  /* Select mode is opened by the select-all icon beside Round Robin. A card is
    inert until something is picked; once it is, tapping a card toggles it. The
    picked card is marked only by a soft blue ring — there is no number badge,
    and no reorder control, so the router's order stays as it reports it. */
  /* The ONE toggle does select-all AND deselect-all. Pressing it with anything
     left to pick fills the selection (and opens the mode); pressing it once
     everything is picked clears the selection and closes the mode. The glyph is
     repainted from the same `every` test by paintSelectMode, so the button and
     the cards can never disagree. */
  host.querySelector('[data-conn-selectall]')?.addEventListener('click', () => {
    const live = new Set(rowEls().map(row => String(rowId(row))));
    const pickedLive = providerDetailState.selected.filter(id => live.has(String(id)));
    const every = live.size > 0 && pickedLive.length >= live.size;
    if (every) {
      providerDetailState.selected = [];
      providerDetailState.selectMode = false;
    } else {
      providerDetailState.selected = routerRows.map(c => String(c.id));
      providerDetailState.selectMode = true;
    }
    /* Paint in place rather than re-render: a full render() rebuilds every card
       node and throws away scroll position, and the cards are exactly what has
       to light up here. */
    paintSelectMode();
  });

  /* Round robin is the router's own per-provider setting, so the switch writes
     it there instead of holding a local flag the router would ignore. The
     Sticky box only exists while round robin is on, because it is meaningless
     without it — same as the router's own screen.
     The LABEL and the SWITCH are two hit targets for the same setting: the
     label reads "Round Robin" when off and becomes the Sticky pin glyph when
     on, so pressing either one toggles it. */
  const toggleRoundRobin = () => {
    const next = !providerDetailState.strategy.round_robin;
    setProviderStrategy({ round_robin: next },
      next ? 'Round Robin on' : 'Round Robin off');
  };
  host.querySelector('[data-conn-rr]')?.addEventListener('click', toggleRoundRobin);
  host.querySelector('[data-conn-rr-switch]')?.addEventListener('click', toggleRoundRobin);
  host.querySelector('[data-conn-sticky]')?.addEventListener('change', (e) => {
    const input = e.currentTarget;
    const n = Math.max(1, Math.min(99, parseInt(input.value, 10) || 1));
    input.value = String(n);
    setProviderStrategy({ sticky: n }, `Sticky: ${n}`);
  });

  /* Test ONE account for real.

     The router's own per-connection test refuses OAuth providers outright
     ("Provider test not supported"), so a token refresh proves nothing here.
     Instead a real model request is pinned to this exact connection: a pass
     means THIS account answered, a fail carries the upstream reason. The badge
     is set first so the row says "testing" while the request is in flight —
     the toast alone would leave the user guessing which account was being
     probed. */
  /* Which model to probe an account with.

     Two facts decide this. The router routes by model prefix, so probing a
     `cbai/` account with an `ag/` model fails for a reason that has nothing to
     do with the account. And within one provider, accounts differ: a Codex
     ChatGPT plan answers `gpt-5.6-luna` but rejects `gpt-5.6-sol`. So the
     connection's OWN history wins — the router records every model it has
     actually served through that connection — and only then does the prefix
     match come into play. Anything else reports a healthy account as broken. */
  const probeCandidatesFor = pvProbeCandidates;

  /* Probe one account, trying the candidate models in order.

     One model name is not enough: a served model may be one this account no
     longer supports, and the router's list spells names with a routing prefix
     the history does not carry. So each candidate is tried until one answers —
     the account is only "failed" when every candidate was rejected, which is
     the same bar the router's own dashboard applies. */
  const testOne = pvTestOneConnection;

  host.querySelectorAll('[data-conn-test]').forEach(btn => btn.addEventListener('click', async () => {
    const id = btn.dataset.connTest;
    const conn = routerRows.find(c => String(c.id) === String(id)) || {};
    btn.disabled = true; btn.classList.add('is-busy');
    const d = await testOne(id, probeCandidatesFor(conn), Boolean(conn.active));
    toast(d.disabled ? 'Account disabled — enable it first to test'
      : d.valid ? `OK${Number.isFinite(d.latency_ms) ? ' · ' + d.latency_ms + 'ms' : ''}`
      : `Failed: ${d.error || 'invalid'}`,
      d.disabled ? 'warn' : d.valid ? 'ok' : 'err');
    if (btn.isConnected) { btn.disabled = false; btn.classList.remove('is-busy'); }
  }));

  /* Test every connection, one by one, reporting live progress.

     One-by-one rather than parallel: the router rate-limits per account, so a
     burst of concurrent probes would report failures that are really just
     contention. The run object is what the progress bar reads, and `cancelled`
     is the only thing Stop has to set — the loop checks it between accounts. */
  const runBatch = async () => {
    const rows = [...routerRows];
    if (!rows.length) return;
    const run = { total: rows.length, done: 0, passed: 0, failed: 0, skipped: 0,
                  current: null, cancelled: false };
    providerDetailState.connRun = run;
    providerDetailState.runHideAt = 0;   // live run: no hide time yet
    providerDetailState.connTest = {};
    providerDetailState.connTestError = {};
    rows.forEach(c => { providerDetailState.connTest[String(c.id)] = 'queued'; });
    renderProviderDetail();

    for (const c of rows) {
      if (run.cancelled || !providerDetailState.open) break;
      run.current = String(c.id);
      renderProviderDetail();
      const d = await testOne(String(c.id), probeCandidatesFor(c), Boolean(c.active));
      run.done += 1;
      if (d.disabled) run.skipped += 1;
      else if (d.valid) run.passed += 1;
      else run.failed += 1;
      renderProviderDetail();
    }
    run.current = null;
    const stopped = run.cancelled || !providerDetailState.open;
    /* The summary is transient: schedule it to disappear 10s from now, then
       re-render at that moment so it actually goes away without a user action.
       The timeout is stored so a NEW run (or leaving the screen) can cancel it. */
    providerDetailState.runHideAt = Date.now() + 10000;
    clearTimeout(providerDetailState.runHideTimer);
    providerDetailState.runHideTimer = setTimeout(() => {
      if (!providerDetailState.open) return;
      renderProviderDetail();
    }, 10050);
    renderProviderDetail();
    const skipped = run.skipped ? ` · ${run.skipped} disabled skipped` : '';
    toast(stopped
      ? `Stopped · ${run.passed} passed, ${run.failed} failed${skipped}`
      : `${run.passed}/${run.total - run.skipped} connections healthy${skipped}`,
      run.failed === 0 && !stopped ? 'ok' : 'warn');
    // Refresh once at the end, not per account: each refresh re-renders the
    // whole screen, which would fight the progress bar for the whole run.
    if (!stopped) await refreshConns();
  };

  host.querySelector('[data-conn-testall]')?.addEventListener('click', () => {
    if (providerDetailState.connRun && !providerDetailState.connRun.cancelled) return;
    runBatch();
  });

  // Delete a connection — destructive, so it asks first in a compact popup.
  host.querySelectorAll('[data-conn-del]').forEach(btn => btn.addEventListener('click', () => {
    const id = btn.dataset.connDel;
    const row = routerRows.find(c => String(c.id) === String(id)) || {};
    const who = row.email || row.name || 'this account';
    const body = el('div', 'delete-confirmation',
      `<strong>Delete this account?</strong><p>${esc(who)} will be removed from ${esc(detailName)}. Its credentials are deleted from the router and cannot be recovered.</p>`);
    modal({
      title: 'Delete account',
      body,
      compact: true,
      actions: [
        { label: 'Cancel', kind: 'ghost', onClick: closeModal },
        { label: 'Delete', kind: 'danger', onClick: async () => {
            /* Drop the row from the DOM first, then write. The delete is a
               single round-trip and the user should see the row go immediately
               instead of watching a spinner on a list that has already decided
               the outcome. If the write fails the row comes back on refresh. */
            closeModal();
            const el0 = host.querySelector(`[data-conn="${CSS.escape(String(id))}"]`);
            if (el0) el0.remove();
            providerDetailState.selected = providerDetailState.selected
              .filter(x => String(x) !== String(id));
            try {
              await api(`/providers/connection/${encodeURIComponent(id)}/delete`, {
                method: 'POST', body: {}, timeoutMs: 20000,
              });
              toast('Connection deleted', 'ok');
              await refreshConns();
            } catch (err) {
              toast(`${err.code || ''} ${err.message}`.trim() || 'Failed to delete', 'err');
              await refreshConns();
            }
          } },
      ],
    });
  }));

  /* Card interaction. `selected` is the single source of truth for the bulk
     bar, and it is filtered against the rows that still exist on every render,
     so a deleted account cannot linger in the selection and get sent again.

     Two gestures live on the same rectangle and must not fight:
       • tap (Select mode on)          -> toggle this card's pick
       • long press (any mode)         -> turn Select mode on, pick this card,
                                          and arm a drag so the card can be
                                          dropped into a new rotation position
     A short press in normal mode therefore does nothing at all, which is what
     lets a tap on the row stop opening an account the user only wanted to read. */
  const rowEls = () => Array.from(host.querySelectorAll('[data-conn-row]'));
  const rowId = r => r.dataset.conn;

  /* Paint the Select-mode UI onto the EXISTING nodes.

     A full render() would be simpler, but it would throw away focus and any
     half-typed input in the panel. Everything the mode changes is therefore
     toggled in place, and this is the ONE place both the fresh render and
     every tap pass through. */
  const paintSelectMode = () => {
    const on = Boolean(providerDetailState.selectMode);
    const picked = new Set(providerDetailState.selected.map(String));
    /* The mode lives on the Round Robin line now: the word "Select" lights up
       and the two actions (select-all, delete) fade in beside it. Everything is
       toggled by classes on the EXISTING nodes, so nothing is inserted or
       removed and the row cannot jump. */
    const bar = host.querySelector('.pv-rr-row');
    bar?.classList.toggle('is-select', on);
    /* The ONE toggle is also the select-all. Its glyph is the state: the
       select-all marks appear while there is something left to pick, and flip
       to an X the moment every card is picked, so the same button that selected
       everything is the button that clears it. Re-rendering the glyph here (not
       only in the markup) is what makes an individual un-pick flip it back
       without a full repaint. */
    const every = routerRows.length > 0 && picked.size >= routerRows.length;
    const toggle = host.querySelector('[data-conn-selectall]');
    if (toggle) {
      const want = every ? 'close' : 'checklist';
      if (toggle.dataset.glyph !== want) {
        toggle.innerHTML = ZI(want);
        toggle.dataset.glyph = want;
      }
      toggle.classList.toggle('is-on', every);
      const lbl = every ? 'Deselect all' : 'Select all';
      toggle.title = lbl;
      toggle.setAttribute('aria-label', lbl);
      toggle.setAttribute('aria-pressed', every ? 'true' : 'false');
    }
    rowEls().forEach(row => {
      const id = String(rowId(row));
      const isPicked = picked.has(id);
      /* Picking is shown by the soft blue ring on the card (see the CSS), and
         by nothing else — there is no number badge any more. Only the ring
         toggle and the ARIA state change here. */
      row.classList.toggle('is-picked', isPicked);
      /* Only in Select mode is the card a hit target at all. Outside it the
         card is inert: no pointer cursor, no checkbox role, no tab stop. */
      if (on) {
        row.dataset.selectable = '1';
        row.setAttribute('role', 'checkbox');
        row.setAttribute('aria-checked', isPicked ? 'true' : 'false');
        row.tabIndex = 0;
      } else {
        delete row.dataset.selectable;
        row.removeAttribute('role');
        row.removeAttribute('aria-checked');
        row.removeAttribute('tabindex');
      }
    });
  };

  /* Cards are NOT a reorder target any more. The ↑/↓ arrows and the earlier
     drag-to-reorder path are both removed: the order shown is whatever the
     router reports, and it cannot be changed from this screen. Pressing a card
     only ever toggles the selection, and only in Select mode — a glance at an
     account can no longer reorder or select anything. */
  host.querySelectorAll('[data-conn-row]').forEach(row => {
    row.addEventListener('click', e => {
      if (!providerDetailState.selectMode) return;
      // Buttons, the switch and the arrows act on their own; the rest of the
      // card is the selection surface.
      if (e.target.closest('button, a, input, select, textarea, label')) return;
      const id = String(rowId(row));
      const on = !providerDetailState.selected.includes(id);
      providerDetailState.selected = on
        ? providerDetailState.selected.concat(id)
        : providerDetailState.selected.filter(x => x !== id);
      paintSelectMode();
    });
    row.addEventListener('keydown', e => {
      if (e.key !== 'Enter' && e.key !== ' ') return;
      if (!providerDetailState.selectMode) return;
      e.preventDefault();
      const id = String(rowId(row));
      const on = !providerDetailState.selected.includes(id);
      providerDetailState.selected = on
        ? providerDetailState.selected.concat(id)
        : providerDetailState.selected.filter(x => x !== id);
      paintSelectMode();
    });
  });

  /* Bulk actions. Only the ticked ids are sent — the server never expands an
     "all" of its own, so a stale selection can never delete an account the user
     did not see. Delete confirms; activate/deactivate do not, because both are
     one tap away from being undone. */
  host.querySelectorAll('[data-conn-bulk]').forEach(btn => btn.addEventListener('click', () => {
    const action = btn.dataset.connBulk;
    const ids = providerDetailState.selected.slice();
    if (!ids.length) return;
    const label = action === 'activate' ? 'activated'
      : action === 'deactivate' ? 'deactivated' : 'deleted';
    const run = async () => {
      try {
        const d = await api('/providers/connections/bulk', {
          method: 'POST', body: { action, ids }, timeoutMs: 60000,
        });
        providerDetailState.selected = [];
        await refreshConns();
        toast(`${d.done}/${d.total} accounts ${label}`,
              d.failed ? 'warn' : 'ok');
      } catch (err) {
        toast(`${err.code || ''} ${err.message}`.trim() || 'Action failed', 'err');
      }
    };
    if (action !== 'delete') return run();
    modal({
      title: `Delete ${ids.length} accounts`,
      subtitle: 'This action is permanent.',
      body: `<p>Delete the <strong>${ids.length} selected accounts</strong> from ${esc(detailName)}? Their credentials are deleted and cannot be recovered.</p>`,
      actions: [
        { label: 'Cancel', kind: 'ghost', onClick: closeModal },
        { label: 'Delete', kind: 'danger', onClick: async () => { closeModal(); await run(); } },
      ],
      footerActions: true,
    });
  }));

  /* Edit opens a POPUP over this screen — not a full-page navigation. The
     broker has no per-row field editor, so the two things it CAN change are
     offered here: the display name (a real PUT the router stores) and the
     credential itself (re-running the OAuth / API-key flow). Everything the
     popup cannot change is stated rather than silently missing. */
  host.querySelectorAll('[data-conn-edit]').forEach(btn => btn.addEventListener('click', () => {
    const id = btn.dataset.connEdit;
    const row = routerRows.find(c => String(c.id) === String(id)) || {};
    const who = row.email || row.name || row.provider || 'this account';
    const body = el('div', 'pv-editconn');
    body.innerHTML = `
      <label class="pv-editconn-field">
        <span>Account name</span>
        <input type="text" id="pvEditName" autocomplete="off" spellcheck="false"
               value="${esc(row.name || '')}" placeholder="${esc(row.email || 'Name for this account')}">
      </label>
      <p class="pv-editconn-hint">Account identity: <b>${esc(who)}</b> · ${esc(pvAuthLabel(row.auth_type))}.
        Credentials are not changed here.</p>
      <button class="pv-action" type="button" data-edit-reauth>
        ${isOAuth ? 'Otorisasi ulang (OAuth)' : 'Ganti API Key'}
      </button>`;
    modal({
      title: 'Edit account',
      subtitle: who,
      body,
      popup: true,
      /* Both buttons stay in the footer: this is a form, so the confirm belongs
         next to the fields it submits, not promoted to the header. */
      footerActions: true,
      actions: [
        { label: 'Cancel', kind: 'ghost', onClick: closeModal },
        { label: 'Save', kind: 'primary', onClick: async () => {
            const input = body.querySelector('#pvEditName');
            const name = input ? input.value.trim() : '';
            if (name === (row.name || '')) { closeModal(); return; }
            try {
              await api(`/providers/connection/${encodeURIComponent(id)}/rename`, {
                method: 'POST', body: { name }, timeoutMs: 20000,
              });
              closeModal();
              toast('Account name saved', 'ok');
              await refreshConns();
            } catch (err) {
              toast(`${err.code || ''} ${err.message}`.trim() || 'Failed to save', 'err');
            }
          } },
      ],
    });
    /* The credential path leaves the popup and opens its own flow, because that
       is a multi-step interaction (device code / redirect), not a form field. */
    body.querySelector('[data-edit-reauth]')?.addEventListener('click', () => {
      closeModal();
      if (isOAuth) return openOAuthConnect(p.id, detailName);
      providerForm(p.id, p.protocol);
    });
  }));

  /* Proxy is no longer offered per row: a proxy is set once on the provider's
     own proxy pool screen, and a per-row picker invited binding one account to
     a pool the others did not use. Kept as an explicit no-op note so a stale
     cached bundle cannot silently re-introduce the control. */

  /* Bulk enable / disable now lives in the selection bar above the list: the
     old header checkbox conflated "tick these" with "apply to everything", so
     one tap flipped every account with no way to pick a subset. */

  /* Thinking level. Persisted server-side and validated there against the live
     model ladder, so a level this provider cannot honour is refused rather than
     silently attached to every copied model name. */
  host.querySelector('[data-thinking]')?.addEventListener('change', async (e) => {
    const sel = e.currentTarget;
    const level = sel.value;
    const previous = providerDetailState.thinking;
    sel.disabled = true;
    try {
      const d = await api(`/providers/${encodeURIComponent(p.id)}/models`, {
        method: 'POST', body: { action: 'thinking', level },
      });
      providerDetailState.models = d.models || providerDetailState.models;
      providerDetailState.thinkingLevels = d.thinking_levels || providerDetailState.thinkingLevels;
      providerDetailState.thinking = d.thinking || 'auto';
      renderProviderDetail();
      toast(level === 'auto' ? 'Thinking: Auto' : `Thinking: ${level}`, 'ok', 1200);
    } catch (err) {
      // Keep the UI honest: revert to what the server still holds.
      providerDetailState.thinking = previous;
      renderProviderDetail();
      toast(`${err.code || ''} ${err.message}`.trim() || 'Failed to save', 'err');
    }
  });

  /* Copy a model id to the clipboard, with the thinking suffix already applied
     by the render pass. The icon flips to a check for a moment — that is the
     only feedback a copy can honestly give. */
  host.querySelectorAll('[data-mcopy]').forEach(btn => btn.addEventListener('click', async (e) => {
    e.stopPropagation();
    const text = btn.dataset.mcopy;
    const bare = String(text).replace(/\([^)]*\)$/, '');
    try {
      await navigator.clipboard.writeText(text);
      providerDetailState.copied = bare;
      renderProviderDetail();
      toast(`Disalin: ${text}`, 'ok', 1200);
      setTimeout(() => {
        if (providerDetailState.copied === bare) {
          providerDetailState.copied = '';
          if (providerDetailState.open) renderProviderDetail();
        }
      }, 1400);
    } catch (_) {
      toast('Clipboard ditolak browser', 'err');
    }
  }));

  host.querySelectorAll('[data-mtest]').forEach(btn => btn.addEventListener('click', async (e) => {
    e.stopPropagation();
    const model = btn.dataset.mtest;
    btn.disabled = true;
    btn.classList.add('is-busy');
    try {
      const d = await api(`/providers/${encodeURIComponent(p.id)}/test-model`, {
        method: 'POST', body: { model }, timeoutMs: 40000
      });
      // Record the verdict so the card's glyph shows it, like the router does.
      providerDetailState.mtest[model] = 'ok';
      if (providerDetailState.open) renderProviderDetail();
      toast(`${model}: OK · ${d.latency_ms}ms`, 'ok');
    } catch (err) {
      providerDetailState.mtest[model] = 'error';
      if (providerDetailState.open) renderProviderDetail();
      toast(`${model}: ${err.code || ''} ${err.message}`.trim(), 'err');
    }
  }));

  // Toggle a model's visibility. Used by the card switch and the chips.
  /* Show / hide a model (the X and + buttons). OPTIMISTIC: the local list is
     flipped and repainted on the same frame, then the write goes out. The old
     version awaited two round-trips (write, then re-read) before repainting, so
     every press showed a beat of "loading" on the row. On failure we re-read the
     truth from the server and say so. */
  const setModelHidden = (model, hide) => {
    const list = providerDetailState.models;
    if (Array.isArray(list)) {
      const row = list.find(m => String(m.id) === String(model));
      if (row) row.hidden = hide;
    }
    renderProviderDetail();
    api(`/providers/${encodeURIComponent(p.id)}/models`, {
      method: 'POST', body: { action: hide ? 'hide' : 'unhide', model }
    }).then(async () => {
      const d = await apiWhenAuthed(`/providers/${encodeURIComponent(p.id)}/models`);
      providerDetailState.models = d.models || [];
      if (providerDetailState.open) renderProviderDetail();
    }).catch(async (err) => {
      /* Roll the row back to the server's truth instead of leaving the optimistic
         flip in place after a rejected write. */
      try {
        const d = await apiWhenAuthed(`/providers/${encodeURIComponent(p.id)}/models`);
        providerDetailState.models = d.models || [];
        if (providerDetailState.open) renderProviderDetail();
      } catch (_) { /* keep the optimistic state if even the re-read fails */ }
      toast(`${model}: ${err.code || ''} ${err.message}`.trim(), 'err');
    });
  };
  host.querySelectorAll('[data-mhide]').forEach(btn => btn.addEventListener('click', (e) => {
    e.stopPropagation();
    setModelHidden(btn.dataset.mhide, btn.dataset.hidden !== '1');
  }));

  /* The trash button. Two outcomes, decided by where the model comes from:
       - A HAND-ADDED model (m.custom) is not offered by the provider, so it is
         genuinely deleted.
       - A model the PROVIDER offers is only taken out of rotation — it moves to
         the "Tidak dipakai" block below, where a restore button brings it back.
         Deleting it outright would lie about what the endpoint can serve. */
  host.querySelectorAll('[data-mdel]').forEach(btn => btn.addEventListener('click', async (e) => {
    e.stopPropagation();
    const model = btn.dataset.mdel;
    const row = (providerDetailState.models || []).find(m => String(m.id) === String(model)) || {};
    const isCustom = Boolean(row.custom);
    const card = host.querySelector(`[data-model="${CSS.escape(String(model))}"]`);
    if (card) card.remove();
    try {
      const d = await api(`/providers/${encodeURIComponent(p.id)}/models`, {
        method: 'POST', body: { action: isCustom ? 'remove' : 'hide', model }, timeoutMs: 20000,
      });
      providerDetailState.models = d.models || [];
      renderProviderDetail();
      toast(isCustom ? `Model dihapus: ${model}`
                     : `Dipindah ke "Tidak dipakai": ${model}`, 'ok');
    } catch (err) {
      renderProviderDetail();
      toast(`${model}: ${err.code || ''} ${err.message}`.trim(), 'err');
    }
  }));

  /* Add Model — a pop-up with the same three glyphs the existing cards carry,
     plus a real existence check.

     "Add" must not just record a string: the whole point of adding a model is
     that the provider can answer with it. So the sheet probes it first (a real
     one-token request through this provider) and only saves it once it answers.
     A model the provider rejects is reported with the upstream reason instead
     of silently landing in the list as a dead entry. */
  const openAddModel = () => {
    const body = el('div', 'pv-addmodel-sheet');
    /* The bar already says "Add Model", so the sheet does not repeat it — it
       leads with what the action does instead. */
    body.innerHTML = `
      <div class="pv-addmodel-head">
        <span class="pv-mcard-glyph">${ZI('agentchip')}</span>
        <div class="pv-addmodel-copy">
          <strong>Uji model ke provider</strong>
          <small>The model is tested first; only one that answers is saved.</small>
        </div>
      </div>
      <label class="pv-addmodel-field">
        <span>Model ID</span>
        <input type="text" id="pvAddModelId" placeholder="mis. gpt-4o-mini"
               autocomplete="off" spellcheck="false" enterkeyhint="go">
      </label>
      <div class="pv-addmodel-status" id="pvAddModelStatus"></div>`;
    const input = body.querySelector('#pvAddModelId');
    const status = body.querySelector('#pvAddModelStatus');
    let probed = '';

    const setStatus = (kind, text) => {
      status.className = 'pv-addmodel-status' + (kind ? ' is-' + kind : '');
      status.textContent = text || '';
    };

    const check = async (announce) => {
      const model = input.value.trim();
      if (!model) return false;
      setStatus('busy', `Testing ${model} against the provider…`);
      try {
        const d = await api(`/providers/${encodeURIComponent(p.id)}/test-model`, {
          method: 'POST', body: { model }, timeoutMs: 60000,
        });
        probed = model;
        setStatus('ok', `Model ada dan menjawab · ${d.latency_ms}ms`);
        if (announce) toast(`${model}: OK`, 'ok', 1600);
        return true;
      } catch (err) {
        probed = '';
        setStatus('err', `${err.message || 'Model did not answer'}`);
        return false;
      }
    };

    // Any edit invalidates the previous pass, so Save can never store a model
    // that was verified under a different id.
    input.addEventListener('input', () => {
      if (probed && input.value.trim() !== probed) { probed = ''; setStatus('', ''); }
    });
    input.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') { e.preventDefault(); check(true); }
    });

    modal({
      title: 'Add Model',
      body,
      popup: true,
      actions: [
        { label: 'Test', kind: 'ghost', onClick: () => check(true) },
        { label: 'Cancel', kind: 'ghost', onClick: closeModal },
        { label: 'Add', kind: 'primary', onClick: async () => {
            const model = input.value.trim();
            if (!model) { setStatus('err', 'Model ID is required.'); return; }
            // Re-probe on save when the id changed since the last pass, so the
            // stored model is always one the provider just answered with.
            if (probed !== model && !(await check(false))) return;
            try {
              await api(`/providers/${encodeURIComponent(p.id)}/models`, {
                method: 'POST', body: { action: 'add', model }, timeoutMs: 20000,
              });
              const d = await apiWhenAuthed(`/providers/${encodeURIComponent(p.id)}/models`);
              providerDetailState.models = d.models || [];
              closeModal();
              renderProviderDetail();
              toast(`Model added: ${model}`, 'ok');
            } catch (err) {
              setStatus('err', `${err.code || ''} ${err.message}`.trim());
            }
          } },
      ],
      footerActions: true,
    });
    setTimeout(() => input.focus(), 60);
  };
  host.querySelector('[data-pd-addmodel]')?.addEventListener('click', openAddModel);

  /* "Add API Key" opens the same sheet the provider list uses for a fresh
     provider, but scoped to THIS provider: name + key (+ optional default
     model), with the Single / Bulk Add tabs. No proxy field anywhere. */
  host.querySelector('[data-pd-addkey]')?.addEventListener('click', () => addKeySheet(p));
  host.querySelector('[data-pd-oauth]')?.addEventListener('click', () => openOAuthConnect(p.id, p.name));
}

/* ── Add API key (Single | Bulk Add) ─────────────────────────────────────────

   Adding a key to a provider that is ALREADY set up is a small, repeatable
   action, so it is a pop-up over the detail screen rather than a full-screen
   form. Both tabs live in the same sheet so the parsing rules cannot drift, and
   the bulk parser is deliberately the same shape the router's own sheet
   documents: one key per line, ``name|apiKey`` or a bare ``apiKey``.

   No proxy field anywhere: a proxy is bound to a connection afterwards, as an
   explicit choice, and never as a side effect of pasting a key. */
function parseBulkKeys(text) {
  const out = [];
  String(text || '').split('\n').forEach((line, i) => {
    const raw = line.trim();
    if (!raw || raw.startsWith('#')) return;
    const bar = raw.indexOf('|');
    if (bar > 0) {
      const name = raw.slice(0, bar).trim();
      const key = raw.slice(bar + 1).trim();
      if (key) out.push({ name: name || `Key ${i + 1}`, api_key: key });
      return;
    }
    out.push({ name: `Key ${i + 1}`, api_key: raw });
  });
  return out;
}

function addKeySheet(provider) {
  const name = provider.name || provider.id;
  const body = el('div', 'pv-addkey-sheet');
  let mode = 'single';
  /* The footer's primary label follows the active tab, so it names the action
     the user is actually about to take. It is refreshed on every tab switch
     rather than captured once — a "Bulk Add" sheet offering "Add Key" reads
     like it will only take the first line. */
  const primaryBtn = () => document.querySelector('.modal-foot .btn.primary');

  const tabs = el('div', 'pv-addkey-tabs');
  tabs.innerHTML = `
    <button class="pv-addkey-tab is-on" data-keymode="single" type="button">Single</button>
    <button class="pv-addkey-tab" data-keymode="bulk" type="button">Bulk Add</button>`;
  body.appendChild(tabs);

  const pane = el('div', 'pv-addkey-pane');
  body.appendChild(pane);

  const status = el('div', 'pv-addkey-status');
  body.appendChild(status);
  const setStatus = (kind, text) => {
    status.className = 'pv-addkey-status' + (kind ? ' is-' + kind : '');
    status.textContent = text || '';
  };

  const renderPane = () => {
    pane.innerHTML = mode === 'single' ? `
      <label class="pv-addkey-field">
        <span>Name</span>
        <input type="text" id="pvKeyName" placeholder="Production Key"
               autocomplete="off" spellcheck="false">
      </label>
      <label class="pv-addkey-field">
        <span>API Key</span>
        <span class="pv-addkey-row">
          <input type="password" id="pvKeyValue" placeholder="sk-…"
                 autocomplete="off" spellcheck="false" enterkeyhint="done">
          <button class="pv-mini" type="button" data-keycheck>Check</button>
        </span>
      </label>
      <label class="pv-addkey-field">
        <span>Default Model <em>optional</em></span>
        <input type="text" id="pvKeyModel" placeholder="gpt-4o-mini"
               autocomplete="off" spellcheck="false">
      </label>
      <p class="pv-addkey-hint">Write the model ID exactly as the endpoint expects it.
        Leave blank if the provider already has a model stored.</p>` : `
      <p class="pv-addkey-hint">One key per line. Format: <code>name|apiKey</code>
        or just <code>apiKey</code> (named automatically).</p>
      <label class="pv-addkey-field">
        <span>Keys</span>
        <textarea id="pvKeyBulk" rows="7" spellcheck="false"
                  placeholder="name1|sk-key1&#10;name2|sk-key2&#10;sk-key-only-auto-named"></textarea>
      </label>
      <label class="pv-addkey-field">
        <span>Default Model <em>optional</em></span>
        <input type="text" id="pvKeyModelBulk" placeholder="gpt-4o-mini"
               autocomplete="off" spellcheck="false">
      </label>`;
    setStatus('', '');
    if (mode === 'single') {
      pane.querySelector('[data-keycheck]')?.addEventListener('click', async () => {
        const key = pane.querySelector('#pvKeyValue').value.trim();
        const model = pane.querySelector('#pvKeyModel').value.trim();
        if (!key) return setStatus('err', 'API key is required.');
        setStatus('busy', 'Testing the key against the provider…');
        try {
          /* Proven by a real call: the key is used for one request and never
             echoed back. A saved-then-broken key would look like a working
             account until the first chat failed. */
          const d = await api(`/providers/${encodeURIComponent(provider.id)}/test-model`, {
            method: 'POST', body: { model: model || '', api_key: key }, timeoutMs: 60000,
          });
          setStatus('ok', `Key diterima · ${d.latency_ms}ms`);
        } catch (err) {
          setStatus('err', err.message || 'Key ditolak endpoint');
        }
      });
    }
  };

  tabs.querySelectorAll('[data-keymode]').forEach(btn => btn.addEventListener('click', () => {
    mode = btn.dataset.keymode;
    tabs.querySelectorAll('[data-keymode]').forEach(b =>
      b.classList.toggle('is-on', b === btn));
    renderPane();
    const pb = primaryBtn();
    if (pb) {
      pb.textContent = mode === 'bulk' ? 'Add All Keys' : 'Add Key';
      pb.classList.remove('is-locked');
      pb.disabled = false;
    }
  }));
  renderPane();

  modal({
    title: `Add ${name} API Key`,
    body,
    popup: true,
    actions: [
      { label: 'Cancel', kind: 'ghost', onClick: closeModal },
      { label: mode === 'bulk' ? 'Add All Keys' : 'Add Key', kind: 'primary', onClick: async () => {
          if (mode === 'single') {
            const key = pane.querySelector('#pvKeyValue').value.trim();
            const who = pane.querySelector('#pvKeyName').value.trim();
            const model = pane.querySelector('#pvKeyModel').value.trim();
            if (!key) return setStatus('err', 'API key is required.');
            try {
              await api('/providers/connections/add', {
                method: 'POST',
                body: { provider: provider.id, name: who, api_key: key, model },
                timeoutMs: 40000,
              });
              closeModal();
              await refreshConns();
              toast('API key added', 'ok');
            } catch (err) {
              setStatus('err', `${err.code || ''} ${err.message}`.trim());
            }
            return;
          }
          const entries = parseBulkKeys(pane.querySelector('#pvKeyBulk').value);
          const model = pane.querySelector('#pvKeyModelBulk').value.trim();
          if (!entries.length) return setStatus('err', 'No keys could be read.');
          setStatus('busy', `Adding ${entries.length} keys…`);
          try {
            const d = await api('/providers/connections/add', {
              method: 'POST',
              body: { provider: provider.id, keys: entries, model },
              timeoutMs: 120000,
            });
            closeModal();
            await refreshConns();
            toast(`${d.added}/${d.total} keys added${d.failed ? ` · ${d.failed} failed` : ''}`,
                  d.failed ? 'warn' : 'ok');
          } catch (err) {
            setStatus('err', `${err.code || ''} ${err.message}`.trim());
          }
        } },
    ],
    footerActions: true,
  });
}

/* Proxy pools live on the router, not in Zeline. They are fetched on demand and
   cached here only so the picker can render instantly; every write goes straight
   through and then re-reads, so this cache can never become the source of truth. */
let proxyPoolState = { pools: [], loaded: false };

async function loadProxyPools(force = false) {
  if (proxyPoolState.loaded && !force) return proxyPoolState.pools;
  try {
    const d = await apiWhenAuthed('/providers/proxy-pools');
    proxyPoolState.pools = d.proxy_pools || [];
    proxyPoolState.loaded = true;
  } catch (_) {
    // A router that is down must not blank the list a caller is about to show;
    // the sheet reports the failure itself.
    if (!proxyPoolState.loaded) proxyPoolState.pools = [];
  }
  return proxyPoolState.pools;
}

/* Show a proxy URL without its credentials. `http://user:pass@host:port` is
   reduced to `http://host:port` for anything that is not the edit form — a
   screenshot or a shared screen must not leak the proxy login. */
function maskProxyUrl(url) {
  const raw = String(url || '');
  if (!raw) return '';
  try {
    const u = new URL(raw);
    const auth = u.username ? '••••@' : '';
    return `${u.protocol}//${auth}${u.hostname}${u.port ? ':' + u.port : ''}`;
  } catch (_) {
    // Not parseable — show only the scheme so a malformed value still says
    // something useful without echoing a possible credential.
    return raw.split('@').pop().slice(0, 40);
  }
}


/* Reload the broker connection list and repaint the detail page if it is open.
   Top-level on purpose: the proxy sheets are separate functions and also need to
   refresh the row they just changed. While this lived inside
   renderProviderDetail, calling it from proxyPicker threw a ReferenceError that
   the surrounding catch swallowed — the bind reached the router but the row kept
   showing the old state until the page was reopened. */
async function refreshConns() {
  await loadRouterConnections();
  if (providerDetailState.open) renderProviderDetail();
  /* The provider LIST reads its connected/disabled state from the same router
     rows, so a toggle there must repaint it too — otherwise a card keeps the
     pre-toggle switch until the page is reopened. */
  if (providerState.data && $('providerGrid')) renderProviderList();
}

/* Which pool a single connection routes through. Selecting "No proxy" is a real
   choice — it is how a connection is unbound — so it is offered explicitly
   rather than only as the absence of a selection. */
async function proxyPicker(conn) {
  const pools = await loadProxyPools(true);
  const who = conn.email || conn.name || 'this account';
  const body = el('div', 'proxy-picker');
  const note = el('small', 'field-desc',
    pools.length
      ? 'Traffic from this account goes through the selected proxy.'
      : 'No proxy pools yet. Add one in Manage Proxy first.');
  body.appendChild(note);

  const list = el('div', 'pp-list');
  const options = [{ id: '', name: 'No proxy', meta: 'Direct, no proxy' }].concat(
    pools.map(p => ({
      id: p.id, name: p.name,
      meta: `${maskProxyUrl(p.proxy_url)}${p.bound_count ? ` · ${p.bound_count} accounts` : ''}`
        + `${p.active ? '' : ' · inactive'}`,
      off: !p.active,
    })));
  options.forEach(o => {
    const btn = el('button', 'pp-row' + (String(conn.proxy_pool_id || '') === String(o.id) ? ' is-on' : '')
      + (o.off ? ' is-off' : ''));
    btn.type = 'button';
    btn.dataset.poolId = o.id;
    btn.innerHTML = `<span class="pp-radio"></span>
      <span class="pp-copy"><strong>${esc(o.name)}</strong><small>${esc(o.meta)}</small></span>`;
    btn.onclick = async () => {
      btn.disabled = true;
      try {
        await api(`/providers/connection/${encodeURIComponent(conn.id)}/proxy`, {
          method: 'POST', body: { pool_id: o.id || null }, timeoutMs: 25000,
        });
        closeModal();
        await loadProxyPools(true);
        await refreshConns();
        toast(o.id ? `Proxy: ${o.name}` : 'Proxy unbound', 'ok');
      } catch (err) {
        btn.disabled = false;
        toast(`${err.code || ''} ${err.message}`.trim() || 'Failed to save proxy', 'err');
      }
    };
    list.appendChild(btn);
  });
  body.appendChild(list);

  const manage = el('button', 'pv-action');
  manage.type = 'button';
  manage.textContent = 'Manage Proxy Pools';
  manage.onclick = () => { closeModal(); proxyPoolManager(); };
  body.appendChild(manage);

  modal({
    title: 'Proxy',
    subtitle: who,
    body,
    actions: [{ label: 'Close', kind: 'ghost', onClick: closeModal }],
    footerActions: true,
  });
}

/* Create / edit / test / delete proxy pools. Every mutation hits the router and
   then re-reads the list, so what is shown is what the broker holds. */
async function proxyPoolManager() {
  const render = async () => {
    const pools = await loadProxyPools(true);
    const body = el('div', 'proxy-manager');
    body.appendChild(el('small', 'field-desc',
      'Pools live in the router, not Zeline. Proxy credentials are never shown in full.'));

    if (!pools.length) {
      body.appendChild(el('div', 'pv-empty', 'No proxy pools yet.'));
    }
    pools.forEach(p => {
      const row = el('div', 'pm-row');
      row.innerHTML = `
        <div class="pm-copy">
          <strong>${esc(p.name)}</strong>
          <code>${esc(maskProxyUrl(p.proxy_url))}</code>
          <div class="pm-meta">
            <span class="pm-badge ${p.active ? 'on' : 'off'}">${p.active ? 'active' : 'inactive'}</span>
            <span class="pm-badge">${esc(p.type)}</span>
            ${p.strict ? '<span class="pm-badge">strict</span>' : ''}
            ${p.bound_count ? `<span class="pm-badge">${p.bound_count} accounts</span>` : ''}
            ${p.status && p.status !== 'unknown' ? `<span class="pm-badge">${esc(p.status)}</span>` : ''}
          </div>
        </div>
        <div class="pm-acts">
          <button class="pv-icon-btn" data-pm-test="${esc(p.id)}" title="Test the proxy connection">${ZI('ping')}</button>
          <button class="pv-icon-btn" data-pm-toggle="${esc(p.id)}" data-active="${p.active ? 1 : 0}"
                  title="${p.active ? 'Disable' : 'Enable'}">${ZI(p.active ? 'check' : 'close')}</button>
          <button class="pv-icon-btn" data-pm-edit="${esc(p.id)}" title="Edit">${ZI('pencil')}</button>
          <button class="pv-icon-btn danger" data-pm-del="${esc(p.id)}" title="Delete">${ZI('trash')}</button>
        </div>`;
      body.appendChild(row);
    });

    const add = el('button', 'pv-action primary');
    add.type = 'button';
    add.textContent = '+ Add Proxy Pool';
    add.onclick = () => poolForm(null, render);
    body.appendChild(add);

    modal({
      title: 'Manage Proxy Pools',
      body,
      actions: [{ label: 'Close', kind: 'ghost', onClick: closeModal }],
      footerActions: true,
    });

    body.querySelectorAll('[data-pm-test]').forEach(btn => btn.addEventListener('click', async () => {
      btn.disabled = true;
      try {
        const d = await api('/providers/proxy-pools', {
          method: 'POST', body: { action: 'test', id: btn.dataset.pmTest }, timeoutMs: 45000,
        });
        toast(d.ok ? `Proxy OK${Number.isFinite(d.latency_ms) ? ' · ' + d.latency_ms + 'ms' : ''}`
                   : `Proxy failed: ${d.error || 'not reachable'}`,
              d.ok ? 'ok' : 'err');
      } catch (err) {
        toast(`${err.code || ''} ${err.message}`.trim(), 'err');
      } finally {
        if (btn.isConnected) btn.disabled = false;
      }
    }));

    body.querySelectorAll('[data-pm-toggle]').forEach(btn => btn.addEventListener('click', async () => {
      btn.disabled = true;
      try {
        await api('/providers/proxy-pools', {
          method: 'POST',
          body: { action: 'update', id: btn.dataset.pmToggle, active: btn.dataset.active !== '1' },
        });
        await render();
      } catch (err) {
        btn.disabled = false;
        toast(`${err.code || ''} ${err.message}`.trim(), 'err');
      }
    }));

    body.querySelectorAll('[data-pm-edit]').forEach(btn => btn.addEventListener('click', () => {
      poolForm(pools.find(p => String(p.id) === btn.dataset.pmEdit) || null, render);
    }));

    body.querySelectorAll('[data-pm-del]').forEach(btn => btn.addEventListener('click', () => {
      const pool = pools.find(p => String(p.id) === btn.dataset.pmDel) || {};
      modal({
        title: 'Delete proxy pool',
        subtitle: 'This action is permanent.',
        body: `<p>Delete <strong>${esc(pool.name || 'this pool')}</strong>?`
          + (pool.bound_count ? ` <strong>${pool.bound_count} accounts</strong> still use it and will fall back to no proxy.` : '')
          + '</p>',
        actions: [
          { label: 'Cancel', kind: 'ghost', onClick: closeModal },
          { label: 'Delete', kind: 'danger', onClick: async () => {
              closeModal();
              try {
                await api('/providers/proxy-pools', {
                  method: 'POST', body: { action: 'delete', id: pool.id }, timeoutMs: 25000,
                });
                await render();
                toast('Proxy pool deleted', 'ok');
              } catch (err) {
                toast(`${err.code || ''} ${err.message}`.trim(), 'err');
              }
            } },
        ],
        footerActions: true,
      });
    }));
  };
  await render();
}

/* Add or edit one pool. A brand-new URL can be probed BEFORE it is saved, so a
   typo is caught while the form is still open instead of silently breaking
   routing later. */
function poolForm(pool, onDone) {
  const editing = Boolean(pool && pool.id);
  const body = el('div', 'proxy-form');
  body.appendChild(field('Name', 'pmName', {
    value: editing ? pool.name : '', placeholder: 'e.g. Jakarta proxy',
    desc: 'A label for this pool.',
  }));
  body.appendChild(field('Proxy URL', 'pmUrl', {
    value: editing ? pool.proxy_url : '', placeholder: 'http://user:pass@host:8080',
    desc: 'Include the scheme. Credentials may be embedded.',
  }));
  body.appendChild(field('No proxy (optional)', 'pmNoProxy', {
    value: editing ? pool.no_proxy : '', placeholder: 'localhost,127.0.0.1',
    desc: 'Hosts that bypass the proxy, comma-separated.',
  }));

  const typeWrap = field('Type', 'pmType', {
    tag: 'select', value: editing ? pool.type : 'http',
    options: [{ value: 'http', label: 'HTTP' }, { value: 'vercel', label: 'Vercel' },
              { value: 'cloudflare', label: 'Cloudflare' }, { value: 'deno', label: 'Deno' }],
  });
  body.appendChild(typeWrap);

  const activeWrap = el('label', 'pm-check');
  const activeCb = el('input'); activeCb.type = 'checkbox';
  activeCb.checked = editing ? pool.active : true;
  activeWrap.appendChild(activeCb);
  activeWrap.appendChild(el('span', '', 'Enable this pool'));
  body.appendChild(activeWrap);

  const strictWrap = el('label', 'pm-check');
  const strictCb = el('input'); strictCb.type = 'checkbox';
  strictCb.checked = editing ? pool.strict : false;
  strictWrap.appendChild(strictCb);
  strictWrap.appendChild(el('span', '', 'Strict proxy (fail when the proxy is down)'));
  body.appendChild(strictWrap);

  const testRow = el('div', 'pm-testrow');
  const testBtn = el('button', 'pv-action');
  testBtn.type = 'button';
  testBtn.textContent = 'Test URL';
  const testOut = el('small', 'field-desc', '');
  testRow.appendChild(testBtn); testRow.appendChild(testOut);
  body.appendChild(testRow);

  testBtn.onclick = async () => {
    const url = body.querySelector('#pmUrl').value.trim();
    if (!url) return toast('Proxy URL is required', 'warn');
    testBtn.disabled = true; testOut.textContent = 'Testing…';
    try {
      const d = await api('/providers/proxy-pools', {
        method: 'POST', body: { action: 'test-url', proxy_url: url }, timeoutMs: 45000,
      });
      testOut.textContent = d.ok
        ? `Connected${Number.isFinite(d.latency_ms) ? ` · ${d.latency_ms}ms` : ''}`
        : `Failed: ${d.error || 'not reachable'}`;
      testOut.className = 'field-desc ' + (d.ok ? 'is-ok' : 'is-err');
    } catch (err) {
      testOut.textContent = `${err.code || ''} ${err.message}`.trim();
      testOut.className = 'field-desc is-err';
    } finally {
      testBtn.disabled = false;
    }
  };

  const save = el('button', 'pv-action primary');
  save.type = 'button';
  save.textContent = editing ? 'Save' : 'Add';
  save.onclick = async () => {
    const payload = {
      name: body.querySelector('#pmName').value.trim(),
      proxy_url: body.querySelector('#pmUrl').value.trim(),
      no_proxy: body.querySelector('#pmNoProxy').value.trim(),
      type: body.querySelector('#pmType').value,
      active: activeCb.checked,
      strict: strictCb.checked,
    };
    if (!payload.name) return toast('Pool name is required', 'warn');
    if (!payload.proxy_url) return toast('Proxy URL is required', 'warn');
    save.disabled = true;
    try {
      await api('/providers/proxy-pools', {
        method: 'POST',
        body: editing ? { action: 'update', id: pool.id, ...payload }
                      : { action: 'create', ...payload },
        timeoutMs: 25000,
      });
      toast(editing ? 'Proxy pool saved' : 'Proxy pool added', 'ok');
      await onDone();
    } catch (err) {
      save.disabled = false;
      toast(`${err.code || ''} ${err.message}`.trim(), 'err');
    }
  };

  const back = el('button', 'pv-action');
  back.type = 'button';
  back.textContent = 'Cancel';
  back.onclick = () => onDone();

  const acts = el('div', 'pv-actions');
  acts.appendChild(back); acts.appendChild(save);
  body.appendChild(acts);

  modal({
    title: editing ? 'Edit Proxy Pool' : 'Add Proxy Pool',
    subtitle: 'Pools are stored in the router.',
    body,
    actions: [{ label: 'Close', kind: 'ghost', onClick: closeModal }],
    footerActions: true,
  });
}

/* ─────────────── OAuth connect (driven through the local router) ─────────────── */
/* Zeline never holds OAuth credentials. Every flow is run by the local router,
   which already owns the provider connections: Zeline asks it for an authorize
   URL or a device code, the user approves in a browser, and the router records
   the connection. Zeline only reads back display fields afterwards. */
let oauthFlowState = null;
// Broker connections, keyed by provider id — refreshed whenever the router is
// asked, so the page can say "3 connected" without a second request per card.
let routerConnections = { available: null, base_url: '', byProvider: {}, total: 0 };

/* The broker's OWN display name for each provider, keyed by the routing prefix
   its models carry. The catalog labels a custom endpoint with the dialect it
   speaks ("OpenAI", "Anthropic"), but the user named it something else when
   they added it ("Vantis", "JustWoker", "b.ai") — and THAT is what must show on
   the card. /v1/models reports the real name per model as `owned_by`, so the
   prefix → owner map is read straight from the runtime instead of guessed.
   Shape: { 'JustWoker': 'JustWoker', 'ag': 'Antigravity', ... }          */
let routerModelOwners = {};
/* Prefixes whose `owned_by` is a short routing code rather than a display name,
   mapped to the name a user would recognise. Everything not listed here is used
   verbatim (Vantis, JustWoker, b.ai — the user's own labels). */
const PV_PREFIX_DISPLAY = {
  ag: 'Antigravity', cbai: 'CodeBuddy', cbcn: 'CodeBuddy', cx: 'OpenAI Codex',
  gc: 'Gemini CLI', gb: 'xAI', kr: 'Kimi', kc: 'Kilo Code', cl: 'Cline',
  if: 'iFlow', gh: 'GitHub', gl: 'GitLab', qd: 'Qoder', uni: 'Universal',
};
function pvPrefixDisplay(prefix, owner) {
  /* Prefer the runtime's own owner name unless it is a bare routing code that
     carries no meaning on a card ("ag" → "Antigravity"). */
  const code = String(prefix || '').toLowerCase();
  const known = PV_PREFIX_DISPLAY[code];
  const own = String(owner || '');
  /* A short all-lowercase code with no vowel-spacing (ag, cbai) reads as a
     machine token; a real name (Vantis, JustWoker) has a capital or a dot. */
  if (known && (!own || /^[a-z0-9]{1,6}$/.test(own))) return known;
  return own || known || prefix || '';
}
async function loadModelOwners() {
  try {
    const d = await api('/models', { timeoutMs: 15000 });
    const list = Array.isArray(d) ? d : (d && d.data) || [];
    const map = {};
    list.forEach(m => {
      const id = String(m?.id || '');
      const prefix = id.includes('/') ? id.split('/')[0] : '';
      const owner = String(m?.owned_by || m?.owned_by_name || '');
      if (prefix && !map[prefix]) map[prefix] = pvPrefixDisplay(prefix, owner);
    });
    routerModelOwners = map;
  } catch (_) {
    routerModelOwners = routerModelOwners || {};
  }
  return routerModelOwners;
}

function oauthStopPolling() {
  if (oauthFlowState?.timer) { clearInterval(oauthFlowState.timer); oauthFlowState.timer = null; }
}

function routerProviderKeys(providerId) {
  /* The local gateway card is the UI home for Codex connections. The broker
     calls that provider `codex` (and sometimes `cx`), while the center catalog
     keys the same gateway as `9router`; merge those aliases so this detail
     screen shows one OpenAI Codex card regardless of which key the row came
     back under. (These are internal ids — the UI never prints them.) */
  if (providerId === '9router') return ['9router', 'codex', 'cx'];
  if (providerId === 'codex' || providerId === 'cx') return ['codex', 'cx', '9router'];
  return [providerId];
}

function routerProviderRows(providerId) {
  const seen = new Set();
  return routerProviderKeys(providerId).flatMap(key => routerConnections.byProvider[key] || [])
    .filter(row => row && !seen.has(row.id) && (seen.add(row.id), true));
}

function routerConnectionCount(providerId) {
  return routerProviderRows(providerId).length;
}

async function loadRouterConnections() {
  try {
    const d = await apiWhenAuthed('/providers/router');
    const byProvider = {};
    (d.connections || []).forEach(c => {
      if (!c.provider) return;
      (byProvider[c.provider] = byProvider[c.provider] || []).push(c);
    });
    routerConnections = {
      available: Boolean(d.available),
      base_url: d.base_url || '',
      byProvider, total: d.count || (d.connections || []).length,
    };
  } catch (e) {
    routerConnections = { available: false, base_url: '', byProvider: {}, total: 0 };
  }
  return routerConnections;
}

/* Build the "open the provider's page" affordance once and reuse it. The link
   is a real anchor so long-press / copy-link work on a phone, where window.open
   is often blocked. */
function oauthLinkButton(url, label) {
  const a = el('a', 'pv-oauth-open', esc(label || 'Buka halaman otorisasi'));
  a.href = url;
  a.target = '_blank';
  a.rel = 'noopener noreferrer';
  return a;
}

function oauthCodeChip(code) {
  const chip = el('div', 'pv-oauth-code');
  chip.innerHTML = `<span class="pv-oauth-code-label">Kode</span>
    <strong class="pv-oauth-code-value">${esc(code || '—')}</strong>`;
  const copy = el('button', 'pv-mini ghost', 'Copy');
  copy.type = 'button';
  copy.onclick = async () => {
    try { await navigator.clipboard.writeText(code || ''); toast('Kode disalin', 'ok'); }
    catch (_) { toast('Copy failed — copy manually', 'warn'); }
  };
  chip.appendChild(copy);
  return chip;
}

async function openOAuthConnect(providerId, providerName) {
  oauthStopPolling();
  oauthFlowState = { provider: providerId, name: providerName, timer: null, done: false };

  const body = el('div', 'pv-oauth');
  const note = el('p', 'pv-oauth-note', 'Menghubungi router lokal…');
  body.appendChild(note);

  modal({
    title: 'Connect ' + providerName,
    subtitle: 'Otorisasi lewat router lokal. Kredensial tidak pernah melewati Zeline.',
    body,
    actions: [{ label: 'Close', kind: 'ghost', onClick: () => { oauthStopPolling(); closeModal(); } }],
    footerActions: true,
  });

  let auth;
  try {
    auth = await apiWhenAuthed('/providers/oauth/authorize', {
      method: 'POST', body: { provider: providerId }, timeoutMs: 20000,
    });
  } catch (e) {
    note.className = 'pv-oauth-note is-bad';
    note.textContent = 'Tidak bisa memulai: ' + (e.message || e.code || 'error');
    return;
  }

  oauthFlowState.flowType = auth.flow_type;
  oauthFlowState.state = auth.state;
  oauthFlowState.codeVerifier = auth.code_verifier;
  oauthFlowState.redirectUri = auth.redirect_uri;

  if (auth.flow_type === 'device_code') {
    await oauthStartDeviceCode(providerId, body, note);
  } else {
    oauthShowRedirect(body, note, auth);
  }
}

/* Device-code path: the user gets a short code and a URL, then the page polls
   until the provider accepts it. This is the flow that actually works on a
   phone, where no redirect can land on the app. */
async function oauthStartDeviceCode(providerId, body, note) {
  let dc;
  try {
    dc = await apiWhenAuthed('/providers/oauth/device-code', {
      method: 'POST', body: { provider: providerId }, timeoutMs: 20000,
    });
  } catch (e) {
    note.className = 'pv-oauth-note is-bad';
    note.textContent = 'Provider ini tidak mendukung device code: ' + (e.message || e.code || '');
    return;
  }

  oauthFlowState.deviceCode = dc.device_code;
  oauthFlowState.codeVerifier = dc.code_verifier || oauthFlowState.codeVerifier;
  oauthFlowState.extra = dc.extra || {};

  note.className = 'pv-oauth-note';
  // Some providers (e.g. link-based device flows) carry no user_code at all —
  // the verification URL itself is the whole handshake. Only show the chip
  // when there is actually a code to read and copy.
  if (dc.user_code) {
    note.textContent = 'Buka halaman otorisasi, lalu masukkan kode di bawah.';
    body.appendChild(oauthCodeChip(dc.user_code));
  } else {
    note.textContent = 'Buka halaman otorisasi dan setujui. Halaman ini akan terhubung sendiri.';
  }
  body.appendChild(oauthLinkButton(dc.verification_uri_complete || dc.verification_uri,
                                   'Buka halaman otorisasi'));

  const status = el('p', 'pv-oauth-status', 'Menunggu otorisasi…');
  body.appendChild(status);

  const interval = Math.max(3, Number(dc.interval) || 5) * 1000;
  const tick = async () => {
    if (!oauthFlowState || oauthFlowState.done) return;
    let r;
    try {
      r = await apiWhenAuthed('/providers/oauth/poll', {
        method: 'POST', timeoutMs: 20000,
        body: { provider: providerId, device_code: oauthFlowState.deviceCode,
                code_verifier: oauthFlowState.codeVerifier, extra: oauthFlowState.extra },
      });
    } catch (e) {
      status.className = 'pv-oauth-status is-bad';
      status.textContent = 'Poll failed: ' + (e.message || e.code || '');
      return;
    }
    if (r.success && r.connection) {
      oauthFlowState.done = true;
      oauthStopPolling();
      status.className = 'pv-oauth-status is-ok';
      status.textContent = 'Terhubung: ' + (r.connection.email || r.connection.name || providerId);
      toast(`${oauthFlowState.name} terhubung`, 'ok');
      await loadRouterConnections();
      await loadProviders({ silent: true });
      setTimeout(() => closeModal(), 1200);
      return;
    }
    /* `pending: true` with error "authorization_pending" is the NORMAL state
       while the user is still approving — it is not a rejection. Only a real
       error code (access_denied, expired_token, …) ends the flow. */
    if (r.pending || !r.error || r.error === 'authorization_pending') return;
    oauthFlowState.done = true;
    oauthStopPolling();
    status.className = 'pv-oauth-status is-bad';
    status.textContent = 'Ditolak: ' + (r.error_description || r.error);
  };
  oauthFlowState.timer = setInterval(tick, interval);
  tick();
}

/* Redirect path: the user approves in a browser. The browser is sent back to
   Zeline's OWN callback (/oauth/callback), which exchanges the code server-side
   and records the connection — so this tab only has to poll for the outcome.
   That is the fix for "approve selesai tapi nggak konek": the exchange no longer
   depends on another app's dashboard being open. */
function oauthShowRedirect(body, note, auth) {
  note.className = 'pv-oauth-note';
  note.textContent = 'Buka halaman otorisasi, setujui, lalu kembali ke sini.';

  if (auth.auth_url) body.appendChild(oauthLinkButton(auth.auth_url, 'Buka halaman otorisasi'));

  const status = el('p', 'pv-oauth-status', 'Menunggu kamu menyelesaikan otorisasi di browser…');
  body.appendChild(status);

  const finish = async (connection) => {
    oauthFlowState.done = true;
    oauthStopPolling();
    status.className = 'pv-oauth-status is-ok';
    status.textContent = 'Terhubung: ' + ((connection && (connection.email || connection.name)) || oauthFlowState.provider);
    toast(`${oauthFlowState.name} terhubung`, 'ok');
    await loadRouterConnections();
    await loadProviders({ silent: true });
    setTimeout(() => closeModal(), 1400);
  };

  // Poll the server for the outcome of the browser round-trip.
  const state = auth.state;
  if (state) {
    const startedAt = Date.now();
    const tick = async () => {
      if (!oauthFlowState || oauthFlowState.done) return;
      if (Date.now() - startedAt > 10 * 60 * 1000) {
        oauthStopPolling();
        status.className = 'pv-oauth-status is-bad';
        status.textContent = 'Timed out. Close and try again.';
        return;
      }
      let r;
      try {
        r = await apiWhenAuthed('/providers/oauth/status', {
          method: 'POST', body: { state }, timeoutMs: 15000,
        });
      } catch (_) { return; }  // transient; try again next tick
      if (r.done && r.ok) return finish(r.connection);
      if (r.done && !r.ok) {
        oauthFlowState.done = true;
        oauthStopPolling();
        status.className = 'pv-oauth-status is-bad';
        status.textContent = 'Failed: ' + (r.error || 'rejected by provider');
      }
    };
    oauthFlowState.timer = setInterval(tick, 3000);
  }

  // Manual fallback: if the browser could not reach the callback (rare on a
  // phone), the user can paste the code from the address bar and we exchange it
  // here with the verifier the server already stored.
  const form = el('form', 'pv-oauth-manual');
  form.innerHTML = `<label>Kalau browser tidak kembali otomatis, tempel URL/kode di sini</label>
    <input type="text" placeholder="code atau URL callback…" autocomplete="off" spellcheck="false">`;
  const submit = el('button', 'pv-mini', 'Tukar');
  submit.type = 'submit';
  form.appendChild(submit);
  form.onsubmit = async (e) => {
    e.preventDefault();
    let code = form.querySelector('input').value.trim();
    if (!code) return;
    // Accept a full callback URL as well as a bare code.
    const m = code.match(/[?&]code=([^&]+)/);
    if (m) code = decodeURIComponent(m[1]);
    submit.disabled = true;
    try {
      const r = await apiWhenAuthed('/providers/oauth/exchange', {
        method: 'POST', timeoutMs: 25000,
        body: { provider: oauthFlowState.provider, code,
                redirect_uri: auth.redirect_uri, code_verifier: auth.code_verifier,
                state: auth.state },
      });
      if (r.success && r.connection) {
        await finish(r.connection);
      } else {
        status.className = 'pv-oauth-status is-bad';
        status.textContent = 'Kode ditolak: ' + (r.error || 'tidak diketahui');
      }
    } catch (err) {
      status.className = 'pv-oauth-status is-bad';
      status.textContent = 'Exchange failed: ' + (err.message || err.code || '');
    } finally {
      if (submit.isConnected) submit.disabled = false;
    }
  };
  body.appendChild(form);
}

function pvSection(groupId, providers) {
  const meta = PV_GROUP_META[groupId] || { label: groupId };
  const section = el('section', 'pv-section');

  /* Custom gets ONE Add card. Tapping it reveals the two dialects, so the
     section stays calm until you actually mean to add something — two
     permanent cards would dominate a list that is usually empty.

     The "+" is an SVG cross rather than a text glyph: a text "+" sits on the
     font baseline and reads visibly low inside a centred box. */
  const plusSvg = `<span class="pv-add-plus" aria-hidden="true">
           <svg viewBox="0 0 24 24" width="19" height="19" fill="none"
                stroke="currentColor" stroke-width="2.1" stroke-linecap="round">
             <path d="M12 5v14M5 12h14"/>
           </svg>
         </span>`;
  const dialectIcon = (d) => `<span class="pv-add-plus" aria-hidden="true">
           <svg viewBox="0 0 24 24" width="19" height="19" fill="none"
                stroke="currentColor" stroke-width="2.1" stroke-linecap="round"
                stroke-linejoin="round">
             ${d === 'anthropic'
               ? '<path d="M4 18l5.5-12h2L17 18M6.5 14h8"/>'
               : '<circle cx="12" cy="12" r="8"/><path d="M12 8v8M8 12h8"/>'}
           </svg>
         </span>`;
  const headerAction = groupId === 'openai-compatible'
    ? `<button class="pv-add-card pv-add-main" data-add-open type="button">
         ${plusSvg}
         <span class="pv-add-copy">
           <strong>Add Provider</strong>
           <small>Custom endpoint</small>
         </span>
         <span class="pv-add-chev" aria-hidden="true">
           <svg viewBox="0 0 24 24" width="16" height="16" fill="none"
                stroke="currentColor" stroke-width="2.2" stroke-linecap="round"
                stroke-linejoin="round"><path d="M9 6l6 6-6 6"/></svg>
         </span>
       </button>`
    /* No Test All button: the section header holds only the title. Testing is
       done per provider from its detail screen. */
    : '';

  section.innerHTML = `
    <div class="pv-section-head">
      <div class="pv-section-title">
        <h3>${esc(meta.label)}</h3>
        ${meta.sub ? `<small class="pv-section-sub">${esc(meta.sub)}</small>` : ''}
      </div>
      ${headerAction}
    </div>
    <div class="pv-list"></div>`;

  const list = section.querySelector('.pv-list');
  providers.forEach(p => list.appendChild(pvProviderCard(p)));

  /* Add Provider opens a NEW screen — the two dialects live inside it as tabs,
     so switching between them swaps only the form. Expanding in place would
     bury the choice under the section it belongs to. */
  const addMain = section.querySelector('[data-add-open]');
  if (addMain) addMain.onclick = () => providerForm();

  // Add opens the form with the protocol left to the preset/auto-detect path
  // instead of locking it up front.
  section.querySelectorAll('[data-add-protocol]').forEach(btn => {
    btn.onclick = () => providerForm('', btn.dataset.addProtocol || '');
  });

  return section;
}

// The boot sequence renders every page before the auth helper has necessarily
// minted a session, and api() reads S.token at call time. Rather than depend on
// that ordering, wait for a token and retry once — otherwise the page paints
// "Memuat provider…" forever because the first request came back UNAUTHORIZED.
async function apiWhenAuthed(path, options) {
  if (!S.token) {
    for (let attempt = 0; attempt < 40 && !S.token; attempt += 1) {
      await new Promise(resolve => setTimeout(resolve, 250));
    }
  }
  try {
    return await api(path, options);
  } catch (error) {
    if (error?.code === 'UNAUTHORIZED' && typeof login === 'function') {
      await login();
      return api(path, options);
    }
    throw error;
  }
}

async function loadProviders({ silent = false } = {}) {
  const g = $('providerGrid');
  if (providerState.loading) return providerState.data;
  providerState.loading = true;
  if (!silent && g) g.innerHTML = '<div class="pv-skeleton"></div><div class="pv-skeleton"></div>';
  // Fetch the preset catalog alongside the saved connections so the add form
  // opens with its dropdown already populated instead of flashing an empty one.
  // The router's connection list rides along: it is what makes an OAuth card
  // read "3 connected" instead of "No connections", since those connections
  // live in the broker, not in Zeline's own config.
  const [center, presets] = await Promise.allSettled([
    apiWhenAuthed('/providers/center'),
    loadProviderPresets(),
    loadRouterConnections(),
    loadModelOwners(),
  ]);
  providerState = center.status === 'fulfilled'
    ? { data: center.value, loading: false, error: null }
    : { data: providerState.data, loading: false, error: center.reason };
  renderProviderList();
  return providerState.data;
}

// Entry point used by the page router: fetch from the runtime, then paint.
// renderProviderList() below is the pure render half, so a re-render triggered
// by a navigation event never re-issues a request.
function renderProviders() {
  // Idempotent: the app bar wires itself once, but the router may call this on
  // every visit, and the nodes only exist after the page shell is in the DOM.
  wireProviderAppbar();
  if (providerState.data) { renderProviderList(); return providerState.data; }
  return loadProviders();
}

function renderProviderList() {
  const g = $('providerGrid');
  if (!g) return;
  const { data, error } = providerState;
  if (!data) {
    g.innerHTML = `<div class="pv-empty">${error
      ? 'Cannot read providers from the runtime: ' + esc(error.message || error.code || 'error')
      : 'Memuat provider…'}</div>`;
    return;
  }
  const all = data.providers || [];
  if (!all.length) {
    g.innerHTML = '<div class="pv-empty">The runtime has no providers yet. Add one from the CLI, then reopen this page.</div>';
    return;
  }
  // An open field with no query is a blank slate — results appear once the user
  // types, so nothing competes with the field (same rule as the workspace sheet).
  if (providerSearchOpen && !providerQuery) {
    g.innerHTML = '';
    return;
  }
  // Search matches what a card actually shows: name, endpoint, and model ids.
  const providers = providerQuery
    ? all.filter(p => `${p.name || ''}\n${p.endpoint_label || ''}\n${p.base_url || ''}\n${(p.models || []).join(' ')}`
        .toLocaleLowerCase().includes(providerQuery))
    : all;
  g.innerHTML = '';
  if (!providers.length) {
    g.innerHTML = `<div class="pv-empty">No provider matches “${esc(providerQuery)}”</div>`;
    return;
  }
  /* Two sections, rendered top to bottom:
       1. openai-compatible — the "Add Provider" card, then every custom
          endpoint the user added there (Vantis, JustWoker), connected or not.
          Custom endpoints live under the form that creates them.
       2. available   — everything else, with the providers that already hold an
          API key / OAuth pinned to the TOP of the section, then the rest A→Z.
     Nothing is hidden: every catalog provider is still listed, the configured
     ones simply float to the head of the list. */
  const isCustomBucket = p =>
    (p.group === 'openai-compatible' || p.group === 'anthropic-compatible')
    /* The local gateway's catalog group is also `openai-compatible`, but it is
       not a user-added custom endpoint — exclude it so it lands in Available
       with the other catalog providers, not under the Add-Provider form. */
    && !pvIsCodexGateway(p);
  const byName = (a, b) =>
    providerDisplayName(a).localeCompare(providerDisplayName(b), undefined, { sensitivity: 'base' });
  const byGroup = {};
  /* Custom endpoints sit with the form that adds them. Order: connected first,
     then A→Z, so a working one is not buried under a half-filled entry. */
  byGroup['openai-compatible'] = providers
    .filter(isCustomBucket)
    .sort((a, b) => (Number(pvIsConnected(b)) - Number(pvIsConnected(a))) || byName(a, b));
  /* Everything non-custom, keyed providers (one we actually hold a credential
     for) first, then the untouched catalog A→Z. */
  byGroup.available = providers
    .filter(p => !isCustomBucket(p))
    .sort((a, b) => (Number(pvIsConnected(b)) - Number(pvIsConnected(a))) || byName(a, b));
  for (const groupId of PV_GROUP_ORDER) {
    const list = byGroup[groupId] || [];
    // The Custom section always renders (its Add buttons create the first
    // connection). Other sections only render when they have cards — and while
    // searching, an empty Custom section would just be noise.
    if (!list.length && (groupId !== 'openai-compatible' || providerQuery)) continue;
    g.appendChild(pvSection(groupId, list));
  }
}

/* Provider app bar — same interaction contract as the workspace destinations:
   Back, a centred title, a search icon that takes over the bar, and a small
   pull nudge on the sheet. Wired once; safe to call again on every page open. */
function wireProviderAppbar() {
  const bar = $('pvAppbar');
  const sheet = $('pvSheet');
  const list = $('providerGrid');
  if (!bar || bar.dataset.pvWired) return;
  bar.dataset.pvWired = '1';

  const action = $('pvSearchAction');
  const wrap = $('pvSearchWrap');
  const input = $('pvSearchInput');

  if (action) {
    action.innerHTML = ZI('search');
    action.onclick = () => {
      const opening = Boolean(wrap?.hidden);
      if (wrap) wrap.hidden = !opening;
      providerSearchOpen = opening;
      bar.classList.toggle('pv-search-open', opening);
      action.innerHTML = ZI(opening ? 'close' : 'search');
      action.setAttribute('aria-label', opening ? 'Cancel search' : 'Search Provider');
      action.setAttribute('aria-expanded', String(opening));
      if (opening) {
        renderProviderList();
        setTimeout(() => input?.focus(), 0);
        return;
      }
      // Cancelling restores the plain list and drops focus so the mobile
      // keyboard closes together with the field.
      input?.blur();
      if (input) input.value = '';
      providerQuery = '';
      renderProviderList();
    };
  }

  input?.addEventListener('input', () => {
    providerQuery = String(input.value || '').trim().toLocaleLowerCase();
    renderProviderList();
  });

  // Reuse the exact nudge used by the workspace sheets so the gesture feels
  // identical across destinations.
  if (typeof wireWorkspacePullNudge === 'function') wireWorkspacePullNudge(list, sheet);
}

/* Adding a connection: pick an endpoint from the preset catalog, paste a key,
   prove it works. The catalog supplies the base URL and wire protocol so nobody
   has to recall an API root; both stay editable for self-hosted setups. */
let providerPresets = null;

async function loadProviderPresets() {
  if (providerPresets) return providerPresets;
  try {
    providerPresets = (await api('/providers/presets')).providers || [];
  } catch (_) {
    providerPresets = [];
  }
  return providerPresets;
}

async function providerForm(presetId = '', protocol = '') {
  const presets = await loadProviderPresets();
  /* Deliberately NOT `.workspace-sheet`. That class carries
     `overflow:hidden!important` (it wraps lists that never scroll themselves and
     instead get a pull gesture). This sheet IS the scroll container, so adopting
     it locked the form at viewport height — scrollHeight was 799px against a
     364px box, and the content below was simply unreachable. The app-bar styling
     this sheet needs comes from `.provider-sheet-modal`, not from this class. */
  const body = el('div', 'provider-form');

  /* One screen, two dialects, switched by the segmented control at the top.
     Only `#pvFields` is rebuilt on switch, so the values already typed survive
     the change. */
  let dialect = protocol === 'anthropic' ? 'anthropic' : 'openai';
  // Create is gated on a passing Check. Any edit invalidates it again.
  let checkPassed = false;

  const options = presets.map(p => ({ value: p.id, label: p.name }));
  const showPresetPicker = Boolean(presetId) && options.length > 0;

  /* The endpoint choice gets its own titled group, so it reads as a step
     ("Select Endpoint") rather than two loose buttons above the fields. */
  /* `Select Endpoint` is an ordinary titled group: title, one description, then
     the cards — the same three-part shape every other field on this form uses.
     The description is STATIC. It must not swap or slide when a card is picked
     (that made a caption appear directly above the clicked card). Both endpoints
     are named in the one line instead. */
  const segGroup = el('div', 'pv-seg-group');
  /* One description slot under "Select Endpoint", in the same position every
     other field's description occupies. Its TEXT follows the selected endpoint,
     but it is never re-created or moved — only the string is swapped, so the
     line cannot slide around when a card is clicked. */
  const segHead = el('div', 'pv-seg-head');
  segHead.innerHTML = `
    <h4>Select Endpoint</h4>
    <small class="field-desc" id="pvSegDesc"></small>`;
  segGroup.appendChild(segHead);
  const segDesc = segHead.querySelector('#pvSegDesc');
  const SEG_DESC = {
    anthropic: 'Use /v1/messages',
    openai: 'Use /v1/chat/completions or /v1/responses'
  };

  const seg = el('div', 'pv-seg');
  seg.setAttribute('role', 'tablist');
  seg.innerHTML = `
    <button class="pv-seg-btn" data-dialect="anthropic" type="button" role="tab">
      <strong>Anthropic Compatible</strong>
    </button>
    <button class="pv-seg-btn" data-dialect="openai" type="button" role="tab">
      <strong>OpenAI Compatible</strong>
    </button>`;
  segGroup.appendChild(seg);
  if (!showPresetPicker) body.appendChild(segGroup);

  if (showPresetPicker) {
    body.appendChild(field('Provider', 'pvPreset', {
      tag: 'select', value: presetId, disabled: true,
      desc: 'This provider\'s endpoint is filled in automatically.', options
    }));
  }

  const fields = el('div', 'pv-fields');
  fields.id = 'pvFields';
  body.appendChild(fields);

  const note = el('small', 'provider-form-note', '');
  body.appendChild(note);

  /* Action cards live INSIDE the form, right below Model ID — no footer bar and
     no header action, so the buttons sit with the fields they submit. */
  /* Two buttons on one row, equal width. Cancel is gone — the app bar's Back
     control already dismisses, and a third button only crowded the row. */
  const acts = el('div', 'pv-actions');
  acts.innerHTML = `
    <button class="pv-act pv-act-check" data-act="check" type="button">Check</button>
    <button class="pv-act pv-act-create is-locked" data-act="create" type="button" disabled>Create</button>`;
  body.appendChild(acts);

  const protoField = el('input');
  protoField.type = 'hidden';
  protoField.id = 'pvProtocol';
  body.appendChild(protoField);

  const btnCheck  = acts.querySelector('[data-act="check"]');
  const btnCreate = acts.querySelector('[data-act="create"]');

  const setCreateEnabled = (on) => {
    checkPassed = on;
    btnCreate.disabled = !on;
    btnCreate.classList.toggle('is-locked', !on);
    btnCreate.title = on ? 'Save this provider'
                         : 'Run Check first — the endpoint must be valid';
  };

  /* Any edit to a field the check depends on invalidates the previous result,
     so Create can never save a config that was never verified. */
  const invalidate = () => {
    if (!checkPassed) return;
    setCreateEnabled(false);
    note.className = 'provider-form-note';
    note.textContent = 'Fields changed — run Check again before creating.';
  };

  const carry = () => ({
    name: fields.querySelector('#pvName')?.value ?? '',
    key: fields.querySelector('#pvKey')?.value ?? '',
    model: fields.querySelector('#pvModel')?.value ?? ''
  });

  /* The screen keeps ONE title ("Custom Endpoint"); which endpoint is active is
     shown by the option cards below, so nothing here rewrites the bar. */
  const setHead = () => {};

  const renderFields = (keep, animate = false) => {
    const isAnthropic = dialect === 'anthropic';
    const vendor = isAnthropic ? 'Anthropic' : 'OpenAI';
    fields.innerHTML = '';
    protoField.value = isAnthropic ? 'anthropic' : 'openai';
    /* Re-arm the swap animation. Removing the class and forcing a reflow is
       what makes it replay on a second switch — without the reflow the browser
       coalesces remove+add into no change at all. */
    if (animate) {
      fields.classList.remove('is-swapping');
      void fields.offsetWidth;
      fields.classList.add('is-swapping');
    }

    fields.appendChild(field('Provider Name', 'pvName', {
      value: keep?.name || '',
      placeholder: `${vendor} Compatible (Prod)`,
      desc: `A friendly label for this ${vendor}-compatible provider.`
    }));

    // API Type is OpenAI-only: Anthropic has exactly one wire format.
    if (!isAnthropic) {
      const wrap = el('div', 'field');
      wrap.id = 'pvApiTypeWrap';
      wrap.innerHTML = `
        <label for="pvApiType">API Type</label>
        <small class="field-desc">Select an option:</small>
        <select id="pvApiType">
          <option value="chat">Chat Completions</option>
          <option value="responses">Responses</option>
        </select>`;
      fields.appendChild(wrap);
    }

    fields.appendChild(field('Base URL', 'pvURL', {
      placeholder: isAnthropic ? 'https://api.anthropic.com/v1' : 'https://api.openai.com/v1',
      desc: isAnthropic
        ? 'Use the base URL (ending in /v1) The system will append /messages.'
        : 'Enter the API endpoint base URL ending in /v1.'
    }));

    fields.appendChild(field('API Key', 'pvKey', {
      type: 'password', value: keep?.key || '', placeholder: 'sk-…',
      desc: 'Enter your api key to check'
    }));

    fields.appendChild(field('Model ID (optional)', 'pvModel', {
      value: keep?.model || '',
      placeholder: isAnthropic ? 'e.g. claude-fable-5-1' : 'e.g. gpt-6-astra',
      desc: 'If provider lacks /models endpoint, enter a model ID for validation'
    }));

    fields.querySelectorAll('input, select').forEach(node => {
      node.addEventListener('input', invalidate);
      node.addEventListener('change', invalidate);
    });

    seg.querySelectorAll('[data-dialect]').forEach(b => {
      const on = b.dataset.dialect === dialect;
      b.classList.toggle('is-active', on);
      b.setAttribute('aria-selected', on ? 'true' : 'false');
    });
    // Only ever change the string — the element stays put, so there is no shift.
    if (segDesc) segDesc.textContent = SEG_DESC[dialect] || SEG_DESC.openai;
    note.className = 'provider-form-note';
    note.textContent = '';
    setCreateEnabled(false);
    setHead();
  };

  /* Guard against a rapid double-tap: a second switch landing mid-animation
     used to leave fields at partial opacity. `swapping` drops taps for the
     length of the transition, so the sequence can never interleave. */
  let swapping = false;
  seg.querySelectorAll('[data-dialect]').forEach(btn => {
    btn.onclick = () => {
      if (swapping || btn.dataset.dialect === dialect) return;
      swapping = true;
      const keep = carry();
      dialect = btn.dataset.dialect;
      renderFields(keep, true);
      const done = () => { swapping = false; };
      fields.addEventListener('animationend', done, { once: true });
      // Fallback: if the animation is disabled (reduced motion) no event fires.
      setTimeout(done, 320);
    };
  });

  renderFields(null);

  if (showPresetPicker) {
    const preset = presets.find(p => p.id === presetId);
    if (preset) {
      dialect = preset.protocol === 'anthropic' ? 'anthropic' : 'openai';
      renderFields(null);
      fields.querySelector('#pvURL').value = preset.base_url || '';
      fields.querySelector('#pvName').value = preset.name || '';
    }
  }

  const readForm = () => ({
    isAnthropic: dialect === 'anthropic',
    base_url: fields.querySelector('#pvURL').value.trim(),
    api_key: fields.querySelector('#pvKey').value,
    model: fields.querySelector('#pvModel').value.trim(),
    name: fields.querySelector('#pvName').value.trim(),
    apiType: dialect === 'anthropic'
      ? 'messages' : (fields.querySelector('#pvApiType')?.value || 'chat')
  });

  const fail = (msg) => {
    note.textContent = msg;
    note.classList.remove('is-set');
    note.classList.add('is-bad');
    setCreateEnabled(false);
    toast(msg, 'err');
  };

  btnCheck.onclick = async () => {
    const f = readForm();
    if (!f.base_url) return fail('Base URL is required.');
    if (!f.api_key) return fail('API Key is required to run the check.');

    btnCheck.disabled = true;
    const label = btnCheck.textContent;
    btnCheck.textContent = 'Checking…';
    note.className = 'provider-form-note';
    note.textContent = 'Checking…';

    try {
      const d = await api('/providers/preflight', {
        method: 'POST', timeoutMs: 20000,
        body: { base_url: f.base_url, api_key: f.api_key,
                protocol: protoField.value, api_type: f.apiType, model: f.model }
      });
      const models = Array.isArray(d.models) ? d.models : [];
      /* A provider with no /models route reports zero models. The server then
         proves the credential with a real request instead (see `note`), so an
         empty catalog must NOT be read as "the model I typed is missing" —
         that would lock Create on a perfectly good endpoint. Only judge the
         model when the endpoint actually published a list. The server owns the
         match (it tolerates decorated ids like `cx/gpt-5.6-sol`). */
      const hasCatalog = models.length > 0;
      const modelOk = (f.model && hasCatalog) ? d.model_found !== false : null;
      const parts = ['VALID — endpoint responded.'];
      parts.push(hasCatalog ? `${d.model_count || models.length} models available`
                            : (d.note || 'no /models route; verified with a live request'));
      parts.push(`${d.protocol || protoField.value} · ${f.apiType}`);
      parts.push(`${d.latency_ms}ms`);
      if (f.model && hasCatalog) {
        parts.push(modelOk
          ? `model "${f.model}" found`
          : `model "${f.model}" NOT in this endpoint's list`);
      }
      note.textContent = parts.join(' · ');
      const good = !f.model || !hasCatalog || modelOk;
      note.classList.remove('is-set', 'is-bad');
      note.classList.add(good ? 'is-set' : 'is-bad');
      // Only a fully good result unlocks Create.
      setCreateEnabled(good);
      toast(good ? 'Connection valid — you can create it now'
                 : 'Model not found on this endpoint',
            good ? 'ok' : 'warn');
    } catch (e) {
      /* State WHY it failed. A bare "invalid" is useless when the cause could
         be a wrong key, a wrong URL, or a reachable endpoint that simply has
         no /models route. */
      const code = e.code || '';
      const WHY = {
        PROVIDER_UNAUTHORIZED:
          'Endpoint responded but rejected the API Key (401/403). Check the key.',
        PROVIDER_UNAVAILABLE:
          'Endpoint could not be reached. Check the Base URL (typo, host down, or offline).',
        VALIDATION_ERROR: 'Base URL or API Key is incomplete.',
        TIMEOUT: 'Endpoint did not respond in time. Try again.'
      };
      const why = WHY[code] || e.message || 'Endpoint returned an unreadable response.';
      note.textContent = `INVALID — ${why}`;
      note.classList.remove('is-set');
      note.classList.add('is-bad');
      setCreateEnabled(false);
      toast(`Invalid: ${why.slice(0, 90)}`, 'err');
    } finally {
      btnCheck.disabled = false;
      btnCheck.textContent = label;
    }
  };

  btnCreate.onclick = async () => {
    // Belt and braces: the button is disabled, but never trust only that.
    if (!checkPassed) {
      toast('Run Check first — the endpoint must be valid', 'warn');
      return;
    }
    const f = readForm();
    const payload = {
      name: f.name || `${f.isAnthropic ? 'Anthropic' : 'OpenAI'} Compatible`,
      base_url: f.base_url, api_key: f.api_key,
      protocol: protoField.value, api_type: f.apiType,
      model: f.model, active: true
    };
    btnCreate.disabled = true;
    const label = btnCreate.textContent;
    btnCreate.textContent = 'Creating…';
    try {
      await api('/providers', { method: 'POST', body: payload, timeoutMs: 20000 });
      toast(`Provider "${payload.name}" created`, 'ok');
      untag();
      closeModal();
      renderProviderList();
    } catch (e) {
      const why = e.message || e.code || 'unknown error';
      note.textContent = `Could not create: ${why}`;
      note.classList.remove('is-set');
      note.classList.add('is-bad');
      toast(`Create failed: ${why}`.slice(0, 110), 'err');
      btnCreate.disabled = false;
      btnCreate.textContent = label;
    }
  };

  /* Strip the workspace tags on the way out: this shell is shared, and leaving
     them behind would restyle the next modal that reuses it. */
    const shell = document.querySelector('.modal');
  const untag = () => shell?.classList.remove('workspace-modal', 'provider-sheet-modal');


  /* Keyboard dismiss — decided by POINT, not by which node the event targeted.
     `event.target` is unreliable here: a tap between the description and a card
     lands on `.pv-seg-group` (generic padding), and a tap inside a card can
     report a nested `STRONG`. Both look alike to a closest() check, which is
     why tapping the 5px gutter silently switched endpoint.

     Instead, a tap counts as "on a card" only if the touch coordinates fall
     inside that card's own rectangle. Everything else — the gutter above or
     below a card, headings, the sheet background, the modal padding — is a pure
     dismiss: close the keyboard and touch nothing else. */
  const outsideTapGuard = (() => {
    let dismissing = false;
    let lastX = 0, lastY = 0;

    const isEditable = n => n && /^(INPUT|SELECT|TEXTAREA)$/.test(n.tagName);

    // True only when (x, y) is physically inside one of these elements' boxes.
    const hitsBox = (selector, x, y) => {
      for (const el of document.querySelectorAll(selector)) {
        const b = el.getBoundingClientRect();
        if (x >= b.left && x <= b.right && y >= b.top && y <= b.bottom) return true;
      }
      return false;
    };

    const onDown = event => {
      dismissing = false;
      const active = document.activeElement;
      if (!isEditable(active)) return;                  // no keyboard -> do nothing

      const t = event.touches?.[0] || event.changedTouches?.[0] || event;
      const x = t.clientX, y = t.clientY;
      lastX = x; lastY = y;

      const inCard = hitsBox('.pv-seg-btn', x, y);
      const inAct  = hitsBox('.pv-act', x, y);
      /* Whether the tap is "in a field" is decided by the CONTROL's own
         rectangle, never by `closest()`. A label carries `for=`, so letting a
         label-hit count as a field tap is exactly what moved focus into the
         wrong input when the gutter was touched. */
      const inControl = hitsBox('.provider-form input, .provider-form select, .provider-form textarea', x, y);

      // A deliberate tap on a card or a button: dismiss the keyboard AND let it
      // do its job. Everything else is dismiss-only.
      if (inCard || inAct) { active.blur(); return; }
      if (inControl) return;                            // moving between fields

      dismissing = true;
      /* Do NOT preventDefault here. Calling it on touchstart cancels the
         gesture outright, and because this listener is on `document` it killed
         scrolling for the WHOLE sheet whenever a field had focus — the scroll
         stayed stuck until the keyboard was dismissed. The tap is neutralised by
         swallowing the tail events instead. */
      event.stopPropagation();
      event.stopImmediatePropagation?.();
      active.blur();
    };

    const onTail = event => {
      if (!dismissing) return;
      event.preventDefault();
      event.stopPropagation();
      event.stopImmediatePropagation?.();
    };

    document.addEventListener('pointerdown', onDown, { capture: true });
    document.addEventListener('touchstart', onDown, { capture: true, passive: false });
    document.addEventListener('click', onTail, { capture: true });
    document.addEventListener('pointerup', onTail, { capture: true });

    return () => {
      document.removeEventListener('pointerdown', onDown, { capture: true });
      document.removeEventListener('touchstart', onDown, { capture: true });
      document.removeEventListener('click', onTail, { capture: true });
      document.removeEventListener('pointerup', onTail, { capture: true });
    };
  })();


  modal({
    title: 'Custom Endpoint',
    body,
    actions: []
  });
  setHead();

  /* Elastic drag at the top of the sheet, matching the Providers page.
     Only engages when the scroller is already at scrollTop 0 and the gesture is
     clearly downward; everything else — upward scroll, horizontal swipe, a drag
     starting inside a field — is handed straight back to the browser. */
  (() => {
    const scroller = document.querySelector('.modal-body');
    const form = document.querySelector('.provider-form');
    if (!scroller || !form || form.dataset.pullWired) return;
    form.dataset.pullWired = '1';
    const MAX_PX = 12, INTENT_PX = 7, RANGE_PX = 64;
    let g = null, frame = 0, timer = 0;

    const clear = () => {
      clearTimeout(timer); timer = 0;
      form.classList.remove('sheet-pull-releasing');
      form.style.transform = '';
    };
    const paint = () => {
      frame = 0;
      if (!g?.active) return;
      form.style.transform = `translate3d(0,${g.pull.toFixed(2)}px,0)`;
    };
    const queue = () => { if (!frame) frame = requestAnimationFrame(paint); };
    const release = () => {
      const pulled = g?.active && g.pull > 0;
      g = null;
      if (frame) { cancelAnimationFrame(frame); frame = 0; }
      form.classList.remove('sheet-pull-active');
      if (!pulled) { clear(); return; }
      form.classList.add('sheet-pull-releasing');
      form.style.transform = '';
      const done = () => clear();
      form.addEventListener('transitionend', done, { once: true });
      timer = setTimeout(done, 320);
    };

    scroller.addEventListener('touchstart', e => {
      clear();
      /* Only a multi-touch or a genuinely scrollable inner control is handed
         back to the browser. Bailing on ANY input was what made the sheet feel
         stuck: a drag starting on a field produced no pull, and because the
         form usually fits the viewport there was no native scroll either, so
         nothing moved at all. Single-line inputs and selects do not pan
         vertically, so the sheet may own that gesture. */
      const inner = e.target.closest?.('textarea,[contenteditable=""],[contenteditable="true"]');
      if (e.touches.length !== 1 || scroller.scrollTop > 0 || inner) { g = null; return; }
      const t = e.touches[0];
      g = { x: t.clientX, y: t.clientY, pull: 0, active: false, dead: false };
    }, { passive: true });

    scroller.addEventListener('touchmove', e => {
      const st = g; const t = e.touches[0];
      if (!st || !t || st.dead) return;
      const dx = t.clientX - st.x, dy = t.clientY - st.y;
      if (!st.active) {
        if (Math.max(Math.abs(dx), Math.abs(dy)) < INTENT_PX) return;
        if (scroller.scrollTop > 0 || dy <= 0 || Math.abs(dy) <= Math.abs(dx) * 1.15) {
          st.dead = true; return;
        }
        st.active = true;
        form.classList.add('sheet-pull-active');
      }
      st.pull = MAX_PX * (1 - Math.exp(-Math.max(0, dy) / RANGE_PX));
      queue();
    }, { passive: true });

    scroller.addEventListener('touchend', release, { passive: true });
    scroller.addEventListener('touchcancel', release, { passive: true });
  })();

  /* Tag the shell so `.workspace-modal` rules (back glyph 26px, bar tone,
     title metrics) win here exactly as they do on Cronjob. */
  document.querySelector('.modal')?.classList.add('workspace-modal', 'provider-sheet-modal');
  /* Intentionally NO pull-to-stretch gesture on this sheet.
     `wireWorkspacePullNudge` is built for the workspace sheets, whose lists sit
     inside a sheet with `overflow:hidden` and never scroll themselves; there the
     gesture is the only vertical affordance. Here `.modal-body` IS the scroller,
     so attaching the gesture to it both fought the native pan and left the sheet
     feeling stuck at the top — it could not be dragged up or down. Native
     scrolling is the correct behaviour for a long form, so the gesture stays off.
     The grid backdrop is already `position:fixed`, so it needs no pull to stay
     put. */
}



/* ───────────────── mobile agent list actions ───────────────── */
const agentFlags = () => JSON.parse(localStorage.getItem('zeline.agentFlags') || '{"pinned":[]}');
const saveAgentFlags = flags => localStorage.setItem('zeline.agentFlags', JSON.stringify(flags));
let selectedAgents = new Set();
let selectedSessions = new Set();
let selectionMode = false;
let selectionHistoryState = false;
let activeAgentRowGesture = null;
let suppressAgentRowClickUntil = 0;

const selectionCount = () => selectedAgents.size + selectedSessions.size;

function cancelAgentRowGesture(suppressClick = true) {
  if (activeAgentRowGesture) {
    clearTimeout(activeAgentRowGesture.timer);
    activeAgentRowGesture.cancelled = true;
    activeAgentRowGesture = null;
  }
  if (suppressClick) suppressAgentRowClickUntil = performance.now() + 450;
}
window.cancelAgentRowGesture = cancelAgentRowGesture;

function openSelectionMode() {
  if (!selectionHistoryState) {
    history.pushState({ zelineSelection: true }, '');
    selectionHistoryState = true;
  }
}

function enterSelectionMode(agent) {
  selectionMode = true;
  selectedAgents.clear();
  selectedSessions.clear();
  selectedAgents.add(agent.id);
  openSelectionMode();
  renderAgentHome();
}

/* Saved Sessions join the very same selection mode as chats, so the header Pin
   button is the one and only pin feature. */
function enterSessionSelectionMode(session) {
  selectionMode = true;
  selectedAgents.clear();
  selectedSessions.clear();
  selectedSessions.add(session.id);
  openSelectionMode();
  renderAgentHome();
}

function cancelSelectionMode(fromHistory = false) {
  if (!selectionMode) return false;
  selectionMode = false;
  selectedAgents.clear();
  selectedSessions.clear();
  if (!fromHistory && selectionHistoryState) history.back();
  selectionHistoryState = false;
  renderAgentHome();
  return true;
}

function agentPayload(agent, patch = {}) {
  return {
    name: agent.name,
    icon: agent.icon || '◆',
    description: agent.description || '',
    provider_id: agent.provider_id || '',
    model: agent.model || '',
    system_instructions: agent.system_instructions || '',
    enabled_tools: [...ALL_TOOLS],
    enabled_skills: [...ALL_SKILLS],
    memory_enabled: true,
    ...patch
  };
}

async function deleteAgent(agent) {
  try {
    await api('/agents/' + agent.id, { method: 'DELETE', timeoutMs: 12000 });
  } catch (error) {
    const fresh = await api('/agents', { timeoutMs: 6000 });
    if ((fresh.agents || []).some(item => item.id === agent.id)) throw error;
  }
  const fresh = await api('/agents', { timeoutMs: 6000 });
  if ((fresh.agents || []).some(item => item.id === agent.id)) throw new Error('Agent still exists after delete');
  const card = document.querySelector(`.agent-card[data-agent-id="${agent.id}"]`);
  if (card) {
    card.classList.add('agent-card-deleting');
    await new Promise(resolve => setTimeout(resolve, 260));
  }
  S.agents = fresh.agents || [];
  selectedAgents.delete(agent.id);
}

async function deleteAgentsStrict(agents) {
  for (const agent of agents) await deleteAgent(agent);
  await refreshAll();
  renderAgentHome();
}

function confirmDeleteAgents(agents) {
  const targets = [...agents].filter(Boolean);
  if (!targets.length) return;
  const body = el('div', 'delete-confirmation');
  body.innerHTML = `<strong>Delete ${targets.length === 1 ? esc(targets[0].name) : targets.length + ' profiles'}?</strong><p>This cannot be undone. Saved sessions for the selected profile may also be removed.</p>`;
  modal({
    title: 'Confirm delete', body,
    compact: true,
    actions: [
      { label: 'No' },
      { label: 'Yes', pendingLabel: 'Deleting…', kind: 'danger', onClick: async close => {
        await deleteAgentsStrict(targets);
        close();
        if (selectionMode) cancelSelectionMode();
      } }
    ]
  });
  document.querySelector('.modal').classList.add('delete-confirm-modal', 'compact-confirm-modal');
}

/* Pin writes are recency-ordered: promoting always moves ids to the FRONT of the
   shared array so the last thing pinned renders topmost, and re-pinning an
   already-pinned id promotes it again instead of leaving a duplicate. */
function promotePins(ids) {
  const list = [...ids].filter(Boolean);
  if (!list.length) return;
  const flags = agentFlags();
  flags.pinned = [...list, ...flags.pinned.filter(id => !list.includes(id))];
  saveAgentFlags(flags);
}

function removePins(ids) {
  const list = [...ids].filter(Boolean);
  if (!list.length) return;
  const flags = agentFlags();
  flags.pinned = flags.pinned.filter(id => !list.includes(id));
  saveAgentFlags(flags);
}

function togglePin(agent) {
  const pinned = agentFlags().pinned.includes(agent.id);
  pinned ? removePins([agent.id]) : promotePins([agent.id]);
  renderAgentHome();
}

function renderSelectionBar(box) {
  const head = $('agentHomeActions');
  const add = $('createAgentTop');
  if (!head) return;
  head.innerHTML = '';
  const title = $('homeTitle');
  const menu = $('homeHeaderMenu');
  head.hidden = !selectionMode;
  if (add) add.hidden = selectionMode;
  if (!selectionMode) {
    if (title) { title.textContent = 'Zeline'; title.hidden = true; title.classList.remove('selection-cancel', 'selection-count'); title.onclick = null; }
    if (menu) {
      menu.classList.remove('selection-menu-cancel');
      menu.setAttribute('aria-label', 'Open menu');
      menu.innerHTML = '<span class="home-menu-glyph" aria-hidden="true"><i></i><i></i><i></i></span>';
      menu.onclick = event => { event.stopPropagation(); openSidebar(); };
    }
    return;
  }
  const flags = agentFlags();
  const selected = S.agents.filter(a => selectedAgents.has(a.id));
  const selectedSessionItems = S.sessions.filter(s => selectedSessions.has(s.id));
  const selectedIds = [...selected.map(a => a.id), ...selectedSessionItems.map(s => s.id)];
  if (title) { title.textContent = selectionCount() + ' selected'; title.hidden = false; title.classList.add('selection-count'); title.classList.remove('selection-cancel'); title.onclick = null; }
  if (menu) {
    menu.classList.add('selection-menu-cancel');
    menu.setAttribute('aria-label', 'Cancel selection');
    menu.innerHTML = ZI('close');
    menu.onclick = event => { event.stopPropagation(); cancelSelectionMode(); };
  }
  const make = (label, cls, icon, fn) => {
    const b = el('button', 'agent-head-action ' + cls, icon);
    b.title = label; b.onclick = e => { e.stopPropagation(); fn(); };
    head.appendChild(b);
  };
  const pinIcon = ZI('pin');
  const trashIcon = ZI('trash');
  // One Pin button for both chats and Saved Sessions — same store, same action.
  // Selecting a chat implicitly covers its Sessions, so they pin together and the
  // whole group lands at the top in one promotion.
  const impliedSessionIds = selected.flatMap(a => sessionsForAgent(a.id).map(s => s.id));
  const pinTargets = [...new Set([...selectedIds, ...impliedSessionIds])];
  make(flags.pinned.some(id => pinTargets.includes(id)) ? 'Unpin' : 'Pin', 'pin', pinIcon, () => {
    const shouldUnpin = agentFlags().pinned.some(id => pinTargets.includes(id));
    shouldUnpin ? removePins(pinTargets) : promotePins(pinTargets);
    cancelSelectionMode();
  });
  make('Delete', 'delete', trashIcon, () => {
    if (selectedSessionItems.length && !selected.length) return confirmDeleteSessions(selectedSessionItems);
    confirmDeleteAgents(selected);
  });
}

function confirmDeleteSessions(sessions) {
  const targets = [...sessions].filter(Boolean);
  if (!targets.length) return;
  const body = el('div', 'delete-confirmation');
  body.innerHTML = `<strong>Delete ${targets.length === 1 ? esc(targets[0].title || 'this session') : targets.length + ' sessions'}?</strong><p>The selected session${targets.length === 1 ? '' : 's'} and all of their messages will be deleted permanently.</p>`;
  modal({
    title: 'Confirm delete', body,
    compact: true,
    actions: [
      { label: 'No' },
      { label: 'Yes', pendingLabel: 'Deleting…', kind: 'danger', onClick: async close => {
        for (const session of targets) {
          await deleteSessionCascade(session);
          if (session.id === S.sessionId) { S.sessionId = null; S.messages = []; S.chatMode = 'general'; }
        }
        close();
        if (selectionMode) cancelSelectionMode(); else renderAgentHome();
        renderRecent(); renderSessions();
        toast(targets.length === 1 ? 'Session deleted' : targets.length + ' sessions deleted', 'ok', 1400);
      } }
    ]
  });
  document.querySelector('.modal').classList.add('delete-confirm-modal', 'compact-confirm-modal');
}

function profileActions(agent) {
  const flags = agentFlags();
  const body = el('div', 'profile-action-sheet');
  const pinned = flags.pinned.includes(agent.id);
  const pinIcon = '<span class="profile-action-icon pin">' + ZI('pin') + '</span>';
  const deleteIcon = '<span class="profile-action-icon danger">' + ZI('trash') + '</span>';
  body.innerHTML = `<div class="profile-action-identity"><strong>${esc(agent.name)}</strong><small>${pinned ? 'Pinned chat profile' : 'Chat profile'}</small></div><div class="profile-action-list"><button data-action="pin" class="profile-pin-action">${pinIcon}<span><strong>${pinned ? 'Unpin chat' : 'Pin chat'}</strong><small>${pinned ? 'Return to normal order' : 'Keep this profile at the top'}</small></span><span class="profile-pin-state">${pinned ? 'On' : 'Off'}</span></button><button data-action="delete" class="danger">${deleteIcon}<span><strong>Delete Agent</strong><small>Remove this profile permanently</small></span></button></div>`;
  body.onclick = async e => {
    const action = e.target.closest('[data-action]')?.dataset.action;
    if (action === 'pin') { togglePin(agent); closeModal(); }
    if (action === 'delete') { closeModal(); confirmDeleteAgents([agent]); }
  };
  modal({ title: 'Chat Profile', body, actions: [{ label: 'Done', kind: 'primary' }] });
  document.querySelector('.modal').classList.add('agent-profile-modal');
}

/* Long-press a Saved Session to enter the SAME selection mode used by chats, so
   the header Pin and Delete buttons serve both. A plain tap still opens it. */
const SESSION_HOLD_MS = 500;

function attachSessionPinGesture(item, session) {
  let holdTimer = null;
  let longPressed = false;
  let suppressed = false;
  let startX = 0;
  let startY = 0;

  const selectThis = () => {
    if (!selectionMode) enterSessionSelectionMode(session);
    else { selectedSessions.add(session.id); renderAgentHome(); }
  };

  const clearHold = () => { clearTimeout(holdTimer); holdTimer = null; };
  const beginHold = (clientX, clientY) => {
    clearHold();
    longPressed = false;
    suppressed = false;
    startX = clientX; startY = clientY;
    holdTimer = setTimeout(() => {
      if (suppressed) return;
      longPressed = true;
      selectThis();
    }, SESSION_HOLD_MS);
  };
  const cancelForMove = (clientX, clientY) => {
    if (Math.hypot(clientX - startX, clientY - startY) > 8) { clearHold(); suppressed = true; }
  };

  item.addEventListener('touchstart', event => {
    const touch = event.touches[0];
    if (touch) beginHold(touch.clientX, touch.clientY);
  }, { passive: true });
  item.addEventListener('touchmove', event => {
    const touch = event.touches[0];
    if (touch) cancelForMove(touch.clientX, touch.clientY);
  }, { passive: true });
  item.addEventListener('touchend', clearHold, { passive: true });
  item.addEventListener('touchcancel', () => { clearHold(); suppressed = true; }, { passive: true });
  item.addEventListener('contextmenu', event => {
    event.preventDefault();
    clearHold();
    longPressed = true;
    selectThis();
  });

  item.onclick = async event => {
    event.stopPropagation();
    if (longPressed || suppressed) { longPressed = false; return; }
    if (selectionMode) {
      selectedSessions.has(session.id) ? selectedSessions.delete(session.id) : selectedSessions.add(session.id);
      if (!selectionCount()) cancelSelectionMode(); else renderAgentHome();
      return;
    }
    await openSession(session.id);
  };
}

/* Single-agent model: one account = one agent (its key is the gateway key). The
   HOME is now a hub — three action cards (Chat with Agent / Session / Info Agent)
   plus a live ACTIVITY panel. The Session card opens the ROOM LIST (each room a
   separate chat history, like one bot living in several Telegram groups). */
function roomTitle(session) {
  if (isGeneralSession(session)) return 'Main chat';
  return String(session?.title || 'Untitled').replace(/\s+/g, ' ').trim() || 'Untitled';
}

/* Toggle between the hub (default) and the room list. */
function showHomeHub() {
  $('homeHub')?.removeAttribute('hidden');
  $('homeRooms')?.setAttribute('hidden', '');
  renderHomeHub();
}
function showHomeRooms() {
  $('homeHub')?.setAttribute('hidden', '');
  $('homeRooms')?.removeAttribute('hidden');
  renderAgentHome();
}

/* Reference-dashboard icon set. Kept local so the home layout has the exact
   optical shapes from the supplied design instead of inheriting generic app icons. */
function hubReferenceIcon(name) {
  const common = 'viewBox="0 0 24 24" aria-hidden="true" focusable="false"';
  const icons = {
    wifi: `<svg ${common}><path d="M3.5 9.3a13.2 13.2 0 0 1 17 0M6.7 12.6a8.4 8.4 0 0 1 10.6 0M9.8 15.8a3.5 3.5 0 0 1 4.4 0"/><circle cx="12" cy="19" r="1.45" fill="currentColor" stroke="none"/></svg>`,
    cube: `<svg ${common}><path d="m12 2.8 8 4.6v9.2l-8 4.6-8-4.6V7.4Z"/><path d="m4.2 7.5 7.8 4.6 7.8-4.6M12 12.1v9"/><path class="hub-icon-fill" d="m12 3 7.7 4.5-7.7 4.4-7.7-4.4Z"/></svg>`,
    chat: `<svg ${common}><path d="M5.2 5h13.6A2.2 2.2 0 0 1 21 7.2v8.1a2.2 2.2 0 0 1-2.2 2.2H9.2L4 20.4v-3.9a2.2 2.2 0 0 1-1-1.9V7.2A2.2 2.2 0 0 1 5.2 5Z"/><circle cx="8" cy="11.3" r="1" fill="currentColor" stroke="none"/><circle cx="12" cy="11.3" r="1" fill="currentColor" stroke="none"/><circle cx="16" cy="11.3" r="1" fill="currentColor" stroke="none"/></svg>`,
    clock: `<svg ${common}><circle cx="12" cy="12" r="8.5"/><path d="M12 7.2v5.2l3.3 2"/></svg>`,
    bookmark: `<svg ${common}><path d="M7 3.7h10a1.4 1.4 0 0 1 1.4 1.4v15.2L12 16.4l-6.4 3.9V5.1A1.4 1.4 0 0 1 7 3.7Z"/></svg>`,
    info: `<svg ${common}><circle cx="12" cy="12" r="9"/><path d="M12 10.7v6M12 7.2h.01"/></svg>`,
    github: `<svg ${common}><path d="M12 2.2a9.8 9.8 0 0 0-3.1 19.1c.5.09.66-.21.66-.48v-1.7c-2.7.59-3.28-1.3-3.28-1.3-.44-1.13-1.08-1.43-1.08-1.43-.89-.6.07-.59.07-.59.98.07 1.5 1.01 1.5 1.01.87 1.5 2.29 1.06 2.85.81.09-.63.34-1.06.62-1.3-2.16-.25-4.43-1.08-4.43-4.8 0-1.06.38-1.93 1-2.61-.1-.25-.44-1.24.1-2.58 0 0 .82-.26 2.7 1a9.3 9.3 0 0 1 4.9 0c1.87-1.26 2.69-1 2.69-1 .54 1.34.2 2.33.1 2.58.63.68 1 1.55 1 2.61 0 3.73-2.27 4.55-4.44 4.79.35.3.66.9.66 1.81v2.69c0 .27.16.58.67.48A9.8 9.8 0 0 0 12 2.2Z" fill="currentColor" stroke="none"/></svg>`,
    docs: `<svg ${common}><path d="M6.5 3.5h7.3L18.5 8v11.3a1.2 1.2 0 0 1-1.2 1.2H6.5a1.2 1.2 0 0 1-1.2-1.2V4.7A1.2 1.2 0 0 1 6.5 3.5Z"/><path d="M13.6 3.6v4.5h4.6M8.4 12.3h7.2M8.4 15.4h7.2M8.4 9.2h2.6"/></svg>`,
  };
  return icons[name] || icons.info;
}

function hubModelPresentation(rawModel) {
  const raw = String(rawModel || '').trim();
  if (!raw) return { name: 'Set model', source: 'Select' };
  // Strip EVERY provider/relay prefix: take the segment after the last '/'.
  // e.g. "ss/ccx/claude-opus-4-8" -> "claude-opus-4-8"
  const lastSlash = raw.lastIndexOf('/');
  const sourceRaw = lastSlash >= 0 ? raw.slice(0, lastSlash) : '';
  let modelRaw = lastSlash >= 0 ? raw.slice(lastSlash + 1) : raw;

  // Known brand/acronym casing (lowercase key -> display form).
  const CASING = {
    gpt: 'GPT', glm: 'GLM', qwen: 'Qwen', qwq: 'QwQ', kimi: 'Kimi',
    minimax: 'MiniMax', deepseek: 'DeepSeek', claude: 'Claude', opus: 'Opus',
    sonnet: 'Sonnet', haiku: 'Haiku', gemini: 'Gemini', gemma: 'Gemma',
    grok: 'Grok', llama: 'Llama', mistral: 'Mistral', mixtral: 'Mixtral',
    codestral: 'Codestral', ministral: 'Ministral', pixtral: 'Pixtral',
    phi: 'Phi', nova: 'Nova', doubao: 'Doubao', seed: 'Seed', hunyuan: 'Hunyuan',
    nemotron: 'Nemotron', nvidia: 'NVIDIA', cohere: 'Cohere', command: 'Command',
    aya: 'Aya', yi: 'Yi', thinking: 'Thinking', instruct: 'Instruct',
    chat: 'Chat', mini: 'Mini', flash: 'Flash', pro: 'Pro', max: 'Max',
    plus: 'Plus', turbo: 'Turbo', air: 'Air', lite: 'Lite', sol: 'Sol',
    luna: 'Luna', terra: 'Terra', reasoner: 'Reasoner', coder: 'Coder',
    vision: 'Vision', preview: 'Preview', latest: 'Latest', ai: 'AI',
  };

  const prettyToken = (tok) => {
    if (!tok) return tok;
    const low = tok.toLowerCase();
    if (CASING[low]) return CASING[low];
    // Pure version number (4, 5.6, 2.5) -> keep as-is
    if (/^\d+(?:\.\d+)*$/.test(tok)) return tok;
    // Brand+version glued: "qwen3.6" / "m2.5" / "v4" / "k2.6" / "gpt5"
    const m = tok.match(/^([a-z]+)([\d.]+)$/i);
    if (m) {
      const head = m[1].toLowerCase();
      const cased = CASING[head] || (head.length <= 2 ? m[1].toUpperCase() : m[1].charAt(0).toUpperCase() + m[1].slice(1));
      return cased + m[2];
    }
    // Short all-alpha tokens (<=2 chars) like "v", "m" -> upper
    if (/^[a-z]{1,2}$/i.test(tok)) return tok.toUpperCase();
    return tok.charAt(0).toUpperCase() + tok.slice(1);
  };

  let name = modelRaw.replace(/[_/]+/g, ' ').replace(/-/g, ' ').replace(/\s+/g, ' ').trim();
  name = name.split(' ').map(prettyToken).join(' ');
  // Rejoin split version segments: "4 8" -> "4.8" (Anthropic hyphen-dot convention)
  name = name.replace(/\b(\d+) (\d+)\b/g, '$1.$2');

  const source = sourceRaw
    ? sourceRaw.split('/').pop().charAt(0).toUpperCase() + sourceRaw.split('/').pop().slice(1)
    : 'Active';
  return { name: name || raw, source };
}

const HUB_PROVIDER_LOGOS = [
  // Model-family matches come first: a relay/gateway must not make every
  // routed model use the relay's own logo. Order matters — the most specific
  // model-family patterns win before any relay/provider name match.
  /* `claude` also matches the transposed/typo spellings relay catalogs ship
     (`claide`, `clade`, `cluade`). The family is unmistakable, and a routing
     prefix like `tencent/` must not knock it out. The alternatives are anchored
     to word boundaries so ordinary words (case, code, create) never match. */
  { match: /\b(claude|claide|cluade|clade)\b|anthropic/, asset: 'anthropic', label: 'Anthropic' },
  { match: /deepseek/, asset: 'deepseek', label: 'DeepSeek' },
  /* Tencent Hunyuan. `hy3` / `hy4-preview` are its short model ids and carry no
     "hunyuan" substring, so a provider card that only shows `hy3` would fall
     through to the robot glyph without this row. */
  { match: /hunyuan|tencent|\bhy[0-9](-|$)/, asset: 'hunyuan', label: 'Hunyuan' },
  /* Gemini CLI must be claimed BEFORE the generic google/gemini family row, or
     an OAuth "Gemini CLI" connection renders the plain Google mark. The pattern
     requires an explicit CLI marker (not just "gemini"), so a routed
     `google/gemini-3-flash` model still falls through to the family logo. */
  { match: /gemini[-_ ]?cli|\bgcli\b/, asset: 'gemini', label: 'Gemini CLI' },
  { match: /google|gemini|vertex|gemma/, asset: 'google', label: 'Google' },
  { match: /(^|[^a-z])glm([^a-z]|$)|z-ai|\bzai\b|chatglm|zhipu/, asset: 'zai', label: 'Z.ai' },
  { match: /kimi|moonshot/, asset: 'moonshot', label: 'Moonshot' },
  { match: /minimax|\babab\b/, asset: 'minimax', label: 'MiniMax' },
  { match: /qwen|qwq|tongyi/, asset: 'qwen', label: 'Qwen' },
  /* Grok CLI (SuperGrok) must be claimed BEFORE the generic xAI row below —
     that row matches the bare substring `grok` and would otherwise swallow
     `grok-cli`, making the two cards indistinguishable. Requires an explicit
     CLI marker, so a plain `xai/...` or `grok-4` model still gets the xAI mark.
     `gb` / `grok-build` are the gateway's aliases for this same OAuth
     connection. NOTE: `gcli` is NOT included here — the gateway assigns that
     alias to Gemini CLI, so claiming it would steal Gemini CLI's logo. */
  { match: /grok[-_ ]?cli|grok[-_ ]?build|\bgb\b/, asset: 'grok-cli', label: 'xAI (SuperGrok)' },
  { match: /(^|[^a-z])xai([^a-z]|$)|grok/, asset: 'x', label: 'xAI' },
  { match: /meta|\bllama\b|\blama\b/, asset: 'meta', label: 'Meta' },
  { match: /mistral|mixtral|codestral|magistral|ministral|pixtral|devstral/, asset: 'mistral', label: 'Mistral AI' },
  { match: /cohere|command-|command\b|\baya\b/, asset: 'cohere', label: 'Cohere' },
  { match: /\bphi\b|phi-\d|microsoft|\bmai\b|azure/, asset: 'microsoft', label: 'Microsoft' },
  { match: /nemotron|nvidia/, asset: 'nvidia', label: 'Nvidia' },
  { match: /(^|[^a-z])nova([^a-z]|$)|amazon-nova|titan/, asset: 'nova', label: 'Amazon Nova' },
  { match: /doubao|\bseed\b|seed-|bytedance/, asset: 'doubao', label: 'Doubao' },
  { match: /hunyuan|tencent/, asset: 'hunyuan', label: 'Hunyuan' },
  { match: /gpt|openai|\bo[134]\b|codex|davinci/, asset: 'openai', label: 'OpenAI' },
  { match: /openrouter/, asset: 'openrouter', label: 'OpenRouter' },
  { match: /ollama/, asset: 'ollama', label: 'Ollama' },
  /* v382 — first-party provider/CLI identities that the gateway connects via OAuth
     or API key. These MUST come last: every entry above matches a model
     family, and a CLI wrapper (e.g. "Gemini CLI", "Grok CLI") also carries its
     vendor's name in the identity string. Putting these first would hijack
     plain model routing — e.g. an `anthropic/...` model would render the
     Claude Code mark instead of Anthropic. Matched on the provider/CLI name
     only, so they win just when nothing model-family-specific matched.
     Gemini CLI is the one exception that must precede its family row (see the
     note at the top of this table); `xai` reuses the existing `x` family mark. */
  { match: /antigravity/, asset: 'antigravity', label: 'Antigravity' },
  { match: /kiro/, asset: 'kiro-cli', label: 'Kiro AI' },
  { match: /cursor/, asset: 'cursor-cli', label: 'Cursor' },
  { match: /qoder/, asset: 'qoder-cli', label: 'Qoder' },
  { match: /perplexity|\bpplx\b/, asset: 'perplexity-cli', label: 'Perplexity' },
];

function hubProviderLogo(agent) {
  const provider = S.providers.find(item => item.id === agent?.provider_id);
  const identity = [provider?.id, provider?.name, provider?.type, agent?.provider_id, agent?.model]
    .filter(Boolean).join(' ').toLowerCase();
  const known = HUB_PROVIDER_LOGOS.find(item => item.match.test(identity));
  if (!known) return `<span class="hub-provider-logo is-fallback" aria-label="${esc(provider?.name || agent?.provider_id || 'Provider')}">${ZI('provider')}</span>`;
  return `<span class="hub-provider-logo" aria-label="${esc(known.label)}"><img src="assets/provider-logos/${known.asset}.svg?v=8" alt="" draggable="false"></span>`;
}

/* The round mark for a MODEL, picked from the model id itself (`gemini-3.8` →
   the Gemini mark, `claude-opus` → Anthropic, `gpt-5` → OpenAI). Reuses the same
   match table the hub uses, so a model and a provider never disagree about which
   vendor a family belongs to. Falls back to the robot glyph when nothing
   matches, so an unknown family still renders something. */
function pvModelLogoAsset(modelId) {
  const key = String(modelId || '').toLowerCase();
  const known = HUB_PROVIDER_LOGOS.find(item => item.match.test(key));
  return known ? known.asset : '';
}

/* Environment card second line. Detected 100% from the runtime (/system →
   S.system.env_label). States:
     - Detecting…              : no snapshot yet OR a probe is actively re-checking
     - Offline                 : runtime couldn't be reached on the last check
     - Not detected            : /system answered but the platform is unrecognised
     - "<OS> · <context>"      : e.g. "Termux · Android", "Linux · VPS", "macOS · Apple Silicon"
   Never shows "Remote" (that's a connection type) or "Unknown". */
function envDisplayLabel() {
  const hc = S.hc || {};
  if (hc.environment === 'checking') return 'Detecting…';   // only while actively probing
  if (hc.environment === 'down') return 'Offline';
  // Show the real detected environment whenever we have a runtime snapshot
  // (fetched at boot), regardless of whether a manual health check has run.
  const label = S.system ? (S.system.env_label || '').trim() : '';
  return label || 'Not detected';
}

/* HOME HERO v302 — centered Zeline ghost emblem + greeting. The mark is the
   official Zeline ghost logo (white on black), framed by the neon halo. */
function homeReferenceLogo() {
  return `<img class="home-ai-logo" src="assets/zeline-logo.png?v=2" alt="Zeline" draggable="false">`;
}
function renderHomeHero() {
  const hero = $('hubHero');
  if (!hero) return;
  const markup = `
    <div class="hub-hero-mark" aria-hidden="true">${homeReferenceLogo()}</div>
    <div class="hub-hero-copy">
      <h2 class="hub-hero-title"><span>I'm </span><strong>Zeline</strong></h2>
      <p class="hub-hero-sub">Your agentic AI, always here.</p>
    </div>`;
  if (hero.dataset.hubSig !== markup) {
    hero.dataset.hubSig = markup;
    hero.innerHTML = markup;
  }
}

/* HOME COMPOSER v299 — premium frosted ask card. No leading "+": typing starts
   immediately. A live preview row (like a chat list entry) shows the last
   message tail with time + unread badge. The model button is a compact chip
   with a small provider logo. Sending hands off to the existing send() flow. */
function renderHomeComposer() {
  const host = $('hubComposer');
  if (!host) return;
  const agent = S.agents[0] || null;
  const model = hubModelPresentation(agent?.model || '');
  const general = agent ? generalSessionForAgent(agent.id) : null;
  const dmTyping = agent && agentLiveActivity.has(agent.id);
  const dmUnread = agent ? agentUnreadCount(agent.id) : 0;
  const previewText = dmTyping ? 'Typing…' : (hubLastChatPreview(agent) || 'Start a conversation with Zeline');
  const previewTime = general?.updated_at ? timeAgo(general.updated_at) : '';
  const markup = `
    <div class="hub-ask" id="hubAskCard">
      <button class="hub-ask-preview" id="hubAskPreview" type="button" aria-label="Open last chat">
        <span class="hub-ask-preview-copy"><span class="hub-ask-preview-text${dmTyping ? ' typing' : ''}">${esc(previewText)}</span></span>
        <span class="hub-ask-preview-meta">${previewTime ? `<time>${esc(previewTime)}</time>` : ''}${dmUnread ? `<em class="hub-ask-unread" aria-label="${dmUnread} unread">${dmUnread > 99 ? '99+' : dmUnread}</em>` : ''}</span>
      </button>
      <div class="hub-ask-field" id="hubAskField">
        <textarea id="hubAskInput" rows="1" placeholder="Ask anything…" aria-label="Ask anything"></textarea>
        <button class="hub-ask-send" id="hubAskSend" type="button" aria-label="Send" disabled>${homeShortcutIcon('send')}</button>
      </div>
      <div class="hub-ask-foot">
        <button class="hub-ask-model" id="hubAskModel" type="button" aria-label="Choose model" aria-expanded="false">
          ${hubProviderLogo(agent)}<span data-hub-model-name="1">${esc(model.name)}</span>${ZI('chevron')}
        </button>
      </div>
    </div>`;
  if (host.dataset.hubSig !== markup) {
    host.dataset.hubSig = markup;
    host.innerHTML = markup;
    const ta = host.querySelector('#hubAskInput');
    const sendBtn = host.querySelector('#hubAskSend');
    const refresh = () => { sendBtn.disabled = !String(ta.value || '').trim(); };
    ta.addEventListener('input', () => {
      ta.style.height = 'auto';
      ta.style.height = Math.min(ta.scrollHeight, 150) + 'px';
      refresh();
    });
    ta.addEventListener('keydown', e => {
      if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); submitHomeAsk(); }
    });
    host.querySelector('#hubAskPreview').onclick = () => {
      if (!agent) return toast('No agent linked yet', 'warn');
      openAgentChat(agent);
    };
    sendBtn.onclick = () => submitHomeAsk();
    host.querySelector('#hubAskModel').onclick = () => {
      if (!agent) return toast('No agent linked yet', 'warn');
      S.agentId = agent.id; openModelPicker();
    };
    refresh();
  }
}

/* Route a home-composer message into the existing chat send() so one flow owns
   attachments, slash commands, streaming, and persistence. */
async function submitHomeAsk() {
  const ta = $('hubAskInput');
  const text = String(ta?.value || '').trim();
  if (!text) return;
  const agent = S.agents[0];
  if (!agent) return toast('No agent linked yet', 'warn');
  await openAgentChat(agent);
  const input = $('input');
  if (input) { input.value = text; input.dispatchEvent(new Event('input', { bubbles: true })); }
  if (ta) { ta.value = ''; ta.style.height = 'auto'; }
  send();
}

/* Composer placeholder: shows the tail of the most recent chat ("…last words")
   with a typing-shimmer animation, falling back to "Ask anything…". */
function hubLastChatPreview(agent) {
  if (!agent) return '';
  const rooms = S.sessions.filter(s => s.agent_id === agent.id && !isGeneralSession(s));
  const general = generalSessionForAgent(agent.id);
  const pool = [...rooms, general].filter(Boolean)
    .sort((a, b) => String(b.updated_at || '').localeCompare(String(a.updated_at || '')));
  const latest = pool.find(s => String(s.last_preview || '').trim());
  const text = String(latest?.last_preview || '').replace(/\s+/g, ' ').trim();
  return text;
}
function hubComposerPlaceholder(agent) {
  const last = hubLastChatPreview(agent);
  if (!last) return 'Ask anything…';
  const tail = last.length > 46 ? '…' + last.slice(-46) : last;
  return tail + '…';
}

/* Optional universal + launcher. Each choice still opens the exact same
   name-only dialog used by the matching first-class workspace destination. */
function openHomeAddSheet() {
  const agent = agentById(S.agentId) || S.agents[0];
  if (!agent) return toast('No agent linked yet', 'warn');
  const body = el('div', 'home-add-sheet');
  body.innerHTML = `
    <button class="home-add-row" data-kind="session" type="button">
      <span class="home-add-row-ic tone-blue">${ZI('chat')}</span>
      <span><strong>New Session</strong><small>Chat thread in this workspace</small></span>
    </button>
    <button class="home-add-row" data-kind="project" type="button">
      <span class="home-add-row-ic tone-navy">${ZI('code')}</span>
      <span><strong>New Project</strong><small>Grouped room with a goal</small></span>
    </button>
    <button class="home-add-row" data-kind="cronjob" type="button">
      <span class="home-add-row-ic tone-blue">${ZI('clock')}</span>
      <span><strong>New Cronjob</strong><small>Configure it conversationally</small></span>
    </button>
    <button class="home-add-row" data-kind="workflow" type="button">
      <span class="home-add-row-ic tone-blue">${ZI('workspace')}</span>
      <span><strong>New Workflow</strong><small>Build it conversationally</small></span>
    </button>`;
  body.onclick = event => {
    const row = event.target.closest('[data-kind]');
    if (!row) return;
    closeModal();
    promptWorkspaceName(agent, row.dataset.kind);
  };
  modal({ title: 'Create new', body, actions: [] });
}

/* Lightweight drag-to-reorder for workspace rows. Uses native DnD events,
   a single CSS transform for the drag preview, and persists the new order
   via the existing session sort-order field. No heavy libraries. */
const ROW_REORDER_KEY = 'workspace_order_';
function getWorkspaceOrder(kind) {
  try { return JSON.parse(localStorage.getItem(ROW_REORDER_KEY + kind) || '[]'); }
  catch (_) { return []; }
}
function saveWorkspaceOrder(kind, ids) {
  localStorage.setItem(ROW_REORDER_KEY + kind, JSON.stringify(ids));
}
function applyWorkspaceOrder(rooms, kind) {
  const order = getWorkspaceOrder(kind);
  if (!order.length) return rooms;
  const rank = new Map(order.map((id, i) => [id, i]));
  return rooms.slice().sort((a, b) => {
    const ra = rank.has(a.id) ? rank.get(a.id) : 999999;
    const rb = rank.has(b.id) ? rank.get(b.id) : 999999;
    if (ra !== rb) return ra - rb;
    return String(b.updated_at || '').localeCompare(String(a.updated_at || ''));
  });
}
function _clearDragShift(list) {
  list.querySelectorAll('.workspace-row').forEach(r => {
    r.classList.remove('drag-shift-up', 'drag-shift-down', 'drag-over');
  });
}

function _applyDragShift(list, dragRow, overRow, above) {
  _clearDragShift(list);
  const rows = Array.from(list.querySelectorAll('.workspace-row'));
  const dragIdx = rows.indexOf(dragRow);
  const overIdx = rows.indexOf(overRow);
  rows.forEach((r, i) => {
    if (r === dragRow) return;
    if (above) {
      // dragging upward: rows between target and drag origin shift down
      if (i >= overIdx && i < dragIdx) r.classList.add('drag-shift-down');
    } else {
      // dragging downward: rows between drag origin and target shift up
      if (i > dragIdx && i <= overIdx) r.classList.add('drag-shift-up');
    }
  });
}

function attachRowReorder(list, rooms, kind) {
  if (!list || rooms.length < 2) return;
  let dragRow = null;

  // Native scrolling owns the list; no boundary transform or custom bounce here.
  // A transformed scroller can look frozen on Android when a swipe ends at an edge.

  list.querySelectorAll('.workspace-row').forEach((row) => {
    /* --- Mouse reorder (desktop) --- */
    row.addEventListener('dragstart', (e) => {
      dragRow = row;
      row.classList.add('dragging');
      e.dataTransfer.effectAllowed = 'move';
      try { e.dataTransfer.setData('text/plain', row.dataset.workspaceRowId || ''); } catch (_) {}
    });
    row.addEventListener('dragend', () => {
      row.classList.remove('dragging');
      _clearDragShift(list);
      persistReorder(list, kind);
      dragRow = null;
    });
    row.addEventListener('dragover', (e) => {
      e.preventDefault();
      if (!dragRow || dragRow === row) return;
      const rect = row.getBoundingClientRect();
      const mid = rect.top + rect.height / 2;
      const above = e.clientY < mid;
      _applyDragShift(list, dragRow, row, above);
      list.insertBefore(dragRow, above ? row : row.nextSibling);
    });
  });
}
function persistReorder(list, kind) {
  const ids = Array.from(list.querySelectorAll('.workspace-row')).map(r => r.dataset.workspaceRowId);
  saveWorkspaceOrder(kind, ids);
}

/* The four workspace destinations share a short native-style top-boundary
   nudge. Only the sheet below the app-bar moves: the modal header and its
   divider remain the visual top edge, while the canvas behind the sheet stays
   visible in the small gap. This is passive on purpose—native list scrolling
   must never be prevented or reimplemented on Android. */
function wireWorkspacePullNudge(list, body) {
  const WORKSPACE_PULL_MAX_PX = 12;
  const WORKSPACE_PULL_INTENT_PX = 7;
  const WORKSPACE_PULL_RANGE_PX = 64;
  if (!list || !body || body.dataset.workspacePullWired) return;
  body.dataset.workspacePullWired = '1';

  let gesture = null;
  let frame = 0;
  let releaseTimer = 0;

  const clearRelease = () => {
    clearTimeout(releaseTimer);
    releaseTimer = 0;
    body.classList.remove('workspace-pull-releasing');
    body.style.transform = '';
  };

  const paint = () => {
    frame = 0;
    if (!gesture?.active) return;
    body.style.transform = `translate3d(0,${gesture.pull.toFixed(2)}px,0)`;
  };

  const queuePaint = () => {
    if (!frame) frame = requestAnimationFrame(paint);
  };

  const release = () => {
    const pulled = gesture?.active && gesture.pull > 0;
    gesture = null;
    if (frame) { cancelAnimationFrame(frame); frame = 0; }
    if (!pulled) {
      clearRelease();
      body.classList.remove('workspace-pull-active');
      return;
    }
    body.classList.remove('workspace-pull-active');
    body.classList.add('workspace-pull-releasing');
    body.style.transform = '';
    const finish = () => clearRelease();
    body.addEventListener('transitionend', finish, { once: true });
    releaseTimer = setTimeout(finish, 300);
  };

  list.addEventListener('touchstart', event => {
    clearRelease();
    if (event.touches.length !== 1 || list.scrollTop > 0
      || event.target.closest('input,textarea,select,[contenteditable="true"],[contenteditable=""]')) {
      gesture = null;
      return;
    }
    const touch = event.touches[0];
    gesture = { startX: touch.clientX, startY: touch.clientY, pull: 0, active: false, cancelled: false };
  }, { passive: true });

  list.addEventListener('touchmove', event => {
    const state = gesture;
    const touch = event.touches[0];
    if (!state || !touch || state.cancelled) return;
    const dx = touch.clientX - state.startX;
    const dy = touch.clientY - state.startY;
    if (!state.active) {
      if (Math.max(Math.abs(dx), Math.abs(dy)) < WORKSPACE_PULL_INTENT_PX) return;
      if (list.scrollTop > 0 || dy <= 0 || Math.abs(dy) <= Math.abs(dx) * 1.15) {
        state.cancelled = true;
        return;
      }
      state.active = true;
      body.classList.add('workspace-pull-active');
    }
    state.pull = WORKSPACE_PULL_MAX_PX * (1 - Math.exp(-Math.max(0, dy) / WORKSPACE_PULL_RANGE_PX));
    queuePaint();
  }, { passive: true });

  list.addEventListener('touchend', release, { passive: true });
  list.addEventListener('touchcancel', release, { passive: true });
}


const WORKSPACE_NAV = {
  session:  { kind: 'session',  icon: 'chat',      singular: 'Session',  plural: 'Sessions',  empty: 'No sessions yet' },
  project:  { kind: 'project',  icon: 'code',      singular: 'Project',  plural: 'Projects',  empty: 'No projects yet' },
  cronjob:  { kind: 'cronjob',  icon: 'clock',     singular: 'Cronjob',  plural: 'Cronjobs',  empty: 'No cronjobs yet' },
  workflow: { kind: 'workflow', icon: 'workspace', singular: 'Workflow', plural: 'Workflows', empty: 'No workflows yet' },
};

function workspaceNav(kind) {
  return WORKSPACE_NAV[canonicalWorkspaceKind(kind, 'session')] || WORKSPACE_NAV.session;
}

function openWorkspace(kind = activeWorkspaceKind) {
  const agent = agentById(S.agentId) || S.agents[0] || null;
  if (!agent) return toast('No agent linked yet', 'warn');
  const item = workspaceNav(kind);
  activeWorkspaceKind = item.kind;
  localStorage.setItem(WORKSPACE_KIND_KEY, item.kind);

  // A destination owns its own query and result list.  We do not re-use the
  // global chat search here: typing searches only this workspace type and asks
  // the persisted API for the current result set.
const WORKSPACE_DESC = {
    session:  `Create a session to keep conversations organized by topic, task, or idea. Start a separate context with Zeline anytime.`,
    cronjob:  `Create a cronjob to automate recurring tasks and let Zeline run them automatically on your schedule.`,
    project:  `Create a project to keep related work, files, tasks, and context organized in one dedicated space.`,
    workflow: `Create a workflow to connect tasks and actions into a seamless flow, allowing Zeline to handle them automatically.`,
  };
  const createLabels = {
    session: 'Create a session',
    cronjob: 'Create a cronjob',
    project: 'Create a project',
    workflow: 'Create a workflow',
  };
  const createLabel = createLabels[item.kind] || '';
  const descHtml = (WORKSPACE_DESC[item.kind] || '').replace(
    createLabel,
    `<button class="workspace-desc-create" data-workspace-create="${item.kind}" type="button">${createLabel}</button>`
  );

  const body = el('div', `workspace-sheet workspace-kind-${item.kind}`);
  body.innerHTML = `
    <div class="workspace-list" aria-label="${item.plural}" aria-live="polite">
      ${descHtml ? `<div class="workspace-desc">${descHtml}</div>` : ''}
    </div>`;

  // Search is an app-bar surface, not a body field: when open it takes over the
  // whole header row, so Back and the title are replaced instead of pushed down.
  const searchWrap = el('label', 'modal-workspace-search');
  searchWrap.hidden = true;
  searchWrap.innerHTML = `
    <span aria-hidden="true">${ZI('search')}</span>
    <input data-workspace-search type="search" autocomplete="off" spellcheck="false" placeholder="Search ${item.plural}" aria-label="Search ${item.plural}">`;

  const input = searchWrap.querySelector('[data-workspace-search]');
  const list = body.querySelector('.workspace-list');
  // Held outside the render so a blanked search view can restore it verbatim.
  const descNode = list.querySelector('.workspace-desc');
  let query = '';
  let searchOpen = false;
  let remoteRooms = null;
  let requestId = 0;
  let searchTimer = null;

  const localRooms = () => S.sessions
    .filter(session => session.agent_id === agent.id && !isGeneralSession(session))
    .filter(session => workspaceKindOf(session) === item.kind)
    .filter(session => !query || `${session.title || ''}\n${session.last_preview || ''}`.toLocaleLowerCase().includes(query))
    .sort((a, b) => String(b.updated_at || '').localeCompare(String(a.updated_at || '')));

  const renderedRooms = () => {
    if (Array.isArray(remoteRooms)) return applyWorkspaceOrder(remoteRooms, item.kind);
    return applyWorkspaceOrder(localRooms(), item.kind);
  };

  const renderRooms = () => {
    if (!list?.isConnected) return;
    // Preserve the description node across every list refresh/search render.
    // It is a real child of the scroller, so it naturally scrolls away.
    const descEl = list.querySelector('.workspace-desc') || descNode;
    // An open search bar with no query is a blank slate: results appear only
    // once the user actually types, so nothing competes with the field.
    if (searchOpen && !query) {
      list.innerHTML = '';
      return;
    }
    const rooms = renderedRooms();
    list.innerHTML = rooms.length ? rooms.map(session => {
      const unread = sessionUnreadCount(session);
      return `<div class="workspace-row" draggable="true" data-workspace-row-id="${esc(session.id)}">
        <button class="workspace-open" data-workspace-session="${esc(session.id)}" type="button">
          <span class="workspace-row-icon workspace-kind-${item.kind}" aria-hidden="true">${ZI(item.icon)}</span>
          <span class="workspace-row-copy"><strong>${esc(roomTitle(session))}</strong></span>
          <span class="workspace-row-badge">${unread ? `<em>${unread > 99 ? '99+' : unread}</em>` : ''}</span>
        </button>
      </div>`;
    }).join('') : `<div class="workspace-empty">${query ? `No ${item.plural.toLowerCase()} match “${esc(query)}”` : item.empty}</div>`;
    if (descEl && !searchOpen) list.prepend(descEl);
    attachRowReorder(list, rooms, item.kind);
  };

  const refreshWorkspaceSearch = async () => {
    // Nothing to fetch while the open field is still empty: the blank state is
    // intentional, and a late response must not repopulate it.
    if (searchOpen && !query) { renderRooms(); return; }
    const thisRequest = ++requestId;
    const params = new URLSearchParams({ agent_id: agent.id, kind: item.kind });
    if (query) params.set('q', query);
    input?.setAttribute('aria-busy', 'true');
    try {
      const response = await api(`/sessions?${params.toString()}`, { timeoutMs: 8000 });
      if (thisRequest !== requestId || !body.isConnected) return;
      remoteRooms = Array.isArray(response?.sessions) ? response.sessions : [];
      remoteRooms.forEach(room => {
        const existing = S.sessions.find(session => session.id === room.id);
        if (existing) Object.assign(existing, room);
        else S.sessions.push(room);
      });
      saveSessionCache(S.sessions);
      renderRooms();
    } catch (_) {
      // A cached local list remains useful offline. The next query/reopen retries
      // the persistence-backed endpoint instead of pretending a static list is live.
      if (thisRequest === requestId) {
        remoteRooms = null;
        renderRooms();
      }
    } finally {
      if (thisRequest === requestId) input?.removeAttribute('aria-busy');
    }
  };

  body.onclick = event => {
    const createButton = event.target.closest('[data-workspace-create]');
    if (createButton) {
      closeModal();
      promptWorkspaceName(agent, createButton.dataset.workspaceCreate);
      return;
    }
    const roomButton = event.target.closest('[data-workspace-session]');
    if (roomButton) {
      S._leaveBack = item.kind;
      closeModal();
      openSession(roomButton.dataset.workspaceSession);
    }
  };
  input?.addEventListener('input', () => {
    query = String(input.value || '').trim().toLocaleLowerCase();
    remoteRooms = null;
    renderRooms();
    clearTimeout(searchTimer);
    searchTimer = setTimeout(refreshWorkspaceSearch, 160);
  });
  renderRooms();
  modal({ title: item.plural, body, actions: [] });
  const workspaceModal = document.querySelector('.modal');
  workspaceModal?.classList.add('workspace-modal');
  // The first render happens before modal() attaches the body. Render once
  // more now so the description and initial cached rows are visible immediately.
  renderRooms();

  // Keep the list natively scrollable. The nudge listener is passive and moves
  // only its sheet after a confirmed pull at scrollTop 0.
  wireWorkspacePullNudge(list, body);

  const searchAction = $('modalSearchAction');
  const modalHead = workspaceModal?.querySelector('.modal-head');
  // Mount the search field into the app bar itself, after modal() has cleaned
  // the shell — otherwise the fresh node is removed again on the next open.
  modalHead?.appendChild(searchWrap);
  if (searchAction) {
    searchAction.hidden = false;
    searchAction.innerHTML = ZI('search');
    searchAction.setAttribute('aria-label', `Search ${item.plural}`);
    searchAction.setAttribute('aria-expanded', 'false');
    searchAction.onclick = () => {
      const opening = Boolean(searchWrap.hidden);
      searchWrap.hidden = !opening;
      searchOpen = opening;
      if (workspaceModal) workspaceModal.classList.toggle('workspace-search-open', opening);
      searchAction.innerHTML = ZI(opening ? 'close' : 'search');
      searchAction.setAttribute('aria-label', opening ? 'Cancel search' : `Search ${item.plural}`);
      searchAction.setAttribute('aria-expanded', String(opening));
      if (opening) {
        // Blank the list immediately so the open field starts on a clean slate.
        renderRooms();
        setTimeout(() => input?.focus(), 0);
        return;
      }
      // Cancelling restores the plain list: clear the query and drop focus so
      // the mobile keyboard closes with the field.
      input?.blur();
      if (input) input.value = '';
      query = '';
      remoteRooms = null;
      renderRooms();
    };
  }

  const createAction = $('modalHeadAction');
  if (createAction) {
    createAction.hidden = true;  // removed — create is in the desc link instead
  }
  refreshWorkspaceSearch();
}

/* HOME GRID — circular feature shortcuts (2 rows × 4). Each opens a real,
   existing surface; none are decorative. */
function openMoreMenu() {
  /* Twelve capability surfaces, each with its own colour tone so the sheet
     reads like a real capability browser instead of a monochrome list. */
  const items = [
    { key: 'library',      icon: 'media',     tone: 'rose',   label: 'Library',      description: 'Storage: images, files, and attachments from past conversations' },
    { key: 'skills',       icon: 'spark',     tone: 'violet', label: 'Skills',       description: 'Agent capabilities: research, coding, writing, analysis' },
    { key: 'tools',        icon: 'terminal',  tone: 'slate',  label: 'Tools',        description: 'Tools the agent can call: browser, terminal, calculator, APIs' },
    { key: 'integrations', icon: 'link',      tone: 'green',  label: 'Integrations', description: 'External connections: GitHub, Google Drive, Telegram, Discord' },
    { key: 'memory',       icon: 'bookmark',  tone: 'amber',  label: 'Memory',       description: 'Information the agent remembers across conversations' },
    { key: 'knowledge',    icon: 'docs',      tone: 'cyan',   label: 'Knowledge',    description: 'Documents and data that feed the agent knowledge' },
    { key: 'workflows',    icon: 'gateway',   tone: 'blue',   label: 'Workflows',    description: 'Sequences of steps and actions the agent runs' },
    { key: 'tasks',        icon: 'check',     tone: 'pink',   label: 'Tasks',        description: 'Work the agent needs to complete' },
    { key: 'agents',       icon: 'agents',    tone: 'indigo', label: 'Agents',       description: 'Agent configuration and persona' },
    { key: 'activity',     icon: 'usage',     tone: 'orange', label: 'Activity',     description: 'Log of all agent activity' },
    { key: 'artifacts',    icon: 'code',      tone: 'teal',   label: 'Artifacts',    description: 'Agent output: files, reports, code, and more' },
    { key: 'triggers',     icon: 'power',     tone: 'red',    label: 'Triggers',     description: 'Triggers besides cron: webhooks, events, and more' },
  ];
  const body = el('div', 'more-menu-sheet');
  /* v299 — compact 4-across icon grid (tonal wells + labels), not a long list. */
  body.innerHTML = `<div class="more-menu-grid">${items.map(item => `
    <button class="more-menu-tile" data-more-key="${item.key}" type="button" aria-label="${item.label}">
      <span class="more-menu-ic hub-tone-${item.tone}">${homeShortcutIcon(MORE_ICON_MAP[item.icon] || 'menu')}</span>
      <span class="more-menu-tile-label">${item.label}</span>
    </button>`).join('')}</div>
  <p class="more-menu-hint" id="moreMenuHint">Pick a surface to see its details</p>`;
  body.onclick = event => {
    const tile = event.target.closest('[data-more-key]');
    if (!tile) return;
    const key = tile.dataset.moreKey;
    if (key === 'agents')    { closeModal(); return go('chat'); }
    if (key === 'activity')  { closeModal(); return go('usage'); }
    if (key === 'workflows') { closeModal(); return openWorkspace('workflow'); }
    if (key === 'library')   { closeModal(); return openSavedMessages(); }
    const item = items.find(i => i.key === key);
    const hint = $('moreMenuHint');
    if (hint && item) hint.textContent = item.description;
  };
  modal({ title: 'More', body, actions: [] });
  document.querySelector('.modal')?.classList.add('more-menu-modal');
}

/* Map the Cupertino icon names to the outline HOME_SHORTCUT_PATHS family so the
   More sheet and the home grid share one calm, aligned stroke style. */
const MORE_ICON_MAP = {
  media: 'media', spark: 'spark', terminal: 'terminal', link: 'link', bookmark: 'bookmark',
  docs: 'docs', gateway: 'gateway', check: 'check', agents: 'agents', usage: 'usage',
  code: 'code', power: 'power', chat: 'chat', menu: 'menu', file: 'docs',
};

/* HOME SHORTCUT ICONS — Material Symbols Rounded (filled), same family as the
   global ZICONS set (google/material-design-icons, Apache-2.0). */
const HOME_SHORTCUT_PATHS = {
  chat: '<path d=\"M20 6h-1v8c0 .55-.45 1-1 1H6v1c0 1.1.9 2 2 2h10l4 4V8c0-1.1-.9-2-2-2zm-3 5V4c0-1.1-.9-2-2-2H4c-1.1 0-2 .9-2 2v13l4-4h9c1.1 0 2-.9 2-2z\"/>',
  code: '<path d=\"M8.7 15.9L4.8 12l3.9-3.9c.39-.39.39-1.01 0-1.4-.39-.39-1.01-.39-1.4 0l-4.59 4.59c-.39.39-.39 1.02 0 1.41l4.59 4.6c.39.39 1.01.39 1.4 0 .39-.39.39-1.01 0-1.4zm6.6 0l3.9-3.9-3.9-3.9c-.39-.39-.39-1.01 0-1.4.39-.39 1.01-.39 1.4 0l4.59 4.59c.39.39.39 1.02 0 1.41l-4.59 4.6c-.39.39-1.01.39-1.4 0-.39-.39-.39-1.01 0-1.4z\"/>',
  clock: '<path fill-rule="evenodd" d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2ZM11.28 7.72c0-.4.32-.72.72-.72h.06c.4 0 .72.32.72.72v4.36l3.87 2.3c.35.2.46.65.25.99a.72.72 0 0 1-.98.24l-4.15-2.49a.9.9 0 0 1-.49-.86V7.72Z"/>',
  gateway: '<path d=\"M8.4,18.2C8.78,18.7,9,19.32,9,20c0,1.66-1.34,3-3,3s-3-1.34-3-3s1.34-3,3-3c0.44,0,0.85,0.09,1.23,0.26l1.41-1.77 c-0.92-1.03-1.29-2.39-1.09-3.69l-2.03-0.68C4.98,11.95,4.06,12.5,3,12.5c-1.66,0-3-1.34-3-3s1.34-3,3-3s3,1.34,3,3 c0,0.07,0,0.14-0.01,0.21l2.03,0.68c0.64-1.21,1.82-2.09,3.22-2.32l0-2.16C9.96,5.57,9,4.4,9,3c0-1.66,1.34-3,3-3s3,1.34,3,3 c0,1.4-0.96,2.57-2.25,2.91v2.16c1.4,0.23,2.58,1.11,3.22,2.32l2.03-0.68C18,9.64,18,9.57,18,9.5c0-1.66,1.34-3,3-3s3,1.34,3,3 s-1.34,3-3,3c-1.06,0-1.98-0.55-2.52-1.37l-2.03,0.68c0.2,1.29-0.16,2.65-1.09,3.69l1.41,1.77C17.15,17.09,17.56,17,18,17 c1.66,0,3,1.34,3,3s-1.34,3-3,3s-3-1.34-3-3c0-0.68,0.22-1.3,0.6-1.8l-1.41-1.77c-1.35,0.75-3.01,0.76-4.37,0L8.4,18.2z\"/>',
  bookmark: '<path d=\"M17 3H7c-1.1 0-2 .9-2 2v16l7-3 7 3V5c0-1.1-.9-2-2-2z\"/>',
  providerlink: '<path d=\"M12.6 18.06c-.36.28-.87.28-1.23 0l-6.15-4.78c-.36-.28-.86-.28-1.22 0-.51.4-.51 1.17 0 1.57l6.76 5.26c.72.56 1.73.56 2.46 0l6.76-5.26c.51-.4.51-1.17 0-1.57l-.01-.01c-.36-.28-.86-.28-1.22 0l-6.15 4.79zm.63-3.02l6.76-5.26c.51-.4.51-1.18 0-1.58l-6.76-5.26c-.72-.56-1.73-.56-2.46 0L4.01 8.21c-.51.4-.51 1.18 0 1.58l6.76 5.26c.72.56 1.74.56 2.46-.01z\"/>',
  usage: '<path d=\"M6,20L6,20c1.1,0,2-0.9,2-2v-7c0-1.1-0.9-2-2-2h0c-1.1,0-2,0.9-2,2v7C4,19.1,4.9,20,6,20z\"/><path d=\"M16,15v3c0,1.1,0.9,2,2,2h0c1.1,0,2-0.9,2-2v-3c0-1.1-0.9-2-2-2h0C16.9,13,16,13.9,16,15z\"/><path d=\"M12,20L12,20c1.1,0,2-0.9,2-2V6c0-1.1-0.9-2-2-2h0c-1.1,0-2,0.9-2,2v12C10,19.1,10.9,20,12,20z\"/>',
  menu: '<path d=\"M5,11h4c1.1,0,2-0.9,2-2V5c0-1.1-0.9-2-2-2H5C3.9,3,3,3.9,3,5v4C3,10.1,3.9,11,5,11z\"/><path d=\"M5,21h4c1.1,0,2-0.9,2-2v-4c0-1.1-0.9-2-2-2H5c-1.1,0-2,0.9-2,2v4C3,20.1,3.9,21,5,21z\"/><path d=\"M13,5v4c0,1.1,0.9,2,2,2h4c1.1,0,2-0.9,2-2V5c0-1.1-0.9-2-2-2h-4C13.9,3,13,3.9,13,5z\"/><path d=\"M15,21h4c1.1,0,2-0.9,2-2v-4c0-1.1-0.9-2-2-2h-4c-1.1,0-2,0.9-2,2v4C13,20.1,13.9,21,15,21z\"/>',
  docs: '<path d=\"M19,3H5C3.9,3,3,3.9,3,5v14c0,1.1,0.9,2,2,2h14c1.1,0,2-0.9,2-2V5C21,3.9,20.1,3,19,3z M13,17H8c-0.55,0-1-0.45-1-1 c0-0.55,0.45-1,1-1h5c0.55,0,1,0.45,1,1C14,16.55,13.55,17,13,17z M16,13H8c-0.55,0-1-0.45-1-1c0-0.55,0.45-1,1-1h8 c0.55,0,1,0.45,1,1C17,12.55,16.55,13,16,13z M16,9H8C7.45,9,7,8.55,7,8c0-0.55,0.45-1,1-1h8c0.55,0,1,0.45,1,1 C17,8.55,16.55,9,16,9z\"/>',
  workspace: '<path d=\"M17,11h3c1.11,0,2-0.9,2-2V5c0-1.11-0.9-2-2-2h-3c-1.11,0-2,0.9-2,2v1H9.01V5c0-1.11-0.9-2-2-2H4C2.9,3,2,3.9,2,5v4 c0,1.11,0.9,2,2,2h3c1.11,0,2-0.9,2-2V8H11v7.01c0,1.65,1.34,2.99,2.99,2.99H15v1c0,1.11,0.9,2,2,2h3c1.11,0,2-0.9,2-2v-4 c0-1.11-0.9-2-2-2h-3c-1.11,0-2,0.9-2,2v1h-1.01C13.45,16,13,15.55,13,15.01V8h2v1C15,10.1,15.9,11,17,11z\"/>',
  media: '<path d=\"M22 16V4c0-1.1-.9-2-2-2H8c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2zm-10.6-3.47l1.63 2.18 2.58-3.22c.2-.25.58-.25.78 0l2.96 3.7c.26.33.03.81-.39.81H9c-.41 0-.65-.47-.4-.8l2-2.67c.2-.26.6-.26.8 0zM2 7v13c0 1.1.9 2 2 2h13c.55 0 1-.45 1-1s-.45-1-1-1H5c-.55 0-1-.45-1-1V7c0-.55-.45-1-1-1s-1 .45-1 1z\"/>',
  spark: '<path d=\"M19.46,8l0.79-1.75L22,5.46c0.39-0.18,0.39-0.73,0-0.91l-1.75-0.79L19.46,2c-0.18-0.39-0.73-0.39-0.91,0l-0.79,1.75 L16,4.54c-0.39,0.18-0.39,0.73,0,0.91l1.75,0.79L18.54,8C18.72,8.39,19.28,8.39,19.46,8z M11.5,9.5L9.91,6 C9.56,5.22,8.44,5.22,8.09,6L6.5,9.5L3,11.09c-0.78,0.36-0.78,1.47,0,1.82l3.5,1.59L8.09,18c0.36,0.78,1.47,0.78,1.82,0l1.59-3.5 l3.5-1.59c0.78-0.36,0.78-1.47,0-1.82L11.5,9.5z M18.54,16l-0.79,1.75L16,18.54c-0.39,0.18-0.39,0.73,0,0.91l1.75,0.79L18.54,22 c0.18,0.39,0.73,0.39,0.91,0l0.79-1.75L22,19.46c0.39-0.18,0.39-0.73,0-0.91l-1.75-0.79L19.46,16 C19.28,15.61,18.72,15.61,18.54,16z\"/>',
  terminal: '<path d=\"M20,4H4C2.89,4,2,4.9,2,6v12c0,1.1,0.89,2,2,2h16c1.1,0,2-0.9,2-2V6C22,4.9,21.11,4,20,4z M20,18H4V8h16V18z M12,16 c0-0.55,0.45-1,1-1h4c0.55,0,1,0.45,1,1c0,0.55-0.45,1-1,1h-4C12.45,17,12,16.55,12,16z M6.79,9.71c0.39-0.39,1.02-0.39,1.41,0 l2.59,2.59c0.39,0.39,0.39,1.02,0,1.41l-2.59,2.59c-0.39,0.39-1.02,0.39-1.41,0c-0.39-0.39-0.39-1.02,0-1.41L8.67,13l-1.88-1.88 C6.4,10.73,6.4,10.1,6.79,9.71z\"/>',
  link: '<path d=\"M17,7h-3c-0.55,0-1,0.45-1,1s0.45,1,1,1h3c1.65,0,3,1.35,3,3s-1.35,3-3,3h-3c-0.55,0-1,0.45-1,1c0,0.55,0.45,1,1,1h3 c2.76,0,5-2.24,5-5S19.76,7,17,7z M8,12c0,0.55,0.45,1,1,1h6c0.55,0,1-0.45,1-1s-0.45-1-1-1H9C8.45,11,8,11.45,8,12z M10,15H7 c-1.65,0-3-1.35-3-3s1.35-3,3-3h3c0.55,0,1-0.45,1-1s-0.45-1-1-1H7c-2.76,0-5,2.24-5,5s2.24,5,5,5h3c0.55,0,1-0.45,1-1 C11,15.45,10.55,15,10,15z\"/>',
  check: '<path d=\"M21.29,5.89l-10,10c-0.39,0.39-1.02,0.39-1.41,0l-2.83-2.83c-0.39-0.39-0.39-1.02,0-1.41l0,0c0.39-0.39,1.02-0.39,1.41,0 l2.12,2.12l9.29-9.29c0.39-0.39,1.02-0.39,1.41,0l0,0C21.68,4.87,21.68,5.5,21.29,5.89z M15.77,2.74c-1.69-0.69-3.61-0.93-5.61-0.57 C6.09,2.9,2.84,6.18,2.15,10.25C1.01,17,6.63,22.78,13.34,21.91c3.96-0.51,7.28-3.46,8.32-7.31c0.4-1.47,0.44-2.89,0.21-4.22 c-0.13-0.8-1.12-1.11-1.7-0.54v0c-0.23,0.23-0.33,0.57-0.27,0.89c0.22,1.33,0.12,2.75-0.52,4.26c-1.16,2.71-3.68,4.7-6.61,4.97 c-5.1,0.47-9.33-3.85-8.7-8.98c0.43-3.54,3.28-6.42,6.81-6.91c1.73-0.24,3.37,0.09,4.77,0.81c0.39,0.2,0.86,0.13,1.17-0.18l0,0 c0.48-0.48,0.36-1.29-0.24-1.6C16.31,2.98,16.04,2.85,15.77,2.74z\"/>',
  agents: '<path d=\"M16 11c1.66 0 2.99-1.34 2.99-3S17.66 5 16 5s-3 1.34-3 3 1.34 3 3 3zm-8 0c1.66 0 2.99-1.34 2.99-3S9.66 5 8 5 5 6.34 5 8s1.34 3 3 3zm0 2c-2.33 0-7 1.17-7 3.5V18c0 .55.45 1 1 1h12c.55 0 1-.45 1-1v-1.5c0-2.33-4.67-3.5-7-3.5zm8 0c-.29 0-.62.02-.97.05.02.01.03.03.04.04 1.14.83 1.93 1.94 1.93 3.41V18c0 .35-.07.69-.18 1H22c.55 0 1-.45 1-1v-1.5c0-2.33-4.67-3.5-7-3.5z\"/>',
  power: '<path d=\"M10.67,21L10.67,21c-0.35,0-0.62-0.31-0.57-0.66L11,14H7.5c-0.88,0-0.33-0.75-0.31-0.78c1.26-2.23,3.15-5.53,5.65-9.93 c0.1-0.18,0.3-0.29,0.5-0.29h0c0.35,0,0.62,0.31,0.57,0.66L13.01,10h3.51c0.4,0,0.62,0.19,0.4,0.66c-3.29,5.74-5.2,9.09-5.75,10.05 C11.07,20.89,10.88,21,10.67,21z\"/>',
  search: '<path d=\"M15.5 14h-.79l-.28-.27c1.2-1.4 1.82-3.31 1.48-5.34-.47-2.78-2.79-5-5.59-5.34-4.23-.52-7.79 3.04-7.27 7.27.34 2.8 2.56 5.12 5.34 5.59 2.03.34 3.94-.28 5.34-1.48l.27.28v.79l4.25 4.25c.41.41 1.08.41 1.49 0 .41-.41.41-1.08 0-1.49L15.5 14zm-6 0C7.01 14 5 11.99 5 9.5S7.01 5 9.5 5 14 7.01 14 9.5 11.99 14 9.5 14z\"/>',
  settings: '<path d=\"M19.5,12c0-0.23-0.01-0.45-0.03-0.68l1.86-1.41c0.4-0.3,0.51-0.86,0.26-1.3l-1.87-3.23c-0.25-0.44-0.79-0.62-1.25-0.42 l-2.15,0.91c-0.37-0.26-0.76-0.49-1.17-0.68l-0.29-2.31C14.8,2.38,14.37,2,13.87,2h-3.73C9.63,2,9.2,2.38,9.14,2.88L8.85,5.19 c-0.41,0.19-0.8,0.42-1.17,0.68L5.53,4.96c-0.46-0.2-1-0.02-1.25,0.42L2.41,8.62c-0.25,0.44-0.14,0.99,0.26,1.3l1.86,1.41 C4.51,11.55,4.5,11.77,4.5,12s0.01,0.45,0.03,0.68l-1.86,1.41c-0.4,0.3-0.51,0.86-0.26,1.3l1.87,3.23c0.25,0.44,0.79,0.62,1.25,0.42 l2.15-0.91c0.37,0.26,0.76,0.49,1.17,0.68l0.29,2.31C9.2,21.62,9.63,22,10.13,22h3.73c0.5,0,0.93-0.38,0.99-0.88l0.29-2.31 c0.41-0.19,0.8-0.42,1.17-0.68l2.15,0.91c0.46,0.2,1,0.02,1.25-0.42l1.87-3.23c0.25-0.44,0.14-0.99-0.26-1.3l-1.86-1.41 C19.49,12.45,19.5,12.23,19.5,12z M12.04,15.5c-1.93,0-3.5-1.57-3.5-3.5s1.57-3.5,3.5-3.5s3.5,1.57,3.5,3.5S13.97,15.5,12.04,15.5z\"/>',
  sun: '<path d=\"M12,7c-2.76,0-5,2.24-5,5s2.24,5,5,5s5-2.24,5-5S14.76,7,12,7L12,7z M2,13l2,0c0.55,0,1-0.45,1-1s-0.45-1-1-1l-2,0 c-0.55,0-1,0.45-1,1S1.45,13,2,13z M20,13l2,0c0.55,0,1-0.45,1-1s-0.45-1-1-1l-2,0c-0.55,0-1,0.45-1,1S19.45,13,20,13z M11,2v2 c0,0.55,0.45,1,1,1s1-0.45,1-1V2c0-0.55-0.45-1-1-1S11,1.45,11,2z M11,20v2c0,0.55,0.45,1,1,1s1-0.45,1-1v-2c0-0.55-0.45-1-1-1 C11.45,19,11,19.45,11,20z M5.99,4.58c-0.39-0.39-1.03-0.39-1.41,0c-0.39,0.39-0.39,1.03,0,1.41l1.06,1.06 c0.39,0.39,1.03,0.39,1.41,0s0.39-1.03,0-1.41L5.99,4.58z M18.36,16.95c-0.39-0.39-1.03-0.39-1.41,0c-0.39,0.39-0.39,1.03,0,1.41 l1.06,1.06c0.39,0.39,1.03,0.39,1.41,0c0.39-0.39,0.39-1.03,0-1.41L18.36,16.95z M19.42,5.99c0.39-0.39,0.39-1.03,0-1.41 c-0.39-0.39-1.03-0.39-1.41,0l-1.06,1.06c-0.39,0.39-0.39,1.03,0,1.41s1.03,0.39,1.41,0L19.42,5.99z M7.05,18.36 c0.39-0.39,0.39-1.03,0-1.41c-0.39-0.39-1.03-0.39-1.41,0l-1.06,1.06c-0.39,0.39-0.39,1.03,0,1.41s1.03,0.39,1.41,0L7.05,18.36z\"/>',
  send: '<path d=\"M3.4 20.4l17.45-7.48c.81-.35.81-1.49 0-1.84L3.4 3.6c-.66-.29-1.39.2-1.39.91L2 9.12c0 .5.37.93.87.99L17 12 2.87 13.88c-.5.07-.87.5-.87 1l.01 4.61c0 .71.73 1.2 1.39.91z\"/>',
  plus: '<path d=\"M18 13h-5v5c0 .55-.45 1-1 1s-1-.45-1-1v-5H6c-.55 0-1-.45-1-1s.45-1 1-1h5V6c0-.55.45-1 1-1s1 .45 1 1v5h5c.55 0 1 .45 1 1s-.45 1-1 1z\"/>',
  pencil: '<path d=\"M3 17.46v3.04c0 .28.22.5.5.5h3.04c.13 0 .26-.05.35-.15L17.81 9.94l-3.75-3.75L3.15 17.1c-.1.1-.15.22-.15.36zM20.71 7.04c.39-.39.39-1.02 0-1.41l-2.34-2.34c-.39-.39-1.02-.39-1.41 0l-1.83 1.83 3.75 3.75 1.83-1.83z\"/>',
  library: '<path d=\"M3 6c-.55 0-1 .45-1 1v13c0 1.1.9 2 2 2h13c.55 0 1-.45 1-1s-.45-1-1-1H5c-.55 0-1-.45-1-1V7c0-.55-.45-1-1-1zm17-4H8c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zm-2 9h-8c-.55 0-1-.45-1-1s.45-1 1-1h8c.55 0 1 .45 1 1s-.45 1-1 1zm-4 4h-4c-.55 0-1-.45-1-1s.45-1 1-1h4c.55 0 1 .45 1 1s-.45 1-1 1zm4-8h-8c-.55 0-1-.45-1-1s.45-1 1-1h8c.55 0 1 .45 1 1s-.45 1-1 1z\"/>',
  build: '<path d=\"M12.09 2.91C10.08.9 7.07.49 4.65 1.67L8.28 5.3c.39.39.39 1.02 0 1.41L6.69 8.3c-.39.4-1.02.4-1.41 0L1.65 4.67C.48 7.1.89 10.09 2.9 12.1c1.86 1.86 4.58 2.35 6.89 1.48l7.96 7.96c1.03 1.03 2.69 1.03 3.71 0 1.03-1.03 1.03-2.69 0-3.71L13.54 9.9c.92-2.34.44-5.1-1.45-6.99z\"/>',
  memory: '<path d=\"M14 9h-4c-.55 0-1 .45-1 1v4c0 .55.45 1 1 1h4c.55 0 1-.45 1-1v-4c0-.55-.45-1-1-1zm-1 4h-2v-2h2v2zm8-3c0-.55-.45-1-1-1h-1V7c0-1.1-.9-2-2-2h-2V4c0-.55-.45-1-1-1s-1 .45-1 1v1h-2V4c0-.55-.45-1-1-1s-1 .45-1 1v1H7c-1.1 0-2 .9-2 2v2H4c-.55 0-1 .45-1 1s.45 1 1 1h1v2H4c-.55 0-1 .45-1 1s.45 1 1 1h1v2c0 1.1.9 2 2 2h2v1c0 .55.45 1 1 1s1-.45 1-1v-1h2v1c0 .55.45 1 1 1s1-.45 1-1v-1h2c1.1 0 2-.9 2-2v-2h1c.55 0 1-.45 1-1s-.45-1-1-1h-1v-2h1c.55 0 1-.45 1-1zm-5 7H8c-.55 0-1-.45-1-1V8c0-.55.45-1 1-1h8c.55 0 1 .45 1 1v8c0 .55-.45 1-1 1z\"/>',
  activity: '<path d=\"M19.88,18.47c0.48-0.77,0.75-1.67,0.69-2.66c-0.13-2.15-1.84-3.97-3.97-4.2c-2.72-0.3-5.02,1.81-5.02,4.47 c0,2.49,2.01,4.5,4.49,4.5c0.88,0,1.7-0.26,2.39-0.7l2.41,2.41c0.39,0.39,1.03,0.39,1.42,0v0c0.39-0.39,0.39-1.03,0-1.42 L19.88,18.47z M16.08,18.58c-1.38,0-2.5-1.12-2.5-2.5c0-1.38,1.12-2.5,2.5-2.5s2.5,1.12,2.5,2.5 C18.58,17.46,17.46,18.58,16.08,18.58z M15.72,10.08c-0.74,0.02-1.45,0.18-2.1,0.45l-0.55-0.83l-3.08,5.01 c-0.36,0.58-1.17,0.64-1.61,0.13l-2.12-2.47l-3.06,4.9c-0.31,0.49-0.97,0.62-1.44,0.28l0,0c-0.42-0.31-0.54-0.89-0.26-1.34 l3.78-6.05c0.36-0.57,1.17-0.63,1.61-0.12L9,12.5l3.18-5.17c0.38-0.62,1.28-0.64,1.68-0.03L15.72,10.08z M18.31,10.58 c-0.64-0.28-1.33-0.45-2.05-0.49L20.8,2.9c0.31-0.49,0.97-0.61,1.43-0.27l0,0c0.43,0.31,0.54,0.9,0.26,1.34L18.31,10.58z\"/>',
  more: '<path d=\"M6 10c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2zm12 0c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2zm-6 0c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2z\"/>',
};
/* Per-icon optical scale: Material glyphs ship with uneven internal padding,
   so each one is scaled to fill its tile evenly (smooth, not harsh). */
const HOME_ICON_SCALE = {
  chat: 1.0, clock: 1.0, workspace: 1.0, agents: 1.0, send: 1.0, search: 1.0,
  settings: 1.0, pencil: 1.0, build: 1.0, library: 1.0, memory: 1.0, spark: 1.0,
  power: 1.0, sun: 1.0, bookmark: 1.0, link: 1.0, plus: 1.0, media: 1.0,
  gateway: 0.88, providerlink: 1.12, usage: 1.16, menu: 1.08, more: 1.08,
  code: 1.22, docs: 1.06, terminal: 1.1, check: 1.0, activity: 1.0,
};
function homeShortcutIcon(name) {
  const paths = HOME_SHORTCUT_PATHS[name] || HOME_SHORTCUT_PATHS.menu;
  const k = HOME_ICON_SCALE[name] || 1;
  const inner = k === 1 ? paths : `<g transform="translate(12 12) scale(${k}) translate(-12 -12)">${paths}</g>`;
  return `<svg class="home-shortcut-icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false" xmlns="http://www.w3.org/2000/svg">${inner}</svg>`;
}

function renderHomeGrid() {
  const grid = $('hubGrid');
  if (!grid) return;
  const agent = S.agents[0] || null;
  const rooms = agent ? S.sessions.filter(s => s.agent_id === agent.id && !isGeneralSession(s)) : [];
  const countFor = kind => rooms.filter(s => workspaceKindOf(s) === kind).length;
  /* Home exposes two clean rows:
     row 1 — four first-class chat workspaces;
     row 2 — system surfaces (Gateway, Provider, Usage, More). */
  const defs = [
    { key: 'session',  icon: 'chat',      label: 'Sessions',  tone: 'violet', badge: countFor('session')  },
    { key: 'project',  icon: 'code',      label: 'Projects',  tone: 'green',  badge: countFor('project')  },
    { key: 'cronjob',  icon: 'clock',     label: 'Cronjobs',  tone: 'amber',  badge: countFor('cronjob')  },
    { key: 'workflow', icon: 'workspace', label: 'Workflows', tone: 'cyan',   badge: countFor('workflow') },
    { key: 'gateway',   icon: 'gateway',      label: 'Gateway',   tone: 'indigo'                            },
    { key: 'providers', icon: 'providerlink', label: 'Providers', tone: 'blue',   page: 'providers'         },
    { key: 'usage',     icon: 'usage',        label: 'Usage',     tone: 'pink',   page: 'usage'             },
    { key: 'more',      icon: 'menu',         label: 'More',      tone: 'slate'                             },
  ];
  const markup = defs.map(d => `
    <button class="hub-sc${d.page ? ' hub-sc-nav' : ''}" data-hub-sc="${d.key}" type="button" aria-label="${d.label}${d.page ? ' navigation' : ''}">
      <span class="hub-sc-ic hub-tone-${d.tone}${d.brand ? ' hub-sc-brand' : ''}">${d.brand ? hubProviderLogo(agent) : homeShortcutIcon(d.icon)}${d.badge ? `<em class="hub-sc-badge${d.badge > 9 ? ' is-wide' : ''}">${d.badge > 99 ? '99+' : d.badge}</em>` : ''}</span>
      <span class="hub-sc-label">${d.label}</span>
    </button>`).join('');
  if (grid.dataset.hubSig !== markup) {
    grid.dataset.hubSig = markup;
    grid.innerHTML = markup;
  }
  grid.onclick = event => {
    const btn = event.target.closest('[data-hub-sc]');
    if (!btn) return;
    const act = btn.dataset.hubSc;
    // Each workspace tile has its own list/create surface, not a combined menu.
    if (act === 'session')  return openWorkspace('session');
    if (act === 'project')  return openWorkspace('project');
    if (act === 'cronjob')  return openWorkspace('cronjob');
    if (act === 'workflow') return openWorkspace('workflow');
    // Reuse the exact page router used by the old bottom dock/sidebar.
    if (act === 'providers' || act === 'usage') return go(act);
    if (act === 'gateway') {
      if (!agent) return toast('No agent linked yet', 'warn');
      return showGatewayDetail(agent);
    }
    if (act === 'more') return openMoreMenu();
  };
}

/* HOME HUB — DeepSeek-style landing: hero + ask-composer + circular shortcut
   grid. Secondary status hosts remain available to older routes, while the
   landing itself finishes after the grid and Workspace owns its room lists. */
function renderHomeHub() {
  renderHomeHero();
  renderHomeGrid();
  const agent = S.agents[0] || null;
  const connection = agent ? agentConnectionPresentation(agent) : { label: 'Unconnected', tone: 'red' };
  const model = hubModelPresentation(agent?.model || '');
  const rooms = agent
    ? S.sessions.filter(session => session.agent_id === agent.id)
        .sort((a, b) => String(b.updated_at || '').localeCompare(String(a.updated_at || '')))
    : [];
  const workspaceRooms = rooms.filter(room => !isGeneralSession(room));
  const general = agent ? generalSessionForAgent(agent.id) : null;
  const dmTyping = agent && agentLiveActivity.has(agent.id);
  const dmPreview = dmTyping ? 'Typing...' : String(general?.last_preview || '')
    .replace(/\s+/g, ' ').trim() || 'Start a conversation with Zeline';
  const dmUpdatedAt = general?.updated_at || '';
  const dmUnread = agent ? agentUnreadCount(agent.id) : 0;

  // Top row: Gateway status card + Environment card (equal halves), then the
  // Docs + GitHub 1:1 icon buttons on the right.
  const top = $('hubTop');
  if (top) {
    // Health check state (S.hc): each node is 'unknown' | 'checking' | 'ok' | 'down'.
    const hc = (S.hc = S.hc || {});
    // Left card (102px) = INTERFACE (ZEROLINEAR ↔ gateway connection).
    // Middle card (flex) = GATEWAY (Zeline Agentic AI runtime on the host).
    const iface = interfaceStatus();
    const gw = gatewayRunStatus();
    const topMarkup = `
      <button class="hub-status-card hub-status-gateway tone-${esc(iface.tone)}" data-hub-action="interface" type="button">
        <span class="hub-status-copy">
          <span class="hub-status-kicker">INTERFACE</span>
          <span class="hub-status-label">ZEROLINEAR</span>
          <span class="hub-status-sub">${esc(iface.label)}</span>
        </span>
        <span class="hub-reference-chevron">${ZI('chevron')}</span>
      </button>
      <button class="hub-status-card hub-status-env tone-${esc(gw.tone)}" data-hub-action="gateway" type="button">
        <span class="hub-status-copy">
          <span class="hub-status-kicker">GATEWAY</span>
          <span class="hub-status-label">Zeline Agentic AI</span>
          <span class="hub-status-sub">${esc(gw.label)}</span>
        </span>
        <span class="hub-reference-chevron">${ZI('chevron')}</span>
      </button>
      <div class="hub-top-links">
        <a class="hub-link-card" href="https://github.com/Mftrferdinand/Zerolinear#readme" target="_blank" rel="noopener" aria-label="Docs">${hubReferenceIcon('docs')}</a>
        <a class="hub-link-card hub-link-github" href="https://github.com/Mftrferdinand/Zerolinear" target="_blank" rel="noopener" aria-label="GitHub">${hubReferenceIcon('github')}</a>
      </div>`;
    // Rebuild only when the content actually changed; handlers are re-wired
    // every pass so they always close over the freshest agent. Keeping the
    // DOM stable is what makes category switches flicker-free.
    if (top.dataset.hubSig !== topMarkup) {
      top.dataset.hubSig = topMarkup;
      top.innerHTML = topMarkup;
    }
    top.onclick = event => {
      const action = event.target.closest('[data-hub-action]')?.dataset.hubAction;
      if (!action) return;
      if (!agent) return toast('No agent linked yet', 'warn');
      if (action === 'gateway') showGatewayDetail(agent);
      else if (action === 'interface') showInterfaceStatus(agent);
    };
    // /system is fetched ONCE at boot (non-blocking, see boot()) and cached in
    // S.system. The hub never fires its own async fetch here — a late-resolving
    // promise re-rendering mid-interaction was what caused the first-refresh jolt.
  }

  // Long full-width MODELS card.
  const modelsHost = $('hubModels');
  if (modelsHost) {
    const modelsMarkup = `
      <button class="hub-models-slot" data-hub-action="recheck-status" type="button" aria-label="Refresh / recheck status" title="Recheck status">${ZI('restart')}</button>
      <button class="hub-models-card hub-status-model" data-hub-action="model" type="button">
        <span class="hub-models-logo">${hubProviderLogo(agent)}</span>
        <span class="hub-models-copy">
          <span class="hub-status-kicker">MODEL</span>
          <strong class="hub-model-name">${esc(model.name)}</strong>
        </span>
        <span class="hub-reference-chevron hub-models-menu-icon">${ZI('chevron')}</span>
      </button>`;
    if (modelsHost.dataset.hubSig !== modelsMarkup) {
      modelsHost.dataset.hubSig = modelsMarkup;
      modelsHost.innerHTML = modelsMarkup;
    }
    const slotBtn = modelsHost.querySelector('.hub-models-slot');
    if (slotBtn) {
      if (S.gatewayRestarting) slotBtn.classList.add('is-spinning');
      slotBtn.onclick = () => recheckHealth(slotBtn);
    }
    modelsHost.querySelector('.hub-models-card').onclick = () => {
      if (!agent) return toast('No agent linked yet', 'warn');
      S.agentId = agent.id; openModelPicker();
    };
  }

  // Agent DM card (full-width): last-chat preview + unread badge only.
  const chatHost = $('hubChat');
  if (chatHost) {
    const markup = `
      <button class="hub-dm-card" type="button">
        <span class="hub-dm-copy">
          <span class="hub-dm-preview${dmTyping ? ' typing' : ''}">${dmTyping ? 'Typing…' : agentPreviewMarkup(dmPreview)}</span>
        </span>
        <span class="hub-dm-meta">
          ${dmUnread ? `<span class="hub-dm-unread${dmUnread > 9 ? ' is-wide' : ''}" aria-label="${dmUnread} unread">${dmUnread > 99 ? '99+' : dmUnread}</span>` : ''}
        </span>
      </button>`;
    // Rebuild only when the visible copy changed (preview/unread).
    if (chatHost.dataset.hubSig !== markup) {
      chatHost.dataset.hubSig = markup;
      chatHost.innerHTML = markup;
    }
    chatHost.querySelector('.hub-dm-card').onclick = () => {
      agent ? openAgentChat(agent) : toast('No agent linked yet', 'warn');
    };
  }

  // Session, Project, and Cron Job moved into the dedicated Workspace menu.
  // Keep this host empty so the landing finishes cleanly after the 2 × 4 grid.
  const trio = $('hubTrio');
  if (trio) {
    if (trio.childElementCount) trio.replaceChildren();
  }

  // The header + button was moved into the circular home grid ("New" tile).
  // openHomeAddSheet() below owns the create flow now.

  // n8n-style flow connectors between the hub cards. Wire the resize recompute
  // once; the path itself is recomputed from live geometry on every render.
  if (!window.__hubConnResize) {
    window.__hubConnResize = true;
    window.addEventListener('resize', () => requestAnimationFrame(renderHubConnectors));
  }
  requestAnimationFrame(renderHubConnectors);
}

/* Draw the n8n-like connector flow over the hub:
   GitHub → Docs → Gateway → Models → Agent chat → Session.
   An absolutely-positioned SVG overlay (pointer-events:none) whose paths are
   recomputed from each card's live bounding box, so it stays correct on resize.
   Lines live in the gaps between cards; endpoint dots read as node ports. */
function hubAnchorPoint(rect, side, origin) {
  let x = (rect.left + rect.right) / 2;
  let y = (rect.top + rect.bottom) / 2;
  if (side === 'left') x = rect.left;
  else if (side === 'right') x = rect.right;
  else if (side === 'top') y = rect.top;
  else if (side === 'bottom') y = rect.bottom;
  return { x: x - origin.left, y: y - origin.top };
}

function renderHubConnectors() {
  const hub = $('homeHub');
  if (!hub || hub.hasAttribute('hidden') || !hub.offsetParent) return;
  let svg = $('hubConnectors');
  if (!svg) {
    svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('id', 'hubConnectors');
    svg.setAttribute('class', 'hub-connectors');
    svg.setAttribute('aria-hidden', 'true');
    hub.insertBefore(svg, hub.firstChild);
  }
  const q = sel => hub.querySelector(sel);
  const nodes = {
    github: q('.hub-link-github'),
    docs: q('.hub-link-card:not(.hub-link-github)'),
    gateway: q('.hub-status-gateway'),
    environment: q('.hub-status-env'),
    slot: q('.hub-models-slot'),
    models: q('.hub-models-card'),
    chat: q('.hub-dm-card'),
    session: q('.hub-workspace-panel[data-hub-card="workspace"]'),
  };
  if (Object.values(nodes).some(n => !n)) {
    svg.innerHTML = '';
    svg.__wires = null; svg.__group = null;   // dropped nodes must not be reused
    return;
  }

  const origin = hub.getBoundingClientRect();
  const W = Math.round(origin.width);
  const H = Math.round(hub.scrollHeight);
  svg.setAttribute('width', W);
  svg.setAttribute('height', H);
  svg.setAttribute('viewBox', `0 0 ${W} ${H}`);

  const r = {};
  for (const k in nodes) r[k] = nodes[k].getBoundingClientRect();
  // Ordered flow: GitHub → Docs → Environment → Models → Agent chat → Session,
  // plus a Gateway → Environment tap-in and a Gateway → placeholder-slot drop
  // (the 1:1 empty card sits directly under the Gateway card). 'h' = A sits to
  // the right of B (line runs leftward across the top row); 'v' = A sits above B
  // (drops down the stacked cards).
  const links = [
    ['github', 'docs', 'h'],          // GitHub (rightmost) → Docs
    ['docs', 'environment', 'h'],     // Docs → Environment
    ['environment', 'gateway', 'h'],  // Gateway → Environment (adjacent tap-in)
    ['gateway', 'slot', 'u'],         // Gateway → empty slot: straight vertical line up
    ['gateway', 'models', 'l'],       // Gateway → Models LEFT edge (the red dot)
    ['models', 'chat', 'v'],          // Models → Agent chat (vertical drop)
    ['chat', 'session', 'v'],         // Agent chat → Session
  ];

  // Orthogonal (right-angle) routing: instead of a free 360° bezier, every link
  // is a polyline of horizontal + vertical segments so it only ever turns at 90°.
  // Corners are lightly rounded for a clean n8n look, but the paths never slant.
  const R = 7; // corner radius
  const orthoPath = pts => {
    // Collapse duplicate/near-duplicate consecutive points.
    const p = [];
    for (const pt of pts) {
      const last = p[p.length - 1];
      if (!last || Math.abs(last.x - pt.x) > 0.5 || Math.abs(last.y - pt.y) > 0.5) p.push(pt);
    }
    if (p.length < 2) return '';
    let d = `M${p[0].x} ${p[0].y}`;
    for (let i = 1; i < p.length - 1; i++) {
      const prev = p[i - 1], cur = p[i], next = p[i + 1];
      const d1 = Math.hypot(cur.x - prev.x, cur.y - prev.y);
      const d2 = Math.hypot(next.x - cur.x, next.y - cur.y);
      const r = Math.min(R, d1 / 2, d2 / 2);
      const a = { x: cur.x - (cur.x - prev.x) / (d1 || 1) * r, y: cur.y - (cur.y - prev.y) / (d1 || 1) * r };
      const b = { x: cur.x + (next.x - cur.x) / (d2 || 1) * r, y: cur.y + (next.y - cur.y) / (d2 || 1) * r };
      d += ` L${a.x} ${a.y} Q${cur.x} ${cur.y} ${b.x} ${b.y}`;
    }
    const end = p[p.length - 1];
    d += ` L${end.x} ${end.y}`;
    return d;
  };

  let paths = '';
  const linkStates = [];
  // Per-node health. Source of truth is S.hc (set by the health-check runner):
  //   'unknown'  → not checked yet / not configured  → neutral gray, NEVER auto-red
  //   'checking' → probe in flight                    → white-gray "checking"
  //   'ok'       → passed its check                    → green
  //   'down'     → expected up but unreachable/failed  → red
  // GitHub & Docs are static links (always reachable) → always ok.
  const agent = S.agents[0] || null;
  const hc = (S.hc = S.hc || {});
  const st = k => hc[k] || 'unknown';
  const health = {
    github: st('github'),
    docs: st('docs'),
    gateway: st('gateway'),
    environment: st('environment'),
    slot: 'unknown',                 // the recheck button itself is neutral
    models: st('models'),
    chat: st('chat'),
    session: st('session'),
  };
  // Map a per-node state to a CSS edge class. Unknown/idle → no colour class.
  const cls = s => s === 'ok' ? 'ok' : s === 'down' ? 'down' : s === 'checking' ? 'check' : 'idle';
  // A connection line's colour: red if EITHER end is down; green only if BOTH
  // ends are ok; checking if either is checking; otherwise idle/gray. This keeps
  // a single failure local — the rest of the graph is not dragged red.
  const wireState = (x, y) => {
    if (x === 'down' || y === 'down') return 'down';
    if (x === 'checking' || y === 'checking') return 'check';
    if (x === 'ok' && y === 'ok') return 'ok';
    return 'idle';
  };
  // Paint each card edge from its own state.
  for (const k in nodes) {
    if (nodes[k]) { nodes[k].dataset.health = cls(health[k]); }
  }
  for (const [index, [a, b, dir]] of links.entries()) {
    let pts;
    if (dir === 'h') {
      // Across the top row: A sits to the right of B. Leave A's left edge, enter
      // B's right edge, with a vertical step midway if the rows differ.
      const p1 = hubAnchorPoint(r[a], 'left', origin);
      const p2 = hubAnchorPoint(r[b], 'right', origin);
      const midX = (p1.x + p2.x) / 2;
      pts = [p1, { x: midX, y: p1.y }, { x: midX, y: p2.y }, p2];
    } else if (dir === 'l') {
      // Enter the target's LEFT-middle edge (the red dot). Leave the source from
      // the edge that faces the target, run vertically to the target's row, then
      // one horizontal segment straight into the left edge.
      const p2 = hubAnchorPoint(r[b], 'left', origin);
      const srcAbove = (r[a].top + r[a].bottom) / 2 < (r[b].top + r[b].bottom) / 2;
      const p1 = hubAnchorPoint(r[a], srcAbove ? 'bottom' : 'top', origin);
      pts = [p1, { x: p1.x, y: p2.y }, p2];
    } else if (dir === 'u') {
      // Straight vertical line: slot's top-centre up to the card above, entering
      // that card's bottom edge at the SAME x (not centred on the gateway).
      const p1 = hubAnchorPoint(r[b], 'top', origin);     // b = slot (below)
      const p2 = { x: p1.x, y: hubAnchorPoint(r[a], 'bottom', origin).y };
      pts = [p1, p2];
    } else {
      // Vertical drop A → B with a horizontal step if their centres differ.
      const p1 = hubAnchorPoint(r[a], 'bottom', origin);
      const p2 = hubAnchorPoint(r[b], 'top', origin);
      const midY = (p1.y + p2.y) / 2;
      pts = [p1, { x: p1.x, y: midY }, { x: p2.x, y: midY }, p2];
    }
    // The 'u' wire feeds the neutral restart button — keep it idle.
    const ws = dir === 'u' ? 'idle' : wireState(health[a], health[b]);
    linkStates.push({ a, b, dir, d: orthoPath(pts), cls: cls(ws) });
  }
  // In-place wire update: build the <path> nodes ONCE (keyed by link), then only
  // swap their class/d attributes on later renders. Rebuilding svg.innerHTML on
  // every health step is what made the lines flicker/replay — this kills it.
  if (!svg.__wires) {
    svg.innerHTML = '<g class="hub-conn-lines"></g>';
    svg.__wires = [];
    svg.__group = svg.firstChild;
  }
  const group = svg.__group;
  while (svg.__wires.length < linkStates.length) {
    const p = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    group.appendChild(p);
    svg.__wires.push(p);
  }
  linkStates.forEach((wire, index) => {
    const p = svg.__wires[index];
    if (p.__d !== wire.d) {
      p.__d = wire.d;
      p.setAttribute('d', wire.d);
      // exact length so the energy packet truly travels the whole wire
      try { p.style.setProperty('--hc-len', Math.ceil(p.getTotalLength())); } catch (_) {}
    }
    const next = 'hc-' + wire.cls;
    // Preserve the one-shot flow class across re-renders during the hold —
    // only the epoch gate is allowed to arm/disarm it.
    const keepFlow = p.classList.contains('hc-flow');
    if (p.__cls !== next) { p.__cls = next; }
    p.setAttribute('class', next + (keepFlow ? ' hc-flow' : ''));
  });
  // Sequential cascade timing: the moment the whole chain goes green, each wire
  // gets its turn — the energy wave runs GitHub → … → Session, one after another.
  // __cascadeEpoch stamps this run so re-renders during the hold don't restart it.
  const epoch = hc.__cascade ? (hc.__cascadeEpoch || 0) : 0;
  if (svg.__cascadeEpoch !== epoch) {
    svg.__cascadeEpoch = epoch;
    if (epoch) {
      svg.__wires.forEach((p, index) => {
        p.style.setProperty('--hc-delay', Math.round(index * 190) + 'ms');
        if (!p.style.getPropertyValue('--hc-len')) {
          try { p.style.setProperty('--hc-len', Math.ceil(p.getTotalLength())); } catch (_) {}
        }
        // Only green wires join the energy wave — idle/down/checking wires stay
        // put (the 'u' restart feed and any broken link must not animate).
        const isOk = p.classList.contains('hc-ok');
        if (isOk) {
          // restart the one-shot flow animation on this new run only
          p.classList.remove('hc-flow');
          void p.getBoundingClientRect();
          p.classList.add('hc-flow');
        } else {
          p.classList.remove('hc-flow');
        }
      });
    } else {
      svg.__wires.forEach(p => { p.classList.remove('hc-flow'); p.style.removeProperty('--hc-delay'); });
    }
  }
  hub.removeAttribute('data-health');   // per-node styling drives colours
}

/* Saved messages aggregated across all the agent's rooms. */
function collectSavedMessages() {
  const agent = S.agents[0] || null;
  if (!agent) return [];
  const out = [];
  S.sessions.filter(s => s.agent_id === agent.id).forEach(session => {
    const ids = Array.isArray(session?.saved_message_ids) ? session.saved_message_ids : [];
    if (!ids.length) return;
    const byId = new Map(readMessageCache(session.id).map(m => [m.id, m]));
    ids.forEach(id => {
      const m = byId.get(id);
      if (m) out.push({ session, message: m });
    });
  });
  return out;
}

function openSavedMessagesHub() {
  const saved = collectSavedMessages();
  const body = el('div', 'saved-messages-screen');
  body.innerHTML = saved.length
    ? saved.map(({ session, message }) =>
        `<button class="saved-message-row" data-session-id="${esc(session.id)}" data-saved-message-id="${esc(message.id)}">
          <span>${ZI('pin')}</span>
          <span class="saved-message-copy"><strong>${esc(String(message.content || '').replace(/\s+/g, ' ').trim() || '—')}</strong><small>${esc(roomTitle(session))}</small></span>
        </button>`).join('')
    : '<div class="room-collection-empty">No saved messages yet. Tap the save icon under an agent reply.</div>';
  body.onclick = async event => {
    const btn = event.target.closest('[data-saved-message-id]');
    if (!btn) return;
    const sid = btn.dataset.sessionId;
    const mid = btn.dataset.savedMessageId;
    closeModal();
    const session = S.sessions.find(s => s.id === sid);
    if (session && isGeneralSession(session)) await openAgentChat(S.agents[0]);
    else await openSession(sid);
    setTimeout(() => document.querySelector(`.msg[data-message-id="${CSS.escape(mid)}"]`)?.scrollIntoView({ behavior: 'smooth', block: 'center' }), 260);
  };
  modal({ title: 'Saved messages', body, actions: [] });
}

/* Live ACTIVITY feed on the home hub — a running list of the agent's status
   events (title only): step labels from its live run (Thinking / Analyzing /
   Searching / Reading / Generating / Response …) fused with run + gateway state
   (Working / Ready / Connected / Reconnected / Unconnected / Gateway error).
   Newest at the bottom. A persistent log accumulates transitions over the
   session so it reads like a live feed, not a single latest status. */
function latestActivityHistory() {
  const agent = S.agents[0] || null;
  if (!agent) return [];
  const rooms = S.sessions.filter(s => s.agent_id === agent.id);
  let best = null, bestAt = '';
  rooms.forEach(room => {
    readMessageCache(room.id).forEach(m => {
      const hist = m?.metadata?.activity_history;
      if (Array.isArray(hist) && hist.length) {
        const at = String(hist[hist.length - 1].at || m.created_at || '');
        if (at >= bestAt) { bestAt = at; best = hist; }
      }
    });
  });
  return best || [];
}

/* Persistent rolling log of agent status events (title-only feed). */
const hubActivityLog = [];
function pushHubActivity(tone, title) {
  if (!title) return;
  const last = hubActivityLog[hubActivityLog.length - 1];
  if (last && last.title === title) { last.at = new Date().toISOString(); return; }
  hubActivityLog.push({ tone, title, at: new Date().toISOString() });
  if (hubActivityLog.length > 40) hubActivityLog.shift();
}

/* Fold the current real status (live action label, run state, gateway state)
   into the rolling log — called on every hub render, so each change appends a
   new titled row. */
function syncHubActivity() {
  const agent = S.agents[0] || null;
  if (!agent) return;
  if (liveSessions.size > 0) {
    const label = agentLiveActivity.get(agent.id);
    if (label) {
      const semantic = activitySemantic(label, '');
      pushHubActivity(semantic.tone, activityTitle({ label }));
    } else {
      pushHubActivity('green', 'Working');
    }
    return;
  }
  const connection = agentConnectionPresentation(agent);
  // Map gateway state to the owner's status vocabulary.
  if (connection.label === 'Unconnected') pushHubActivity('red', 'Unconnected');
  else if (connection.label === 'Reconnected') pushHubActivity('yellow', 'Reconnected');
  else pushHubActivity('green', 'Connected');
}

function renderActivityPanel() {
  const panel = $('activityPanel');
  if (!panel) return;
  syncHubActivity();
  const live = liveSessions.size > 0;

  // Title-only feed: step history from the last run (mapped) + the rolling
  // status log, deduped on consecutive identical titles.
  const rows = [];
  latestActivityHistory().forEach(entry => {
    const semantic = activitySemantic(entry.label || 'Processing...', entry.tool || '');
    rows.push({ tone: semantic.tone, title: activityTitle(entry), at: entry.at || '' });
  });
  hubActivityLog.forEach(item => rows.push({ tone: item.tone, title: item.title, at: item.at }));
  const feed = [];
  rows.forEach(r => {
    const prev = feed[feed.length - 1];
    if (prev && prev.title === r.title) { prev.at = r.at || prev.at; return; }
    feed.push({ ...r });
  });
  const recent = feed.slice(-8);

  panel.innerHTML = `
    <div class="activity-panel-head">
      <span class="activity-panel-label">ACTIVITY</span>
      <span class="activity-panel-live ${live ? 'on' : ''}">${ZI('ping')}<span>${live ? 'Live' : 'Idle'}</span></span>
    </div>
    <div class="activity-panel-body" id="activityPanelBody"></div>
    <button class="activity-panel-all" id="activityPanelAll" type="button">View all activity ${ZI('chevron')}</button>`;
  const body = panel.querySelector('#activityPanelBody');
  if (!recent.length) {
    body.innerHTML = '<div class="activity-empty">No activity yet. Start a chat to see the agent work.</div>';
  } else {
    recent.forEach((entry, i) => {
      const liveDot = live && i === recent.length - 1;
      const row = el('div', `activity-row title-only tone-${entry.tone}${liveDot ? ' live' : ''}`);
      row.innerHTML = `
        <span class="activity-node"></span>
        <span class="activity-row-copy"><strong>${esc(entry.title)}</strong></span>`;
      body.appendChild(row);
    });
  }
  panel.querySelector('#activityPanelAll').onclick = () => {
    const agent = S.agents[0];
    if (agent) openAgentChat(agent);
  };
}

function renderAgentHome() {
  renderActivityPanel();  // keep the hub feed fresh whenever state changes
  const box = $('agentList'); if (!box) return;
  box.innerHTML = '';
  renderSelectionBar(box);

  // The single agent bound to this account's key.
  const agent = S.agents[0] || null;
  const connection = agent ? agentConnectionPresentation(agent) : { label: 'Unconnected', tone: 'red' };

  // Every session (room) owned by the agent, newest first. General ("Main chat")
  // is a first-class room here, not hidden.
  const rooms = agent
    ? S.sessions.filter(s => s.agent_id === agent.id)
        .sort((a, b) => String(b.updated_at || '').localeCompare(String(a.updated_at || '')))
    : [];

  const query = ($('agentSearch')?.value || '').toLowerCase();
  const items = rooms.filter(s => !query
    || roomTitle(s).toLowerCase().includes(query)
    || String(s.last_preview || '').toLowerCase().includes(query));

  // Identity strip: the one agent + its live connection state.
  if (agent) {
    const idc = el('article', 'account-agent-strip');
    idc.innerHTML = `
      <span class="account-agent-icon">${fixedChatAvatar(agent.name)}</span>
      <span class="account-agent-body">
        <strong>${esc(agent.name)}</strong>
        <span class="account-agent-status tone-${connection.tone}">${esc(connection.label)}</span>
      </span>
      <button class="account-agent-info" type="button" aria-label="Agent info">${ZI('info')}</button>`;
    idc.querySelector('.account-agent-info').onclick = () => showAgentInformation(agent);
    idc.querySelector('.account-agent-icon').onclick = () => showInterfaceStatus(agent);
    box.appendChild(idc);
  }

  if (!agent) {
    box.appendChild(el('div', 'empty-list', 'No agent linked. Connect your Zeline account key.'));
    return;
  }

  if (!items.length) {
    box.appendChild(el('div', 'empty-list', query ? 'No chats match.' : 'No chats yet. Tap New chat to start.'));
    return;
  }

  const flags = agentFlags();
  items.forEach(s => {
    const pinned = flags.pinned.includes(s.id);
    const unread = sessionUnreadCount(s);
    const liveLabel = sessionIsLive(s.id) ? (agentLiveActivity.get(agent.id) || '') : '';
    const preview = String(s.last_preview || '').replace(/\s+/g, ' ').trim();
    const footText = liveLabel || preview || (isGeneralSession(s) ? 'Main conversation' : 'No messages yet');
    const footTone = liveLabel ? statusTone(liveLabel) : 'white';

    const card = el('article', 'agent-card room-card');
    card.dataset.sessionId = s.id;
    card.innerHTML = `
      <button class="agent-card-main" type="button" aria-label="Open ${esc(roomTitle(s))}">
        <span class="agent-card-icon">${ZI(isGeneralSession(s) ? 'chat' : 'agentchip')}</span>
        <span class="agent-card-body">
          <span class="agent-card-title">${esc(roomTitle(s))}</span>
          <span class="agent-card-foot">
            <span class="agent-card-status tone-${footTone}" data-label="${esc(footText)}">${esc(footText)}</span>
          </span>
        </span>
        <span class="agent-card-open" aria-hidden="true">${ZI('chevron')}</span>
      </button>
      <span class="agent-card-rail">
        <span class="agent-card-rail-top">${pinned ? `<span class="agent-card-pin" aria-label="Pinned">${ZI('pin')}</span>` : ''}<button class="agent-card-menu" type="button" aria-label="Chat options" aria-haspopup="menu"><i></i><i></i><i></i></button></span>
        ${unread ? `<span class="agent-card-unread${unread > 99 ? ' is-wide' : ''}" aria-label="${unread} unread">${unread > 99 ? '99+' : unread}</span>` : '<span class="agent-card-unread-spacer" aria-hidden="true"></span>'}
      </span>`;

    const main = card.querySelector('.agent-card-main');
    const overflow = card.querySelector('.agent-card-menu');
    main.onclick = event => {
      if (document.body.classList.contains('popover-dismiss-pending') || performance.now() < suppressAgentRowClickUntil) {
        event.preventDefault(); event.stopPropagation(); return;
      }
      isGeneralSession(s) ? openAgentChat(agent) : openSession(s.id);
    };
    overflow.onpointerdown = event => event.stopPropagation();
    overflow.onclick = event => {
      event.preventDefault(); event.stopPropagation();
      openRoomCardMenu(s, agent, event.currentTarget);
    };
    box.appendChild(card);
  });
}

/* Room (session) overflow menu: Pin / Delete. General ("Main chat") can only be
   pinned, never deleted (it's the agent's base room). */
function openRoomCardMenu(session, agent, anchor) {
  document.querySelector('.agent-card-popover')?.remove();
  document.querySelector('.popover-scrim')?.remove();
  const flags = agentFlags();
  const pinned = flags.pinned.includes(session.id);
  const general = isGeneralSession(session);
  const scrim = el('div', 'popover-scrim');
  document.body.appendChild(scrim);
  const pop = el('div', 'agent-card-popover');
  pop.innerHTML = `
    <button data-act="pin"><span class="acp-ic">${ZI('pin')}</span>${pinned ? 'Unpin' : 'Pin'}</button>
    ${general ? '' : `<button data-act="delete" class="danger"><span class="acp-ic">${ZI('trash')}</span>Delete chat</button>`}`;
  document.body.appendChild(pop);
  const r = anchor.getBoundingClientRect();
  const pw = pop.offsetWidth || 168;
  pop.style.top = (r.bottom + 6) + 'px';
  pop.style.left = Math.max(8, Math.min(window.innerWidth - pw - 8, r.right - pw)) + 'px';
  const removeScrim = () => { document.body.classList.remove('popover-dismiss-pending'); scrim.remove(); };
  const close = () => { pop.remove(); removeScrim(); };
  let dismissTimer = 0;
  const finishDismiss = e => { e?.preventDefault(); e?.stopPropagation(); clearTimeout(dismissTimer); dismissTimer = setTimeout(removeScrim, 90); };
  const beginDismiss = e => {
    e.preventDefault(); e.stopPropagation();
    document.body.classList.add('popover-dismiss-pending');
    pop.remove();
    try { if (e.pointerId != null) scrim.setPointerCapture(e.pointerId); } catch (_) { /* optional */ }
    clearTimeout(dismissTimer); dismissTimer = setTimeout(removeScrim, 700);
  };
  scrim.addEventListener('pointerdown', beginDismiss, { passive: false });
  scrim.addEventListener('pointerup', finishDismiss, { passive: false });
  scrim.addEventListener('pointercancel', finishDismiss, { passive: false });
  scrim.addEventListener('click', finishDismiss, { passive: false });
  scrim.addEventListener('wheel', beginDismiss, { passive: false });
  scrim.addEventListener('touchmove', beginDismiss, { passive: false });
  pop.onclick = e => {
    e.preventDefault(); e.stopPropagation();
    const act = e.target.closest('[data-act]')?.dataset.act;
    if (!act) return;
    close();
    if (act === 'pin') { toggleSessionPin(session); }
    else if (act === 'delete') { confirmDeleteSessions([session]); }
  };
}

const AGENT_GATEWAY_HOLD_MS = 560;
function attachAgentGatewayGesture(main, agent) {
  let timer = 0, startX = 0, startY = 0;
  const clear = () => { clearTimeout(timer); timer = 0; };
  main.addEventListener('pointerdown', event => {
    if (event.pointerType === 'mouse' && event.button !== 0) return;
    startX = event.clientX; startY = event.clientY; clear();
    timer = setTimeout(() => {
      suppressAgentRowClickUntil = performance.now() + 700;
      navigator.vibrate?.(18);
      showInterfaceStatus(agent);
    }, AGENT_GATEWAY_HOLD_MS);
  });
  main.addEventListener('pointermove', event => {
    if (Math.hypot(event.clientX - startX, event.clientY - startY) > 9) clear();
  });
  ['pointerup','pointercancel','pointerleave'].forEach(type => main.addEventListener(type, clear));
  main.addEventListener('contextmenu', event => {
    event.preventDefault(); clear(); suppressAgentRowClickUntil = performance.now() + 700;
    showInterfaceStatus(agent);
  });
}

/* Repaint hub health (labels + card edges + wires) WITHOUT rebuilding any card
   innerHTML, so a recheck never flashes/reloads the screen. */
function applyHubHealthInPlace() {
  // INTERFACE card (left): ZEROLINEAR title, sub = connection status + tone class.
  const ifaceCard = document.querySelector('.hub-status-gateway');
  const iface = interfaceStatus();
  const ifaceSub = ifaceCard?.querySelector('.hub-status-sub');
  if (ifaceSub) ifaceSub.textContent = iface.label;
  if (ifaceCard) ifaceCard.className = ifaceCard.className.replace(/\btone-\w+\b/, '') + ' tone-' + iface.tone;
  // GATEWAY card (middle): "Zeline Agentic AI" title, sub = Running/Stopped/etc.
  const gwCard = document.querySelector('.hub-status-env');
  const gw = gatewayRunStatus();
  const gwSub = gwCard?.querySelector('.hub-status-sub');
  if (gwSub) gwSub.textContent = gw.label;
  if (gwCard) gwCard.className = gwCard.className.replace(/\btone-\w+\b/, '') + ' tone-' + gw.tone;
  // The three workspace selectors flash only while the final sequential health
  // step is actively checking. Once Session becomes ok, the green edge clears.
  const workspaceHealthPulse = Boolean(S.workspaceHealthPulse);
  document.querySelector('.hub-workspace-panel')?.classList.toggle('workspace-health-pulse', workspaceHealthPulse);
  // renderHubConnectors reads S.hc, sets each node's data-health and repaints the
  // wires — cards keep their DOM, only borders/glow + SVG update.
  if (typeof renderHubConnectors === 'function') renderHubConnectors();
}

/* Refresh / RECHECK STATUS — the small round "↻" button under the ZEROLINEAR
   card. This is NOT a restart: it never touches Termux, the gateway process,
   Zeline, or any remote runtime. It just runs fresh health checks and repaints
   the graph in place:  Refresh → Checking… → probe each component → Update Status.
   Flow per node: unknown/old → 'checking' (white-gray) → 'ok'(green)/'down'(red). */
let workspacePulseRunId = 0;   // latest recheck owns the 5s green hold
async function recheckHealth(btn) {
  if (btn && btn.dataset.busy === '1') return;
  const started = Date.now();
  S.gatewayRestarting = true;             // reuse spinner flag so it survives re-render
  if (btn) { btn.dataset.busy = '1'; btn.classList.add('is-spinning'); }

  const hc = (S.hc = S.hc || {});
  // Invalidate any still-running cascade hold from a previous recheck.
  workspacePulseRunId++;
  // SEQUENTIAL check in the visual flow order:
  //   GitHub → Docs → Environment → Gateway → Models → Chat Agent → Session.
  // Everything starts idle/gray; we light ONE card 'checking' at a time, probe
  // it, and only advance to the next card if it passed. The moment a card fails
  // (red), every card after it stays gray — never 'checking'.
  hc.github = 'unknown'; hc.docs = 'unknown'; hc.environment = 'unknown';
  hc.gateway = 'unknown'; hc.models = 'unknown'; hc.chat = 'unknown'; hc.session = 'unknown';
  applyHubHealthInPlace();

  const agent = S.agents[0] || null;
  // Small helper: mark a node checking, paint, and give the eye a beat to see it.
  const stepDelay = () => new Promise(r => setTimeout(r, 300));
  const beginStep = async key => { hc[key] = 'checking'; applyHubHealthInPlace(); await stepDelay(); };

  let broken = false;   // once a link fails, everything downstream is gray
  let reason = null;    // specific status title of the FIRST failure (for the toast)

  // Map a thrown api() error to one of the specific status titles.
  const classify = (err, scope) => {
    const msg = String((err && err.message) || '');
    const m = msg.match(/HTTP\s+(\d{3})/);
    const status = m ? parseInt(m[1], 10) : 0;
    if (navigator.onLine === false) return 'Network offline';
    if (/timed out|abort|timeout/i.test(msg)) return 'Connection timed out';
    if (scope === 'gateway') {
      if (status === 401 || status === 403) return 'Authentication failed';
      if (status >= 500) return 'Server error';
      return 'Gateway unreachable';          // fetch failed / refused / no route
    }
    if (scope === 'provider') {
      if (status === 401 || status === 403) return 'Invalid API key';
      if (status === 429) return 'API limit reached';
      if (status === 402) return 'Insufficient credits';
      if (status === 404) return 'Model not found';
      if (status >= 500) return 'Provider unavailable';
      return 'Provider unreachable';
    }
    return 'Unknown error';
  };

  // 1) GitHub — static link, always reachable. (check → ok)
  await beginStep('github'); hc.github = 'ok'; applyHubHealthInPlace();

  // 2) Docs — static link, always reachable. (check → ok)
  await beginStep('docs'); hc.docs = 'ok'; applyHubHealthInPlace();

  // 3) Environment — detected from the runtime via /system. Reachable → ok
  //    (env_label set); unreachable → down (Environment unavailable / Offline).
  await beginStep('environment');
  try {
    S.system = await api('/system', { timeoutMs: 6000 });
    hc.environment = 'ok';
  } catch (e) {
    S.system = null; hc.environment = 'down'; broken = true;
    reason = classify(e, 'gateway') === 'Gateway unreachable' ? 'Environment unavailable' : classify(e, 'gateway');
  }
  applyHubHealthInPlace();

  // 4) Interface — ZEROLINEAR ↔ gateway link via /health + bound-agent flag.
  //    (S.hc.gateway drives the INTERFACE card.) Only if the gateway runtime is up.
  if (!broken) {
    await beginStep('gateway');
    let gatewayReachable = false;
    S.__ifReason = null;
    try {
      const h = await api('/health', { timeoutMs: 6000 });
      S.health = h || { ok: true };
      gatewayReachable = (h && h.ok !== false);
    } catch (e) {
      S.health = { ok: false }; gatewayReachable = false;
      reason = classify(e, 'gateway');
      S.__ifReason = 'Connection failed';
    }
    if (!agent) { hc.gateway = 'down'; broken = true; reason = reason || 'Agent not found'; S.__ifReason = 'Disconnected'; }
    else if (!gatewayReachable) { hc.gateway = 'down'; broken = true; if (!reason) reason = 'Gateway unreachable'; S.__ifReason = S.__ifReason || 'Connection failed'; }
    else if (agent.is_connected_agent === false) { hc.gateway = 'down'; broken = true; reason = 'Invalid Agent Key'; S.__ifReason = 'Unauthorized'; }
    else { hc.gateway = 'ok'; S.__ifReason = null; }
    applyHubHealthInPlace();
  }

  // 5) Model / provider — only if upstream passed.
  if (!broken) {
    const provider = (S.providers || []).find(p => p.id === agent.provider_id);
    if (!provider) { hc.models = 'down'; broken = true; reason = 'API key missing'; applyHubHealthInPlace(); }
    else if (provider.credential_status !== 'configured') {
      await beginStep('models');
      hc.models = 'down'; broken = true; reason = 'API key missing'; applyHubHealthInPlace();
    } else {
      await beginStep('models');
      try {
        await api(`/providers/${provider.id}/test`, { method: 'POST', timeoutMs: 9000 });
        hc.models = 'ok';
      } catch (e) {
        hc.models = 'down'; broken = true; reason = classify(e, 'provider');
      }
      applyHubHealthInPlace();
    }
  }

  // 6) Chat Agent + 7) Session — only if the whole chain passed.
  if (!broken) {
    await beginStep('chat'); hc.chat = 'ok'; applyHubHealthInPlace();
    await beginStep('session'); hc.session = 'ok'; applyHubHealthInPlace();
    // Only after the full GitHub → ... → Session chain is green, flash the
    // three category borders once. Clear it after the one-shot animation.
    const chainComplete = ['github', 'docs', 'environment', 'gateway', 'models', 'chat', 'session']
      .every(key => hc[key] === 'ok');
    if (chainComplete) {
      // Smooth cascade: wires fill one after another (GitHub → … → Session),
      // then the workspace pills flash, and the whole glow gently fades away
      // so nothing is left lit after ~5 seconds.
      hc.__cascade = true;
      hc.__cascadeEpoch = (hc.__cascadeEpoch || 0) + 1;
      S.workspaceHealthPulse = true;
      applyHubHealthInPlace();
      const recheckRunId = ++workspacePulseRunId;
      setTimeout(() => {
        if (recheckRunId !== workspacePulseRunId) return;   // a newer run owns the UI
        S.workspaceHealthPulse = false;
        hc.__cascade = false;
        for (const key of ['github', 'docs', 'environment', 'gateway', 'models', 'chat', 'session']) {
          hc[key] = 'unknown';
        }
        // Soft exit, in place: strip the green classes WITHOUT rebuilding the
        // SVG so the wire stroke and card borders fade out via their own
        // transitions instead of snapping.
        document.querySelectorAll('.home-hub [data-health]').forEach(node => {
          node.removeAttribute('data-health');
        });
        document.querySelectorAll('.hub-conn-lines path.hc-ok').forEach(path => {
          path.classList.remove('hc-ok');
          path.classList.remove('hc-flow');
          path.style.removeProperty('--hc-delay');
          path.__cls = 'hc-idle';
          path.setAttribute('class', 'hc-idle');
        });
        document.querySelector('.hub-workspace-panel')?.classList.remove('workspace-health-pulse');
      }, 5000);
    }
  }

  // Repaint status IN PLACE only. We deliberately do NOT call refreshAll() here —
  // refetching agents/providers/sessions rebuilds the recent list & selects and
  // makes the whole screen visibly reload ("pull-to-refresh" feel). The probes
  // above already updated S.health / S.system; a plain repaint is enough.
  applyHubHealthInPlace();

  const anyDown = ['gateway', 'environment', 'models', 'chat', 'session'].some(k => hc[k] === 'down');
  if (anyDown) toast(reason || 'Unknown error', 'err', 2200);
  else toast('Connected', 'ok', 1400);

  // Keep the spinner turning at least ~900ms so it reads as a real check.
  const wait = Math.max(0, 900 - (Date.now() - started));
  setTimeout(() => {
    S.gatewayRestarting = false;
    const live = document.querySelector('.hub-models-slot');
    const target = live || btn;
    if (target) settleSpinner(target);
    if (btn && btn !== target) settleSpinner(btn);
  }, wait);
}

/* Stop the infinite spin without a hard snap back to 0°. We read the current
   rotation from the running animation, freeze the icon at that exact angle,
   then transition it smoothly to the home position (nearest full turn). */
function settleSpinner(slot) {
  const svg = slot && slot.querySelector('svg');
  slot && (slot.dataset.busy = '0');
  if (!svg) { slot && slot.classList.remove('is-spinning'); return; }
  // Current visual angle from the live transform matrix.
  const m = getComputedStyle(svg).transform;
  let deg = 0;
  if (m && m !== 'none') {
    const v = m.match(/matrix\(([^)]+)\)/);
    if (v) { const [a, b] = v[1].split(',').map(parseFloat); deg = Math.atan2(b, a) * 180 / Math.PI; }
  }
  // Freeze at the current angle (kill the keyframe animation), then ease home.
  slot.classList.remove('is-spinning');
  svg.style.transform = `rotate(${deg}deg)`;
  // next frame: enable transition and glide to 0 (the icon's home orientation).
  requestAnimationFrame(() => {
    slot.classList.add('is-settling');
    svg.style.transform = 'rotate(0deg)';
    const done = () => {
      slot.classList.remove('is-settling');
      svg.style.transform = '';
      svg.removeEventListener('transitionend', done);
    };
    svg.addEventListener('transitionend', done);
    setTimeout(done, 650);  // safety in case transitionend doesn't fire
  });
}

/* INTERFACE card → a dialog for the ZEROLINEAR ↔ Zeline Gateway connection:
   status, agent, session, provider, model. */
function showInterfaceStatus(agent) {
  document.querySelector('.gateway-status-overlay')?.remove();
  const provider = S.providers.find(item => item.id === agent.provider_id);
  const session = S.sessions.find(item => item.agent_id === agent.id && isGeneralSession(item));
  const iface = interfaceStatus();
  const overlay = el('div', 'gateway-status-overlay');
  const bubble = el('section', 'gateway-status-bubble');
  bubble.setAttribute('role', 'dialog');
  bubble.setAttribute('aria-modal', 'true');
  bubble.setAttribute('aria-label', 'ZEROLINEAR Interface');
  bubble.innerHTML = `<div class="gateway-status-head"><span class="gateway-status-mark">${ZI('windowsgrid')}</span><span><strong>ZEROLINEAR Interface</strong><small class="tone-${iface.tone}">${esc(iface.label)}</small></span></div>
    <div class="gateway-status-rows">
      <span><small>Interface</small><b>ZEROLINEAR</b></span>
      <span><small>Connection</small><b>via Zeline Gateway</b></span>
      <span><small>Session ID</small><b class="gateway-session-value"><span class="mono">${esc(session?.id || 'Not active')}</span>${session?.id ? `<button type="button" class="gateway-copy-session" aria-label="Copy Session ID">${ZI('copy')}</button>` : ''}</b></span>
      <span><small>Agent</small><b>${esc(agent.name || 'Zeline')}</b></span>
      <span><small>Provider</small><b>${esc(provider?.name || 'Not configured')}</b></span>
      <span><small>Model</small><b>${esc(agent.model || 'Not configured')}</b></span>
    </div>`;
  overlay.appendChild(bubble);
  const close = () => overlay.remove();
  overlay.addEventListener('pointerdown', event => {
    if (event.target === overlay) close();
  });
  bubble.addEventListener('pointerdown', event => event.stopPropagation());
  bubble.querySelector('.gateway-copy-session')?.addEventListener('click', async event => {
    event.stopPropagation();
    try { await navigator.clipboard.writeText(session.id); toast('Session ID copied', 'ok', 1200); }
    catch (_) { toast('Could not copy Session ID', 'warn', 1400); }
  });
  document.body.appendChild(overlay);
}

/* GATEWAY card → a dialog for the Zeline Gateway running with the Zeline Agentic
   AI runtime on the host: status, environment (auto-detected), host, version,
   uptime, latency, and a Restart Gateway button. Data from /system + a live
   latency probe. No IP address — too sensitive for the UI. */
function showGatewayDetail(agent) {
  document.querySelector('.gateway-status-overlay')?.remove();

  const overlay = el('div', 'gateway-status-overlay');
  const bubble = el('section', 'gateway-status-bubble');
  bubble.setAttribute('role', 'dialog');
  bubble.setAttribute('aria-modal', 'true');
  bubble.setAttribute('aria-label', 'Zeline Gateway');

  const fmtUptime = s => {
    if (s == null) return '—';
    s = Math.max(0, Math.floor(s));
    const d = Math.floor(s / 86400), h = Math.floor((s % 86400) / 3600), m = Math.floor((s % 3600) / 60);
    if (d) return `${d}d ${h}h`;
    if (h) return `${h}h ${m}m`;
    if (m) return `${m}m`;
    return `${s}s`;
  };

  let latencyMs = null;
  const render = sys => {
    const gw = gatewayRunStatus();
    const envLine = (sys && (sys.env_label || '').trim()) || envDisplayLabel();
    const rows = [];
    rows.push(['Gateway', 'Zeline']);
    rows.push(['Status', gw.label]);
    rows.push(['Environment', envLine]);
    if (sys?.hostname) rows.push(['Host', sys.hostname, true]);
    rows.push(['Version', sys?.zeline_version ? `v${sys.zeline_version}` : '—']);
    rows.push(['Uptime', fmtUptime(sys?.uptime_s)]);
    rows.push(['Latency', latencyMs == null ? '—' : `${latencyMs} ms`]);
    const rowsHtml = rows.map(([k, v, copy]) => `<span><small>${esc(k)}</small><b${copy ? ' class="gateway-session-value"' : ''}>${copy ? `<span class="mono">${esc(v)}</span><button type="button" class="gateway-copy-session" aria-label="Copy ${esc(k)}">${ZI('copy')}</button>` : esc(v)}</b></span>`).join('');
    bubble.innerHTML = `<div class="gateway-status-head"><span class="gateway-status-mark">${ZI('windowsgrid')}</span><span><strong>Zeline Gateway</strong><small class="tone-${gw.tone}">${esc(gw.label)}</small></span></div>
      <div class="gateway-status-rows">${rowsHtml}</div>
      <button type="button" class="gateway-restart-btn">${ZI('restart')}<span>Restart Gateway</span></button>`;
    bubble.querySelector('.gateway-copy-session')?.addEventListener('click', async event => {
      event.stopPropagation();
      try { await navigator.clipboard.writeText(sys.hostname); toast('Host copied', 'ok', 1200); }
      catch (_) { toast('Could not copy', 'warn', 1400); }
    });
    bubble.querySelector('.gateway-restart-btn')?.addEventListener('click', async event => {
      event.stopPropagation();
      const btn = event.currentTarget;
      if (btn.dataset.busy === '1') return;
      btn.dataset.busy = '1'; btn.classList.add('is-busy');
      try {
        await api('/gateway/restart', { method: 'POST', timeoutMs: 8000 });
        toast('Gateway restarted', 'ok', 1600);
        try { S.system = await api('/system', { timeoutMs: 6000 }); } catch (_) {}
        latencyMs = null;
        render(S.system || null);
        probeLatency();
        if (typeof applyHubHealthInPlace === 'function') applyHubHealthInPlace();
      } catch (e) {
        toast('Restart failed', 'err', 2000);
      } finally {
        btn.dataset.busy = '0'; btn.classList.remove('is-busy');
      }
    });
  };

  const probeLatency = () => {
    const t0 = performance.now();
    api('/health', { timeoutMs: 6000 })
      .then(() => { latencyMs = Math.round(performance.now() - t0); render(S.system || null); })
      .catch(() => { latencyMs = null; render(S.system || null); });
  };

  render(S.system || null);
  overlay.appendChild(bubble);
  const close = () => overlay.remove();
  overlay.addEventListener('pointerdown', event => { if (event.target === overlay) close(); });
  bubble.addEventListener('pointerdown', event => event.stopPropagation());
  document.body.appendChild(overlay);

  // Refresh /system + latency on open so details are current.
  api('/system', { timeoutMs: 6000 })
    .then(d => { if (d) { S.system = d; render(d); } })
    .catch(() => { /* keep cached/fallback */ });
  probeLatency();
}
/* Three-dot menu on each agent card → a small anchored bubble: Info, Pin, Delete. */
function openAgentCardMenu(agent, anchor) {
  document.querySelector('.agent-card-popover')?.remove();
  document.querySelector('.popover-scrim')?.remove();
  const flags = agentFlags();
  const pinned = flags.pinned.includes(agent.id);
  // Full-screen invisible scrim: catches the FIRST outside tap/scroll, closes the
  // bubble, and swallows that interaction so it can't hit another control or scroll.
  const scrim = el('div', 'popover-scrim');
  document.body.appendChild(scrim);
  const pop = el('div', 'agent-card-popover');
  pop.innerHTML = `
    <button data-act="info"><span class="acp-ic">${ZI('info')}</span>Info</button>
    <button data-act="pin"><span class="acp-ic">${ZI('pin')}</span>${pinned ? 'Unpin' : 'Pin'}</button>
    <button data-act="delete" class="danger"><span class="acp-ic">${ZI('trash')}</span>Delete Agent</button>`;
  document.body.appendChild(pop);

  const r = anchor.getBoundingClientRect();
  const pw = pop.offsetWidth || 168;
  pop.style.top = (r.bottom + 6) + 'px';
  pop.style.left = Math.max(8, Math.min(window.innerWidth - pw - 8, r.right - pw)) + 'px';

  const removeScrim = () => {
    document.body.classList.remove('popover-dismiss-pending');
    scrim.remove();
  };
  const close = () => { pop.remove(); removeScrim(); };
  let dismissTimer = 0;
  const finishDismiss = e => {
    e?.preventDefault(); e?.stopPropagation();
    clearTimeout(dismissTimer);
    dismissTimer = setTimeout(removeScrim, 90);
  };
  const beginDismiss = e => {
    e.preventDefault(); e.stopPropagation();
    cancelAgentRowGesture(true);
    document.body.classList.add('popover-dismiss-pending');
    pop.remove();
    try { if (e.pointerId != null) scrim.setPointerCapture(e.pointerId); } catch (_) { /* optional */ }
    // Keep the scrim mounted through pointerup + synthetic click. Removing it on
    // pointerdown lets the same physical tap activate the agent underneath.
    clearTimeout(dismissTimer);
    dismissTimer = setTimeout(removeScrim, 700);
  };
  scrim.addEventListener('pointerdown', beginDismiss, { passive: false });
  scrim.addEventListener('pointerup', finishDismiss, { passive: false });
  scrim.addEventListener('pointercancel', finishDismiss, { passive: false });
  scrim.addEventListener('click', finishDismiss, { passive: false });
  scrim.addEventListener('wheel', beginDismiss, { passive: false });
  scrim.addEventListener('touchmove', beginDismiss, { passive: false });

  pop.onclick = e => {
    e.preventDefault();
    e.stopPropagation();
    const act = e.target.closest('[data-act]')?.dataset.act;
    if (!act) return;
    close();
    if (act === 'info') showAgentInformation(agent);
    else if (act === 'pin') togglePin(agent);
    else if (act === 'delete') confirmDeleteAgents([agent]);
  };
}

async function openAgentChat(agent) {
  const loadVersion = ++S.roomLoadVersion;
  S.agentId = agent.id; S.model = agent.model;
  S.chatMode = 'general';
  let general = S.sessions.find(session => session.agent_id === agent.id && isGeneralSession(session));
  // Reload race: the session list may not have synced yet, but a mid-stream turn
  // was cached under the general session id and the active-room pointer remembers
  // it. Fall back to that remembered id (and its cache) so a refresh WHILE the
  // agent is running never blanks the room. Reconciliation later fixes the list.
  if (!general) {
    const saved = activeConversationSnapshot();
    if (saved && saved.agentId === agent.id && saved.sessionId) {
      general = { id: saved.sessionId, agent_id: agent.id, kind: 'general',
                  title: `__general__${agent.id}`, updated_at: new Date().toISOString() };
      if (!S.sessions.some(s => s.id === general.id)) { S.sessions.push(general); saveSessionCache(S.sessions); }
    }
  }
  S.sessionId = general?.id || null;
  S.messages = general ? readMessageCache(general.id) : [];
  resetRoomOverlayFocus();
  $('chatHome').hidden = true; $('chatDetail').hidden = false;
  document.body.classList.add('conversation-open');
  const headName = $('chatHeadName');
  if (headName) headName.textContent = agent.name;
  updateConversationIdentity();
  persistActiveConversation();
  renderMessages({ force: true });
  try {
    await syncAgentSelect();
  } catch (error) {
    console.warn('Agent sync failed; keeping cached room visible', error);
  }
  if (general) {
    try {
      const data = await api(`/sessions/${general.id}/messages`, { timeoutMs: 12000 });
      if (loadVersion !== S.roomLoadVersion || S.agentId !== agent.id || S.sessionId !== general.id) return;
      if (Array.isArray(data?.messages) && (data.messages.length || !S.messages.length)) {
        S.messages = reconcileMessageHistory(general.id, data.messages);
        saveMessageCache(general.id, S.messages);
      }
    } catch (error) {
      console.warn('General chat refresh failed; keeping cached room', error);
      if (!S.messages.length) toast('Chat could not be synced', 'warn', 2600);
    }
    markSessionRead(general.id);
    updateAgentCardStatusInPlace(agent.id) || renderAgentHome();
  }
  persistActiveConversation();
  renderMessages({ force: true });
}

function showAgentToken(agent, created) {
  const token = agent.agent_api_token || '';
  const body = el('div', 'agent-token-panel');
  body.innerHTML = `<div class="agent-token-warning">${ZI('shield')}<span><strong>Save this key now</strong><small>Do not share it with anyone. This token grants control of ${esc(agent.name)} and may only be shown once.</small></span></div>
    <label class="field"><span>Zeline account key</span><div class="token-copy-row"><input class="token-preview" readonly value="${esc(token)}"><button class="btn primary sm" id="copyAgentToken">Copy key</button></div></label>
    <p class="note token-help">Store it in a password manager. Use <code>Authorization: Bearer ***</code> when connecting a Zeline Gateway.</p>`;
  modal({ title: created ? 'Account created securely' : agent.name + ' — Account key', body, actions: [{ label: 'I saved the key', kind: 'primary' }] });
  body.querySelector('#copyAgentToken').onclick = async () => {
    try { await navigator.clipboard.writeText(token); toast('Account key copied', 'ok', 1800); }
    catch (_) { body.querySelector('.token-preview').select(); toast('Select and copy the key', 'info'); }
  };
}

function renderUsage() {
  const usage = JSON.parse(localStorage.getItem('zeline.usage') || '{"requests":0,"input":0,"output":0,"cached":0,"cost":0}');
  const totalTokens = Number(usage.input || 0) + Number(usage.output || 0);
  $('usageSpend').textContent = '$' + Number(usage.cost || 0).toFixed(2);
  $('usageRequests').textContent = Number(usage.requests || 0).toLocaleString();
  $('usageTokens').textContent = totalTokens.toLocaleString();
  $('usageCached').textContent = Number(usage.cached || 0).toLocaleString();
  const breakdown = $('usageProviderBreakdown');
  const providers = usage.providers || S.providers.map((provider, index) => ({ name: providerDisplayName(provider), requests: index === 0 ? Number(usage.requests || 0) : 0 }));
  const totalRequests = Math.max(1, providers.reduce((sum, provider) => sum + Number(provider.requests || 0), 0));
  breakdown.innerHTML = providers.map(provider => {
    const requests = Number(provider.requests || 0);
    const share = Math.round(requests / totalRequests * 100);
    return `<div class="usage-provider-row"><span class="usage-provider-dot"></span><span><strong>${esc(provider.name)}</strong><small>${requests.toLocaleString()} requests</small></span><div class="usage-provider-meter"><i style="width:${share}%"></i></div><b>${share}%</b></div>`;
  }).join('') || '<div class="empty-list">No provider activity</div>';
  const bars = $('usageBars'); if (bars) bars.innerHTML = [22, 38, 30, 55, 42, 68, 47].map((h, i) => `<span style="height:${h}%" title="Day ${i + 1}"></span>`).join('');
}


async function renderSettings() {
  // v323 — the old profile/preferences sections moved to the hamburger
  // profile menu. The Settings page is now system-only (Gateway Setup +
  // connection status), so only the diagnostics row is refreshed here.
  try { S.status = await api('/status', { timeoutMs: 6000 }); } catch { S.status = null; }
  const diag = $('diagInfo');
  if (diag) diag.textContent = `${location.host} · ${S.health?.sse ? 'SSE ready' : 'offline'}`;
}
