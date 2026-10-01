/* Zeline Settings Center — content engine for the sidebar pages.
   Data source: /api/v1/settings/<page> (server.py reads the real Zeline
   runtime config ~/.zeline/config.json + usage.db). Local-only preferences
   persist via the same API (~/.zeline/app_settings.json). No fake features:
   anything without backend support is labelled unavailable / coming soon. */
'use strict';

const SETTINGS_PAGES = {
  profile: { title: 'Profile', icon: 'person', keywords: 'name agent preference language timezone' },
  setup: { title: 'Setup your Zeline', icon: 'agentchip', keywords: 'install diagnostics doctor config runtime cli termux' },
  subscription: { title: 'Subscription / Plan', icon: 'library', keywords: 'plan billing free pro upgrade' },
  'access-token': { title: 'Access Token', icon: 'key', keywords: 'token connect runtime cli pairing link app terminal copy' },
  privacy: { title: 'Privacy', icon: 'lock', keywords: 'history memory personalization data export delete conversations' },
  'security-logs': { title: 'Security Logs', icon: 'clock', keywords: 'activity login events device' },
  notifications: { title: 'Notifications', icon: 'bell', keywords: 'agent automations security system push' },
  voice: { title: 'Voice', icon: 'music', keywords: 'voice mode microphone push to talk speed auto play' },
  appearance: { title: 'Appearance', icon: 'moon', keywords: 'theme dark light density animations reduce motion sidebar' },
  accent: { title: 'Accent Color', icon: 'spark', keywords: 'color theme highlight blue purple cyan green orange red pink custom' },
  language: { title: 'Language', icon: 'workspace', keywords: 'english indonesian translation i18n device language' },
  about: { title: 'About', icon: 'info', keywords: 'version build license github changelog security zerolinear open source' },
};

const ACCENT_MAP = {
  blue: '#2f7fe8', purple: '#8b7cff', cyan: '#2bbfa7', green: '#3ecf7a',
  orange: '#d99b37', red: '#e35d5d', pink: '#e377c2',
};

let settingsState = { page: null, data: null, saving: false, query: '' };

function settingsApi(path, options = {}) {
  return api(`/settings/${path}`, { timeoutMs: 15000, ...options });
}

function settingsOverlay() {
  let overlay = $('settingsOverlay');
  if (overlay) return overlay;
  overlay = el('div', 'settings-overlay');
  overlay.id = 'settingsOverlay';
  overlay.innerHTML = `
    <div class="settings-shell" role="dialog" aria-modal="true" aria-label="Settings">
      <header class="settings-shell-head">
        <button class="settings-shell-back" type="button" aria-label="Close settings">${ZI('chevleft')}</button>
        <div class="settings-shell-title"><strong id="settingsPageTitle">Settings</strong><small id="settingsPageHint">Control center for your agent</small></div>
        <span class="settings-save-state" id="settingsSaveState"></span>
      </header>
      <div class="settings-shell-body" id="settingsBody"></div>
    </div>`;
  document.body.appendChild(overlay);
  overlay.querySelector('.settings-shell-back').onclick = closeSettingsPage;
  overlay.addEventListener('pointerdown', event => {
    if (event.target === overlay) closeSettingsPage();
  });
  return overlay;
}

function setSaveState(text, tone) {
  const slot = $('settingsSaveState');
  if (!slot) return;
  slot.textContent = text || '';
  slot.dataset.tone = tone || '';
}

