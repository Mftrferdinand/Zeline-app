#!/usr/bin/env python3
"""Select Endpoint becomes an ordinary titled field group.

Requested shape:

    Select Endpoint          <- title
    Use /v1/messages or /v1/chat/completions or /v1/responses
                             <- one static description, same slot as every
                                other field's description
    [ Anthropic Compatible ] [ OpenAI Compatible ]

The description must NOT move or swap when a card is clicked. Previously each
option carried its own caption above its card, so picking OpenAI slid a line in
directly above it — that is the "deskripsi malah di atas open ai" complaint.

Also:
  * same gap from the cards down to the next title as between any two fields
  * Model ID gains an example hint per dialect
"""
import pathlib

ROOT = pathlib.Path("/data/data/com.termux/files/home/zeline-frontend")


def patch_js():
    p = ROOT / "app3.js"
    s = p.read_text(encoding="utf-8")

    # ---- Select Endpoint: static description, plain cards
    OLD = """  const segGroup = el('div', 'pv-seg-group');
  const segHead = el('div', 'pv-seg-head');
  segHead.innerHTML = '<h4>Select Endpoint</h4>';
  segGroup.appendChild(segHead);

  /* Each option is its own titled block: description line, then the card.
     The caption lives ABOVE its card, so the two options read as two distinct
     choices instead of one control with internal text. */
  const seg = el('div', 'pv-seg');
  seg.setAttribute('role', 'tablist');
  seg.innerHTML = `
    <div class="pv-opt" data-opt="anthropic">
      <small class="pv-opt-desc">Use /v1/messages</small>
      <button class="pv-seg-btn" data-dialect="anthropic" type="button" role="tab">
        <strong>Anthropic Compatible</strong>
      </button>
    </div>
    <div class="pv-opt" data-opt="openai">
      <small class="pv-opt-desc">Use /v1/chat/completions or /v1/responses</small>
      <button class="pv-seg-btn" data-dialect="openai" type="button" role="tab">
        <strong>OpenAI Compatible</strong>
      </button>
    </div>`;
  segGroup.appendChild(seg);
  if (!showPresetPicker) body.appendChild(segGroup);"""
    NEW = """  /* `Select Endpoint` is an ordinary titled group: title, one description, then
     the cards — the same three-part shape every other field on this form uses.
     The description is STATIC. It must not swap or slide when a card is picked
     (that made a caption appear directly above the clicked card). Both endpoints
     are named in the one line instead. */
  const segGroup = el('div', 'pv-seg-group');
  const segHead = el('div', 'pv-seg-head');
  segHead.innerHTML = `
    <h4>Select Endpoint</h4>
    <small class="field-desc">Use /v1/messages or /v1/chat/completions or /v1/responses</small>`;
  segGroup.appendChild(segHead);

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
  if (!showPresetPicker) body.appendChild(segGroup);"""
    assert OLD in s, "seg group markup not found"
    s = s.replace(OLD, NEW)

    # the per-option active class is no longer needed
    s = s.replace("""    // Only the chosen option shows its description line.
    seg.querySelectorAll('.pv-opt').forEach(o => {
      o.classList.toggle('is-active', o.dataset.opt === dialect);
    });
""", "")

    # ---- Model ID examples per dialect
    OLD_M = """    fields.appendChild(field('Model ID (optional)', 'pvModel', {
      value: keep?.model || '',
      placeholder: isAnthropic ? 'claude-3-opus' : 'gpt-4o-mini',
      desc: 'If provider lacks /models endpoint, enter a model ID to validate via chat/completions instead.'
    }));"""
    NEW_M = """    fields.appendChild(field('Model ID (optional)', 'pvModel', {
      value: keep?.model || '',
      placeholder: isAnthropic ? 'e.g. claude-fable-5-1' : 'e.g. gpt-6-astra',
      desc: 'If provider lacks /models endpoint, enter a model ID to validate via chat/completions instead.'
    }));"""
    assert OLD_M in s, "model field not found"
    s = s.replace(OLD_M, NEW_M)

    p.write_text(s, encoding="utf-8")
    print("app3.js: static Select Endpoint description, model ID examples")


