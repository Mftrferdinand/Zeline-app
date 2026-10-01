/* Zeline FE — part 2: chat rendering + SSE streaming + cancel */
'use strict';

const TOOL_IC = {
  terminal: ZI('terminal'),
  web_search: ZI('web'),
  file: ZI('file'),
  code: ZI('code')
};
const toolIcon = (n) => TOOL_IC[n] || TOOL_IC.code;

/* Native-messaging scroll behaviour ("jangan loncat"):
   - If the user is already AT/near the bottom, keep pinning to the bottom as new
     content streams in (normal chat follow).
   - If the user has scrolled UP to read history, a new/growing message must NOT
     yank them to the bottom — leave their scroll position exactly where it is.
   `force` (a user action: sending a message, opening the room) always jumps.

   The jump the user still felt came from RELYING on scattered scrollDown()
   calls: the bubble's innerHTML is re-rendered every animation frame, the
   activity tracker is recreated on every tool.output, and the live-status bar
   mounts/unmounts — each grows the content AFTER the last scrollDown() ran, so
   the view drifts up a few px then snaps back next call = a visible bounce.
   Native chat never chases growth with manual scrolls; it ANCHORS to the bottom
   on every layout change. We do the same with a MutationObserver that pins the
   bottom BEFORE the next paint whenever the stream mutates and the user is at
   the bottom — zero perceptible movement. */
const STICK_THRESHOLD_PX = 120;   // "is the view effectively at the bottom?"
const REARM_THRESHOLD_PX = 2;     // re-glue ONLY at the true bottom (was 24 — a small drag stayed inside it and re-armed)
const RELEASE_DELTA_PX = 2;       // any upward scrollTop delta past this = user reading → release glue
let _stickBottom = true;          // is the view currently glued to the bottom?
let _wiredStreamNode = null;      // guard: wire the observer once per #stream node
let _streamMutObserver = null;
let _programmaticScroll = false;  // true while WE move the scroll (pinBottomNow) — ignore that scroll event
let _lastScrollTop = 0;

function streamRoot() { return $('stream'); }

function isNearBottom(s) {
  return (s.scrollHeight - s.scrollTop - s.clientHeight) <= STICK_THRESHOLD_PX;
}
function isAtBottom(s) {
  return (s.scrollHeight - s.scrollTop - s.clientHeight) <= REARM_THRESHOLD_PX;
}
function pinBottomNow(s) {
  // Instant pin, never animated — `scroll-behavior:smooth` (if ever active)
  // would slide the new pixels and read as "loncat".
  const prev = s.style.scrollBehavior;
  s.style.scrollBehavior = 'auto';
  s.scrollTop = s.scrollHeight;
  s.style.scrollBehavior = prev;
  _lastScrollTop = s.scrollTop;
}
/* Attach the auto-anchor once. #stream is a stable node in index.html (its
   innerHTML is cleared but the element itself is never replaced), so a single
   wiring holds for the app's lifetime. */
function ensureStreamStick() {
  const s = streamRoot();
  if (!s || _wiredStreamNode === s) return;
  _wiredStreamNode = s;
  _lastScrollTop = s.scrollTop;
  /* Glue policy — ONE source of truth: the scroll handler, driven by the sign
     of the scrollTop delta.
       • scrollTop went UP (user reading history)  → release glue, full stop.
       • scrollTop is exactly at the bottom         → re-arm glue (follow again).
       • anything else                              → leave the current state.
     The previous bug: the handler only ever SET glue=true (at/near bottom) and
     never set it false, so the first 1–2px of an upward drag (still at bottom)
     re-armed the glue and the next stream mutation pinned the view back down —
     the "geser sedikit langsung balik ke bawah" snap. pinBottomNow() writes
     scrollTop too, but it always lands at the exact bottom (delta 0, never a
     negative/up delta), so it can only ever RE-ARM, never spuriously release. */
  s.addEventListener('scroll', () => {
    const top = s.scrollTop;
    const distFromBottom = s.scrollHeight - top - s.clientHeight;
    if (top < _lastScrollTop - RELEASE_DELTA_PX) {
      _stickBottom = false;              // moved up = reading → hands off
    } else if (distFromBottom <= REARM_THRESHOLD_PX) {
      _stickBottom = true;               // truly at the bottom → follow again
    }
    _lastScrollTop = top;
  }, { passive: true });
  _streamMutObserver?.disconnect();
  _streamMutObserver = new MutationObserver(() => {
    // Runs as a microtask right after the DOM mutates, BEFORE the browser
    // paints — so the pin lands in the same frame as the growth: no bounce.
    if (_stickBottom) pinBottomNow(s);
  });
  _streamMutObserver.observe(s, { childList: true, subtree: true, characterData: true });
}
function scrollDown(force) {
  if (!S.opt.autoScroll && !force) return;
  const s = streamRoot();
  if (!s) return;
  ensureStreamStick();
  // A forced scroll (send / room open) re-arms the glue and always lands at the
  // bottom. Otherwise follow ONLY while the glue is armed (the user is parked at
  // the bottom). If they scrolled up even slightly to read — releasing the glue
  // — we do NOT pin, no matter how close to the bottom they still are. Relying
  // on isNearBottom here was the bug: a reader a few px above the live-status
  // bar was still "near" (120px) and got yanked down on every stream mutation.
  if (force) { _stickBottom = true; _lastScrollTop = s.scrollHeight; }
  else if (!_stickBottom) return;
  pinBottomNow(s);
}

function agentById(id) { return S.agents.find(a => a.id === id); }

let replyTargetMessage = null;
let activeStreamContext = null;

function messageById(id) { return S.messages.find(message => message.id === id); }

function renderReplyPreview() {
  let preview = document.querySelector('.message-reply-preview');
  if (!replyTargetMessage) { preview?.remove(); return; }
  if (!preview) { preview = el('div', 'message-reply-preview'); $('composer')?.before(preview); }
  preview.innerHTML = `<span><small>Replying to ${replyTargetMessage.role === 'user' ? 'You' : esc(agentById(replyTargetMessage.agent_id)?.name || 'Agent')}</small><strong>${esc(roomMessageText(replyTargetMessage).slice(0, 100))}</strong></span><button aria-label="Cancel reply">${ZI('close')}</button>`;
  preview.querySelector('button').onclick = () => { replyTargetMessage = null; renderReplyPreview(); };
}

function savedMessageIds(session) {
  return [...new Set(Array.isArray(session?.saved_message_ids) ? session.saved_message_ids : [])];
}

async function copyAssistantMessage(message) {
  try {
    await navigator.clipboard.writeText(roomMessageText(message));
    toast('Message copied', 'ok', 1200);
  } catch (_) { toast('Unable to copy message', 'err'); }
}

function replyToAssistantMessage(message) {
  replyTargetMessage = message;
  renderReplyPreview();
  $('input')?.focus();
}

/* Read the answer aloud via the browser SpeechSynthesis API (no network). */
function speakAssistantMessage(message, button) {
  try {
    const synth = window.speechSynthesis;
    if (!synth) return toast('Speech not available', 'warn');
    if (synth.speaking) { synth.cancel(); button?.classList.remove('active'); setActionIconFill(button, 'speaker', false); return; }
    const text = roomMessageText(message);
    if (!text) return;
    const utter = new SpeechSynthesisUtterance(text);
    utter.lang = 'id-ID';
    utter.onend = () => { button?.classList.remove('active'); setActionIconFill(button, 'speaker', false); };
    utter.onerror = () => { button?.classList.remove('active'); setActionIconFill(button, 'speaker', false); };
    button?.classList.add('active');
    setActionIconFill(button, 'speaker', true);
    synth.speak(utter);
  } catch (_) { toast('Unable to read aloud', 'err'); }
}

/* 👍 / 👎 — stored locally per message id; toggling the same vote clears it. */
function rateAssistantMessage(message, direction, button) {
  if (!message?.id) return;
  let store = {};
  try { store = JSON.parse(localStorage.getItem('zeline.ratings') || '{}'); } catch (_) { store = {}; }
  const cur = store[message.id];
  store[message.id] = cur === direction ? null : direction;
  if (!store[message.id]) delete store[message.id];
  localStorage.setItem('zeline.ratings', JSON.stringify(store));
  const row = button?.closest('.assistant-message-actions');
  row?.querySelectorAll('[data-action="up"],[data-action="down"]').forEach(btn => btn.classList.remove('active'));
  if (store[message.id]) button?.classList.add('active');
  toast(store[message.id] === 'up' ? 'Thanks for the feedback' : store[message.id] === 'down' ? 'Feedback noted' : 'Feedback cleared', 'ok', 1100);
}

/* Share: native share sheet when available, else copy to clipboard. */
async function shareAssistantMessage(message) {
  const text = roomMessageText(message);
  try {
    if (navigator.share) { await navigator.share({ text }); return; }
    await navigator.clipboard.writeText(text);
    toast('Copied to share', 'ok', 1200);
  } catch (_) { /* user dismissed */ }
}

/* ⋮ — small menu: copy, reply, select text. */
function openMessageMoreMenu(message, anchor) {
  document.querySelector('.msg-more-menu')?.remove();
  const menu = el('div', 'msg-more-menu');
  const add = (label, fn) => {
    const b = el('button', 'msg-more-item', esc(label));
    b.type = 'button';
    b.onclick = e => { e.stopPropagation(); menu.remove(); fn(); };
    menu.appendChild(b);
  };
  add('Copy', () => copyAssistantMessage(message));
  add('Reply', () => replyToAssistantMessage(message));
  add('Select text', () => selectMessageText(message));
  document.body.appendChild(menu);
  const r = anchor.getBoundingClientRect();
  const w = 168;
  menu.style.width = `${w}px`;
  menu.style.left = `${Math.max(8, Math.min(innerWidth - w - 8, r.right - w))}px`;
  menu.style.top = `${Math.min(innerHeight - 8, r.bottom + 6)}px`;
  requestAnimationFrame(() => menu.classList.add('show'));
  const close = ev => { if (!menu.contains(ev.target)) { menu.remove(); document.removeEventListener('pointerdown', close); } };
  setTimeout(() => document.addEventListener('pointerdown', close), 0);
}

function selectMessageText(message) {
  const node = [...document.querySelectorAll('.msg.assistant')].find(m => m.dataset.messageId === message.id);
  const target = node?.querySelector('.assistant-plain-content');
  if (!target) return;
  const range = document.createRange();
  range.selectNodeContents(target);
  const sel = window.getSelection();
  sel.removeAllRanges(); sel.addRange(range);
}

async function toggleSavedMessage(message, button) {
  const session = S.sessions.find(item => item.id === S.sessionId);
  if (!session || !message?.id || String(message.id).startsWith('local_')) return toast('Wait until this response is saved', 'warn');
  const current = savedMessageIds(session);
  const saved = current.includes(message.id);
  const saved_message_ids = saved ? current.filter(id => id !== message.id) : [...current, message.id];
  try {
    const updated = await api(`/sessions/${session.id}`, { method: 'PUT', body: { saved_message_ids } });
    Object.assign(session, updated);
    button?.classList.toggle('saved', !saved);
    if (button) setActionIconFill(button, 'save', !saved);
    button?.setAttribute('aria-label', saved ? 'Save message' : 'Remove saved message');
    toast(saved ? 'Removed from saved messages' : 'Message saved', 'ok', 1200);
  } catch (error) { toast(error.message, 'err'); }
}