async function openSettingsPage(page) {
  if (!SETTINGS_PAGES[page]) return;
  const overlay = settingsOverlay();
  settingsState = { page, data: null, saving: false, query: settingsState.query };
  $('settingsPageTitle').textContent = SETTINGS_PAGES[page].title;
  $('settingsPageHint').textContent = 'Control center for your agent';
  const body = $('settingsBody');
  body.innerHTML = `<div class="settings-loading"><span class="settings-spinner"></span>Loading ${SETTINGS_PAGES[page].title.toLowerCase()}…</div>`;
  overlay.classList.add('open');
  document.body.classList.add('settings-open');
  setSaveState('');
  try {
    const data = await settingsApi(page);
    settingsState.data = data;
    renderSettingsPage();
  } catch (error) {
    body.innerHTML = `<div class="settings-error">${ZI('warning')}<strong>Failed to load</strong><small>${esc(error?.message || 'Settings backend unavailable')}</small><button class="btn sm" type="button" id="settingsRetry">Retry</button></div>`;
    $('settingsRetry')?.addEventListener('click', () => openSettingsPage(page));
  }
}

function closeSettingsPage() {
  const overlay = $('settingsOverlay');
  overlay?.classList.remove('open');
  document.body.classList.remove('settings-open');
}

/* ---------- shared builders ---------- */

function sectionEl(label, inner) {
  return `<section class="st-section"><h4>${esc(label)}</h4>${inner}</section>`;
}

function rowKV(label, value, opts = {}) {
  const v = value == null || value === '' ? '<em class="st-na">Not available</em>' : `<b>${esc(String(value))}</b>`;
  return `<div class="st-row"><span>${esc(label)}</span>${v}</div>`;
}

function rowToggle(id, label, desc, checked, opts = {}) {
  const disabled = opts.disabled ? 'disabled' : '';
  const note = opts.unavailable ? `<small class="st-tag">Not available</small>` : '';
  return `<label class="st-toggle" data-setting="${esc(id)}"><span><strong>${esc(label)}</strong><small>${esc(desc || '')}</small></span>${note}<input type="checkbox" data-toggle="${esc(id)}" ${checked ? 'checked' : ''} ${disabled}><i></i></label>`;
}

function rowChoice(name, label, desc, options, current, opts = {}) {
  const buttons = options.map(opt => {
    const value = typeof opt === 'string' ? opt : opt.id;
    const text = typeof opt === 'string' ? opt : opt.label;
    return `<button type="button" data-choice-name="${esc(name)}" data-choice-value="${esc(value)}" class="${value === current ? 'active' : ''}">${esc(text)}</button>`;
  }).join('');
  return `<div class="st-choice" data-choice-group="${esc(name)}"><span><strong>${esc(label)}</strong><small>${esc(desc || '')}</small></span><div class="st-choice-row">${buttons}</div></div>`;
}

function rowAction(id, label, desc, opts = {}) {
  const kind = opts.kind ? ` ${opts.kind}` : '';
  const status = opts.disabled
    ? `<span class="st-action-status">${esc(opts.tag || 'Not available')}</span>`
    : '';
  const button = opts.disabled
    ? ''
    : `<button type="button" class="btn sm${kind}" data-action="${esc(id)}">${esc(opts.cta || label)}</button>`;
  return `<div class="st-action${opts.disabled ? ' is-disabled' : ''}"><span><strong>${esc(label)}</strong><small>${esc(desc || '')}</small>${status}</span>${button}</div>`;
}

function cmdRow(label, command) {
  return `<div class="st-cmd"><span>${esc(label)}</span><code>${esc(command)}</code><button type="button" class="st-copy" data-copy="${esc(command)}" aria-label="Copy ${esc(command)}">${ZI('copy')}</button></div>`;
}

function stateLabel(state) {
  return { allow: 'Allow', ask: 'Ask every time', deny: 'Deny' }[state] || state;
}

async function persistSection(section, payload) {
  if (settingsState.saving) return null;
  settingsState.saving = true;
  setSaveState('Saving…', 'busy');
  try {
    const data = await settingsApi(section, { method: 'POST', body: payload });
    setSaveState('Saved', 'ok');
    setTimeout(() => setSaveState(''), 1800);
    return data;
  } catch (error) {
    setSaveState('Failed to save', 'err');
    toast(error?.message || 'Failed to save', 'err', 2200);
    return null;
  } finally {
    settingsState.saving = false;
  }
}

