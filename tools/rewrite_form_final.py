#!/usr/bin/env python3
"""Rewrite providerForm() to the requested spec.

Layout per field is: TITLE -> DESCRIPTION -> CONTROL.

  Provider Name
  A friendly label for this OpenAI-compatible provider.
  [ input ]

  API Type                     (OpenAI only)
  Select an option:
  [ select ]

  Base URL
  Use the base URL (ending in /v1) for your OpenAI-compatible API.
  [ input ]

  API Key
  Enter your api key to check
  [ input ]

  Model ID (optional)
  If provider lacks /models endpoint, enter a model ID to validate via
  chat/completions instead.
  [ input ]

Buttons: Check, Create, Cancel. Create stays DISABLED until a Check passes, and
goes back to disabled whenever any field that affects the check is edited.
Prefix is removed entirely.
"""
import pathlib

SRC = pathlib.Path("/data/data/com.termux/files/home/zeline-frontend/app3.js")

NEW = r'''async function providerForm(presetId = '', protocol = '') {
  const presets = await loadProviderPresets();
  const body = el('div', 'provider-form');

  /* One screen, two dialects, switched by the segmented control at the top.
     Only `#pvFields` is rebuilt on switch, so the modal never reopens and the
     values the user already typed survive the change. */
  let dialect = protocol === 'anthropic' ? 'anthropic' : 'openai';
  // Create is gated on a passing Check. Any edit invalidates it again.
  let checkPassed = false;

  const options = presets.map(p => ({ value: p.id, label: p.name }));
  const showPresetPicker = Boolean(presetId) && options.length > 0;

  const seg = el('div', 'pv-seg');
  seg.setAttribute('role', 'tablist');
  seg.innerHTML = `
    <button class="pv-seg-btn" data-dialect="anthropic" type="button" role="tab">
      <strong>Anthropic Compatible</strong>
    </button>
    <button class="pv-seg-btn" data-dialect="openai" type="button" role="tab">
      <strong>OpenAI Compatible</strong>
    </button>`;
  if (!showPresetPicker) body.appendChild(seg);

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

  const protoField = el('input');
  protoField.type = 'hidden';
  protoField.id = 'pvProtocol';
  body.appendChild(protoField);

  // Look the Create button up lazily: the modal builds its footer after this.
  const createBtn = () =>
    [...document.querySelectorAll('.modal-foot .btn')]
      .find(b => b.textContent.trim() === 'Create');

  const setCreateEnabled = (on) => {
    checkPassed = on;
    const b = createBtn();
    if (!b) return;
    b.disabled = !on;
    b.classList.toggle('is-locked', !on);
    b.title = on ? 'Save this provider' : 'Run Check first — the endpoint must be valid';
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

  const setHead = () => {
    const t = document.getElementById('modalTitle');
    if (t) t.textContent = dialect === 'anthropic'
      ? 'Add Anthropic Compatible' : 'Add OpenAI Compatible';
  };

  const renderFields = (keep) => {
    const isAnthropic = dialect === 'anthropic';
    const vendor = isAnthropic ? 'Anthropic' : 'OpenAI';
    fields.innerHTML = '';
    protoField.value = isAnthropic ? 'anthropic' : 'openai';

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
        ? 'Use the base URL (ending in /v1) for your Anthropic-compatible API. The system will append /messages.'
        : 'Use the base URL (ending in /v1) for your OpenAI-compatible API.'
    }));

    fields.appendChild(field('API Key', 'pvKey', {
      type: 'password', value: keep?.key || '', placeholder: 'sk-…',
      desc: 'Enter your api key to check'
    }));

    fields.appendChild(field('Model ID (optional)', 'pvModel', {
      value: keep?.model || '',
      placeholder: isAnthropic ? 'claude-3-opus' : 'gpt-4o-mini',
      desc: 'If provider lacks /models endpoint, enter a model ID to validate via chat/completions instead.'
    }));

    // Editing anything relevant revokes a previous pass.
    fields.querySelectorAll('input, select').forEach(el2 => {
      el2.addEventListener('input', invalidate);
      el2.addEventListener('change', invalidate);
    });

    seg.querySelectorAll('[data-dialect]').forEach(b => {
      const on = b.dataset.dialect === dialect;
      b.classList.toggle('is-active', on);
      b.setAttribute('aria-selected', on ? 'true' : 'false');
    });
    note.className = 'provider-form-note';
    note.textContent = '';
    setCreateEnabled(false);
    setHead();
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

  modal({
    title: dialect === 'anthropic' ? 'Add Anthropic Compatible' : 'Add OpenAI Compatible',
    body,
    footerActions: true,
    actions: [
      { label: 'Cancel' },
      { label: 'Check', kind: 'ghost', onClick: async () => {
          const f = readForm();
          if (!f.base_url) return fail('Base URL is required.');
          if (!f.api_key) return fail('API Key is required to run the check.');

          note.textContent = 'Checking…';
          note.classList.remove('is-set', 'is-bad');

          try {
            const d = await api('/providers/preflight', {
              method: 'POST', timeoutMs: 20000,
              body: { base_url: f.base_url, api_key: f.api_key,
                      protocol: protoField.value, api_type: f.apiType, model: f.model }
            });
            const models = Array.isArray(d.models) ? d.models : [];
            const modelOk = f.model ? models.includes(f.model) : null;
            const parts = [
              'VALID — endpoint responded.',
              `${d.model_count || models.length} models available`,
              `${d.protocol || protoField.value} · ${f.apiType}`,
              `${d.latency_ms}ms`
            ];
            if (f.model) {
              parts.push(modelOk
                ? `model "${f.model}" found`
                : `model "${f.model}" NOT in this endpoint's list`);
            }
            note.textContent = parts.join(' · ');
            const good = !f.model || modelOk;
            note.classList.remove('is-set', 'is-bad');
            note.classList.add(good ? 'is-set' : 'is-bad');
            // Only a fully good result unlocks Create.
            setCreateEnabled(good);
            toast(good ? 'Connection valid — you can create it now'
                       : 'Model not found on this endpoint',
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
            setCreateEnabled(false);
            toast(`Invalid: ${why.slice(0, 90)}`, 'err');
          }
        } },
      { label: 'Create', kind: 'primary', keepOpen: true, onClick: async () => {
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
          try {
            await api('/providers', { method: 'POST', body: payload, timeoutMs: 20000 });
            toast(`Provider "${payload.name}" created`, 'ok');
            closeModal();
            renderProviderList();
          } catch (e) {
            const why = e.message || e.code || 'unknown error';
            note.textContent = `Could not create: ${why}`;
            note.classList.remove('is-set');
            note.classList.add('is-bad');
            toast(`Create failed: ${why}`.slice(0, 110), 'err');
          }
        } }
    ]
  });
  setHead();
  // The footer exists now — apply the initial locked state to Create.
  setCreateEnabled(false);
}
'''

text = SRC.read_text(encoding="utf-8")
lines = text.split("\n")
start = next(i for i, l in enumerate(lines) if l.startswith("async function providerForm("))
end = next(i for i in range(start + 1, len(lines)) if lines[i] == "}")
SRC.write_text("\n".join(lines[:start]) + "\n" + NEW + "\n".join(lines[end + 1:]), encoding="utf-8")
print(f"replaced providerForm(): lines {start+1}..{end+1} -> {NEW.count(chr(10))} lines")
