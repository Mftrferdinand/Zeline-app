/* ═══════════════════════════════════════════════════════════════════════════
   ZELINE ACTIVITY — 88 runtime tool/event labels. One UNIQUE Material icon
   per tool, one descriptive label, optional secondary detail.
   Primary state (12 canonical) comes from zstatus.js; this file supplies the
   concrete action label + icon + tone for each of the 88 runtime entries.
   ═══════════════════════════════════════════════════════════════════════════ */

/* tool name → [icon-key, tone]  (every tool gets a DISTINCT icon) */
const ZELINE_TOOL_MAP = {
  load_skill:      ['menu_book', 'purple'],
  manage_skill:    ['edit_note', 'purple'],
  resolve_lesson:  ['school', 'yellow'],
  add_memory:      ['library_add', 'yellow'],
  remove_memory:   ['library_books', 'yellow'],
  list_memory:     ['book', 'yellow'],
  recall_history:  ['history', 'purple'],
  read_file:       ['description', 'blue'],
  write_file:      ['note_add', 'orange'],
  edit_file:       ['edit', 'orange'],
  patch_file:      ['difference', 'orange'],
  search_files:    ['find_replace', 'blue'],
  undo_file:       ['settings_backup_restore', 'cyan'],
  send_file:       ['send', 'cyan'],
  download_file:   ['download', 'cyan'],
  update_task:     ['task_alt', 'green'],
  execute_code:    ['code', 'green'],
  run_shell:       ['terminal', 'green'],
  process_control: ['pending', 'green'],
  code_intel:      ['monitor_heart', 'cyan'],
  web_search:      ['search', 'blue'],
  deep_research:   ['travel_explore', 'purple'],
  browser:         ['public', 'cyan'],
  git:             ['merge', 'orange'],
  schedule_task:   ['calendar_month', 'yellow'],
  http_request:    ['api', 'blue'],
  delegate_task:   ['diversity_3', 'purple'],
  runtime_info:    ['developer_board', 'cyan'],
  ask_user:        ['question_answer', 'yellow'],
  network_route:   ['route', 'cyan'],
  system_env:      ['memory', 'green'],
  generate_image:  ['palette', 'pink'],
  analyze_media:   ['visibility', 'pink'],
  image:           ['image', 'pink'],
  model:           ['smart_toy', 'blue'],
  /* ── 10 tool tambahan (extra_tools.py) — icon UNIK masing-masing ── */
  port_check:       ['wifi_tethering', 'green'],
  audio_transcribe: ['graphic_eq', 'pink'],
  hash:             ['fingerprint', 'blue'],
  archive:          ['folder_zip', 'yellow'],
  diff:             ['compare', 'orange'],
  json_query:       ['data_object', 'cyan'],
  http_server:      ['dns', 'green'],
  notify:           ['notifications', 'yellow'],
  db_query:         ['storage', 'purple'],
  web_fetch:        ['download_for_offline', 'blue'],
  /* Narasi agent -> row "Zeline : <kalimat>" di activity tracker. */
  narration:        ['chat', 'white'],
};

function zelineToolIcon(tool) {
  const m = ZELINE_TOOL_MAP[tool];
  return m ? m[0] : (String(tool || '').startsWith('mcp__') ? 'mcp' : 'help_outline');
}
function zelineToolTone(tool) {
  const m = ZELINE_TOOL_MAP[tool];
  return m ? m[1] : 'grey';
}
function zelineIconSvg(name) {
  const set = window.ZELINE_TOOL_ICONS || {};
  const g = set[name] || set.help_outline;
  if (!g) return '';
  return `<svg class="zi" viewBox="${g.vb}" fill="currentColor" aria-hidden="true">${g.p}</svg>`;
}

function zelineShortPath(p) {
  const s = String(p || '').replace(/\\/g, '/');
  const parts = s.split('/').filter(Boolean);
  return parts.length > 2 ? '…/' + parts.slice(-2).join('/') : s;
}
function zelineShortHost(url) {
  try { return new URL(url).hostname.replace(/^www\./, ''); } catch (_) { return String(url || '').slice(0, 40); }
}

/* Returns { label, detail, icon, tone }.
   label  = concrete action ("Reading skill", "Running code")
   detail = the concrete subject ("frontend-design", "python3 -m pytest")
   Icons: every sub-action uses its OWN glyph so no two rows share one. */