function confirmDanger({ title, message, requireText, cta, onConfirm }) {
  const body = el('div', 'danger-confirm');
  body.innerHTML = `<p>${esc(message).replace(/\n/g, '<br>')}</p>${requireText ? `<label class="field"><span>Type <b>${esc(requireText)}</b> to continue</span><input id="dangerConfirmInput" autocomplete="off" placeholder="${esc(requireText)}"></label>` : ''}`;
  modal({
    title,
    body,
    compact: true,
    actions: [
      { label: 'Cancel' },
      {
        label: cta || 'Confirm', kind: 'danger',
        onClick: () => {
          if (requireText) {
            const input = body.querySelector('#dangerConfirmInput');
            if ((input.value || '').trim() !== requireText) {
              input.focus();
              input.classList.add('invalid');
              toast(`Type ${requireText} to continue`, 'warn', 2000);
              return;
            }
          }
          closeModal();
          onConfirm();
        },
      },
    ],
  });
}

/* ---------- pages ---------- */

function renderSettingsPage() {
  const { page, data } = settingsState;
  const body = $('settingsBody');
  if (!body || !data) return;
  const renderers = {
    profile: renderProfile,
    setup: renderSetup, subscription: renderSubscription,
    'access-token': renderAccessToken,
    privacy: renderPrivacy, 'security-logs': renderSecurityLogs,
    notifications: renderNotifications, voice: renderVoice,
    appearance: renderAppearance, accent: renderAccent, language: renderLanguage,
    about: renderAbout,
  };
  const renderer = renderers[page];
  body.innerHTML = renderer ? renderer(data) : '<div class="settings-error">Unknown page</div>';
  wireSettingsBody(body);
}

function renderProfile(d) {
  const p = d.profile || {};
  const a = d.account || {};
  const name = p.agent_call_name || 'Zeline User';
  const initials = name.trim().split(/\s+/).map(x => x[0]).join('').slice(0, 2).toUpperCase() || 'Z';
  return `
    <div class="st-hero">${ZI('person')}<strong>One name, one agent.</strong><small>No social profile is needed here. These preferences only shape how Zeline addresses you.</small></div>
    ${sectionEl('Agent identity', `
      <div class="st-identity"><span class="st-avatar">${esc(initials)}</span><span><strong>${esc(name)}</strong><small>Used inside your Zeline runtime</small></span></div>
      <label class="field"><span>What should your agent call you?</span><input data-field="agent_call_name" value="${esc(p.agent_call_name || '')}" placeholder="Mahesa"></label>
    `)}
    ${sectionEl('Language & region', `
      ${rowChoice('response_language', 'Response language', '', ['Indonesian', 'English'], p.response_language || 'Indonesian')}
      <label class="field"><span>Time zone</span><input data-field="timezone" value="${esc(p.timezone || 'Asia/Jakarta')}" placeholder="Asia/Jakarta"></label>
    `)}
    ${sectionEl('Runtime', `
      ${rowKV('Connection', a.status === 'Active' ? 'Zeline CLI runtime' : a.status)}
      ${rowAction('profile-save', 'Save profile', 'Writes these local preferences to Zeline.', { kind: 'primary', cta: 'Save' })}
    `)}`;
}


function renderSetup(d) {
  const check = item => `<div class="st-check ${item.ok ? 'ok' : 'pending'}"><span class="st-check-ic">${item.ok ? '✓' : '○'}</span><span><strong>${esc(item.label)}</strong><small>${esc(item.desc || '')}</small></span></div>`;
  return `
    <div class="st-hero">${ZI('agentchip')}<strong>${d.ready ? 'Your agent is ready.' : 'Setup incomplete'}</strong><small>Runtime status for the Zeline CLI this app connects to.</small></div>
    ${sectionEl('Checklist', (d.checks || []).map(check).join(''))}
    ${d.optional?.length ? sectionEl('Optional', d.optional.map(check).join('')) : ''}
    ${sectionEl('Commands', (d.commands || []).map(c => cmdRow(c.label, c.command)).join(''))}
    ${sectionEl(`Local install — ${esc(d.install?.environment || 'Termux')}`, (d.install?.steps || []).map(s => cmdRow(s.label, s.command)).join(''))}
    ${d.config_error ? `<p class="st-note">Config read fallback: ${esc(d.config_error)}</p>` : ''}`;
}

