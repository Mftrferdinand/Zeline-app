#!/usr/bin/env python3
"""Rewrite providerForm() so the two dialects are TABS inside one screen.

Tapping "Add Provider" opens a new screen. At the top sit two segment buttons
(Anthropic Compatible / OpenAI Compatible). Switching between them rebuilds
only the fields below — the screen, the header and the footer stay put, and
whatever the user already typed into shared fields is carried across.
"""
import pathlib

ROOT = pathlib.Path("/data/data/com.termux/files/home/zeline-frontend")
SRC = ROOT / "app3.js"

NEW = r'''async function providerForm(presetId = '', protocol = '') {
  const presets = await loadProviderPresets();
  const body = el('div', 'provider-form');

  /* One screen, two dialects, switched by the segmented control at the top.
     Only `#pvFields` is rebuilt on switch, so the modal never reopens and the
     values the user already typed survive the change. */
  let dialect = protocol === 'anthropic' ? 'anthropic' : 'openai';

  const options = presets.map(p => ({ value: p.id, label: p.name }));
  const showPresetPicker = Boolean(presetId) && options.length > 0;

  // Segmented switcher — hidden in the preset flow, where the dialect is fixed
  // by the provider that opened the form.
  const seg = el('div', 'pv-seg');
  seg.setAttribute('role', 'tablist');
  seg.innerHTML = `
    <button class="pv-seg-btn" data-dialect="anthropic" type="button" role="tab">
      <strong>Anthropic Compatible</strong>
      <small>/v1/messages</small>
    </button>
    <button class="pv-seg-btn" data-dialect="openai" type="button" role="tab">
      <strong>OpenAI Compatible</strong>
      <small>Chat / Responses</small>
    </button>`;
  if (!showPresetPicker) body.appendChild(seg);

  if (showPresetPicker) {
    body.appendChild(field('Provider', 'pvPreset', {
      tag: 'select', value: presetId, disabled: true,
      hint: 'This provider\'s endpoint is filled in automatically.', options
    }));
  }

  // Everything that depends on the dialect lives here and is re-rendered.
  const fields = el('div', 'pv-fields');
  fields.id = 'pvFields';
  body.appendChild(fields);

  const note = el('small', 'provider-form-note', '');
  body.appendChild(note);

  const protoField = el('input');
  protoField.type = 'hidden';
  protoField.id = 'pvProtocol';
  body.appendChild(protoField);

  /* Carry typed values across a dialect switch. Base URL is deliberately NOT
     carried: the two dialects want different endpoints, and keeping a stale
     OpenAI URL under an Anthropic form is how you get a confusing failure. */
  const carry = () => ({
    name: fields.querySelector('#pvName')?.value ?? '',
    prefix: fields.querySelector('#pvPrefix')?.value ?? '',
    key: fields.querySelector('#pvKey')?.value ?? '',
    model: fields.querySelector('#pvModel')?.value ?? ''
  });

  const renderFields = (keep) => {
    const isAnthropic = dialect === 'anthropic';
    fields.innerHTML = '';
    protoField.value = isAnthropic ? 'anthropic' : 'openai';

    fields.appendChild(field('Name', 'pvName', {
      required: true,
      value: keep?.name || '',
      placeholder: isAnthropic ? 'Anthropic Compatible (Prod)' : 'OpenAI Compatible (Prod)',
      hint: 'Required. A friendly label for this node.'
    }));

    fields.appendChild(field('Prefix', 'pvPrefix', {
      required: true,
      value: keep?.prefix || (isAnthropic ? 'ac-prod' : 'oc-prod'),
      placeholder: isAnthropic ? 'ac-prod' : 'oc-prod',
      hint: 'Required. Used as the provider prefix for model IDs.'
    }));

    // API Type is OpenAI-only: Anthropic has exactly one wire format.
    if (!isAnthropic) {
      const wrap = el('div', 'field');
      wrap.id = 'pvApiTypeWrap';
      wrap.innerHTML = `
        <label for="pvApiType">API Type</label>
        <select id="pvApiType">
          <option value="chat">Chat Completions</option>
          <option value="responses">Responses</option>
        </select>`;
      fields.appendChild(wrap);
    }

    fields.appendChild(field('Base URL', 'pvURL', {
      required: true,
      placeholder: isAnthropic ? 'https://api.anthropic.com/v1' : 'https://api.openai.com/v1',
      hint: isAnthropic
        ? 'Use the base URL (ending in /v1) for your Anthropic-compatible API. The system appends /messages.'
        : 'Use the base URL (ending in /v1) for your OpenAI-compatible API.'
    }));

    fields.appendChild(field('API Key (for Check)', 'pvKey', {
      type: 'password', value: keep?.key || '', placeholder: 'sk-…',
      hint: 'Used for the connection check. Never returned to the browser.'
    }));

    fields.appendChild(field('Model ID', 'pvModel', {
      value: keep?.model || '',
      placeholder: isAnthropic ? 'claude-3-opus' : 'gpt-4o-mini',
      hint: 'Optional. If the provider has no /models endpoint, enter a model ID to validate it via the chat endpoint instead.'
    }));

    // Reflect the active tab and reset any previous check result.
    seg.querySelectorAll('[data-dialect]').forEach(b => {
      const on = b.dataset.dialect === dialect;
      b.classList.toggle('is-active', on);
      b.setAttribute('aria-selected', on ? 'true' : 'false');
    });
    note.className = 'provider-form-note';
    note.textContent = isAnthropic
      ? 'Anthropic: chat endpoint = Base URL + /messages.'
      : 'OpenAI: pick the API Type your endpoint supports.';
    setHead();
  };

  // The screen title follows the active tab, so the new screen is self-evident.
  const setHead = () => {
    const t = document.getElementById('modalTitle');
    if (t) t.textContent = dialect === 'anthropic'
      ? 'Add Anthropic Compatible' : 'Add OpenAI Compatible';
    const sub = document.querySelector('.modal-head-subtitle');
    if (sub) sub.textContent = dialect === 'anthropic'
      ? 'Anthropic-compatible provider — the system appends /messages.'
      : 'OpenAI-compatible provider — choose the API Type it supports.';
  };

  seg.querySelectorAll('[data-dialect]').forEach(btn => {
    btn.onclick = () => {
      if (btn.dataset.dialect === dialect) return;
      const keep = carry();
      dialect = btn.dataset.dialect;
      renderFields(keep);
    };
  });

  renderFields(null);

  // Preset flow: seed Name / Prefix / Base URL from the catalogue entry.
  if (showPresetPicker) {
    const preset = presets.find(p => p.id === presetId);
    if (preset) {
      dialect = preset.protocol === 'anthropic' ? 'anthropic' : 'openai';
      renderFields(null);
      fields.querySelector('#pvURL').value = preset.base_url || '';
      fields.querySelector('#pvName').value = preset.name || '';
      const pfx = fields.querySelector('#pvPrefix');
      if (pfx) pfx.value = (preset.id || '').slice(0, 16);
    }
  }

  modal({
    title: dialect === 'anthropic' ? 'Add Anthropic Compatible' : 'Add OpenAI Compatible',
    subtitle: dialect === 'anthropic'
      ? 'Anthropic-compatible provider — the system appends /messages.'
      : 'OpenAI-compatible provider — choose the API Type it supports.',
    body,
    actions: [
      { label: 'Cancel' },
      { label: 'Check Connection', kind: 'primary', onClick: async () => {
          const isAnthropic = dialect === 'anthropic';
          const base_url = fields.querySelector('#pvURL').value.trim();
          const api_key = fields.querySelector('#pvKey').value;
          const model = fields.querySelector('#pvModel').value.trim();
          const prefix = fields.querySelector('#pvPrefix').value.trim();
          const name = fields.querySelector('#pvName').value.trim();
          const apiType = isAnthropic ? 'messages'
            : (fields.querySelector('#pvApiType')?.value || 'chat');

          const fail = (msg) => {
            note.textContent = msg;
            note.classList.remove('is-set');
            note.classList.add('is-bad');
            toast(msg, 'err');
          };
          if (!name) return fail('Name is required.');
          if (!prefix) return fail('Prefix is required.');
          if (!base_url) return fail('Base URL is required.');
          if (!api_key) return fail('API Key is required for the connection check.');

          note.textContent = 'Checking…';
          note.classList.remove('is-set', 'is-bad');

          try {
            const d = await api('/providers/preflight', {
              method: 'POST', timeoutMs: 20000,
              body: { base_url, api_key, protocol: protoField.value,
                      api_type: apiType, model }
            });
            const models = Array.isArray(d.models) ? d.models : [];
            const modelOk = model ? models.includes(model) : null;
            const parts = [
              'VALID — endpoint responded.',
              `${d.model_count || models.length} models available`,
              `${d.protocol || protoField.value} · ${apiType}`,
              `${d.latency_ms}ms`
            ];
            if (model) {
              parts.push(modelOk
                ? `model "${model}" found`
                : `model "${model}" NOT in this endpoint's list`);
            }
            note.textContent = parts.join(' · ');
            const good = !model || modelOk;
            note.classList.remove('is-set', 'is-bad');
            note.classList.add(good ? 'is-set' : 'is-bad');
            toast(good ? 'Connection valid' : 'Model not found on this endpoint',
                  good ? 'ok' : 'warn');
          } catch (e) {
            /* State WHY it failed. A bare "invalid" is useless when the cause
               could be a wrong key, a wrong URL, or a reachable endpoint that
               simply has no /models route. */
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
            toast(`Invalid: ${why.slice(0, 90)}`, 'err');
          }
        } }
    ]
  });
  // The modal builds its head after we set it, so apply the title once more.
  setHead();
}
'''

text = SRC.read_text(encoding="utf-8")
lines = text.split("\n")
start = next(i for i, l in enumerate(lines) if l.startswith("async function providerForm("))
end = next(i for i in range(start + 1, len(lines)) if lines[i] == "}")
SRC.write_text("\n".join(lines[:start]) + "\n" + NEW + "\n".join(lines[end + 1:]), encoding="utf-8")
print(f"replaced providerForm(): lines {start+1}..{end+1} -> {NEW.count(chr(10))} lines")
