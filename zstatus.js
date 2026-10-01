/* ═══════════════════════════════════════════════════════════════════════════
   LIVE RUNTIME STATUS — inline line di bawah chat, driven by SSE events.
   12 canonical states ONLY. No Error/Failed/Cancelled/Reading/Editing states.
   ═══════════════════════════════════════════════════════════════════════════ */
const LIVE_STATUS = {
  active: false,
  t0: 0,
  tick: null,
  stallTimer: null,
  lastByteAt: 0,
  tone: 'thinking',
  label: 'Thinking',
  STALL_MS: 15000,
};

function liveStatusEls() {
  return {
    bar: $('liveStatus'),
    label: $('liveStatusLabel'),
    meta: $('liveStatusMeta'),
    timer: $('liveStatusTimer'),
    stop: $('liveStatusStop'),
  };
}

function liveStatusFmt(ms) {
  const s = Math.floor(ms / 1000);
  const m = Math.floor(s / 60);
  const h = Math.floor(m / 60);
  if (h > 0) return `${h}h ${m % 60}m ${s % 60}s`;
  return m > 0 ? `${m}m ${s % 60}s` : `${s}s`;
}

/* All valid tone classes — strip stale ones before applying new. */
const LIVE_TONES = [
  'thinking','recalling','reasoning','planning','working',
  'running','executing','reflecting','waiting','typing',
  'waiting-provider','waiting-directions',
];

function liveStatusRender() {
  const { bar, label, meta, timer } = liveStatusEls();
  liveStatusInlineRender();
  if (!bar) return;
  if (LIVE_STATUS.inlineHost) { bar.hidden = true; return; }
  if (!LIVE_STATUS.active) { bar.hidden = true; return; }
  bar.hidden = false;
  LIVE_TONES.forEach(t => bar.classList.remove('tone-' + t));
  bar.classList.toggle('is-waiting',
    LIVE_STATUS.tone === 'waiting' ||
    LIVE_STATUS.tone === 'waiting-provider' ||
    LIVE_STATUS.tone === 'waiting-directions');
  bar.classList.add('tone-' + LIVE_STATUS.tone);
  /* Header bar mirrors the same 12-state TITLE-ONLY rule. */
  if (label) label.textContent = LIVE_STATUS.label;
  if (meta)  meta.textContent  = '';
  if (timer) timer.textContent = liveStatusFmt(Date.now() - LIVE_STATUS.t0);
}

function liveStatusMountInline(hostCol) {
  LIVE_STATUS.inlineHost = hostCol || null;
  liveStatusRender();
}
function liveStatusUnmountInline() {
  LIVE_STATUS.inlineHost = null;
  document.querySelector('.chat-live-inline')?.remove();
}
function liveStatusInlineRender() {
  let host = LIVE_STATUS.inlineHost;
  if (LIVE_STATUS.active && (!host || !host.isConnected)) {
    host = document.querySelector('#stream') || document.querySelector('.stream');
    LIVE_STATUS.inlineHost = host;
  }
  if (!host) return;
  let node = host.querySelector(':scope > .chat-live-inline');
  if (!LIVE_STATUS.active) { node?.remove(); return; }
  if (!node) {
    node = document.createElement('div');
    node.className = 'chat-live-inline';
    /* 12-STATE STATUS = TITLE ONLY (user spec). No detail/subject here — the
       "what it's doing" detail belongs to the 88-state activity row, NOT this
       line. e.g. "Recalling", never "Recalling : Reading skill". */
    node.innerHTML =
      '<span class="chat-live-orb" aria-hidden="true"><i></i><i></i><i></i></span>'
      + '<span class="chat-live-text"><b class="chat-live-label"></b></span>'
      + '<span class="chat-live-timer" aria-hidden="true"></span>';
    host.appendChild(node);
  } else if (host.lastElementChild !== node) {
    host.appendChild(node);
  }
  node.classList.remove(...LIVE_TONES.map(t => 'tone-' + t));
  node.classList.add('tone-' + LIVE_STATUS.tone);
  node.classList.toggle('is-waiting',
    LIVE_STATUS.tone === 'waiting' ||
    LIVE_STATUS.tone === 'waiting-provider' ||
    LIVE_STATUS.tone === 'waiting-directions');
  const l  = node.querySelector('.chat-live-label');
  const tm = node.querySelector('.chat-live-timer');
  if (l) l.textContent = LIVE_STATUS.label;
  if (tm) tm.textContent = liveStatusFmt(Date.now() - LIVE_STATUS.t0);
}