function renderSubscription(d) {
  const plan = d.plan || {};
  return `
    <div class="st-hero">${ZI('library')}<strong>${esc(plan.name || 'Free')}</strong><small>${esc(plan.status || '')} · ${esc(plan.source || '')}</small></div>
    ${sectionEl('Current plan', `
      ${rowKV('Plan', plan.name)}
      ${rowKV('Billing status', plan.status)}
      ${rowKV('Renewal date', plan.renewal)}
      ${(d.capabilities || []).map(c => `<div class="st-check ok"><span class="st-check-ic">✓</span><span><strong>${esc(c)}</strong></span></div>`).join('')}
    `)}
    ${sectionEl('Billing', `
      <div class="st-warn">${ZI('info')}<span>${esc(d.billing?.note || '')}</span></div>
      ${rowAction('billing-upgrade', 'Upgrade', 'Billing backend is not available in this build.', { disabled: true, tag: 'Coming soon' })}
      ${rowAction('billing-manage', 'Manage billing', 'Available when billing lands.', { disabled: true, tag: 'Coming soon' })}
      ${rowAction('billing-history', 'Billing history', 'No billing backend connected.', { disabled: true, tag: 'Coming soon' })}
    `)}`;
}

function renderAccessToken(d) {
  const t = d.access_token || {};
  const c = d.connection || {};
  const configured = Boolean(t.configured);
  return `
    <div class="st-hero">${ZI('key')}<strong>Connect the app to your runtime.</strong><small>${esc(c.note || '')}</small></div>
    ${sectionEl('Runtime access', `
      ${rowKV('Status', t.status)}
      <div class="st-row"><span>Access token</span><b class="mono">${esc(t.hint || 'Not configured')}</b></div>
      ${rowKV('Endpoint', c.endpoint)}
      ${rowKV('Scope', t.scope)}
      ${rowKV('Source', t.source)}
    `)}
    ${sectionEl('How it works', `
      ${rowKV('Runtime', c.runtime)}
      ${rowKV('Transport', c.transport)}
      <p class="st-note">Provider API keys, model selection, tools, and gateways remain managed by Zeline in the terminal. This page only connects this app to that runtime.</p>
    `)}
    ${sectionEl('Pair this app', `
      ${rowAction('token-copy', 'Copy access token', configured ? 'Copy the runtime token, then paste it into the app connection screen.' : 'Configure the Zeline App gateway in the terminal first.', { kind: 'primary', cta: 'Copy token', disabled: !configured, tag: 'Not configured' })}
    `)}`;
}

function renderPrivacy(d) {
  const p = d.privacy || {};
  const notes = d.notes || {};
  const impl = d.implemented || {};
  return `
    ${sectionEl('Conversations', rowToggle('conversation_history', 'Conversation history', notes.conversation_history, p.conversation_history))}
    ${sectionEl('Memory', rowToggle('memory', 'Long-term memory', notes.memory, p.memory))}
    ${sectionEl('Personalization', rowToggle('personalization', 'Remember preferences', notes.personalization, p.personalization))}
    ${sectionEl('Data', `
      ${rowToggle('analytics', 'Analytics', notes.analytics, p.analytics, { unavailable: !impl.analytics })}
      ${rowToggle('crash_reports', 'Crash reports', notes.crash_reports, p.crash_reports, { unavailable: !impl.crash_reports })}
    `)}
    ${sectionEl('Export', rowAction('privacy-export', 'Export my data', 'Download your local settings as JSON.', { cta: 'Export' }))}
    ${sectionEl('Delete', `
      ${rowAction('privacy-delete-conversations', 'Delete conversations', 'Remove every local session and its messages.', { kind: 'danger', cta: 'Delete' })}
      ${rowAction('privacy-delete-memory', 'Delete memory', 'Erase long-term agent memory files on this device.', { kind: 'danger', cta: 'Delete' })}
    `)}`;
}

