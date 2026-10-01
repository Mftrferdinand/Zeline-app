#!/usr/bin/env python3
"""Rewrite providerForm() to the requested two-variant design.

Opened from the two custom cards, the form diverges by dialect:

  Add Anthropic Compatible          Add OpenAI Compatible
  ------------------------          ---------------------
  Name        *                     Name        *
  Prefix      *                     Prefix      *
  Base URL    *  (…/v1)             API Type      [Chat Completions ▾]
  API Key (for Check)               Base URL    *  (…/v1)
  Model ID (optional)               API Key (for Check)
                                    Model ID (optional)

Both keep: the endpoint gets /v1, Anthropic appends /messages, and Model ID is
only needed when the provider has no /models endpoint (validate via the chat
endpoint instead).
"""
import pathlib
import sys

ROOT = pathlib.Path("/data/data/com.termux/files/home/zeline-frontend")
SRC = ROOT / "app3.js"

NEW = r'''async function providerForm(presetId = '', protocol = '') {
  const presets = await loadProviderPresets();
  const body = el('div', 'provider-form');

  /* Two shapes, chosen by the card that opened this form:
       anthropic -> Name, Prefix, Base URL (…/v1), API Key, Model ID
       openai    -> Name, Prefix, API Type, Base URL (…/v1), API Key, Model ID
     `protocol` carries the dialect in from the Add card. A preset flow still
     works: the preset decides the dialect and prefills the endpoint. */
  const isAnthropic = protocol === 'anthropic';

  const options = presets.map(p => ({ value: p.id, label: p.name }));
  const showPresetPicker = Boolean(presetId) && options.length > 0;

  if (showPresetPicker) {
    body.appendChild(field('Provider', 'pvPreset', {
      tag: 'select', value: presetId, disabled: true,
      hint: 'Endpoint provider ini terisi otomatis.', options
    }));
  }

  body.appendChild(field('Name', 'pvName', {
    required: true,
    placeholder: isAnthropic ? 'Anthropic Compatible (Prod)' : 'OpenAI Compatible (Prod)',
    hint: 'Required. Label yang gampang dikenali buat node ini.'
  }));

  /* Prefix — the short id that namespaces this node's model ids. Defaulted per
     dialect (ac-prod / oc-prod) so the field is never empty on open. */
  body.appendChild(field('Prefix', 'pvPrefix', {
    required: true,
    value: isAnthropic ? 'ac-prod' : 'oc-prod',
    placeholder: isAnthropic ? 'ac-prod' : 'oc-prod',
    hint: 'Required. Dipakai sebagai prefix model ID provider ini.'
  }));

  body.appendChild(field('Base URL', 'pvURL', {
    required: true,
    placeholder: isAnthropic ? 'https://api.anthropic.com/v1' : 'https://api.openai.com/v1',
    hint: isAnthropic
      ? 'Pakai base URL (berakhir /v1) untuk API Anthropic-compatible. Sistem menambahkan /messages.'
      : 'Pakai base URL (berakhir /v1) untuk API OpenAI-compatible.'
  }));

  /* API Type only exists on the OpenAI side. Anthropic has exactly one wire
     format, so asking would be noise. */
  const apiTypeWrap = el('div', 'field');
  apiTypeWrap.id = 'pvApiTypeWrap';
  apiTypeWrap.innerHTML = `
    <label for="pvApiType">API Type</label>
    <select id="pvApiType">
      <option value="chat">Chat Completions</option>
      <option value="responses">Responses</option>
    </select>`;
  if (!isAnthropic) body.appendChild(apiTypeWrap);

  body.appendChild(field('API Key (for Check)', 'pvKey', {
    type: 'password', placeholder: 'sk-…',
    hint: 'Dipakai buat cek koneksi. Gak pernah balik ke browser.'
  }));

  body.appendChild(field('Model ID', 'pvModel', {
    placeholder: isAnthropic ? 'claude-3-opus' : 'gpt-4o-mini',
    hint: 'Opsional. Kalau provider nggak punya endpoint /models, isi model ID biar divalidasi lewat chat endpoint.'
  }));

  /* Hidden protocol + api_type, resolved from the dialect so the backend and
     any future save path get an explicit value. */
  const protoField = el('input');
  protoField.type = 'hidden';
  protoField.id = 'pvProtocol';
  protoField.value = isAnthropic ? 'anthropic' : 'openai';
  body.appendChild(protoField);

  const note = el('small', 'provider-form-note', '');
  body.appendChild(note);
  note.textContent = isAnthropic
    ? 'Anthropic: endpoint chat = Base URL + /messages.'
    : 'OpenAI: pilih API Type sesuai endpoint yang didukung.';

  const presetSel = body.querySelector('#pvPreset');

  // A preset flow seeds Name / Prefix / Base URL from the catalogue entry.
  if (presetSel && presetId) {
    const preset = presets.find(p => p.id === presetId);
    if (preset) {
      body.querySelector('#pvURL').value = preset.base_url || '';
      body.querySelector('#pvName').value = preset.name || '';
      const pfx = body.querySelector('#pvPrefix');
      if (pfx && !pfx.value.trim()) pfx.value = (preset.id || '').slice(0, 16);
      protoField.value = preset.protocol || (isAnthropic ? 'anthropic' : 'openai');
    }
  }

  modal({
    title: isAnthropic ? 'Add Anthropic Compatible' : 'Add OpenAI Compatible',
    subtitle: isAnthropic
      ? 'Provider Anthropic-compatible — sistem menambahkan /messages.'
      : 'Provider OpenAI-compatible — pilih API Type yang didukung.',
    body,
    actions: [
      { label: 'Batal' },
      { label: 'Cek koneksi', kind: 'primary', onClick: async () => {
          const base_url = body.querySelector('#pvURL').value.trim();
          const api_key = body.querySelector('#pvKey').value;
          const model = body.querySelector('#pvModel').value.trim();
          const prefix = body.querySelector('#pvPrefix').value.trim();
          const name = body.querySelector('#pvName').value.trim();
          const apiType = isAnthropic ? 'messages'
            : (body.querySelector('#pvApiType')?.value || 'chat');

          const fail = (msg) => {
            note.textContent = msg;
            note.classList.remove('is-set');
            note.classList.add('is-bad');
            toast(msg, 'err');
          };
          if (!name) return fail('Name wajib diisi.');
          if (!prefix) return fail('Prefix wajib diisi.');
          if (!base_url) return fail('Base URL wajib diisi.');
          if (!api_key) return fail('API Key wajib diisi buat cek koneksi.');

          note.textContent = 'Mengecek…';
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
              'VALID — endpoint menjawab.',
              `${d.model_count || models.length} model tersedia`,
              `${d.protocol || protoField.value} · ${apiType}`,
              `${d.latency_ms}ms`
            ];
            if (model) {
              parts.push(modelOk
                ? `model "${model}" ada`
                : `model "${model}" TIDAK ada di daftar endpoint ini`);
            }
            note.textContent = parts.join(' · ');
            const good = !model || modelOk;
            note.classList.remove('is-set', 'is-bad');
            note.classList.add(good ? 'is-set' : 'is-bad');
            toast(good ? 'Koneksi valid' : 'Model tidak ditemukan di endpoint ini',
                  good ? 'ok' : 'warn');
          } catch (e) {
            /* State WHY it failed. A bare "invalid" is useless when the cause
               could be a wrong key, a wrong URL, or a reachable endpoint that
               simply has no /models route. */
            const code = e.code || '';
            const WHY = {
              PROVIDER_UNAUTHORIZED:
                'Endpoint menjawab, tapi API Key ditolak (401/403). Cek key-nya.',
              PROVIDER_UNAVAILABLE:
                'Endpoint nggak bisa dihubungi. Cek Base URL (salah ketik / host mati).',
              VALIDATION_ERROR: 'Base URL atau API Key belum lengkap.',
              TIMEOUT: 'Endpoint nggak jawab dalam batas waktu. Coba lagi.'
            };
            const why = WHY[code] || e.message || 'Endpoint nggak kasih jawaban yang bisa dibaca.';
            note.textContent = `INVALID — ${why}`;
            note.classList.remove('is-set');
            note.classList.add('is-bad');
            toast(`Invalid: ${why.slice(0, 90)}`, 'err');
          }
        } }
    ]
  });
}
'''

text = SRC.read_text(encoding="utf-8")
lines = text.split("\n")
start = next(i for i, l in enumerate(lines) if l.startswith("async function providerForm("))
end = next(i for i in range(start + 1, len(lines)) if lines[i] == "}")
SRC.write_text("\n".join(lines[:start]) + "\n" + NEW + "\n".join(lines[end + 1:]), encoding="utf-8")
print(f"replaced providerForm(): lines {start+1}..{end+1} -> {NEW.count(chr(10))} lines")
