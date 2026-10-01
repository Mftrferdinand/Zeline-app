#!/usr/bin/env python3
"""Align the Add-Provider sheet to the Providers page, and restructure the
endpoint picker.

Measured reference (tools/probe_providers_page.py):
  grid          rgba(255,255,255,.03), 38px, over rgb(13,14,17)
  section h3    12.5px / 680 / rgb(242,242,244) / -0.25px
  section sub   9.5px  / 560 / rgb(125,125,135)
  add card      44px tall, padding 8px 10px, radius 10px
  card strong   12px / 670,  card small 9.5px / 520

Changes:
  1. "Select Endpoint" heading above the two cards.
  2. Cards shrink to the Providers card metric (44px band, not 56px).
  3. Card captions become "Use /v1/messages" and
     "Use /v1/chat/completions or /v1/responses".
  4. Base URL description per dialect, OpenAI now:
     "Enter the API endpoint base URL ending in /v1."
  5. Grid + font tones matched to the Providers page.
"""
import pathlib

ROOT = pathlib.Path("/data/data/com.termux/files/home/zeline-frontend")


def patch_js():
    p = ROOT / "app3.js"
    s = p.read_text(encoding="utf-8")

    # ---- 1 + 3: heading above the pair, and the new captions
    OLD = """  const seg = el('div', 'pv-seg');
  seg.setAttribute('role', 'tablist');
  seg.innerHTML = `
    <button class="pv-seg-btn" data-dialect="anthropic" type="button" role="tab">
      <strong>Anthropic Compatible</strong>
      <small>/v1/messages</small>
    </button>
    <button class="pv-seg-btn" data-dialect="openai" type="button" role="tab">
      <strong>OpenAI Compatible</strong>
      <small>/v1/chat · /v1/responses</small>
    </button>`;
  if (!showPresetPicker) body.appendChild(seg);"""
    NEW = """  /* The endpoint choice gets its own titled group, so it reads as a step
     ("Select Endpoint") rather than two loose buttons above the fields. */
  const segGroup = el('div', 'pv-seg-group');
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
    assert OLD in s, "seg block not found"
    s = s.replace(OLD, NEW)

    # ---- 4: OpenAI Base URL copy
    OLD2 = """      desc: isAnthropic
        ? 'Use the base URL (ending in /v1) for your Anthropic-compatible API. The system will append /messages.'
        : 'Use the base URL (ending in /v1) for your OpenAI-compatible API.'"""
    NEW2 = """      desc: isAnthropic
        ? 'Use the base URL (ending in /v1) for your Anthropic-compatible API. The system will append /messages.'
        : 'Enter the API endpoint base URL ending in /v1.'"""
    assert OLD2 in s, "base url desc not found"
    s = s.replace(OLD2, NEW2)

    p.write_text(s, encoding="utf-8")
    print("app3.js: Select Endpoint heading, new captions, OpenAI base-URL copy")


def patch_css():
    p = ROOT / "style.css"
    s = p.read_text(encoding="utf-8")

    # ---- 5: grid tone identical to the Providers page (.03 not .026)
    s = s.replace("""  background-color:#0d0e11;
  background-image:
    linear-gradient(rgba(255,255,255,.026) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255,255,255,.026) 1px, transparent 1px);""",
"""  background-color:#0d0e11;
  /* .03 alpha over #0d0e11 — the exact pair the Providers page paints. */
  background-image:
    linear-gradient(rgba(255,255,255,.03) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255,255,255,.03) 1px, transparent 1px);""")

    # ---- 2: cards shrink to the Providers card band, plus the group heading
    OLD = """/* Exactly two lines: title on one, endpoint caption on the other. Both are
   clipped rather than wrapped, so a long label can never push the card to a
   third line and desync the two cards' heights. */