function assistantActionIcon(name) {
  // Outline ("rangka") glyphs by default; the button swaps to the filled
  // variant on tap via toggleActionIconFill(). Material Symbols line/fill pair.
  if (name === 'reply') return ZI('act_reply_line');
  if (name === 'copy') return ZI('act_copy_line');
  if (name === 'speaker') return ZI('act_speaker_line');
  if (name === 'save') return ZI('act_save_line');
  if (name === 'share') return ZI('act_share_line');
  return ZI('act_reply_line');
}

/* Swap a button's icon between the outline and filled Material Symbols variant.
   Called on tap so the pressed icon reads as "full". */
function setActionIconFill(button, baseName, filled) {
  if (!button) return;
  button.innerHTML = ZI(`act_${baseName}_${filled ? 'fill' : 'line'}`);
}

function appendAssistantActions(col, message) {
  if (!message?.id || !roomMessageText(message).trim() || message.status === 'streaming') return;
  const session = S.sessions.find(item => item.id === S.sessionId);
  const saved = savedMessageIds(session).includes(message.id);
  const row = el('div', 'assistant-message-actions');
  /* AI-chat action row: reply · copy · speaker · save · share.
     (thumbs up/down and the ⋮ more-menu removed) */
  row.innerHTML =
    `<button data-action="reply" data-icon="reply" aria-label="Reply">${assistantActionIcon('reply')}</button>`
    + `<button data-action="copy" data-icon="copy" aria-label="Copy message">${assistantActionIcon('copy')}</button>`
    + `<button data-action="speak" data-icon="speaker" aria-label="Read aloud">${assistantActionIcon('speaker')}</button>`
    + `<button data-action="save" data-icon="save" aria-label="${saved ? 'Remove saved message' : 'Save message'}" class="${saved ? 'saved' : ''}">${saved ? ZI('act_save_fill') : assistantActionIcon('save')}</button>`
    + `<button data-action="share" data-icon="share" aria-label="Share message">${assistantActionIcon('share')}</button>`;
  const sources = messageSources(message);
  if (sources.length) row.appendChild(answerSources(sources));
  row.onclick = event => {
    const btn = event.target.closest('[data-action]');
    const action = btn?.dataset.action;
    if (!action) return;
    // Fill the tapped icon so it reads as "full" on press. For momentary actions
    // (copy / share / reply) fill briefly then revert to the outline; for
    // stateful ones (save / speaker) the fill tracks the on/off state.
    if (btn.dataset.icon && ['copy', 'reply', 'share'].includes(btn.dataset.icon)) {
      setActionIconFill(btn, btn.dataset.icon, true);
      setTimeout(() => setActionIconFill(btn, btn.dataset.icon, false), 900);
    }
    if (action === 'copy') copyAssistantMessage(message);
    if (action === 'reply') replyToAssistantMessage(message);
    if (action === 'save') toggleSavedMessage(message, btn);
    if (action === 'speak') speakAssistantMessage(message, btn);
    if (action === 'share') shareAssistantMessage(message);
  };
  col.appendChild(row);
}

/* Sources the agent cited, as {url,title,favicon}. Tolerant: accepts a
   message.metadata.sources array of strings or objects; empty when none. */
function messageSources(message) {
  const raw = message?.metadata?.sources || message?.metadata?.citations || [];
  if (!Array.isArray(raw)) return [];
  const out = [];
  raw.forEach(item => {
    if (typeof item === 'string') { out.push({ url: item, title: safeHost(item), favicon: faviconFor(item) }); return; }
    if (item && typeof item === 'object') {
      const url = String(item.url || item.link || '');
      out.push({ url, title: String(item.title || item.name || safeHost(url)), favicon: item.favicon || faviconFor(url) });
    }
  });
  return out.filter(s => s.title || s.url).slice(0, 6);
}

function safeHost(url) {
  try { return new URL(url).hostname.replace(/^www\./, ''); } catch (_) { return String(url || '').slice(0, 24); }
}

function faviconFor(url) {
  const host = safeHost(url);
  return host ? `https://www.google.com/s2/favicons?domain=${encodeURIComponent(host)}&sz=64` : '';
}

/* Overlapping source chip cluster + "Sources" label, right-aligned in the row.
   Uses a stable monogram chip per source rather than a remote favicon, so it
   always renders cleanly (no broken/red-blob favicons) on any device. */
function answerSources(list) {
  const box = el('div', 'answer-sources');
  const seen = new Set();
  list.slice(0, 3).forEach(s => {
    const host = safeHost(s.url || s.title);
    if (seen.has(host)) return;
    seen.add(host);
    const chip = el('span', 'fav-fallback', esc(sourceMonogram(s.title || host)));
    chip.style.setProperty('--src-hue', String(sourceHue(host)));
    chip.title = s.title || host;
    box.appendChild(chip);
  });
  box.appendChild(el('span', 'src-label', 'Sources'));
  return box;
}

/* 1–2 letter monogram from the source name (e.g. "Reuters" → R). */
function sourceMonogram(name) {
  const clean = String(name || '').replace(/^www\./, '').trim();
  if (!clean) return '?';
  const parts = clean.split(/[.\s_-]+/).filter(Boolean);
  if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase();
  return clean.slice(0, 2).toUpperCase();
}

/* Deterministic hue per host so a source always gets the same colour. */
function sourceHue(host) {
  let h = 0;
  for (let i = 0; i < host.length; i++) h = (h * 31 + host.charCodeAt(i)) % 360;
  return h;
}

/* ── message shells ── */
/* `animate` opts in the soft entrance (fade + tiny rise). Only LIVE appends pass
   it — a full renderMessages() rebuild must NOT re-animate every bubble, that is
   the flicker we killed. Reduced-motion users get an instant paint (CSS gates
   the keyframe). */
function msgShell(role, agent, animate = false) {
  const wrap = el('div', 'msg ' + role + ' message-plain' + (animate ? ' msg-enter' : ''));
  const col = el('div', 'bubble-col');
  wrap.appendChild(col);
  streamRoot().appendChild(wrap);
  return col;
}

function attRow(atts) {
  const r = el('div', 'att-row');
  atts.forEach(a => {
    r.appendChild(el('span', 'att-pill',
      `<span>${esc(a.filename || a.name)}</span>
       <span class="mono">${esc(a.type || 'file')}</span>`));
  });
  return r;
}

/* ── tool block (collapsible) ── */
function toolBlock(col, ev) {
  const box = el('div', 'tool running');
  box.dataset.id = ev.tool_call_id;
  const head = el('button', 'tool-head');
  head.innerHTML = `
    <span class="tool-ic">${toolIcon(ev.tool)}</span>
    <span class="tool-title">${esc(ev.title || ev.tool)}</span>
    <span class="tool-sum">${esc(ev.input_summary || '')}</span>
    <span class="tool-dur"></span>
    ${ZI('toolchev', 'tool-chev')}`;
  const body = el('div', 'tool-body');
  const pre = el('pre'); body.appendChild(pre);
  head.onclick = () => box.classList.toggle('open');
  box.appendChild(head); box.appendChild(body);
  if (S.opt.toolOpen) box.classList.add('open');
  col.appendChild(box);
  scrollDown();
  return { box, pre, dur: head.querySelector('.tool-dur') };
}

function eventChip(col, kind, label, mono) {
  col.appendChild(el('div', 'event-chip ' + kind,
    `<span>${esc(label)}</span><span class="mono">${esc(mono || '')}</span>`));
  scrollDown();
}

/* Owner-prefix → real vendor name. Model ids arrive namespaced as
   `owner/model` (e.g. `ag/claude-opus-4-8`). The prefix is the upstream owner
   code, NOT something the user should ever see raw with a slash. */
const MODEL_OWNER_NAMES = { ag: 'Antigravity', cbai: 'Codebuddy', cb: 'Codebuddy', justwoker: 'JustWoker' };
/* Turn a raw `owner/model` id into a clean label with NO slash, keeping the
   model id VERBATIM (hyphens intact) and prefixing the real vendor name:
   `ag/claude-opus-4-8` → `Antigravity claude-opus-4-8`. Bare ids pass through
   unchanged. Used anywhere a model id would otherwise leak into UI text. */
function prettyModelName(rawId) {
  const id = String(rawId || '').trim();
  if (!id) return '';
  if (!id.includes('/')) return id;
  const owner = id.slice(0, id.indexOf('/'));
  const model = id.slice(id.indexOf('/') + 1);
  const vendor = MODEL_OWNER_NAMES[owner.toLowerCase()] || owner;
  return `${vendor} ${model}`;
}

/* Gateway error strings are written for the Telegram bot. In this app they must
   read as native app copy: (1) strip "/model"-style command hints (Telegram-only
   slash commands — this app has a composer model picker instead); (2) replace any
   raw `owner/model` id (which shows an ugly slash + owner code like `ag/…`) with a
   clean human name via prettyModelName. */