function liveStatusStart() {
  const { stop } = liveStatusEls();
  LIVE_STATUS.active = true;
  LIVE_STATUS.t0 = Date.now();
  LIVE_STATUS.lastByteAt = Date.now();
  /* Opening state depends on the turn's complexity:
       • LIGHT ("hey", "bantu gua")  -> open in Typing. A light chat never does
         real work, so it must NOT flash a fake Thinking phase.
       • HARD (long/multi-step brief) -> open in Thinking. The model genuinely
         reasons before answering, so the line should say so from the start.
     `window.__turnAskedHard` is set by app2.js send() right before streaming. */
  if (typeof window !== 'undefined' && window.__turnAskedHard) {
    LIVE_STATUS.tone = 'thinking';
    LIVE_STATUS.label = 'Thinking';
  } else {
    LIVE_STATUS.tone = 'typing';
    LIVE_STATUS.label = 'Typing';
  }
  LIVE_STATUS.meta = '';
  if (stop && !stop._wired) {
    stop._wired = true;
    stop.addEventListener('click', () => { try { cancelGeneration(); } catch (_) {} });
  }
  clearInterval(LIVE_STATUS.tick);
  LIVE_STATUS.tick = setInterval(liveStatusRender, 500);
  const chip = $('roomModelChip');
  if (chip) chip.hidden = true;
  document.querySelector('.telegram-chat-head')?.classList.add('agent-running');
  liveStatusRender();
}

function liveStatusStop() {
  LIVE_STATUS.active = false;
  clearInterval(LIVE_STATUS.tick);
  LIVE_STATUS.tick = null;
  clearTimeout(LIVE_STATUS.stallTimer);
  LIVE_STATUS.stallTimer = null;
  liveStatusUnmountInline();
  liveStatusRender();
  document.querySelector('.telegram-chat-head')?.classList.remove('agent-running');
  if (typeof renderRoomModelChip === 'function') renderRoomModelChip();
}

/* Set the 12-state live status. TITLE ONLY — `_meta` is accepted for
   backward-compatible call sites but deliberately NOT rendered: the detail
   ("what it's doing") belongs to the 88-state activity row, never this line. */
function liveStatusSet(label, _meta, tone) {
  if (!LIVE_STATUS.active) liveStatusStart();
  LIVE_STATUS.lastByteAt = Date.now();
  clearTimeout(LIVE_STATUS.stallTimer);
  LIVE_STATUS.stallTimer = setTimeout(() => {
    if (!LIVE_STATUS.active) return;
    if (typeof navigator !== 'undefined' && navigator.onLine === false) {
      LIVE_STATUS.prevLabel = LIVE_STATUS.label;
      LIVE_STATUS.label = 'Waiting';
      LIVE_STATUS.tone = 'waiting';
      liveStatusRender();
    }
  }, LIVE_STATUS.STALL_MS);
  if (label) LIVE_STATUS.label = label;
  LIVE_STATUS.meta = '';   // never render a detail on the 12-state line
  if (tone) LIVE_STATUS.tone = tone;
  liveStatusRender();
}