function renderSecurityLogs(d) {
  const events = (d.events || []).map(e => `
    <div class="st-event"><span class="st-event-ic ${e.status === 'ok' ? 'ok' : 'warn'}"></span>
      <span><strong>${esc(e.event)}</strong><small>${esc(e.detail || '')}</small><small>${esc(e.ts || '')} · ${esc(e.device || '')}</small></span>
    </div>`).join('');
  const devices = (d.devices || []).map(dev => rowKV(dev.name, dev.current ? 'This device · ' + dev.kind : dev.kind)).join('');
  return `
    ${sectionEl('This device', devices)}
    ${sectionEl('Activity', `<label class="field st-search"><span>Search events</span><input id="securitySearch" type="search" placeholder="Search" autocomplete="off"></label><div id="securityEvents">${events || '<div class="st-empty">No security events yet.</div>'}</div>`)}`;
}

function renderNotifications(d) {
  const n = d.notifications || {};
  return `
    ${sectionEl('Agent', `
      ${rowToggle('task_completed', 'Task completed', '', n.task_completed)}
      ${rowToggle('task_failed', 'Task failed', '', n.task_failed)}
      ${rowToggle('needs_approval', 'Agent needs approval', '', n.needs_approval)}
      ${rowToggle('needs_input', 'Agent needs your input', '', n.needs_input)}
    `)}
    ${sectionEl('Automations', `
      ${rowToggle('automation_completed', 'Automation completed', '', n.automation_completed)}
      ${rowToggle('automation_failed', 'Automation failed', '', n.automation_failed)}
    `)}
    ${sectionEl('Security', `
      ${rowToggle('new_login', 'New login', '', n.new_login)}
      ${rowToggle('new_device', 'New device', '', n.new_device)}
      ${rowToggle('permission_changed', 'Permission changed', '', n.permission_changed)}
    `)}
    ${sectionEl('System', `
      ${rowToggle('updates', 'Updates', '', n.updates)}
      ${rowToggle('errors', 'Errors', '', n.errors)}
    `)}`;
}

function renderVoice(d) {
  const v = d.voice || {};
  return `
    <div class="st-hero">${ZI('music')}<strong>Voice preferences</strong><small>${esc(d.supported?.note || '')}</small></div>
    ${sectionEl('Voice mode', rowChoice('voice_mode', 'Voice mode', '', [{ id: 'off', label: 'Off' }, { id: 'on', label: 'On' }], v.mode || 'off'))}
    ${sectionEl('Input', rowChoice('voice_input', 'Microphone', '', [{ id: 'push_to_talk', label: 'Push to talk' }, { id: 'microphone', label: 'Open microphone' }], v.input || 'push_to_talk'))}
    ${sectionEl('Output', `
      <label class="field"><span>Voice</span><select data-field="voice">${(d.voices || []).map(x => `<option value="${esc(x.id)}" ${v.voice === x.id ? 'selected' : ''}>${esc(x.label)}</option>`).join('')}</select></label>
      <label class="field"><span>Speed</span><input type="range" min="0.5" max="2" step="0.1" value="${esc(String(v.speed ?? 1))}" data-field="speed"><small class="st-range-value">${esc(String(v.speed ?? 1))}×</small></label>
      ${rowToggle('auto_play', 'Auto-play responses', 'Voice backend is not connected yet — saved for when it lands.', v.auto_play, { unavailable: true })}
    `)}`;
}