def patch_css():
    p = ROOT / "style.css"
    s = p.read_text(encoding="utf-8")

    start = s.index("/* ── Select Endpoint ─")
    end = s.index("/* ── field wells ─", start)

    NEW = """/* ── Select Endpoint ──────────────────────────────────────────────────────
   Shaped exactly like every other field group on this form: title, description,
   then the control. One static description line — it never swaps per selection.

   The gap above the title matches the Providers page (14px from the bar rule),
   and the gap below the cards to the next title is the same 14px used between
   fields, so the rhythm is uniform down the sheet. */
.pv-seg-group{display:flex;flex-direction:column;gap:8px;padding-top:12px}
.pv-seg-head{display:flex;flex-direction:column;gap:0}
.pv-seg-head h4{
  margin:0 0 1px;color:#f2f2f4;
  font-size:12px;font-weight:660;letter-spacing:-.02em;line-height:1.3;
}
/* Same tone/metric as `.provider-form .field-desc`. */
.pv-seg-head .field-desc{
  margin:0 0 5px!important;color:#7d7d87!important;
  font-size:9.5px!important;font-weight:560!important;
  line-height:1.4!important;letter-spacing:.002em!important;
}
html[data-app-theme='light'] .pv-seg-head h4{color:#17171a}
html[data-app-theme='light'] .pv-seg-head .field-desc{color:#6d6d76!important}

/* Two equal cards. No captions inside or above them. */
.provider-form .pv-seg{
  display:grid;grid-template-columns:1fr 1fr;gap:9px;
  padding:0;background:transparent;border:0;box-shadow:none;
  align-items:stretch;
}
.provider-form .pv-seg-btn{
  display:flex;align-items:center;justify-content:center;
  height:44px;min-height:44px;padding:0 10px;
  border-radius:10px;text-align:center;
  background:#131418;border:1px solid #23242a;color:#9a9aa2;
  transition:background .2s cubic-bezier(.4,0,.2,1),
             border-color .2s cubic-bezier(.4,0,.2,1),
             color .2s cubic-bezier(.4,0,.2,1),
             box-shadow .2s cubic-bezier(.4,0,.2,1),
             transform .13s ease;
}
.provider-form .pv-seg-btn>strong{
  display:block;max-width:100%;
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis;
  font-size:12px;font-weight:670;letter-spacing:-.015em;line-height:1.2;
}
.provider-form .pv-seg-btn:active{transform:scale(.97)}

/* Anthropic — orange. */
.provider-form .pv-seg-btn[data-dialect="anthropic"].is-active{
  background:linear-gradient(158deg,#e87a44,#cf5626);
  border-color:rgba(255,166,116,.5);
  color:#fff;
  box-shadow:0 3px 12px rgba(186,70,30,.3), inset 0 1px 0 rgba(255,255,255,.18);
}
/* OpenAI — white. */
.provider-form .pv-seg-btn[data-dialect="openai"].is-active{
  background:linear-gradient(178deg,#fafafc,#e9e9ee);
  border-color:rgba(255,255,255,.6);
  color:#15151a;
  box-shadow:0 3px 12px rgba(0,0,0,.3), inset 0 1px 0 #fff;
}
html[data-app-theme='light'] .provider-form .pv-seg-btn{
  background:#fff;border-color:#dcdce3;color:#5f5f68;
}
html[data-app-theme='light'] .provider-form .pv-seg-btn[data-dialect="openai"].is-active{
  background:linear-gradient(178deg,#fff,#f6f6f9);border-color:#c9c9d4;color:#15151a;
  box-shadow:0 3px 11px rgba(30,30,40,.14), inset 0 1px 0 #fff;
}

"""
    s = s[:start] + NEW + s[end:]

    # Uniform vertical rhythm: one gap value everywhere.
    s = s.replace(".provider-form{gap:18px;padding:4px 0 10px}",
                  ".provider-form{gap:14px;padding:4px 0 10px}")
    s = s.replace(".pv-seg-group{display:flex;flex-direction:column;gap:8px;padding-top:12px}",
                  ".pv-seg-group{display:flex;flex-direction:column;gap:14px;padding-top:12px}")
    s = s.replace(".pv-fields{gap:14px}", ".pv-fields{gap:14px}")

    p.write_text(s, encoding="utf-8")
    print("style.css: Select Endpoint uses the standard field rhythm")


patch_js()
patch_css()