function zelineActivity(tool, args = {}) {
  const a = args && typeof args === 'object' ? args : {};
  const out = (label, detail = '') => ({ label, detail, icon: zelineToolIcon(tool), tone: zelineToolTone(tool) });
  const R = (icon, label, detail = '', tone = zelineToolTone(tool)) => ({ label, detail, icon, tone });
  const path = zelineShortPath(a.path);

  switch (tool) {
    case 'load_skill':     return out('Reading skill', String(a.name || '').slice(0, 100));
    case 'manage_skill': {
      const act = String(a.action || '').toLowerCase();
      const name = String(a.name || '').slice(0, 100);
      if (act === 'list' || act === 'inventory') return R('auto_stories', 'Reviewing saved skills');
      if (act === 'create') return R('auto_awesome', 'Saving skill', name);
      if (act === 'write_file') return R('note_add', 'Writing file in skill', a.file_path || 'file');
      if (act === 'delete') return a.absorbed_into
        ? R('call_merge', `Merging skill into ${a.absorbed_into}`, name)
        : R('delete_forever', 'Removing skill', name);
      return R('edit_note', 'Updating skill', [name, a.file_path].filter(Boolean).join(' · '));
    }
    case 'resolve_lesson': return out('Resolving lesson', String(a.tool || '').slice(0, 60));
    case 'add_memory':     return out('Saving to memory');
    case 'remove_memory':  return out('Removing from memory');
    case 'list_memory':    return out('Reading saved memory');
    case 'recall_history': return out('Recalling past chat', String(a.query || '').slice(0, 100));
    case 'read_file': {
      if ('offset' in a || 'limit' in a) {
        const off = Math.max(1, parseInt(a.offset, 10) || 1);
        const lim = Math.max(1, parseInt(a.limit, 10) || 500);
        return out(`Reading file L${off}-${off + lim - 1}`, path);
      }
      return out('Reading file', path);
    }
    case 'write_file':     return out('Writing file', path);
    case 'edit_file':      return out('Editing file', path);
    case 'patch_file':     return out('Patching file', path);
    case 'search_files': {
      const q = String(a.query || a.pattern || a.q || a.search || '').trim();
      const where = zelineShortPath(a.path || a.dir || a.directory || '');
      const detail = q ? (where ? `${q} in ${where}` : q) : where;
      return out('Searching files', detail.slice(0, 200));
    }
    case 'undo_file': {
      const act = String(a.action || '').toLowerCase();
      if (act === 'list') return out('Listing file checkpoints', zelineShortPath(a.path));
      if (act === 'diff') return R('compare_arrows', 'Previewing undo', String(a.checkpoint_id || '').slice(0, 32), 'cyan');
      if (act === 'restore') return out('Restoring file', String(a.checkpoint_id || '').slice(0, 32));
      return out('Undoing a file change');
    }
    case 'send_file':      return out('Sending file', path);
    case 'download_file':  return out(`Downloading from ${zelineShortHost(a.url)}`, path);
    case 'update_task':    return out(`Updating tasks: ${a.status || 'pending'}`, String(a.task || '').slice(0, 120));
    case 'execute_code': {
      const code = String(a.code || '').trim();
      return out('Running code', (code.split('\n')[0] || 'code').slice(0, 100));
    }
    case 'run_shell': {
      const cmd = String(a.command || '').trim();
      if (a.background) return out('Starting background process', cmd.slice(0, 120));
      return out('Running', cmd.slice(0, 160));
    }
    case 'process_control': {
      const act = String(a.action || '').toLowerCase();
      const job = String(a.job_id || '').slice(0, 40);
      const I = { list: 'grid_view', poll: 'data_usage', log: 'receipt_long', kill: 'cancel' };
      const L = { list: 'Listing background processes', poll: 'Checking background process',
                  log: 'Reading process log', kill: 'Stopping background process' };
      return R(I[act] || 'pending', L[act] || 'Managing background process', job, 'green');
    }
    case 'code_intel': {
      const act = String(a.action || '').toLowerCase();
      const I = { diagnostics: 'monitor_heart', definition: 'my_location', references: 'format_list_bulleted',
                  hover: 'help_outline', symbols: 'account_tree', servers: 'dns' };
      const L = { diagnostics: 'Checking code diagnostics', definition: 'Finding definition',
                  references: 'Finding references', hover: 'Inspecting type & docs',
                  symbols: 'Mapping file symbols', servers: 'Checking language servers' };
      return R(I[act] || 'monitor_heart', L[act] || 'Asking the language server', path, 'cyan');
    }
    case 'web_search': {
      const q = String(a.query || '').trim();
      return out('Searching web', (q.split(/\s+/) || [''])[0].slice(0, 40));
    }
    case 'deep_research': return out('Deep research', String(a.query || '').slice(0, 100));
    case 'browser': {
      const act = String(a.action || '').toLowerCase();
      const host = zelineShortHost(a.url);
      const sel = String(a.selector || '').slice(0, 60);
      const I = { open: 'open_in_new', text: 'article', click: 'ads_click', type: 'keyboard',
                  screenshot: 'photo_camera', links: 'link', eval: 'javascript', close: 'tab_unselected' };
      const L = { open: ['Opening page', host], text: ['Reading page text', sel], click: ['Clicking', sel],
                  type: ['Typing into', sel], screenshot: ['Capturing screenshot', path],
                  links: ['Listing page links', ''], eval: ['Running JavaScript on the page', ''],
                  close: ['Closing the browser', ''] };
      const e = L[act] || ['Driving the browser', ''];
      return R(I[act] || 'public', e[0], e[1], 'cyan');
    }
    case 'git': {
      const act = String(a.action || '').toLowerCase();
      const I = { status: 'scatter_plot', diff: 'compare_arrows', log: 'timeline', show: 'commit',
                  branch: 'account_tree', add: 'add_circle', commit: 'check_circle' };
      const L = { status: 'Checking git status', diff: 'Reading the diff', log: 'Reading commit history',
                  show: 'Reading a commit', branch: 'Listing branches', add: 'Staging changes', commit: 'Committing' };
      const detail = act === 'commit' ? String(a.message || '').split('\n')[0].slice(0, 60)
                   : act === 'add' ? zelineShortPath(a.path) : '';
      return R(I[act] || 'merge', L[act] || 'Running git', detail, 'orange');
    }
    case 'schedule_task': {
      const act = String(a.action || '').toLowerCase();
      const job = String(a.job_id || '').slice(0, 32);
      const I = { add: 'event', list: 'calendar_month', show: 'event_note', pause: 'pause_circle',
                  resume: 'play_circle', run: 'play_circle', remove: 'event_busy' };
      const L = { add: 'Scheduling a job', list: 'Checking scheduled jobs', show: 'Reading scheduled job',
                  pause: 'Pausing scheduled job', resume: 'Resuming scheduled job',
                  run: 'Running scheduled job now', remove: 'Removing scheduled job' };
      return R(I[act] || 'calendar_month', L[act] || 'Managing scheduled jobs',
               act === 'add' ? String(a.schedule || '').slice(0, 40) : job, 'yellow');
    }
    case 'http_request': return out('Calling API', String(a.url || '').slice(0, 120));
    case 'delegate_task': return out('Delegating', String(a.goal || '').slice(0, 100));
    case 'runtime_info': return out('Checking runtime: model & provider');
    case 'ask_user':     return out('Asking you', String(a.question || '').slice(0, 80));
    case 'network_route': {
      const act = String(a.action || '').toLowerCase();
      const L = { list: 'Listing network routes', add: 'Adding network route',
                  remove: 'Removing network route', test: 'Testing network route' };
      return out(L[act] || 'Managing network routes', String(a.label || '').slice(0, 60));
    }
    case 'system_env':    return out('Checking system environment');
    case 'generate_image':return out('Generating image', String(a.prompt || '').slice(0, 100));
    case 'analyze_media': {
      const t = String(a.path_or_url || '').toLowerCase();
      const audio = ['.ogg','.oga','.opus','.mp3','.m4a','.wav','.flac','.aac','.amr',
                     '.mp4','.webm','.mov','.mkv','.avi','.m4v','.3gp'].some(x => t.endsWith(x));
      return audio ? R('graphic_eq', 'Transcribing audio', '', 'pink') : out('Looking at image');
    }
    case 'image':  return R('image', 'Looking at image', String(a.path || a.url || '').slice(0, 80), 'pink');
    case 'model':  return R('smart_toy', 'Checking model', String(a.model || a.name || '').slice(0, 80), 'blue');

    /* ── RUNTIME KE-89: NARASI AGENT ──────────────────────────────────────
       Agent BICARA, bukan lapor status. Contoh:
         "(icon) Zeline : Eh file-nya nggak ada, gua cari dulu"
         "(icon) Zeline : Ada 2 opsi, gua pilih A karena lebih aman"
       Label = "Zeline", detail = kalimat narasinya. */
    case 'narration': {
      const line = String(a.text || a.content || a.detail || '').trim();
      return R('chat', 'Zeline', line, 'white');
    }

    /* ── Stream / lifecycle events (label default; gateway title wins) ── */
    case 'stream.started':
    case 'assistant.thinking': return R('spark', 'Thinking', '', 'yellow');
    case 'reasoning':          return R('spark', 'Reasoning', '', 'yellow');
    case 'planning':           return R('account_tree', 'Planning', '', 'cyan');
    case 'assistant.delta':    return R('edit', 'Writing', '', 'grey');
    case 'file.read':          return R('description', 'Reading data', String(a.path || '').slice(0, 80), 'blue');
    case 'file.updated':       return R('pencil', 'Editing', String(a.path || '').slice(0, 80), 'orange');
    case 'code.started':       return R('code', 'Running / Coding', String(a.language || 'python').slice(0, 40), 'green');
    case 'tool.completed':
    case 'code.completed':     return R('check_circle', 'Reflecting', '', 'purple');
    case 'tool.failed':        return R('close', 'Failed', '', 'red');
    case 'stream.error':       return R('provider', 'Waiting for Provider Response', '', 'red');
    case 'stream.cancelled':   return R('cancel', 'Cancelled', '', 'grey');
    case 'self.improvement':
    case 'skill.updated':      return R('spark', 'Improvement', '', 'purple');
    default: {
      if (String(tool || '').startsWith('mcp__')) {
        const parts = String(tool).slice('mcp__'.length).split('__');
        return R('hub', `${(parts[1] || 'tool').replace(/_/g, ' ')} via ${(parts[0] || '').replace(/_/g, ' ')}`);
      }
      const label = String(tool || 'Processing').replace(/_/g, ' ');
      let first = '';
      if (a && typeof a === 'object') { const v = Object.values(a)[0]; if (v != null) first = String(v).slice(0, 80); }
      return { label, detail: first, icon: 'help_outline', tone: 'grey' };
    }
  }
}