/* Classify a provider/stream error → one of the 12 canonical states. */
function classifyProviderError(errorCode, message) {
  if (typeof navigator !== 'undefined' && navigator.onLine === false) {
    return { label: 'Waiting', tone: 'waiting' };
  }
  const hay = String(errorCode || '').toLowerCase() + ' ' + String(message || '').toLowerCase();
  if (/rate.?limit|429|quota|credit|insufficient|balance|billing|payment|too many|overloaded|capacity|unavailable|try again|timeout|timed out|temporarily|503|529/.test(hay)) {
    return { label: 'Waiting for Provider Response', tone: 'waiting-provider' };
  }
  if (/unauthor|401|403|invalid.?api.?key|invalid.?key|api.?key|permission|forbidden/.test(hay)) {
    return { label: 'Waiting for Provider Response', tone: 'waiting-provider' };
  }
  if (/base.?url|not found|404|econnrefused|connection refused|enotfound|dns|getaddrinfo|ssl|certificate|cors|bad gateway|502|500|internal server|no route|network|fetch failed/.test(hay)) {
    return { label: 'Waiting for Provider Response', tone: 'waiting-provider' };
  }
  return { label: 'Waiting for Provider Response', tone: 'waiting-provider' };
}

/* ═══════════════════════════════════════════════════════════════════════════
   RUNTIME STATE MACHINE — 12 canonical states ONLY.
   tone drives the spinner colour + live-line accent.

   State   → tone
   ────────────────────────────────────────────────────────
   Thinking                 → thinking
   Recalling                → recalling
   Reasoning                → reasoning
   Planning                 → planning
   Working                  → working
   Running                  → running
   Executing                → executing
   Waiting for Provider Resp→ waiting-provider
   Reflecting               → reflecting
   Waiting                  → waiting
   Typing                   → typing
   Waiting for Directions   → waiting-directions
   ═══════════════════════════════════════════════════════════════════════════ */
const RUNTIME_STATES = {
  THINKING:           { label: 'Thinking',                    tone: 'thinking' },
  RECALLING:          { label: 'Recalling',                   tone: 'recalling' },
  REASONING:          { label: 'Reasoning',                   tone: 'reasoning' },
  PLANNING:           { label: 'Planning',                    tone: 'planning' },
  WORKING:            { label: 'Working',                     tone: 'working' },
  RUNNING:            { label: 'Running',                     tone: 'running' },
  EXECUTING:          { label: 'Executing',                   tone: 'executing' },
  WAITING_PROVIDER:   { label: 'Waiting for Provider Response', tone: 'waiting-provider' },
  REFLECTING:         { label: 'Reflecting',                  tone: 'reflecting' },
  WAITING:            { label: 'Waiting',                     tone: 'waiting' },
  TYPING:             { label: 'Typing',                      tone: 'typing' },
  WAITING_DIRECTIONS: { label: 'Waiting for Directions',      tone: 'waiting-directions' },
};

/* Resolve tool name + args → one of the 12 canonical runtime states.
   Every tool maps to EXACTLY one state. No additional states created.
   Event-level entries (stream.started, tool.completed, …) are also resolved
   here so the SSE handler and the state machine can never disagree. */