.provider-form .pv-seg-btn{
  display:flex;flex-direction:column;align-items:flex-start;justify-content:center;
  gap:2px;height:56px;padding:0 11px;
  border-radius:13px;text-align:left;
  background:#131418;border:1px solid #23242a;color:#9a9aa2;
  /* Colour/shadow animate; `transform` is reserved for the press so the two
     never fight during a switch. */
  transition:background .2s cubic-bezier(.4,0,.2,1),
             border-color .2s cubic-bezier(.4,0,.2,1),
             color .2s cubic-bezier(.4,0,.2,1),
             box-shadow .2s cubic-bezier(.4,0,.2,1),
             transform .13s ease;
}
.provider-form .pv-seg-btn>strong,
.provider-form .pv-seg-btn>small{
  display:block;max-width:100%;
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis;
}
.provider-form .pv-seg-btn strong{
  font-size:11.5px;font-weight:650;letter-spacing:-.015em;line-height:1.3;
}
.provider-form .pv-seg-btn small{
  font-size:9.5px;font-weight:500;line-height:1.3;
  letter-spacing:0;opacity:.8;font-family:var(--mono,ui-monospace,monospace);
}
.provider-form .pv-seg-btn:active{transform:scale(.97)}"""

    NEW = """/* "Select Endpoint" group heading — same metric as a Providers section title
   (12.5px / 680 / rgb(242,242,244) / -0.25px), so this screen and the list it
   came from share one type scale. */
.pv-seg-group{display:flex;flex-direction:column;gap:7px}
.pv-seg-head h4{
  margin:0;color:#f2f2f4;
  font-size:12.5px;font-weight:680;letter-spacing:-.02em;line-height:1.25;
}
html[data-app-theme='light'] .pv-seg-head h4{color:#17171a}

/* Two lines, but on the Providers card band: 44px, padding 8px 10px, radius
   10px. Both lines are clipped rather than wrapped, so a long caption can never
   push one card taller than the other. */
.provider-form .pv-seg-btn{
  display:flex;flex-direction:column;align-items:flex-start;justify-content:center;
  gap:1px;height:44px;padding:0 10px;
  border-radius:10px;text-align:left;
  background:#131418;border:1px solid #23242a;color:#9a9aa2;
  /* Colour/shadow animate; `transform` is reserved for the press so the two
     never fight during a switch. */
  transition:background .2s cubic-bezier(.4,0,.2,1),
             border-color .2s cubic-bezier(.4,0,.2,1),
             color .2s cubic-bezier(.4,0,.2,1),
             box-shadow .2s cubic-bezier(.4,0,.2,1),
             transform .13s ease;
}
.provider-form .pv-seg-btn>strong,
.provider-form .pv-seg-btn>small{
  display:block;max-width:100%;
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis;
}
/* Providers card copy: strong 12px/670, small 9.5px/520. */
.provider-form .pv-seg-btn strong{
  font-size:12px;font-weight:670;letter-spacing:-.015em;line-height:1.2;
}
.provider-form .pv-seg-btn small{
  font-size:9px;font-weight:520;line-height:1.2;
  letter-spacing:0;opacity:.82;
}
.provider-form .pv-seg-btn:active{transform:scale(.97)}"""
    assert OLD in s, "seg button block not found"
    s = s.replace(OLD, NEW)

    # ---- 5: field label/description tones to match the Providers page
    s = s.replace(""".provider-form .field>label{
  font-size:12px;font-weight:640;letter-spacing:-.005em;color:#b3b3bd;
}""",
"""/* Field titles use the Providers section-title colour; captions use its
   secondary tone (rgb(125,125,135)). */
.provider-form .field>label{
  font-size:12px;font-weight:660;letter-spacing:-.02em;color:#f2f2f4;
}""")
    s = s.replace(""".provider-form .field-desc{
  margin:0 0 5px;color:#8a8a8a;
  font-size:10.5px;line-height:1.35;letter-spacing:-.002em;
}""",
""".provider-form .field-desc{
  margin:0 0 5px;color:#7d7d87;
  font-size:9.5px;font-weight:520;line-height:1.4;letter-spacing:.002em;
}""")

    # Slightly tighter overall rhythm now that the cards are shorter.
    s = s.replace(".provider-form{gap:15px;padding:4px 0 10px}",
                  ".provider-form{gap:14px;padding:4px 0 10px}")
    s = s.replace(".pv-fields{gap:15px}", ".pv-fields{gap:14px}")

    p.write_text(s, encoding="utf-8")
    print("style.css: grid .03, 44px cards, Providers type scale")


patch_js()
patch_css()
