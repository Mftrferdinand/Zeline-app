#!/usr/bin/env python3
"""Move Check / Create / Cancel INTO the form, directly under Model ID.

No footer bar, no header action. The three buttons are plain cards appended to
`.provider-form` after the last field, so they scroll with the content they act
on. Create stays disabled until a Check passes.
"""
import pathlib

SRC = pathlib.Path("/data/data/com.termux/files/home/zeline-frontend/app3.js")

NEW = r'''async function providerForm(presetId = '', protocol = '') {
  const presets = await loadProviderPresets();
  const body = el('div', 'provider-form');

  /* One screen, two dialects, switched by the segmented control at the top.
     Only `#pvFields` is rebuilt on switch, so the values already typed survive
     the change. */
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

  /* Action cards live INSIDE the form, right below Model ID — no footer bar and
     no header action, so the buttons sit with the fields they submit. */
  const acts = el('div', 'pv-actions');
  acts.innerHTML = `
    <button class="pv-act pv-act-check" data-act="check" type="button">Check</button>
    <button class="pv-act pv-act-create is-locked" data-act="create" type="button" disabled>Create</button>
    <button class="pv-act pv-act-cancel" data-act="cancel" type="button">Cancel</button>`;
  body.appendChild(acts);

  const protoField = el('input');
  protoField.type = 'hidden';
  protoField.id = 'pvProtocol';
  body.appendChild(protoField);

  const btnCheck  = acts.querySelector('[data-act="check"]');
  const btnCreate = acts.querySelector('[data-act="create"]');
  const btnCancel = acts.querySelector('[data-act="cancel"]');

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

    fields.querySelectorAll('input, select').forEach(node => {
      node.addEventListener('input', invalidate);
      node.addEventListener('change', invalidate);
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

  btnCancel.onclick = () => closeModal();

  // No footer bar and no header action: the form owns its own buttons.
  modal({
    title: dialect === 'anthropic' ? 'Add Anthropic Compatible' : 'Add OpenAI Compatible',
    body,
    actions: []
  });
  setHead();
}
'''

text = SRC.read_text(encoding="utf-8")
lines = text.split("\n")
start = next(i for i, l in enumerate(lines) if l.startswith("async function providerForm("))
end = next(i for i in range(start + 1, len(lines)) if lines[i] == "}")
SRC.write_text("\n".join(lines[:start]) + "\n" + NEW + "\n".join(lines[end + 1:]), encoding="utf-8")
print(f"replaced providerForm(): lines {start+1}..{end+1} -> {NEW.count(chr(10))} lines")