function sanitizeGatewayMessage(message) {
  let text = String(message || '');
  // 1. Drop any sentence/clause that references the /model (or /models) command.
  text = text.replace(/[^.!?\n]*\/models?\b[^.!?\n]*[.!?]?/gi, '');
  // 2. Humanise any remaining `owner/model` ids (quoted or bare) → clean name.
  text = text.replace(/['"`]?([A-Za-z][\w.-]*\/[\w.:-]+)['"`]?/g, (m, id) => `'${prettyModelName(id)}'`);
  // 3. Tidy leftover doubled spaces / dangling separators.
  text = text.replace(/\s{2,}/g, ' ').replace(/\s+([.!?])/g, '$1').replace(/[ ,;—-]+$/, '').trim();
  return text;
}

function liveActivityForTool(tool) {
  return ({
    web_search: 'Searching...', web_fetch: 'Browsing...',
    browser: 'Browsing...', deep_research: 'Researching...', file: 'Reading data...', skill: 'Reading skill...', load_skill: 'Reading skill...', list_memory: 'Reading data...', recall_history: 'Reading...',
    read_file: 'Reading data...', search_files: 'Reading...', write_file: 'Writing...',
    run_shell: 'Running...', terminal: 'Running...', execute_code: 'Running...', code_exec: 'Running...', patch: 'Editing...', patch_file: 'Editing...',
    edit_file: 'Editing...', image: 'Generating...', generate: 'Generating...',
    generate_image: 'Generating...', save_skill: 'Self Improvement...', update_skill: 'Self Improvement...', add_memory: 'Saved Memory...', memory: 'Saved Memory...'
  })[tool] || 'Processing...';
}

function activitySemantic(label, tool = '') {
  /* NARASI agent -> row "(icon) Zeline : <kalimat>". Context unik per-N supaya
     narasi tidak saling menimpa (satu context = satu slot di activity_events). */
  if (String(tool).startsWith('narration')) {
    return { context: 'narration:' + String(tool), kind: 'narration', tone: 'white', icon: 'chat' };
  }
  /* SETIAP tool mendapat CONTEXT UNIK-nya sendiri.
     Sebelumnya semua tool "operation" berbagi context 'operation' yang SAMA,
     sehingga satu context = satu slot: read_file lalu write_file lalu search
     akan SALING MENIMPA di activity_events — hanya yang terakhir bertahan, dan
     itulah sebabnya baris "Reading skill"/"Writing file" dkk tidak pernah
     terlihat (yang tampak cuma kartu terminal + row terakhir).
     Sekarang: context = 'tool:<nama>', jadi tiap tool punya barisnya sendiri. */
  if (/Provider error/i.test(label)) return { context: 'error:provider', kind: 'provider-error', tone: 'red', icon: 'provider' };
  if (/Rate limited/i.test(label))  return { context: 'error:rate', kind: 'rate-limited', tone: 'red', icon: 'info' };
  if (/Failed|Error|Disconnected/i.test(label)) return { context: 'error:failed', kind: 'failed', tone: 'red', icon: 'close' };
  if (/Self Improvement/i.test(label)) return { context: 'improvement', kind: 'improvement', tone: 'purple', icon: 'spark' };
  if (/Saved Memory/i.test(label))  return { context: 'memory', kind: 'memory', tone: 'yellow', icon: 'clock' };

  /* Tool terminal: context unik per-tool juga, supaya run_shell dan execute_code
     tidak saling menimpa. */
  if (tool === 'run_shell' || tool === 'terminal' || tool === 'execute_code' || tool === 'code_exec') {
    return { context: 'tool:' + tool, kind: 'terminal', tone: 'green', icon: 'terminal', terminal: true };
  }

  if (/Thinking|Reasoning/i.test(label)) return { context: 'reasoning', kind: 'thinking', tone: 'yellow', icon: 'spark' };

  /* Kunci: context unik per NAMA TOOL (bukan satu context 'operation' bersama). */
  const ctx = 'tool:' + (tool || label || 'op');
  if (/Reading skill/i.test(label)) return { context: ctx, kind: 'reading-skill', tone: 'purple', icon: 'agent' };
  if (/Read/i.test(label))   return { context: ctx, kind: 'reading', tone: 'cyan', icon: 'file' };
  if (/Edit/i.test(label))   return { context: ctx, kind: 'editing', tone: 'orange', icon: 'pencil' };
  if (/Writ/i.test(label))   return { context: ctx, kind: 'writing', tone: 'blue', icon: 'code' };
  if (/Search/i.test(label)) return { context: ctx, kind: 'searching', tone: 'blue', icon: 'search' };
  if (/Brows/i.test(label))  return { context: ctx, kind: 'browsing', tone: 'cyan', icon: 'web' };
  if (/Research/i.test(label)) return { context: ctx, kind: 'researching', tone: 'purple', icon: 'web' };
  if (/Generat/i.test(label)) return { context: ctx, kind: 'generating', tone: 'purple', icon: 'spark' };
  if (/Analyzing|Processing/i.test(label)) return { context: ctx, kind: 'analyzing', tone: 'green', icon: 'search' };
  if (/Run|Coding/i.test(label)) return { context: ctx, kind: 'running', tone: 'green', icon: 'terminal' };
  return { context: ctx, kind: 'processing', tone: 'white', icon: 'agentchip' };
}

function terminalFlavor(tool = '', hint = '') {
  const text = String(hint || '').trim().toLowerCase();
  if (/\b(powershell|pwsh)\b/.test(text)) return 'PowerShell';
  if (/\bhtml\b/.test(text) || /<(?:!doctype|html|head|body|div|script|style)\b/.test(text)) return 'HTML';
  if (/\bzsh\b/.test(text)) return 'Zsh';
  if (tool === 'run_shell' || tool === 'terminal') return 'Bash';
  if (/\b(node|npm|npx|javascript|typescript|\.js\b|\.ts\b)/.test(text)) return 'JavaScript';
  if (/\b(python|python3|pytest|pip)\b/.test(text) || tool === 'execute_code' || tool === 'code_exec') return 'Python';
  if (/\b(sh|shell)\b/.test(text)) return 'Shell';
  return 'Code Output';
}

function terminalOutputMarkup(text = '') {
  return String(text || '').split('\n').map(line => {
    const safe = esc(line);
    if (/^\s*(error|failed|fatal|traceback|exception)\b/i.test(line)) return `<span class="term-red">${safe}</span>`;
    if (/\b(passed|success|done|ok)\b/i.test(line)) return `<span class="term-green">${safe}</span>`;
    if (/^\s*(warning|warn)\b/i.test(line)) return `<span class="term-yellow">${safe}</span>`;
    if (/^\s*[$>#❯]/.test(line)) return `<span class="term-prompt">${safe}</span>`;
    return safe;
  }).join('\n');
}

function paintActivityNode(node, label, detail = '', tool = '') {
  const semantic = activitySemantic(label, tool);
  node.className = semantic.terminal ? 'terminal-macos activity-event activity-live-slot' : `activity-event activity-live-slot tone-${semantic.tone} activity-${semantic.kind}`;
  node.dataset.activityContext = semantic.context;
  if (semantic.terminal) {
    node.dataset.terminalFlavor = terminalFlavor(tool, detail);
    node.innerHTML = `<div class="terminal-macos-head"><span class="terminal-macos-dots"><i></i><i></i><i></i></span><strong>${esc(node.dataset.terminalFlavor)}</strong><button class="terminal-copy" type="button" aria-label="Copy terminal output">${ZI('copy')}</button></div><pre>${terminalOutputMarkup(detail)}</pre>`;
    node.querySelector('.terminal-copy').onclick = async event => {
      event.stopPropagation();
      try { await navigator.clipboard.writeText(node.querySelector('pre')?.textContent || ''); toast('Output copied', 'ok', 1100); }
      catch (_) { toast('Unable to copy output', 'err'); }
    };
  } else {
    // Live status row (Telegram-style): normalized action label + the concrete
    // SUBJECT it's working on + animated "…" dots, e.g. "Searching : harga xau …",
    // "Reading skill : Prop Firm …", "Researching : news XAUUSD …". A stray "*"
    // or empty detail collapses to just the label + dots. Error/memory/improvement
    // are terminal results → no animation. The full step still lands in Activity.
    const animated = !['error', 'memory', 'improvement'].includes(semantic.context);
    node.classList.toggle('activity-loading', animated);
    const liveLabel = String(label).replace(/\.+$/, '').replace(/^Agent live$/i, 'Working').replace(/^Reading (?:other|data)$/i, 'Reading').replace(/^Reasoning$/i, 'Thinking');
    // Skill reads humanize the subject (hyphen/underscore → spaced Title Case).
    let subject = String(detail || '').trim();
    if (subject === '*') subject = '';
    if (/^Reading skill$/i.test(liveLabel) && subject) {
      subject = subject.replace(/^skill\s*[:·-]?\s*/i, '').replace(/[-_]+/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
    }
    subject = subject.replace(/\s+/g, ' ').slice(0, 90);
    const subjectMarkup = subject ? `<span class="activity-live-subject"> : ${esc(subject)}</span>` : '';
    const dots = animated ? '<span class="activity-loading-dots"><i></i><i></i><i></i></span>' : '';
    node.innerHTML = `<span class="activity-event-icon">${ZI(semantic.icon)}</span><span class="activity-event-copy"><strong><span>${esc(liveLabel)}</span>${subjectMarkup}</strong>${dots}</span>`;
  }
  return semantic;
}

function updateStoredActivityDetail(target, context, detail) {
  const events = target?.metadata?.activity_events;
  const event = Array.isArray(events) ? events.find(item => item.context === context) : null;
  if (event) {
    event.detail = detail;
    const history = target?.metadata?.activity_history;
    const historical = Array.isArray(history) ? [...history].reverse().find(item => item.context === context) : null;
    if (historical) historical.detail = detail;
    saveMessageCache(target.session_id, S.messages);
  }
}

function activityHistory(target) {
  target.metadata ||= {};
  target.metadata.activity_history ||= [];
  return target.metadata.activity_history;
}

function activityDisplayDetail(entry = {}) {
  let detail = String(entry.detail || '').replace(/^\s*\*\s*$/, '').trim();
  if (entry.kind === 'thinking' && /^(planning|preparing the next action)$/i.test(detail)) return detail.toLowerCase() === 'planning' ? 'Planning' : 'Preparing next action';
  // Error/detail text can carry Telegram-only "/model" hints AND raw `owner/model`
  // ids (e.g. `ag/claude-opus-4-8`). Both are ugly in-app: strip the command hint
  // and humanise the id (no slash, owner code → vendor name). Only errors need
  // this — tool details (paths, queries) may legitimately contain slashes.
  const sem = activitySemantic(entry.label || '', entry.tool || '');
  if (sem.context === 'error' && typeof sanitizeGatewayMessage === 'function') {
    detail = sanitizeGatewayMessage(detail);
  }
  return detail;
}

function activityTitle(entry = {}) {
  // Labels now come pre-formatted from the gateway/zelineActivity ("Reading file",
  // "Running code", …). Only the legacy aliases are still normalised.
  return String(entry.label || 'Activity').replace(/\.+$/, '').replace(/^Agent live$/i, 'Working').replace(/^Reading other$/i, 'Reading').replace(/^Reasoning$/i, 'Thinking');
}

// Detail text shown INLINE after the title as "Title : detail" (never on a new
// line). Detail is surfaced verbatim (paths, skill ids, queries) — no Title Case
// rewriting, to match the Telegram feed exactly.
function activityDetailText(entry = {}) {
  return activityDisplayDetail(entry);
}

function pushActivityHistory(target, event) {
  const history = activityHistory(target);
  const last = history[history.length - 1];

  // 1. Consecutive identical → collapse (increment counter on the last entry).
  if (last && last.label === event.label &&
      (activityDisplayDetail(last) || '') === (activityDisplayDetail(event) || '') &&
      event.kind !== 'thinking') {
    last.count = (last.count || 1) + 1;
    last.at = event.at;
    return last;
  }

  // 2. Alternating loop detection: if the same label+detail already appears
  //    within the last 4 entries (the typical Patch→Analyze→Patch→… cycle),
  //    increment that existing entry instead of appending a new one.
  if (event.kind !== 'thinking' && history.length >= 2) {
    const window4 = history.slice(-4);
    const match = window4.find(e =>
      e.label === event.label &&
      (activityDisplayDetail(e) || '') === (activityDisplayDetail(event) || ''));
    if (match) {
      match.count = (match.count || 1) + 1;
      match.at = event.at;
      return match;
    }
  }

  // 3. Thinking: just update the round.
  if (last && last.kind === event.kind && event.kind === 'thinking') {
    last.label = event.label;
    last.detail = activityDisplayDetail(event) || activityDisplayDetail(last);
    last.at = event.at;
    return last;
  }

  history.push(event);
  return event;
}

/* Terminal output: uniform 3-line box for EVERY terminal. If it overflows the
   3 visual lines, the 3rd ends with a dim "…" (via -webkit-line-clamp). Tapping
   the BODY (the <pre>, not the copy button) expands to show the WHOLE output at
   once (no scroll); tapping again collapses straight back to 3 lines. */
function wireTerminalMore(card) {
  const pre = card && card.querySelector('pre');
  if (!pre) return;
  // Always clamp-by-default (unless the user already opened it). -webkit-line-clamp
  // only truncates + shows "…" when the content actually exceeds 3 VISUAL lines,
  // so a short terminal stays short and a long one gets exactly 3 lines + "…".
  const open = pre.classList.contains('term-open');
  pre.classList.toggle('term-open', open);
  pre.classList.toggle('term-clamped', !open);
  if (!pre._wired) {
    pre._wired = true;
    // Tap the body toggles 3 ⇄ full. The copy button is excluded so copying
    // doesn't also expand/collapse.
    pre.addEventListener('click', event => {
      if (event.target.closest('.terminal-copy')) return;
      event.stopPropagation();
      const isOpen = pre.classList.contains('term-open');
      pre.classList.toggle('term-open', !isOpen);
      pre.classList.toggle('term-clamped', isOpen);
    });
  }
  /* Overflow is measured by VISUAL height, not by counting "\n": a single long
     line of code that WRAPS past 3 rows has only one newline but still needs the
     clamp + "…" + tap affordance. scrollHeight needs the node attached AND
     clamped, so defer the measurement to the next frame. */
  requestAnimationFrame(() => {
    if (pre.classList.contains('term-open')) { pre.classList.add('term-clickable'); return; }
    const overflowing = pre.scrollHeight > pre.clientHeight + 1;
    pre.classList.toggle('term-clickable', overflowing);
  });
}

function activityHistoryItem(entry) {
  const semantic = activitySemantic(entry.label || 'Processing...', entry.tool || '');
  /* Timestamps are intentionally omitted from the activity feed — the user
     asked for a clean list without the clock column. */
  // Terminal steps render the full macOS terminal bubble INSIDE the Activity
  // panel (open terminal in the activity bubble), not just a one-line label.
  if (semantic.terminal) {
    const flavor = terminalFlavor(entry.tool || '', entry.detail || '');
    const card = el('div', `live-history-item live-history-terminal tone-${semantic.tone}`);
    card.innerHTML = `<div class="terminal-macos" data-terminal-flavor="${esc(flavor)}"><div class="terminal-macos-head"><span class="terminal-macos-dots"><i></i><i></i><i></i></span><strong>${esc(flavor)}</strong><button class="terminal-copy" type="button" aria-label="Copy terminal output">${ZI('copy')}</button></div><pre class="term-clamped">${terminalOutputMarkup(entry.detail || '')}</pre></div>`;
    const copyBtn = card.querySelector('.terminal-copy');
    if (copyBtn) copyBtn.onclick = async event => {
      event.stopPropagation();
      try { await navigator.clipboard.writeText(card.querySelector('pre')?.textContent || ''); toast('Output copied', 'ok', 1100); }
      catch (_) { toast('Unable to copy', 'err'); }
    };
    wireTerminalMore(card);
    return card;
  }
  const row = el('div', `live-history-item tone-${entry.tone || semantic.tone} history-${semantic.kind}`);
  const title = activityTitle(entry);
  const detail = activityDetailText(entry);
  // Title and detail live on ONE line joined by " : " — never a newline/<small>
  // stacked below. e.g. "Thinking : Preparing next action", "Reading skill : Frontend Design".
  const detailMarkup = detail ? `<span class="live-history-detail"> : ${esc(detail)}</span>` : '';
  /* Unique per-tool icon (zicons.js); fall back to the legacy set only if the
     tool has no mapping. */
  const iconName = entry.icon || zelineToolIcon(entry.tool || '');
  const iconMarkup = (window.ZELINE_TOOL_ICONS || {})[iconName] ? zelineIconSvg(iconName) : ZI(semantic.icon);
  const countBadge = (entry.count && entry.count > 1)
    ? `<span class="live-history-count">×${entry.count}</span>` : '';
  row.innerHTML = `<span class="live-history-icon">${iconMarkup}</span><span class="live-history-copy"><strong>${esc(title)}${detailMarkup}${countBadge}</strong></span>`;
  return row;
}

/* Stable per-step signature. Terminals keep a fixed identity (by tool/kind) so
   their streamed output updates the SAME node in place — the bubble never
   re-animates as new lines arrive. Other steps change identity when their
   label/detail/count changes, which lets a genuinely-updated row re-enter. */
function activityEntrySig(entry) {
  const sem = activitySemantic(entry.label || '', entry.tool || '');
  /* Terminals keep a stable IDENTITY by tool (so the node is patched in place,
     never remounted/re-animated), but the sig ALSO carries the output length so
     a streamed update actually triggers the in-place <pre> patch below instead
     of being skipped as "unchanged". Without the length, the reconciler saw the
     sig as identical and never re-rendered the output → terminal looked empty
     ("terminal not rendering"). */
  if (sem.terminal) return 'term:' + (entry.tool || sem.kind) + ':' + String(entry.detail || '').length;
  return [entry.label || '', activityDisplayDetail(entry) || '', entry.count || 1,
          entry.icon || '', entry.tone || sem.tone].join('\u0001');
}

function renderLiveHistoryTracker(col, target) {
  if (!col || !target) return null;
  let rawHistory = activityHistory(target);
  /* Robustness: a finished/re-rendered message may carry its steps under
     activity_events (one-per-context) while activity_history came back empty
     (collapsed, or lost across the persist→refetch reconcile). Terminals live
     in BOTH; if history is empty, fall back to events so the terminal card
     never silently vanishes when the answer lands. */
  if (!rawHistory.length) {
    const events = Array.isArray(target?.metadata?.activity_events) ? target.metadata.activity_events : [];
    if (events.length) rawHistory = events;
  }
  /* Telegram-style: only surface MEANINGFUL work. A bare "Thinking"/"Working"
     step with no tool, no terminal and no concrete detail is noise — a plain
     "hey" should show just its answer. Real steps (tool runs, searching,
     terminal, errors, memory) always show. */
  const isNoise = entry => {
    const label = String(entry.label || '');
    /* "Working" / "Agent live" was an echo of the assistant's own text — pure
       noise, never a real step. Drop it outright. */
    if (/^(working|agent live)$/i.test(label.replace(/\.+$/, '').trim())) return true;
    const sem = activitySemantic(label, entry.tool || '');
    if (sem.terminal) return false;
    if (['error', 'memory', 'improvement'].includes(sem.context)) return false;
    if (entry.tool) return false;                       // a named tool = real work
    if (String(entry.detail || '').trim()) return false; // concrete detail present
    return ['thinking', 'analyzing', 'processing', 'reasoning'].includes(sem.kind);
  };
  const history = rawHistory.filter(entry => !isNoise(entry));
  let tracker = col.querySelector('.live-history-tracker');
  /* Nothing meaningful to show → make sure no empty block is left behind. */
  if (!history.length) {
    if (tracker) tracker.remove();
    return null;
  }
  if (!tracker) tracker = el('div', 'live-history-tracker live-history-inline');
  tracker.classList.add('live-history-inline');
  tracker.dataset.count = String(history.length);
  /* Reconcile in place instead of wiping (innerHTML=''): rebuilding the whole
     list every event made every existing row flash/re-appear abruptly. We keep
     nodes whose signature is unchanged, update terminals' <pre> text silently,
     and only NEW rows get the entrance animation. Nothing already on screen
     jumps. */
  const existing = Array.from(tracker.children);
  const usedSigs = existing.map(n => n.dataset.sig || '');
  history.forEach((entry, idx) => {
    const sig = activityEntrySig(entry);
    const current = tracker.children[idx];
    const sem = activitySemantic(entry.label || '', entry.tool || '');
    if (current && current.dataset.sig === sig) {
      return; // identical row already in the right place — leave it untouched
    }
    // A terminal at this slot whose only change is streamed output: patch its
    // <pre> in place so the bubble does not re-mount / re-animate.
    if (current && sem.terminal && current.classList.contains('live-history-terminal')
        && current.dataset.termId === ('term:' + (entry.tool || sem.kind))) {
      const pre = current.querySelector('pre');
      if (pre) pre.innerHTML = terminalOutputMarkup(entry.detail || '');
      wireTerminalMore(current);   // re-evaluate the 3-line clamp / tap-to-expand
      current.dataset.sig = sig;
      return;
    }
    const node = activityHistoryItem(entry);
    node.dataset.sig = sig;
    if (sem.terminal) node.dataset.termId = 'term:' + (entry.tool || sem.kind);
    // Entrance animation ONLY for a genuinely new row appended to a tracker that
    // was ALREADY on screen (a live incremental update). On a full rebuild the
    // tracker starts empty (existing.length === 0), so EVERY row would look
    // "new" and the whole list re-animated at once — that was the flicker/kedip
    // when a completed turn (or terminal) re-rendered. A rebuild restores
    // silently; only live streaming shows the reveal.
    if (existing.length && !usedSigs.includes(sig)) node.classList.add('activity-enter');
    if (current) tracker.replaceChild(node, current);
    else tracker.appendChild(node);
  });
  // Trim any stale trailing rows left from a longer previous render.
  while (tracker.children.length > history.length) tracker.lastElementChild.remove();
  const anchor = col.querySelector('.assistant-plain-content,.assistant-message-actions');
  if (anchor && tracker.parentElement !== col) col.insertBefore(tracker, anchor);
  else if (anchor && tracker.nextElementSibling !== anchor && tracker.parentElement === col) col.insertBefore(tracker, anchor);
  else if (!anchor && tracker.parentElement !== col) col.appendChild(tracker);
  return tracker;
}

function trackLiveNarrative(col, target, text) {
  /* The streamed assistant text is ALREADY shown in the message body
     (.assistant-plain-content). Mirroring it into the activity list produced a
     bogus "Working : <raw markdown>" row. So there is nothing to record here —
     the activity list only carries real steps (Thinking, Searching, tool runs).
     Kept as a no-op so existing callers keep working. */
  void col; void target; void text;
}

function appendActivityEvent(col, label, detail = '', tool = '', target = null, icon = null, tone = null) {
  if (!col || !label) return null;
  const semantic = activitySemantic(label, tool);
  const ic = icon || zelineToolIcon(tool);
  const tn = tone || zelineToolTone(tool);
  col.dataset.lastActivity = label;
  if (target) {
    target.metadata ||= {};
    target.metadata.activity_events ||= [];
    const at = new Date().toISOString();
    const event = { context: semantic.context, kind: semantic.kind, label, detail, tool, icon: ic, tone: tn, terminal: Boolean(semantic.terminal), at };
    const index = target.metadata.activity_events.findIndex(item => (item.context || activitySemantic(item.label || '', item.tool || '').context) === semantic.context);
    if (index >= 0) target.metadata.activity_events[index] = event;
    else target.metadata.activity_events.push(event);
    pushActivityHistory(target, { ...event });
    renderLiveHistoryTracker(col, target);
    saveMessageCache(target.session_id, S.messages);
  }
  scrollDown();
  return null;
}

function renderStoredActivity(col, events) {
  const list = Array.isArray(events) ? events : [];
  if (!list.length) return;
  // The LIVE status slot must be the single most-recent NON-terminal activity —
  // not "whatever context sits last in the array". Stored events are keyed one
  // per context, so replaying them verbatim would resurrect an older operation
  // (e.g. Reading skill) over the true latest (e.g. Analyzing). Pick the latest
  // non-terminal by timestamp; terminals are distinct cards and all replay.
  const withAt = list.map((e, i) => ({ e, i, at: e.at || '' }));
  const terminals = withAt.filter(x => x.e.terminal);
  const nonTerminals = withAt.filter(x => !x.e.terminal);
  terminals.forEach(({ e }) => appendActivityEvent(col, e.label, e.detail, e.tool));
  if (nonTerminals.length) {
    const latest = nonTerminals.reduce((best, x) =>
      (x.at > best.at || (x.at === best.at && x.i > best.i)) ? x : best);
    appendActivityEvent(col, latest.e.label, latest.e.detail, latest.e.tool);
  }
}

function appendRoomNotice(text, tone = 'white') {
  const col = msgShell('assistant', agentById(S.agentId), true);
  col.appendChild(el('div', `room-command-notice tone-${tone}`, esc(text)));
  scrollDown(true);
}

async function steerCurrentTask(text) {
  const guidance = String(text || '').replace(/^\/steer\s*/i, '').trim();
  if (!guidance || !S.sessionId) {
    appendRoomNotice('Usage: /steer <guidance>', 'yellow');
    return;
  }
  const data = await api(`/sessions/${S.sessionId}/steer`, { method: 'POST', body: { content: guidance } });
  if (!data.accepted) {
    appendRoomNotice('No active task can accept steering.', 'yellow');
    return;
  }
  const elapsed = Math.max(0, Math.round((Date.now() - (activeStreamContext?.startedAt || Date.now())) / 60000));
  const iteration = activeStreamContext?.iteration || 1;
  appendRoomNotice(`Interrupting current task (${elapsed} min elapsed, iteration ${iteration}/150). I'll respond to your message shortly.`, 'yellow');
  const input = $('input');
  input.value = ''; input.style.height = 'auto'; updateSendAvailability();
}

async function clearCurrentHistoryConfirmed() {
  const persisted = S.messages.filter(message => message.id && !String(message.id).startsWith('local_'));
  for (const message of persisted) {
    await api(`/sessions/${S.sessionId}/messages/${message.id}`, { method: 'DELETE' });
  }
  S.messages = [];
  saveMessageCache(S.sessionId, []);
  renderMessages();
}

async function handleSlashCommand(text) {
  if (!text.startsWith('/')) return false;
  const [raw, ...parts] = text.trim().split(/\s+/);
  const command = raw.toLowerCase();
  const argument = parts.join(' ').trim();
  if (command === '/start' || command === '/help') {
    appendRoomNotice('/status · /steer <guidance> · /stop · /cancel · /new [title] · /clear confirm · /help');
    return true;
  }
  if (command === '/status') {
    const labels = { connected: 'Connected', reconnecting: 'Reconnected', reconnected: 'Reconnected', unconnected: 'Unconnected' };
    appendRoomNotice(`Gateway: ${labels[roomConnectionState] || 'Unconnected'} · Task: ${S.streaming ? 'Running' : 'Idle'} · Session: ${S.sessionId || 'Not active'}`, S.streaming ? 'blue' : 'white');
    return true;
  }
  if (command === '/steer') { await steerCurrentTask(argument); return true; }
  if (command === '/stop' || command === '/cancel') { await cancelGeneration(); return true; }
  if (command === '/new') {
    const session = await createManualSessionForAgent(agentById(S.agentId), argument || 'New Session');
    if (session) await openSession(session.id);
    return true;
  }
  if (command === '/clear') {
    if (argument.toLowerCase() !== 'confirm') appendRoomNotice('Use /clear confirm to permanently delete this room history.', 'yellow');
    else await clearCurrentHistoryConfirmed();
    return true;
  }
  appendRoomNotice(`Unknown command: ${command}. Use /help.`, 'yellow');
  return true;
}

/* ── render persisted history ── */
/* renderMessages() REPLACES the whole stream via innerHTML, so it must not yank
   the viewer. A *forced* render (opening a room) jumps to the bottom on purpose.
   Every other call — the per-SSE-event persistStreamSnapshot() and the post-turn
   reconcile — is scroll-NEUTRAL: pin to the bottom only if the user was already
   glued there, otherwise restore their exact scrollTop so a mid-stream rebuild
   never loncat to bottom (or to top after the innerHTML wipe). */
function renderMessages(opts = {}) {
  const s = streamRoot();
  const wasNearBottom = _stickBottom && isNearBottom(s);
  const prevTop = s.scrollTop;
  s.innerHTML = '';
  if (!S.messages.length) { renderEmpty(); return; }
  S.messages.forEach(m => {
    const hasContent = roomMessageText(m).trim();
    const agent = agentById(m.agent_id);
    const col = msgShell(m.role === 'user' ? 'user' : 'assistant', agent);
    const wrap = col.closest('.msg');
    wrap.dataset.messageId = m.id || '';
    const reply = messageById(m.metadata?.reply_to);
    if (reply) col.appendChild(el('div', 'message-reply-quote', `<small>${reply.role === 'user' ? 'You' : esc(agentById(reply.agent_id)?.name || 'Agent')}</small><span>${esc(roomMessageText(reply).slice(0, 100))}</span>`));
    if (m.attachments?.length) col.appendChild(attRow(m.attachments));
    const tl = m.metadata?.tool_events || [];
    const activity = m.metadata?.activity_events || [];
    // Live activity slots (with pulsing "loading" dots) belong ONLY to a message
    // that is still streaming. For a finished message we skip them entirely and
    // show the collapsed Activity tracker instead — otherwise a completed turn
    // keeps animating "Thinking…" forever after reload.
    const streamingNow = m.status === 'streaming';
    if (streamingNow) {
      renderStoredActivity(col, activity);
      // Legacy history may contain only tool_events. Consolidate it to one latest
      // operation instead of restoring every historical tool card and spamming chat.
      if (!activity.length && tl.length) {
        const latest = tl[tl.length - 1];
        appendActivityEvent(col, liveActivityForTool(latest.tool), latest.title || latest.tool, latest.tool);
      }
    }
    if (m.role === 'assistant' && (m.metadata?.activity_history?.length || m.metadata?.activity_events?.length)) {
      renderLiveHistoryTracker(col, m);
    } else if (m.role === 'assistant' && !streamingNow && tl.length) {
      // Sesi yang dibuka ulang cuma bawa tool_events (bukan activity_events yang
      // dibangun saat live). Rebuild row activity SEKALI SAJA, tanpa memicu
      // saveMessageCache/re-render di tengah loop renderMessages — kalau tidak,
      // tiap render me-reset lalu menyimpan ulang → chat kedip/hilang & jawaban
      // Zeline berubah. Build array langsung lalu render, jangan lewat
      // appendActivityEvent (yang menyimpan + re-render).
      m.metadata ||= {};
      if (!m.metadata._activityRebuilt) {
        const events = [];
        tl.forEach(te => {
          const za = zelineActivity(te.tool, te.arguments || {});
          const sem = activitySemantic(te.title || za.label, te.tool || '');
          const label = te.title || za.label;
          const rawSummary = String(te.input_summary || '').replace(/^[\s*'"`.]+$/, '').trim();
          const detail = rawSummary || za.detail || '';
          events.push({
            context: sem.context, kind: sem.kind, label, detail,
            tool: te.tool || '', icon: za.icon, tone: za.tone,
            terminal: Boolean(sem.terminal), at: te.at || new Date().toISOString()
          });
        });
        m.metadata.activity_events = events;
        m.metadata.activity_history = events.slice();
        m.metadata._activityRebuilt = true;   // guard: jangan rebuild lagi
      }
      renderLiveHistoryTracker(col, m);
    }
    if (hasContent || m.status !== 'streaming') {
      const b = el('div', (m.role === 'user' ? 'bubble' : 'assistant-plain-content') + (m.status === 'cancelled' ? ' cancelled' : ''));
      b.innerHTML = md(m.content || '(kosong)');
      col.appendChild(b);
    }
    if (m.role === 'assistant') appendAssistantActions(col, m);
  });
  // Scroll discipline: a forced render jumps to bottom; otherwise stay put.
  if (opts.force) { scrollDown(true); return; }
  if (wasNearBottom) pinBottomNow(s);
  else s.scrollTop = prevTop;   // mid-stream rebuild: keep the viewer where they were
}

function renderEmpty() {
  const a = agentById(S.agentId);
  const s = streamRoot();
  s.innerHTML = '';
  const e = el('div', 'empty');
  e.innerHTML = S.chatMode === 'session'
    ? '<p class="session-empty-description">This session has no messages yet.</p>'
    : `<p>Start a conversation.</p>`;
  s.appendChild(e);
}

/* ───────────────────── send + SSE ───────────────────── */
/* Complexity of the message that STARTED the current turn. Written by send(),
   read by the stream handler. Module-level so both functions share it. */
let turnAskedHard = false;

/* ===========================================================================
   COMPLEXITY ASSESSMENT - decides whether a turn legitimately needs a
   Thinking/Reasoning phase, or is light enough to go straight to Typing.

   LIGHT  ("hey", "makasih", "bantu gua")                 -> Typing
   HARD   (multi-step task, code, long brief)             -> Thinking first

   Heuristics only - no network, no model call, instant.
   =========================================================================== */
function assessPromptComplexity(text) {
  const raw = String(text || '').trim();
  if (!raw) return false;
  const low = raw.toLowerCase();
  const words = low.split(/\s+/).filter(Boolean);
  const wc = words.length;

  // Obvious light greetings / acknowledgements - always Typing.
  const LIGHT = /^(hi|hai|hey|halo|hello|yo|oi|test|tes|ok|oke|okay|sip|thanks|thank you|makasih|thx|ty|nice|mantap|bantu gua|bantu aku|help)\b[\s!?.]*$/;
  if (LIGHT.test(low) && wc <= 4) return false;

  let score = 0;

  // Length - a long brief almost always needs planning.
  if (wc >= 60) score += 3;
  else if (wc >= 30) score += 2;
  else if (wc >= 15) score += 1;
  if (raw.length >= 500) score += 1;

  // Multi-line / bulleted / numbered instructions = a real task.
  const lines = raw.split(/\n/).filter(l => l.trim()).length;
  if (lines >= 5) score += 2;
  else if (lines >= 3) score += 1;
  if (/^\s*(\d+[.)]|[-*\u2022])\s/m.test(raw)) score += 1;

  // Task-oriented verbs / multi-step language.
  const TASKY = /\b(buat|bikin|bangun|buatkan|implement|refactor|perbaiki|fix|debug|analisa|analisis|rancang|desain|susun|rencana|plan|bandingkan|compare|migrasi|upgrade|optimas|tambahin|integrasi|deploy|test|uji|audit|review|telusuri|investigasi|jelaskan kenapa|langkah|step by step|how to|tutorial|arsitektur|database|api|seluruh|semua|codebase|semuanya|keseluruhan|menyeluruh|rapi|modular|struktur|kualitas|performa|keamanan)\b/;
  if (TASKY.test(low)) score += 2;

  // Code / config / paths present = concrete engineering work.
  if (/```|\b(function|class|def |import |const |var |let |select |from |where )\b/.test(raw)) score += 2;
  if (/([a-z0-9_-]+\.(py|js|ts|json|html|css|sh|yaml|yml|sql|md))\b/i.test(raw)) score += 1;
  if (/\/\w+\/\w+/.test(raw)) score += 1;

  // Multiple questions asked at once.
  const q = (raw.match(/\?/g) || []).length;
  if (q >= 3) score += 2;
  else if (q >= 2) score += 1;

  // Conjunctions joining multiple demands.
  const joins = (low.match(/\b(dan|lalu|terus|kemudian|juga|serta|plus|and then|also)\b/g) || []).length;
  if (joins >= 3) score += 2;
  else if (joins >= 2) score += 1;

  // Explicit think/plan cues.
  if (/\b(pikir|pikirkan|rencanakan|plan|reasoning|analisa mendalam|teliti|hati-hati|step by step|langkah demi langkah)\b/.test(low)) score += 2;

  // Scope words: whole-system sweeps are never a one-liner.
  if (/\b(seluruh|semua|keseluruhan|menyeluruh|codebase|semuanya)\b/.test(low)) score += 1;

  return score >= 3;
}

async function send() {
  const ta = $('input');
  const text = ta.value.trim();
  if (!text) return;
  // Slash commands always act on the current stream regardless of state.
  if (await handleSlashCommand(text)) { ta.value = ''; ta.style.height = 'auto'; updateSendAvailability(); return; }
  // A 2nd message sent WHILE the main agent is still working is dispatched to a
  // PARALLEL sub-agent (the gateway forks a fresh ephemeral instance for it),
  // not steered/queued onto the main run. Both stream concurrently.
  if (S.streaming) return sendSubAgent(text);
  if (!await ensureConversationThread()) return;

  ta.value = ''; ta.style.height = 'auto'; updateSendAvailability();
  const agent = agentById(S.agentId);
  const streamSessionId = S.sessionId;
  const setLiveActivity = label => {
    setSessionLive(streamSessionId, Boolean(label));
    setConversationLiveActivity(agent?.id, streamSessionId, label);
  };
  /* Session-list preview only. NOT the live status line — that defaults to
     Typing and is driven by the real SSE events. Keep this neutral so a light
     chat never reads "Thinking..." in the chat list either. */
  setLiveActivity('');
  /* Judge THIS message: a light "hey" -> straight to Typing; a long/multi-step
     brief -> a real Thinking/Planning phase before the answer. */
  turnAskedHard = assessPromptComplexity(text);
  /* Publish for zstatus.js — liveStatusStart() reads this to pick the opening
     state (Thinking for a hard brief, Typing for a light one). */
  if (typeof window !== 'undefined') window.__turnAskedHard = turnAskedHard;
  const atts = S.attachments.slice();
  const replyingTo = replyTargetMessage;
  replyTargetMessage = null; renderReplyPreview();
  S.attachments = []; renderTray();

  // Persist the visible turn before waiting for the network. Any render/reload while
  // the agent works must retain both the sent prompt and the streaming placeholder.
  const now = Date.now();
  const optimisticUser = {
    id: 'local_user_' + now, session_id: streamSessionId, agent_id: agent?.id,
    role: 'user', content: text, attachments: atts, status: 'sending',
    created_at: new Date(now).toISOString()
  };
  const optimisticAssistant = {
    id: 'local_assistant_' + now, session_id: streamSessionId, agent_id: agent?.id,
    role: 'assistant', content: '', attachments: [], status: 'streaming',
    created_at: new Date(now + 1).toISOString()
  };
  S.messages.push(optimisticUser, optimisticAssistant);
  const streamMessages = S.messages;
  function persistStreamSnapshot() {
    saveMessageCache(streamSessionId, streamMessages);
    if (S.sessionId !== streamSessionId || !document.body.classList.contains('conversation-open')) return;
    if (S.messages !== streamMessages) S.messages = streamMessages;
    // Do NOT rebuild the whole stream on every SSE frame. The incremental path
    // (acol/bubble/activity nodes below) already paints live content in place.
    // A full renderMessages() here wiped innerHTML + re-parsed markdown for
    // EVERY message each event → the whole chat flickered and the viewport
    // jumped. Only rebuild when the live nodes were detached (user left the
    // room and came back), where there is no incremental DOM left to update.
    if (acol && acol.isConnected) return;
    renderMessages();
  }
  saveMessageCache(streamSessionId, streamMessages);

  if (streamRoot().querySelector('.empty')) streamRoot().innerHTML = '';

  // user bubble
  const ucol = msgShell('user', agent, true);
  if (replyingTo) ucol.appendChild(el('div', 'message-reply-quote', `<small>${replyingTo.role === 'user' ? 'You' : esc(agentById(replyingTo.agent_id)?.name || 'Agent')}</small><span>${esc(roomMessageText(replyingTo).slice(0, 100))}</span>`));
  if (atts.length) ucol.appendChild(attRow(atts));
  const ub = el('div', 'bubble'); ub.innerHTML = md(text); ucol.appendChild(ub);
  scrollDown(true);

  // One semantic activity row plus one narrative node for the entire stream.
  // Do not add a second "planning" placeholder or split cumulative prose.
  const acol = msgShell('assistant', agent, true);

  setStreaming(true);
  liveStatusStart();
  // The running status is ONE persistent line pinned to the very BOTTOM of the
  // whole chat (below every message/turn), showing what the agent is doing now
  // (Searching files : x.py / Reading file / Typing / Analyzing…) with a loading
  // spinner + timer. It self-hosts on the stream container, so it stays at the
  // bottom even as the agent sends more steps. Removed when the turn finishes.
  liveStatusMountInline(null);
  const t0 = Date.now();
  let bubble = null, acc = '', tools = {};
  /* Tracks whether the turn has done any REAL work (a tool call, code run,
     reasoning/planning signal). A light question never sets it, so the live
     line skips straight to Typing instead of faking a Thinking phase. */
  let streamSawWork = false;
  activeStreamContext = { startedAt: t0, iteration: 1, sessionId: streamSessionId };
  appendActivityEvent(acol, 'Thinking...', '', '', optimisticAssistant);
  persistStreamSnapshot();

  const ensureBubble = () => {
    if (!bubble) {
      bubble = el('div', 'assistant-plain-content streaming');
      acol.appendChild(bubble);
    }
    return bubble;
  };
  // Smooth streaming: SSE chunks arrive in bursts, so re-parsing markdown on every
  // chunk makes the text jerk/stutter. Coalesce paints to ONE per animation frame
  // (rAF) — the DOM updates at the display's refresh rate, and the .streaming fade
  // eases new text in instead of hard-snapping. flushPaint() forces a final paint.
  let paintScheduled = false;
  const paint = () => {
    if (paintScheduled) return;
    paintScheduled = true;
    requestAnimationFrame(() => {
      paintScheduled = false;
      ensureBubble().innerHTML = md(acc);
      scrollDown();
    });
  };
  const flushPaint = () => {
    paintScheduled = false;
    ensureBubble().innerHTML = md(acc);
    scrollDown();
  };

  S.abort = new AbortController();
  try {
    const res = await fetch(`${API}/sessions/${streamSessionId}/messages?stream=true`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: 'Bearer ' + S.token },
      body: JSON.stringify({
        content: text,
        attachments: atts,
        model: S.model,
        reply_to: replyingTo?.id || null,
        workspace: currentWorkspaceContext(streamSessionId),
      }),
      signal: S.abort.signal
    });
    if (!res.ok || !res.body) throw new Error('stream failed (HTTP ' + res.status + ')');

    const reader = res.body.getReader();
    const dec = new TextDecoder();
    let buf = '';

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });
      const frames = buf.split('\n\n');
      buf = frames.pop() || '';

      for (const frame of frames) {
        const line = frame.split('\n').find(l => l.startsWith('data: '));
        if (!line) continue;
        let ev; try { ev = JSON.parse(line.slice(6)); } catch { continue; }
        handleEvent(ev);
      }
    }

    function handleEvent(ev) {
      switch (ev.type) {
        case 'stream.started':
          /* Complexity-aware opening. A SHORT/light message ("hey", "bantu gua")
             must go straight to Typing — no fake Thinking. A LONG/complex
             request (multi-step, lots of context, code, an actual task) legitimately
             needs a thinking/reasoning phase, so we surface it. `streamSawWork`
             still gates tool-driven states; `turnAskedHard` decides the opening. */
          streamSawWork = false;
          if (turnAskedHard) {
            setLiveActivity('Thinking...');
            { const st = zelineRuntimeState('assistant.thinking');
              liveStatusSet(st.label, '', st.tone); }
          }
          updateConversationIdentity();
          break;
        case 'assistant.thinking':
          /* HONEST: only show Thinking when the turn is actually thinking —
             i.e. the request was non-trivial, OR real work is already underway.
             A bare greeting stays silent here and lands on Typing. */
          activeStreamContext.iteration = ev.round || activeStreamContext.iteration;
          if (turnAskedHard || streamSawWork) {
            setLiveActivity('Thinking...');
            { const st = zelineRuntimeState('assistant.thinking');
              liveStatusSet(st.label, '', st.tone); }
          }
          break;
        case 'assistant.reasoning':
          streamSawWork = true;
          { const st = zelineRuntimeState('reasoning');
            liveStatusSet(st.label, '', st.tone); }
          break;
        case 'assistant.planning':
          streamSawWork = true;
          { const st = zelineRuntimeState('planning');
            liveStatusSet(st.label, '', st.tone); }
          break;
        case 'assistant.narration': {
          /* NARASI = agent BICARA di antara kerjaan. Contoh:
               "Eh file-nya nggak ada, gua cari dulu"
               "Ada 2 opsi, gua pilih A karena..."
             Dirender sebagai ROW di activity tracker (bukan bubble terpisah),
             formatnya sama seperti 88 label lain:  (icon) Zeline : <narasi>
             Jadi narasi menyatu dengan alur kerja, bukan gelembung sendiri. */
          const line = String(ev.content || '').trim();
          if (line) {
            /* Narasi = row "Zeline : <kalimat>" di activity tracker, formatnya
               sama seperti 88 label: (icon) Zeline : <narasi>.
               Tiap narasi diberi CONTEXT unik (narration-N) supaya tidak saling
               menimpa di activity_events — kalau semua memakai satu context yang
               sama, narasi kedua akan MENGGANTI yang pertama dan yang tersisa
               cuma satu. */
            optimisticAssistant.metadata ||= {};
            const seq = optimisticAssistant.metadata.narration_seq || 0;
            optimisticAssistant.metadata.narration_seq = seq + 1;
            const uniqTool = 'narration-' + seq;
            appendActivityEvent(acol, 'Zeline', line, uniqTool, optimisticAssistant,
                                'chat', 'white');
            renderLiveHistoryTracker(acol, optimisticAssistant);
            scrollDown();
          }
          break;
        }
        case 'assistant.delta':
          setLiveActivity('Writing...');
          /* HARD turn: hold the line in Thinking/Planning while the model is
             still reasoning; only switch to Typing once real work started (a
             tool ran) OR the answer is genuinely streaming as the first thing.
             LIGHT turn: delta IS the start -> Typing immediately. */
          if (!turnAskedHard || streamSawWork) {
            const st = zelineRuntimeState('assistant.delta');
            liveStatusSet(st.label, '', st.tone);
          } else {
            /* Hard turn, no tool yet: the first chunk is still the ANSWER
               streaming (the gateway sends thinking as a separate event, which
               already set Thinking). Once meaningful prose arrives, flip to
               Typing so the line never sticks on "Thinking" through the reply. */
            const chunk = String(ev.content || '');
            acc += chunk;
            if (acc.length >= 40 || /[.!?]\s|\n/.test(acc)) {
              const st = zelineRuntimeState('assistant.delta');
              liveStatusSet(st.label, '', st.tone);
            }
            paint();
            optimisticAssistant.content = acc;
            trackLiveNarrative(acol, optimisticAssistant, acc);
            saveMessageCache(streamSessionId, S.messages);
            break;
          }
          acc += ev.content || ''; paint();
          optimisticAssistant.content = acc;
          trackLiveNarrative(acol, optimisticAssistant, acc);
          saveMessageCache(streamSessionId, S.messages);
          break;
        case 'tool.started': {
          streamSawWork = true;
          /* The gateway already sends a human title + a specific input_summary
             (e.g. "Reading file" + ".../index.html L1–500"). Use them verbatim
             and attach the UNIQUE per-tool icon. */
          const za = zelineActivity(ev.tool, ev.arguments || {});
          const label = ev.title || za.label;
          // Prefer the gateway's input_summary, but reject junk ("*", quotes,
          // dots only) and fall back to our own derived detail so the status
          // never reads "Searching files : *".
          const rawSummary = String(ev.input_summary || '').replace(/^[\s*'"`.]+$/, '').trim();
          const detail = rawSummary || za.detail || '';
          setLiveActivity(label);
          /* TWO SEPARATE SURFACES (user spec):
             • The 12-state LIVE LINE = status only → TITLE ONLY, no detail.
               e.g. "Recalling"            (never "Recalling : Reading skill")
             • The 88-state ACTIVITY ROW = the full "what it's doing":
               (icon) Reading skill : frontend-design
             The concrete tool label + detail go to the activity row via
             appendActivityEvent below — NOT into the live status line. */
          { const st = zelineRuntimeState(ev.tool, ev.arguments || {});
            liveStatusSet(st.label, '', st.tone); }
          tools[ev.tool_call_id] = {
            name: ev.tool || '',
            inputSummary: detail,
            icon: za.icon, tone: za.tone, label,
            activity: appendActivityEvent(acol, label, detail, ev.tool, optimisticAssistant, za.icon, za.tone),
            output: ''
          };
          break;
        }
        case 'tool.output': {
          const t = tools[ev.tool_call_id];
          if (t) {
            t.output += ev.content || '';
            /* Live "…" cards are gone, so there is no terminal node in the DOM to
               patch. Record the output on the message and refresh the inline list,
               which renders the terminal bubble from the stored detail. */
            updateStoredActivityDetail(optimisticAssistant, 'terminal', t.output);
            renderLiveHistoryTracker(acol, optimisticAssistant);
            scrollDown();
          }
          break;
        }
        case 'tool.completed': {
          const t = tools[ev.tool_call_id];
          if (t) { t.completed = true; t.failed = false; }
          /* Skill/lesson tools surface their RESULT as an "Improvement" step
             (ported from telegram.py `_tool_result_text`). The manage_skill
             `list` action is orientation noise → skipped. */
          if (t && t.name === 'manage_skill' && !/^ERROR/.test(t.output || '')) {
            if (!/^(list|inventory)$/i.test(String(t.activity?.action || ''))) {
              appendActivityEvent(acol, 'Improvement', (t.output || '').replace(/\s+/g, ' ').slice(0, 220), '', optimisticAssistant, 'improvement', 'purple');
            }
          }
          /* Reflecting is a TRANSIENT status, not a logged activity. Adding an
             "Evaluating the latest result" row on EVERY tool.completed flooded
             the feed with duplicate Reflectings after 10-15 tool calls. It now
             only updates the 12-state status line; the per-tool ACTIVITY row
             (the tool that just ran) is already recorded at tool.started. */
          setLiveActivity('Reflecting...');
          { const st = zelineRuntimeState('tool.completed');
            liveStatusSet(st.label, '', st.tone); }
          break;
        }
        case 'tool.failed': {
          const t = tools[ev.tool_call_id];
          if (t) { t.completed = false; t.failed = true; t.output += ev.message || ''; }
          // A failed tool is still a RESULT the agent must evaluate → Reflecting
          // (no separate "Failed" runtime state). The failure text is the detail.
          { const st = zelineRuntimeState('tool.failed');
            liveStatusSet(st.label, '', st.tone); }
          appendActivityEvent(acol, 'Failed', ev.message || ev.error_code || 'Tool failed', '', optimisticAssistant);
          break;
        }
        case 'file.read':
          streamSawWork = true;
          setLiveActivity('Reading...');
          { const st = zelineRuntimeState('file.read');
            liveStatusSet(st.label, '', st.tone); }
          appendActivityEvent(acol, 'Reading data...', `${ev.path} · ${ev.lines} lines`, 'read_file', optimisticAssistant); break;
        case 'file.updated':
          streamSawWork = true;
          setLiveActivity('Editing...');
          { const st = zelineRuntimeState('file.updated');
            liveStatusSet(st.label, '', st.tone); }
          appendActivityEvent(acol, 'Editing...', `${ev.path} · ${ev.lines} lines`, 'patch_file', optimisticAssistant); break;
        case 'code.started':
          streamSawWork = true;
          setLiveActivity('Coding...');
          { const st = zelineRuntimeState('code.started');
            liveStatusSet(st.label, '', st.tone); }
          tools[ev.code_call_id] = { name: 'execute_code', inputSummary: ev.language || 'python', activity: appendActivityEvent(acol, 'Running...', ev.language || 'python', 'execute_code', optimisticAssistant), output: '' };
          break;
        case 'code.output': {
          const t = tools[ev.code_call_id];
          if (t) t.output += ev.content || '';
          const pre = t?.activity?.querySelector('pre');
          if (pre) {
            pre.innerHTML = terminalOutputMarkup(t.output);
            updateStoredActivityDetail(optimisticAssistant, 'terminal', t.output);
            scrollDown();
          }
          break;
        }
        case 'code.completed': {
          if (tools[ev.code_call_id]) { tools[ev.code_call_id].completed = true; tools[ev.code_call_id].failed = false; }
          { const st = zelineRuntimeState('code.completed');
            liveStatusSet(st.label, '', st.tone); }
          /* Reflecting is a TRANSIENT status (see tool.completed above) - it must
             NOT append a repeated activity row, or a run with many code blocks
             floods the feed with "Reflecting" entries. */
          break;
        }
        case 'assistant.completed':
          setLiveActivity('');
          liveStatusStop();
          acc = ev.full_content ?? ev.content ?? acc;
          flushPaint();
          { const fb = ensureBubble(); fb.classList.remove('streaming'); fb.classList.add('result-land'); fb.addEventListener('animationend', () => fb.classList.remove('result-land'), { once: true }); }
          /* Keep the activity steps visible in the finished answer — Telegram
             style. Nothing here clears the inline history; it simply re-renders
             it one last time so every logged step (searching, browsing, tool
             runs, terminal output) stays under the reply for good. */
          renderLiveHistoryTracker(acol, optimisticAssistant);
          optimisticUser.status = 'complete';
          optimisticAssistant.content = acc;
          optimisticAssistant.status = 'complete';
          appendAssistantActions(acol, optimisticAssistant);
          saveMessageCache(streamSessionId, S.messages);
          persistStreamSnapshot();
          const usage = JSON.parse(localStorage.getItem('zeline.usage') || '{"requests":0,"input":0,"output":0,"cached":0,"cost":0}');
          usage.requests += 1; usage.input += Math.max(1, Math.round(text.length / 4)); usage.output += Math.max(1, Math.round(acc.length / 4));
          localStorage.setItem('zeline.usage', JSON.stringify(usage));
          break;
        case 'self.improvement':
          // Learning from a result = Reflecting (no separate "Improvement" state).
          { const st = zelineRuntimeState('self.improvement');
            liveStatusSet(st.label, '', st.tone); }
          appendActivityEvent(acol, 'Self Improvement...', ev.detail || 'Improved a reusable workflow', 'update_skill', optimisticAssistant)?.remove();
          renderLiveHistoryTracker(acol, optimisticAssistant);
          break;
        case 'stream.cancelled':
          { const st = zelineRuntimeState('stream.cancelled');
            liveStatusSet(st.label, '', st.tone); }
          setLiveActivity('');
          liveStatusStop();
          setConversationLiveActivity(agent?.id, streamSessionId, 'Cancelled');
          appendActivityEvent(acol, 'Cancelled', '', '', optimisticAssistant);
          acc = ev.partial_content ?? acc;
          optimisticAssistant.status = 'cancelled';
          optimisticAssistant.content = acc || '_(dibatalkan)_';
          optimisticUser.status = 'complete';
          ensureBubble().innerHTML = md(acc || '_(dibatalkan)_');
          ensureBubble().classList.add('cancelled');
          toast('Generation dibatalkan', 'warn');
          break;
        case 'stream.error':
          const errMsg = sanitizeGatewayMessage(ev.message || '');
          // Per the runtime spec, a provider/rate-limit/language-server failure
          // is the single canonical state "Waiting for Provider Response". Show
          // that on the live line (with the reason as detail) BEFORE stopping.
          { const st = zelineRuntimeState('stream.error');
            liveStatusSet(st.label, '', st.tone); }
          setLiveActivity('');
          liveStatusStop();
          setConversationLiveActivity(agent?.id, streamSessionId, 'Waiting for Provider Response');
          appendActivityEvent(acol, 'Waiting for Provider Response', errMsg, '', optimisticAssistant);
          if (!navigator.onLine) setRoomConnectionState('reconnecting');
          // Error dari provider/agent asli: tampilkan apa adanya, jangan diam.
          acc = ev.partial_content ?? acc;
          optimisticAssistant.status = 'error';
          optimisticAssistant.content = acc || `${ev.error_code || 'ERROR'}: ${errMsg || 'failed'}`;
          optimisticUser.status = 'complete';
          if (acc) ensureBubble().innerHTML = md(acc);
          acol.appendChild(el('div', 'bubble cancelled',
            `<p><strong>Waiting for Provider Response:</strong> ${esc(errMsg || 'gagal')}</p>`));
          break;
        case 'session.updated':
          Object.assign(S.sessions.find(s => s.id === ev.session.id) || {}, ev.session);
          saveSessionCache(S.sessions);
          if (ev.session.id === S.sessionId && document.body.classList.contains('conversation-open')) markSessionRead(ev.session.id);
          renderRecent(); renderSessions(); syncSessionSelect();
          renderAgentHome();
          break;
      }
      persistStreamSnapshot();
    }
  } catch (e) {
    setLiveActivity('');
    if (!navigator.onLine) setRoomConnectionState('reconnecting');
    if (e.name === 'AbortError') {
      optimisticAssistant.status = 'cancelled';
      optimisticAssistant.content = acc || '_(dihentikan di client)_';
      ensureBubble().classList.add('cancelled');
      ensureBubble().innerHTML = md(acc || '_(dihentikan di client)_');
    } else {
      optimisticAssistant.status = 'error';
      optimisticAssistant.content = acc || `Failed: ${e.message}`;
      acol.appendChild(el('div', 'bubble cancelled',
        `<p><strong>Failed:</strong> ${esc(e.message)}</p>`));
      // The inline room bubble is the single error surface; avoid a second noisy
      // toast for the same failure.
    }
    persistStreamSnapshot();
  } finally {
    setLiveActivity('');
    setStreaming(false);
    activeStreamContext = null;
    S.abort = null;
    try {
      const history = await api(`/sessions/${streamSessionId}/messages`, { timeoutMs: 12000 });
      const persisted = Array.isArray(history?.messages) ? history.messages : [];
      const persistedAssistant = [...persisted].reverse().find(message => message.role === 'assistant');
      /* Carry the live activity log onto the server-persisted message, otherwise
         the finished render loses every step (the "log disappears when the
         answer appears" bug). Accept EITHER activity_history OR activity_events
         — some turns only accumulate history. */
      const optimisticEvents = optimisticAssistant.metadata?.activity_events || [];
      const optimisticHistory = optimisticAssistant.metadata?.activity_history || [];
      if (persistedAssistant) {
        persistedAssistant.metadata ||= {};
        if (optimisticEvents.length || optimisticHistory.length) {
          persistedAssistant.metadata.activity_events = optimisticEvents;
          persistedAssistant.metadata.activity_history = optimisticHistory;
        }
        /* KUNCI anti "jawaban Zeline tiba-tiba berubah": jawaban yang SUDAH
           dilihat user (hasil streaming) adalah yang otoritatif untuk turn ini.
           Kalau kita biarkan konten server menimpa, re-render berikutnya
           (mis. dari session.updated) bisa menampilkan teks berbeda hasil
           reformat/normalisasi server. Jadi konten optimistic selalu menang
           selama turn-nya sukses. */
        if (optimisticAssistant.content &&
            (optimisticAssistant.status === 'complete' || !persistedAssistant.content)) {
          persistedAssistant.content = optimisticAssistant.content;
        }
        if ((optimisticEvents.length || optimisticHistory.length) &&
            persistedAssistant.id && !String(persistedAssistant.id).startsWith('local_')) {
          api(`/sessions/${streamSessionId}/messages/${persistedAssistant.id}`,
              { method: 'PATCH', body: { metadata: persistedAssistant.metadata } })
            .catch(() => { /* server lama tanpa endpoint PATCH: biarkan local cache */ });
        }
      }
      const reconciled = persistedAssistant ? reconcileMessageHistory(streamSessionId, persisted, optimisticAssistant) : streamMessages;
      if (reconciled.length) saveMessageCache(streamSessionId, reconciled);
      if (S.sessionId === streamSessionId) {
        const prevMessages = S.messages;
        S.messages = reconciled.length ? reconciled : streamMessages;
        /* Avoid the "kedip" on completion: the stream already painted the final
           answer + terminals incrementally into the live DOM. A full
           renderMessages() here wipes innerHTML and re-mounts every bubble at
           once = a visible flash. So on the happy path — same message count and
           the last assistant turn's content unchanged — we DON'T rebuild; we
           just sync the optimistic wrapper's data-message-id to the server id so
           copy/save/reply keep working. Only rebuild when the structure actually
           differs (error/cancel replaced content, server added/removed msgs). */
        const sameShape = prevMessages.length === S.messages.length
          && optimisticAssistant.status === 'complete';
        if (sameShape) {
          const serverAssistant = [...S.messages].reverse().find(m => m.role === 'assistant');
          const wrap = acol.closest('.msg');
          if (wrap && serverAssistant?.id) wrap.dataset.messageId = serverAssistant.id;
        } else {
          renderMessages();
        }
      }
      if (optimisticAssistant.status === 'complete') {
        await autoCaptureWorkspacesFromTurn({
          agent,
          sourceSessionId: streamSessionId,
          userText: text,
          assistantText: optimisticAssistant.content,
          tools,
        });
      }
    } catch (_) { /* keep streamed UI */ }
    scrollDown();
  }
}

/* Parallel sub-agent dispatch: fired when the user sends a 2nd message while the
   main agent is still streaming. Opens its own SSE to the same endpoint (the
   gateway detects the active main stream and forks an ephemeral sub-agent),
   rendering into a SEPARATE assistant bubble that quotes the message it answers.
   The "Sub-agent" label is only shown once the run actually does work (tool
   calls > 0); a plain question just gets its answer without tagging who replied. */
async function sendSubAgent(text) {
  const ta = $('input');
  ta.value = ''; ta.style.height = 'auto'; updateSendAvailability();
  const agent = agentById(S.agentId);
  const subSessionId = S.sessionId;
  const now = Date.now();

  // User bubble for the 2nd message.
  const ucol = msgShell('user', agent, true);
  const ub = el('div', 'bubble'); ub.innerHTML = md(text); ucol.appendChild(ub);
  const userLocalId = 'local_subuser_' + now;

  // Assistant bubble for the sub-agent, quoting which message it answers.
  const acol = msgShell('assistant', agent, true);
  acol.classList.add('subagent-turn');
  const quote = el('div', 'message-reply-quote subagent-reply-quote',
    `<small>Replying to you</small><span>${esc(text.slice(0, 100))}</span>`);
  acol.appendChild(quote);
  scrollDown(true);

  let bubble = null, acc = '', toolCount = 0, labeled = false;
  const optimistic = { id: 'local_subasst_' + now, session_id: subSessionId, agent_id: agent?.id,
    role: 'assistant', content: '', status: 'streaming', metadata: { origin: 'subagent' },
    created_at: new Date(now + 1).toISOString() };
  const ensureBubble = () => {
    if (!bubble) { bubble = el('div', 'assistant-plain-content streaming'); acol.appendChild(bubble); }
    return bubble;
  };
  // Promote the bubble to a labeled "Sub-agent" turn the moment real work starts.
  const markSubagent = () => {
    if (labeled) return;
    labeled = true;
    acol.classList.add('is-subagent');
    const badge = el('div', 'subagent-badge', `${ZI('delegate') || '⚙'}<span>Sub-agent</span>`);
    acol.insertBefore(badge, acol.firstChild);
  };

  const abort = new AbortController();
  try {
    const res = await fetch(`${API}/sessions/${subSessionId}/messages?stream=true`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: 'Bearer ' + S.token },
      body: JSON.stringify({ content: text, model: S.model, workspace: currentWorkspaceContext(subSessionId) }),
      signal: abort.signal
    });
    if (!res.ok || !res.body) throw new Error('sub-agent stream failed (HTTP ' + res.status + ')');
    const reader = res.body.getReader();
    const dec = new TextDecoder();
    let buf = '';
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });
      const frames = buf.split('\n\n');
      buf = frames.pop() || '';
      for (const frame of frames) {
        const line = frame.split('\n').find(l => l.startsWith('data: '));
        if (!line) continue;
        let ev; try { ev = JSON.parse(line.slice(6)); } catch { continue; }
        switch (ev.type) {
          case 'tool.started':
            toolCount++; markSubagent();
            appendActivityEvent(acol, ev.title || 'Working', ev.input_summary || '', ev.tool, optimistic);
            break;
          case 'tool.output': {
            updateStoredActivityDetail(optimistic, 'terminal', (ev.content || ''));
            break;
          }
          case 'assistant.delta':
            acc += ev.content || '';
            ensureBubble().innerHTML = md(acc);
            scrollDown();
            break;
          case 'assistant.completed':
            acc = ev.full_content ?? ev.content ?? acc;
            if ((ev.metadata?.tool_calls || 0) > 0) markSubagent();
            ensureBubble().innerHTML = md(acc);
            ensureBubble().classList.remove('streaming');
            optimistic.content = acc; optimistic.status = 'complete';
            appendAssistantActions(acol, optimistic);
            break;
          case 'stream.error':
            ensureBubble().innerHTML = md(acc || '');
            acol.appendChild(el('div', 'bubble cancelled',
              `<p><strong>Sub-agent failed:</strong> ${esc(sanitizeGatewayMessage(ev.message || 'error'))}</p>`));
            break;
          case 'stream.cancelled':
            acc = ev.partial_content ?? acc;
            ensureBubble().innerHTML = md(acc || '_(sub-agent dihentikan)_');
            ensureBubble().classList.add('cancelled');
            break;
        }
      }
    }
  } catch (e) {
    ensureBubble().innerHTML = md(acc || '');
    acol.appendChild(el('div', 'bubble cancelled', `<p><strong>Sub-agent failed:</strong> ${esc(e.message)}</p>`));
  } finally {
    scrollDown();
  }
}