function renderAppearance(d) {
  const a = d.appearance || {};
  return `
    ${sectionEl('Theme', rowChoice('theme', 'Theme', '', [{ id: 'system', label: 'System' }, { id: 'light', label: 'Light' }, { id: 'dark', label: 'Dark' }], a.theme || 'dark'))}
    ${sectionEl('Layout', `
      ${rowChoice('density', 'Interface density', '', [{ id: 'comfortable', label: 'Comfortable' }, { id: 'compact', label: 'Compact' }], a.density || 'comfortable')}
      ${rowChoice('sidebar', 'Sidebar', '', [{ id: 'expanded', label: 'Expanded' }, { id: 'collapsed', label: 'Collapsed' }], a.sidebar || 'expanded')}
    `)}
    ${sectionEl('Motion', `
      ${rowToggle('animations', 'Animations', '', a.animations !== false)}
      ${rowToggle('reduce_motion', 'Reduce motion', '', !!a.reduce_motion)}
    `)}`;
}

function renderAccent(d) {
  const a = d.appearance || {};
  const current = a.accent || 'blue';
  const swatches = (d.accents || []).map(c => `
    <button type="button" class="st-swatch ${current === c.id ? 'active' : ''}" data-accent-id="${esc(c.id)}" style="--sw:${esc(c.color)}"><i></i><span>${esc(c.label)}</span></button>`).join('');
  return `
    <div class="st-hero">${ZI('spark')}<strong>Accent color</strong><small>Highlights buttons, switches, links, and focus states.</small></div>
    ${sectionEl('Presets', `<div class="st-swatch-grid">${swatches}</div>`)}
    ${sectionEl('Custom', `
      <label class="field st-custom-color"><span>Custom color</span><input type="color" id="accentCustom" value="${esc(a.accent_custom || '#2f7fe8')}"><code>${esc(a.accent_custom || '')}</code></label>
    `)}
    ${sectionEl('Preview', `
      <div class="st-preview">
        <button type="button" class="btn primary sm">Primary button</button>
        <label class="st-toggle"><span><strong>Switch</strong></span><input type="checkbox" checked disabled><i></i></label>
        <a href="#" onclick="return false" class="st-link">Active link</a>
        <span class="st-status-dot">● Agent ready</span>
      </div>
      <p class="st-note">Preview updates live as you pick a color.</p>
    `)}`;
}

function renderLanguage(d) {
  const l = d.language || {};
  return `
    ${sectionEl('Language', `
      ${rowChoice('language_mode', 'Source', '', [{ id: 'device', label: 'Use device language' }, { id: 'manual', label: 'Choose manually' }], l.mode || 'manual')}
      <label class="field"><span>Current language</span><select data-field="language" ${l.mode === 'device' ? 'disabled' : ''}>${(d.languages || []).map(x => `<option value="${esc(x.id)}" ${l.language === x.id ? 'selected' : ''}>${esc(x.label)}</option>`).join('')}</select></label>
      <div class="st-row"><span>System language</span><b>${esc(navigator.language || '—')}</b></div>
    `)}
    <p class="st-note">${esc(d.architecture || '')}</p>`;
}

function renderAbout(d) {
  return `
    <div class="st-about">
      <img src="assets/zeline-logo.png?v=2" alt="Zeline" draggable="false" onerror="this.style.display='none'">
      <strong>${esc(d.name || 'Zeline')}</strong>
      <small>${esc(d.tagline || '')} · by ${esc(d.by || 'Zerolinear')}</small>
      ${d.open_source ? '<span class="st-tag ok">Open source</span>' : ''}
    </div>
    ${sectionEl('Build', `
      ${rowKV('Version', d.version)}
      ${rowKV('Build', d.build)}
      ${rowKV('Environment', d.environment)}
      ${rowKV('License', d.license)}
    `)}
    ${sectionEl('Links', (d.links || []).map(l => `<a class="st-link-row" href="${esc(l.url)}" target="_blank" rel="noopener noreferrer"><span>${esc(l.label)}</span><span class="settings-chevron">${ZI('chevron')}</span></a>`).join(''))}`;
}

/* ---------- wiring ---------- */

