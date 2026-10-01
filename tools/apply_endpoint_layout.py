#!/usr/bin/env python3
"""Restructure the endpoint picker to the requested layout.

Target (per option, not fused inside the card):

    Custom Endpoint                    <- one title for the whole screen

    Select Endpoint                    <- section title
    Use /v1/messages                   <- description, ABOVE its card
    [ Anthropic Compatible ]           <- card

    Use /v1/chat/completions or /v1/responses
    [ OpenAI Compatible ]

Measured reference for the spacing above "Select Endpoint": on the Providers
page the gap from the app-bar line down to the section title is 14px.
"""
import pathlib

ROOT = pathlib.Path("/data/data/com.termux/files/home/zeline-frontend")


def patch_js():
    p = ROOT / "app3.js"
    s = p.read_text(encoding="utf-8")

    # ---- one screen title
    OLD_TITLE = """  modal({
    title: dialect === 'anthropic' ? 'Add Anthropic Compatible' : 'Add OpenAI Compatible',
    body,
    actions: []
  });"""
    NEW_TITLE = """  modal({
    title: 'Custom Endpoint',
    body,
    actions: []
  });"""
    assert OLD_TITLE in s, "modal title call not found"
    s = s.replace(OLD_TITLE, NEW_TITLE)

    # setHead no longer rewrites the title
    OLD_HEAD = """  const setHead = () => {
    const t = document.getElementById('modalTitle');
    if (t) t.textContent = dialect === 'anthropic'
      ? 'Add Anthropic Compatible' : 'Add OpenAI Compatible';
  };"""
    NEW_HEAD = """  /* The screen keeps ONE title ("Custom Endpoint"); which endpoint is active is
     shown by the option cards below, so nothing here rewrites the bar. */
  const setHead = () => {};"""
    assert OLD_HEAD in s, "setHead not found"
    s = s.replace(OLD_HEAD, NEW_HEAD)

    # ---- per-option: description above the card, nothing inside it
    OLD_SEG = """  const segGroup = el('div', 'pv-seg-group');
  const segHead = el('div', 'pv-seg-head');
  segHead.innerHTML = '<h4>Select Endpoint</h4>';
  segGroup.appendChild(segHead);

  const seg = el('div', 'pv-seg');
  seg.setAttribute('role', 'tablist');
  seg.innerHTML = `
    <button class="pv-seg-btn" data-dialect="anthropic" type="button" role="tab">
      <strong>Anthropic Compatible</strong>
      <small>Use /v1/messages</small>
    </button>
    <button class="pv-seg-btn" data-dialect="openai" type="button" role="tab">
      <strong>OpenAI Compatible</strong>
      <small>Use /v1/chat/completions or /v1/responses</small>
    </button>`;
  segGroup.appendChild(seg);
  if (!showPresetPicker) body.appendChild(segGroup);"""
    NEW_SEG = """  const segGroup = el('div', 'pv-seg-group');
  const segHead = el('div', 'pv-seg-head');
  segHead.innerHTML = '<h4>Select Endpoint</h4>';
  segGroup.appendChild(segHead);

  /* Each option is its own titled block: description line, then the card.
     The caption lives ABOVE its card, so the two options read as two distinct
     choices instead of one control with internal text. */
  const seg = el('div', 'pv-seg');
  seg.setAttribute('role', 'tablist');
  seg.innerHTML = `
    <div class="pv-opt">
      <small class="pv-opt-desc">Use /v1/messages</small>
      <button class="pv-seg-btn" data-dialect="anthropic" type="button" role="tab">
        <strong>Anthropic Compatible</strong>
      </button>
    </div>
    <div class="pv-opt">
      <small class="pv-opt-desc">Use /v1/chat/completions or /v1/responses</small>
      <button class="pv-seg-btn" data-dialect="openai" type="button" role="tab">
        <strong>OpenAI Compatible</strong>
      </button>
    </div>`;
  segGroup.appendChild(seg);
  if (!showPresetPicker) body.appendChild(segGroup);"""
    assert OLD_SEG in s, "seg group not found"
    s = s.replace(OLD_SEG, NEW_SEG)

    p.write_text(s, encoding="utf-8")
    print("app3.js: one title 'Custom Endpoint', per-option desc above card")


def patch_css():
    p = ROOT / "style.css"
    s = p.read_text(encoding="utf-8")

    # ---- replace the whole endpoint-picker styling block
    start = s.index("/* \"Select Endpoint\" group heading")
    end = s.index("/* ── field wells ─", start)

    NEW = """/* ── Select Endpoint ──────────────────────────────────────────────────────
   One section title, then two option blocks: description line above each card.
   Spacing above the title matches the Providers page, where the gap from the
   app-bar rule down to the section title measures 14px. */
.pv-seg-group{display:flex;flex-direction:column;gap:9px;padding-top:12px}
.pv-seg-head h4{
  margin:0;color:#f2f2f4;
  font-size:12.5px;font-weight:680;letter-spacing:-.02em;line-height:1.25;
}
html[data-app-theme='light'] .pv-seg-head h4{color:#17171a}

/* Two equal columns; each holds a caption plus its card. */
.provider-form .pv-seg{
  display:grid;grid-template-columns:1fr 1fr;
  gap:9px;padding:0;background:transparent;border:0;box-shadow:none;
  align-items:stretch;
}
.pv-opt{display:flex;flex-direction:column;gap:6px;min-width:0}
/* Description — the Providers page's secondary tone. */
.provider-form .pv-opt-desc{
  display:block;margin:0;
  color:#7d7d87;font-size:9.5px;font-weight:560;
  line-height:1.35;letter-spacing:.002em;
  min-height:calc(2 * 1.35 * 9.5px);   /* reserve two lines so both cards align */
}
html[data-app-theme='light'] .provider-form .pv-opt-desc{color:#6d6d76}

/* The card itself: one line of title, equal height across both columns. */
.provider-form .pv-seg-btn{
  display:flex;align-items:center;justify-content:center;
  flex:1 1 auto;
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

    # Space between the endpoint picker and the first field group.
    s = s.replace(".provider-form{gap:14px;padding:4px 0 10px}",
                  ".provider-form{gap:18px;padding:4px 0 10px}")

    p.write_text(s, encoding="utf-8")
    print("style.css: per-option desc above card, equal columns, 14px top gap")


patch_js()
patch_css()