function zelineRuntimeState(tool, args = {}) {
  const t   = String(tool || '').toLowerCase();
  const a   = (args && typeof args === 'object') ? args : {};
  const act = String(a.action || '').toLowerCase();
  const S   = RUNTIME_STATES;

  // MCP passthrough → Executing (concrete external action)
  if (t.startsWith('mcp__') || t === 'mcpxy') return S.EXECUTING;

  switch (t) {
    /* ── Stream / lifecycle events ─────────────────────────────────── */
    case 'stream.started':
    case 'assistant.thinking':
    case 'thinking':
      return S.THINKING;
    case 'reasoning':
    case 'assistant.reasoning':
      return S.REASONING;
    case 'planning':
    case 'assistant.planning':
      return S.PLANNING;
    case 'assistant.delta':
    case 'streaming':
      return S.TYPING;
    case 'tool.completed':
    case 'tool.failed':
    case 'code.completed':
    case 'code.failed':
    case 'self.improvement':
    case 'skill.updated':
    case 'reflecting':
      return S.REFLECTING;
    case 'stream.error':
    case 'provider.error':
    case 'rate.limited':
      return S.WAITING_PROVIDER;
    case 'stream.cancelled':
    case 'cancelled':
      return S.WAITING;
    case 'code.started':
      return S.RUNNING;
    case 'file.read':
      return S.EXECUTING;
    case 'file.updated':
      return S.EXECUTING;

    /* ── Waiting for Directions ─────────────────────────────────────── */
    case 'ask_user':
    case 'clarify':
    case 'request_input':
    case 'ask_followup':
    case 'user_input':
      return S.WAITING_DIRECTIONS;

    /* ── Recalling (read-only retrieval, no mutation) ──────────────── */
    case 'list_memory':    return S.RECALLING;
    case 'recall_history': return S.RECALLING;
    case 'search_files':   return S.RECALLING;
    case 'runtime_info':   return S.RECALLING;
    case 'system_env':     return S.RECALLING;
    case 'image':          return S.RECALLING;

    case 'manage_skill':
      if (act === 'list' || act === 'inventory') return S.RECALLING;
      return S.EXECUTING;

    case 'undo_file':
      if (act === 'list') return S.RECALLING;
      if (act === 'diff') return S.RECALLING;   // Previewing undo = read-only
      return S.EXECUTING;                        // restore/undo = mutation

    case 'process_control':
      if (act === 'list') return S.RECALLING;
      if (act === 'log')  return S.RECALLING;
      if (act === 'poll') return S.WAITING;      // waiting on a process
      return S.EXECUTING;

    case 'code_intel':
      if (['diagnostics','definition','references','hover','symbols','servers'].includes(act))
        return S.RECALLING;
      return S.WAITING_PROVIDER;                // fallback = waiting on language server

    case 'browser':
      if (act === 'text' || act === 'links') return S.RECALLING;
      if (act === 'eval')                    return S.RUNNING;
      return S.EXECUTING;

    case 'git':
      if (['status','diff','log','show','branch'].includes(act)) return S.RECALLING;
      if (act === 'add' || act === 'commit')                     return S.EXECUTING;
      return S.RUNNING;

    case 'schedule_task':
      if (act === 'list' || act === 'show') return S.RECALLING;
      if (act === 'run')                    return S.RUNNING;
      return S.EXECUTING;

    case 'analyze_media': {
      const p     = String(a.path_or_url || a.path || '').toLowerCase();
      const audio = ['.ogg','.oga','.opus','.mp3','.m4a','.wav','.flac','.aac',
                     '.amr','.mp4','.webm','.mov','.mkv','.avi','.m4v','.3gp']
                    .some(x => p.endsWith(x));
      return audio ? S.EXECUTING : S.RECALLING;
    }

    /* ── Working (broad research / learning) ─────────────────────── */
    case 'resolve_lesson': return S.WORKING;
    case 'deep_research':  return S.WORKING;

    /* ── Running (live process / code / shell) ───────────────────── */
    case 'execute_code':
    case 'code_exec':
      return S.RUNNING;
    case 'run_shell':
    case 'terminal':
      return S.RUNNING;

    /* ── Executing (concrete side-effecting action) ──────────────── */
    case 'load_skill':     return S.EXECUTING;
    case 'add_memory':     return S.EXECUTING;
    case 'remove_memory':  return S.EXECUTING;
    case 'read_file':      return S.EXECUTING;
    case 'write_file':     return S.EXECUTING;
    case 'edit_file':      return S.EXECUTING;
    case 'patch_file':
    case 'patch':          return S.EXECUTING;
    case 'send_file':      return S.EXECUTING;
    case 'download_file':  return S.EXECUTING;
    case 'update_task':    return S.EXECUTING;
    case 'web_search':     return S.EXECUTING;
    case 'http_request':   return S.EXECUTING;
    case 'delegate_task':  return S.EXECUTING;
    case 'network_route':  return S.EXECUTING;
    case 'generate_image': return S.EXECUTING;

    default:
      return S.EXECUTING;
  }
}

/* Back-compat shim */
function liveStatusForTool(tool, _title, _summary) {
  const s = zelineRuntimeState(tool, arguments[3] || {});
  return { label: s.label, meta: '', tone: s.tone };
}