function wireSettingsBody(body) {
  const { page } = settingsState;

  body.querySelectorAll('[data-copy]').forEach(btn => {
    btn.onclick = async () => {
      try { await navigator.clipboard.writeText(btn.dataset.copy); toast('Copied', 'ok', 1200); }
      catch (_) { toast('Could not copy', 'warn', 1500); }
    };
  });

  body.querySelectorAll('[data-action]').forEach(btn => {
    btn.onclick = () => handleSettingsAction(btn.dataset.action, body);
  });

  if (page === 'profile') {
    const collect = () => {
      const payload = {};
      body.querySelectorAll('[data-field]').forEach(input => { payload[input.dataset.field] = input.value; });
      payload.response_language = body.querySelector('[data-choice-name="response_language"].active')?.dataset.choiceValue || 'Indonesian';
      return payload;
    };
    body.querySelectorAll('[data-choice-name="response_language"]').forEach(btn => {
      btn.onclick = () => {
        body.querySelectorAll('[data-choice-name="response_language"]').forEach(b => b.classList.toggle('active', b === btn));
      };
    });
    body.dataset.collectProfile = '1';
    body._collectProfile = collect;
  }

  if (page === 'privacy') {
    body.querySelectorAll('[data-toggle]').forEach(input => {
      input.onchange = async () => {
        const result = await persistSection('privacy', { [input.dataset.toggle]: input.checked });
        if (!result) input.checked = !input.checked;
      };
    });
  }

  if (page === 'notifications') {
    body.querySelectorAll('[data-toggle]').forEach(input => {
      input.onchange = async () => {
        const result = await persistSection('notifications', { [input.dataset.toggle]: input.checked });
        if (!result) input.checked = !input.checked;
      };
    });
  }

  if (page === 'appearance') {
    body.querySelectorAll('[data-choice-name]').forEach(btn => {
      btn.onclick = async () => {
        const name = btn.dataset.choiceName;
        const value = btn.dataset.choiceValue;
        const result = await persistSection('appearance', { [name]: value });
        if (result) {
          body.querySelectorAll(`[data-choice-name="${name}"]`).forEach(b => b.classList.toggle('active', b.dataset.choiceValue === value));
          if (name === 'theme') applyTheme(value === 'system' ? (matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark') : value);
          document.body.classList.toggle('density-compact', (result.appearance || {}).density === 'compact');
        }
      };
    });
    body.querySelectorAll('[data-toggle]').forEach(input => {
      input.onchange = async () => {
        const result = await persistSection('appearance', { [input.dataset.toggle]: input.checked });
        if (!result) input.checked = !input.checked;
      };
    });
  }

  if (page === 'accent') {
    const applyAccent = (id, custom) => {
      const color = id === 'custom' ? (custom || '#2f7fe8') : ACCENT_MAP[id];
      document.documentElement.style.setProperty('--accent', color);
      localStorage.setItem('zeline.accent', id);
      if (custom) localStorage.setItem('zeline.accent_custom', custom);
    };
    body.querySelectorAll('[data-accent-id]').forEach(btn => {
      btn.onclick = async () => {
        const id = btn.dataset.accentId;
        applyAccent(id);
        await persistSection('appearance', { accent: id });
        body.querySelectorAll('[data-accent-id]').forEach(b => b.classList.toggle('active', b === btn));
      };
    });
    const custom = body.querySelector('#accentCustom');
    if (custom) {
      custom.onchange = async () => {
        applyAccent('custom', custom.value);
        await persistSection('appearance', { accent: 'custom', accent_custom: custom.value });
        body.querySelectorAll('[data-accent-id]').forEach(b => b.classList.remove('active'));
      };
    }
  }

  if (page === 'language') {
    body.querySelectorAll('[data-choice-name="language_mode"]').forEach(btn => {
      btn.onclick = async () => {
        const mode = btn.dataset.choiceValue;
        const result = await persistSection('language', { mode });
        if (result) renderSettingsPage();
      };
    });
    const select = body.querySelector('[data-field="language"]');
    if (select) {
      select.onchange = async () => {
        const result = await persistSection('language', { language: select.value });
        if (result) document.documentElement.lang = select.value;
      };
    }
  }

  if (page === 'voice') {
    body.querySelectorAll('[data-choice-name]').forEach(btn => {
      btn.onclick = async () => {
        const name = btn.dataset.choiceName.replace('voice_', '');
        const result = await persistSection('voice', { [name]: btn.dataset.choiceValue });
        if (result) body.querySelectorAll(`[data-choice-name="voice_${name}"]`).forEach(b => b.classList.toggle('active', b === btn));
      };
    });
    body.querySelectorAll('[data-field]').forEach(input => {
      input.onchange = async () => {
        if (input.dataset.field === 'speed') {
          body.querySelector('.st-range-value').textContent = `${input.value}×`;
        }
        await persistSection('voice', { [input.dataset.field]: input.type === 'checkbox' ? input.checked : input.value });
      };
    });
    const autoPlay = body.querySelector('[data-toggle="auto_play"]');
    if (autoPlay) {
      autoPlay.onchange = async () => {
        const result = await persistSection('voice', { auto_play: autoPlay.checked });
        if (!result) autoPlay.checked = !autoPlay.checked;
      };
    }
  }

  if (page === 'security-logs') {
    const search = body.querySelector('#securitySearch');
    if (search) {
      search.oninput = () => {
        const q = search.value.trim().toLowerCase();
        body.querySelectorAll('.st-event').forEach(row => {
          row.hidden = q && !row.textContent.toLowerCase().includes(q);
        });
      };
    }
  }
}

async function handleSettingsAction(action, body) {
  if (action === 'profile-save') {
    const payload = body._collectProfile ? body._collectProfile() : {};
    await persistSection('profile', payload);
  } else if (action === 'privacy-export') {
    try {
      const data = await settingsApi('privacy');
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = el('a');
      a.href = url;
      a.download = `zeline-privacy-export-${Date.now()}.json`;
      a.click();
      URL.revokeObjectURL(url);
      toast('Export downloaded', 'ok', 1800);
    } catch (_) { toast('Export failed', 'err', 2000); }
  } else if (action === 'privacy-delete-conversations') {
    confirmDanger({
      title: 'Delete all conversations?',
      message: 'Every local session and its messages will be permanently removed. This cannot be undone.',
      requireText: 'DELETE',
      cta: 'Delete conversations',
      onConfirm: async () => {
        const result = await persistSection('privacy-delete-conversations', {});
        if (result) toast('Conversations deleted', 'ok', 2000);
      },
    });
  } else if (action === 'privacy-delete-memory') {
    confirmDanger({
      title: 'Delete agent memory?',
      message: 'Long-term memory files on this device will be erased. Your agent will not remember past preferences.',
      requireText: 'DELETE',
      cta: 'Delete memory',
      onConfirm: async () => {
        const result = await persistSection('privacy-delete-memory', {});
        if (result) toast('Memory deleted', 'ok', 2000);
      },
    });
  } else if (action === 'token-copy') {
    try {
      const result = await settingsApi('access-token-reveal', { method: 'POST', body: {} });
      const value = result?.access_token_value;
      if (!value) throw new Error('Access token unavailable');
      await navigator.clipboard.writeText(value);
      toast('Access token copied', 'ok', 1800);
    } catch (error) {
      toast(error?.message || 'Could not copy access token', 'err', 2400);
    }
  }
}

/* Sidebar integration: replace the modal stubs with the full settings pages. */
function settingsGo(action) {
  if (action === 'logout') {
    confirmDanger({
      title: 'Log out?',
      message: "You're currently signed in on this device.",
      cta: 'Log out from this device',
      onConfirm: () => { if (typeof window.zelineLogout === 'function') window.zelineLogout(); },
    });
    return true;
  }
  if (SETTINGS_PAGES[action]) {
    openSettingsPage(action);
    return true;
  }
  return false;
}

window.settingsGo = settingsGo;
window.openSettingsPage = openSettingsPage;