function setStreaming(on) {
  S.streaming = on;
  const sendBtn = $('sendBtn');
  const stopBtn = $('stopBtn');
  const input = $('input');
  // Composer no longer swaps send→Stop. The send/mic button stays live so a 2nd
  // message can be dispatched to a parallel sub-agent while the main agent works.
  // Pause/stop now lives on the header ⋮ button (see setHeaderWorking).
  if (sendBtn) sendBtn.hidden = false;
  if (stopBtn) stopBtn.hidden = true;
  if (input) { input.disabled = false; input.placeholder = on ? 'Steer Current Task' : 'Message'; }
  setHeaderWorking(on);
  updateSendAvailability();
}

/* Header ⋮ ↔ pause. While the agent works, the 3-dot menu button becomes a
   white-bg / black-icon PAUSE control that cancels the run; when idle it reverts
   to the ordinary 3-dot menu. The pause affordance only exists during work. */
function setHeaderWorking(on) {
  const btn = $('roomMenuBtn');
  if (!btn) return;
  const was = btn.classList.contains('is-working');
  btn.classList.toggle('is-working', !!on);
  btn.setAttribute('aria-label', on ? 'Pause / stop the running task' : 'Room menu');
  // Replay the glyph-swap pop each time the state actually flips (⋮ ⇄ pause),
  // same feel as the composer mic↔send swap. Force a reflow so the animation
  // restarts even on rapid toggles.
  if (was !== !!on) {
    btn.classList.remove('menu-swap-in');
    void btn.offsetWidth;
    btn.classList.add('menu-swap-in');
    // Drop the class when the pop finishes so the paused-state "breathing"
    // pulse animation can take over (both use the `animation` property).
    btn.addEventListener('animationend', function done(e) {
      if (e.animationName && e.animationName.indexOf('zMenuGlyphIn') !== -1) {
        btn.classList.remove('menu-swap-in');
        btn.removeEventListener('animationend', done);
      }
    });
  }
}

async function cancelGeneration() {
  if (!S.streaming || !S.sessionId) return;
  try {
    const d = await api(`/sessions/${S.sessionId}/cancel`, { method: 'POST' });
    if (!d.cancelled) toast('No active generation', 'warn');
  } catch (e) { toast(e.message, 'err'); }
  setTimeout(() => S.abort?.abort(), 1500);   // fallback if the server goes silent
}

