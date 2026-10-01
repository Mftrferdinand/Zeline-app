#!/usr/bin/env python3
"""Rewrite `providerForm()` in app3.js to the exact spec requested:

    Name      :          (no placeholder — deliberately blank)
    Base URL  :          OpenAI-format example
    Base URL  :          Anthropic-format example   (both shown side by side)
    API Key   :
    API Type  :          auto — Anthropic shows "messages" (may be empty),
                         OpenAI shows the endpoints OpenAI actually supports
    Model     :
    [Cek koneksi]  ->   valid, or invalid WITH the reason

Splices the function body between its `async function providerForm(...)` line
and its closing brace, so the surrounding file is untouched.
"""
import re
import pathlib
import sys

ROOT = pathlib.Path("/data/data/com.termux/files/home/zeline-frontend")
SRC = ROOT / "app3.js"

NEW = r'''async function providerForm(presetId = '', protocol = '') {
  const presets = await loadProviderPresets();
  const body = el('div', 'provider-form');

  /* Field order per the requested layout:
       Name            blank, no example text
       Base URL (OpenAI)     with a real OpenAI-format example
       Base URL (Anthropic)  with a real Anthropic-format example
       API Key
       API Type        driven by whichever Base URL is filled in
       Model
     Both Base URLs are shown at once because this form serves BOTH dialects —
     you fill in the one your endpoint speaks and API Type follows it. */

  const options = presets.map(p => ({ value: p.id, label: p.name }));
  const hasPreset = options.length > 0;

  if (hasPreset) {
    body.appendChild(field('Provider', 'pvPreset', {
      tag: 'select',
      hint: 'Pilih provider buat isi otomatis, atau Custom buat endpoint sendiri.',
      options: [{ value: '', label: 'Custom (endpoint sendiri)' }, ...options]
    }));
  }

  // No placeholder on Name — an example there reads as a value.
  body.appendChild(field('Name', 'pvName', { placeholder: '' }));

  body.appendChild(field('Base URL (OpenAI)', 'pvURL', {
    placeholder: 'https://api.openai.com/v1',
    hint: 'Format OpenAI: diakhiri /v1, chat lewat /chat/completions.'
  }));

  body.appendChild(field('Base URL (Anthropic)', 'pvURLAnthropic', {
    placeholder: 'https://api.anthropic.com',
    hint: 'Format Anthropic: tanpa /v1, chat lewat /v1/messages.'
  }));

  body.appendChild(field('API Key', 'pvKey', {
    type: 'password', placeholder: 'sk-…', required: true,
    hint: 'Key cuma dikirim sekali dan gak pernah balik ke browser.'
  }));

  /* API Type follows the dialect, it is never asked for abstractly:
       anthropic -> "messages" only (and may legitimately be empty)
       openai    -> the endpoints OpenAI itself supports
     Repopulated whenever the dialect changes. */
  const apiTypeWrap = el('div', 'field');
  apiTypeWrap.id = 'pvApiTypeWrap';
  apiTypeWrap.innerHTML = `
    <label for="pvApiType">API Type</label>
    <select id="pvApiType"></select>
    <small id="pvApiTypeHint"></small>`;
  body.appendChild(apiTypeWrap);

  body.appendChild(field('Model', 'pvModel', {
    placeholder: 'gpt-4o-mini',
    hint: 'Opsional. Cek koneksi buat lihat model yang tersedia dari endpoint ini.'
  }));

  const activeWrap = el('div', 'field pv-active-row');
  activeWrap.innerHTML = `
    <label for="pvActive">Active</label>
    <label class="pv-switch">
      <input type="checkbox" id="pvActive" checked>
      <i></i>
      <small>Aktifkan provider ini buat dipakai aplikasi</small>
    </label>`;
  body.appendChild(activeWrap);

  /* Hidden protocol field — kept so a preset can pin the dialect and so the
     preflight call has somewhere to record what it detected. */
  const protoField = el('input');
  protoField.type = 'hidden';
  protoField.id = 'pvProtocol';
  protoField.value = protocol || '';
  body.appendChild(protoField);

  const note = el('small', 'provider-form-note', '');
  body.appendChild(note);

  const presetSel = body.querySelector('#pvPreset');
  const urlOpenAI = body.querySelector('#pvURL');
  const urlAnthropic = body.querySelector('#pvURLAnthropic');
  const apiTypeSel = body.querySelector('#pvApiType');
  const apiTypeHint = body.querySelector('#pvApiTypeHint');

  /* Anthropic speaks exactly one wire format; OpenAI supports two. These lists
     mirror 9Router's own OPENAI_API_TYPES = ["chat", "responses"] plus
     Anthropic's single "messages". */
  const API_TYPES = {
    openai: [
      { value: 'chat', label: 'chat — /chat/completions' },
      { value: 'responses', label: 'responses — /responses' }
    ],
    anthropic: [
      { value: 'messages', label: 'messages — /v1/messages' },
      { value: '', label: '(kosongkan — pakai default)' }
    ]
  };

  /* Which dialect is the user actually filling in? Whichever Base URL has a
     value. Defaults to OpenAI so the picker is never empty on a blank form. */
  const dialect = () => (urlAnthropic.value.trim() && !urlOpenAI.value.trim())
    ? 'anthropic' : 'openai';

  const refreshApiTypes = () => {
    const d = dialect();
    const list = API_TYPES[d];
    apiTypeSel.innerHTML = '';
    list.forEach(o => {
      const op = el('option', '', esc(o.label));
      op.value = o.value;
      apiTypeSel.appendChild(op);
    });
    apiTypeHint.textContent = d === 'anthropic'
      ? 'Anthropic cuma punya satu format: messages. Boleh dikosongkan.'
      : 'Pilih endpoint yang didukung endpoint OpenAI ini.';
  };

  const applyPreset = () => {
    const preset = presets.find(p => p.id === presetSel?.value);
    if (preset) {
      // A preset is OpenAI-shaped unless it says otherwise.
      const proto = preset.protocol || 'openai';
      protoField.value = proto;
      if (proto === 'anthropic') {
        urlAnthropic.value = preset.base_url || '';
        urlOpenAI.value = '';
      } else {
        urlOpenAI.value = preset.base_url || '';
        urlAnthropic.value = '';
      }
      const nameEl = body.querySelector('#pvName');
      const auto = nameEl.dataset.autoFilled === '1';
      if (!nameEl.value.trim() || auto) {
        nameEl.value = preset.name;
        nameEl.dataset.autoFilled = '1';
      }
      note.textContent = 'Endpoint terisi otomatis, bisa diubah buat mirror sendiri.';
    } else {
      protoField.value = '';
      note.textContent = 'Isi salah satu Base URL, lalu Cek koneksi.';
    }
    note.classList.remove('is-set');
    refreshApiTypes();
  };

  // Typing in either URL switches the dialect, so API Type always matches.
  const onUrlEdit = () => { protoField.value = ''; refreshApiTypes(); note.classList.remove('is-set'); };
  urlOpenAI.addEventListener('input', onUrlEdit);
  urlAnthropic.addEventListener('input', onUrlEdit);
  if (presetSel) presetSel.onchange = applyPreset;
  if (presetId && presetSel) { presetSel.value = presetId; applyPreset(); }
  refreshApiTypes();

  modal({
    title: 'Tambah Provider',
    subtitle: 'Isi endpoint dan key, lalu cek koneksi buat memastikan valid.',
    body,
    actions: [
      { label: 'Batal' },
      { label: 'Cek koneksi', kind: 'primary', onClick: async () => {
          const useAnthropic = dialect() === 'anthropic';
          const base_url = (useAnthropic ? urlAnthropic : urlOpenAI).value.trim();
          const api_key = body.querySelector('#pvKey').value;
          const model = body.querySelector('#pvModel').value.trim();

          if (!base_url) {
            note.textContent = 'Base URL masih kosong — isi salah satu dari dua field di atas.';
            note.classList.remove('is-set', 'is-bad');
            note.classList.add('is-bad');
            toast('Base URL wajib diisi', 'err'); return;
          }
          if (!api_key) {
            note.textContent = 'API Key masih kosong.';
            note.classList.remove('is-set', 'is-bad');
            note.classList.add('is-bad');
            toast('API key wajib buat cek', 'err'); return;
          }

          const apiType = apiTypeSel.value || '';
          protoField.value = useAnthropic ? 'anthropic' : 'openai';
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
              `VALID — endpoint menjawab.`,
              `${d.model_count || models.length} model tersedia`,
              `protokol: ${d.protocol || protoField.value}${d.detected ? ' (auto-detect)' : ''}`,
              `${d.latency_ms}ms`
            ];
            if (model) {
              parts.push(modelOk
                ? `model "${model}" ada di daftar`
                : `model "${model}" TIDAK ada di daftar endpoint ini`);
            }
            note.textContent = parts.join(' · ');

            const good = !model || modelOk;
            note.classList.remove('is-set', 'is-bad');
            note.classList.add(good ? 'is-set' : 'is-bad');
            toast(good ? 'Koneksi valid' : `Model tidak ditemukan di endpoint ini`,
                  good ? 'ok' : 'warn');
          } catch (e) {
            /* Say WHY it failed, in plain language — a bare "invalid" is
               useless when the cause is a wrong key vs a wrong URL vs a
               provider that simply doesn't offer a model list. */
            const code = e.code || '';
            const WHY = {
              PROVIDER_UNAUTHORIZED:
                'Endpoint menjawab, tapi API Key ditolak (401/403). Cek key-nya, atau pastikan key ini memang buat endpoint itu.',
              PROVIDER_UNAVAILABLE:
                'Endpoint tidak bisa dihubungi. Cek Base URL (salah ketik / host mati / nggak ada internet).',
              VALIDATION_ERROR:
                'Base URL atau API Key belum lengkap.',
              TIMEOUT:
                'Endpoint tidak menjawab dalam batas waktu. Coba lagi, atau cek Base URL-nya.',
              NETWORK_ERROR:
                'Gagal konek jaringan dari server Zeline.'
            };
            const why = WHY[code]
              || e.message
              || 'Endpoint tidak memberi jawaban yang bisa dibaca.';
            note.textContent = `INVALID — ${why}`;
            note.classList.remove('is-set', 'is-bad');
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

# locate the function
start = next(i for i, l in enumerate(lines) if l.startswith("async function providerForm("))
# first line that is exactly "}" at column 0 after the start = end of function
end = next(i for i in range(start + 1, len(lines)) if lines[i] == "}")

before = "\n".join(lines[:start])
after = "\n".join(lines[end + 1:])
SRC.write_text(before + "\n" + NEW + after, encoding="utf-8")
print(f"replaced providerForm(): lines {start+1}..{end+1} ({end-start+1} lines) -> {NEW.count(chr(10))} lines")
