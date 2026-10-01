#!/usr/bin/env python3
"""Five fixes on the Add-Provider screen, matched to Project/Session/Cronjob.

1. Back icon + title: same size/position as the workspace sheets
     title 16px / weight 500 / letterSpacing normal, back svg 23px,
     head grid 64px 1fr 64px.
2. Elastic pull-to-stretch on the sheet body, same damped spring Home uses.
3. Label -> description spacing tightened.
4. Card wells darkened to the workspace tone instead of the lighter gradient.
5. Anthropic / OpenAI split into TWO separate cards side by side in one row,
   each with its caption underneath (not a fused segmented control).
"""
import pathlib

ROOT = pathlib.Path("/data/data/com.termux/files/home/zeline-frontend")


def patch_css():
    p = ROOT / "style.css"
    s = p.read_text(encoding="utf-8")

    # ---------------------------------------------------------------- 1 + 3 + 4
    # Replace the whole v384 chrome section with values matched to the workspace.
    start = s.index("/* ── modal chrome while a provider form is open ─")
    # Stop before the action cards: the old range swallowed .pv-act* and
    # .field-desc, deleting rules this patch then tried to edit.
    end = s.index("/* Action cards inside the form", start)

    NEW_CHROME = """/* ── modal chrome: matched to Project/Session/Cronjob ─────────────────────
   Measured from those sheets rather than guessed:
     title      16px / weight 500 / letter-spacing normal
     back svg   23px
     head grid  64px minmax(0,1fr) 64px, padding 0 8px
   The earlier pass had 15.5px/700/-.03em, a 25px glyph and a 56px column, so
   the header visibly disagreed with every other full-screen sheet. */
.modal:not(.compact-confirm-modal):has(.provider-form) .modal-head{
  grid-template-columns:64px minmax(0,1fr) 64px!important;
  padding:env(safe-area-inset-top) 8px 0!important;
  background:#131313!important;
  border-bottom:1px solid #1f1f1f!important;
}
.modal:has(.provider-form) .modal-head h3{
  font-size:16px!important;font-weight:500!important;letter-spacing:normal!important;
  color:#f1f1ef!important;
}
.modal:has(.provider-form) .modal-back{
  width:48px!important;height:48px!important;color:#f1f1ef!important;
}
.modal:has(.provider-form) .modal-back svg{width:23px!important;height:23px!important}
.modal:has(.provider-form) .modal-back:active{background:#202020!important;transform:none!important}

"""
    s = s[:start] + NEW_CHROME + s[end:]

    # Darker field wells — match the workspace surface tone (#131313 body), so
    # the inputs read as recessed panels rather than lifted light cards.
    OLD_WELL = """.provider-form .field input,
.provider-form .field select{
  height:48px;padding:0 14px;border-radius:13px;
  font-size:14.5px;font-weight:500;letter-spacing:-.01em;
  background:linear-gradient(180deg,#1d1d22,#191920);
  border:1px solid #34343d;
  box-shadow:inset 0 1px 0 rgba(255,255,255,.032);
  transition:border-color .16s ease, box-shadow .16s ease, background .16s ease;
}
.provider-form .field input:focus,
.provider-form .field select:focus{
  background:linear-gradient(180deg,#212129,#1c1c24);
  border-color:#5b8cf5;
  box-shadow:0 0 0 3px rgba(77,127,240,.20), inset 0 1px 0 rgba(255,255,255,.05);
}"""
    NEW_WELL = """.provider-form .field input,
.provider-form .field select{
  height:46px;padding:0 13px;border-radius:12px;
  font-size:14px;font-weight:500;letter-spacing:-.01em;
  /* Darker than the previous gradient: on a #131313 sheet the old #1d1d22 well
     read as a bright card. This sits just above the surface instead. */
  background:#171719;
  border:1px solid #262629;
  box-shadow:none;
  transition:border-color .16s ease, box-shadow .16s ease, background .16s ease;
}
.provider-form .field input:focus,
.provider-form .field select:focus{
  background:#1a1a1d;
  border-color:#3f6fd0;
  box-shadow:0 0 0 3px rgba(63,111,208,.16);
}"""
    assert OLD_WELL in s
    s = s.replace(OLD_WELL, NEW_WELL)

    # Tighter label -> description -> control rhythm.
    OLD_DESC = """.provider-form .field-desc{
  margin:0 0 2px;color:#8d8d97;
  font-size:11.5px;line-height:1.45;letter-spacing:-.002em;
}"""

    NEW_DESC = """/* Title, description and control belong together: the previous 16px field gap
   plus a 2px margin left the caption floating between two fields. */
.provider-form .field{gap:3px}
.provider-form .field>label{margin:0}
.provider-form .field-desc{
  margin:0 0 5px;color:#8a8a92;
  font-size:11px;line-height:1.4;letter-spacing:-.002em;
}"""
    assert OLD_DESC in s
    s = s.replace(OLD_DESC, NEW_DESC)

    s = s.replace(".provider-form{gap:18px;padding:6px 0 10px}",
                  ".provider-form{gap:15px;padding:4px 0 10px}")
    s = s.replace(".pv-fields{gap:18px}", ".pv-fields{gap:15px}")

    # ------------------------------------------------------------------------ 5
    # Two separate dialect cards in one row, each captioned underneath.
    OLD_SEG_START = ".provider-form .pv-seg{"
    i = s.index(OLD_SEG_START)
    j = s.index("/* ── field wells ─", i)

    NEW_SEG = """/* ── dialect cards ───────────────────────────────────────────────────────
   TWO separate cards, side by side in one row, each with its own caption. The
   earlier fused segmented control read as one control with a slider; these are
   two distinct choices, so they get two distinct cards. */
.provider-form .pv-seg{
  display:grid;grid-template-columns:1fr 1fr;gap:9px;
  padding:0;background:transparent;border:0;box-shadow:none;
}
.provider-form .pv-seg-btn{
  display:flex;flex-direction:column;align-items:flex-start;gap:3px;
  height:auto;min-height:60px;padding:11px 12px;line-height:1.25;
  border-radius:13px;text-align:left;white-space:normal;
  background:#171719;border:1px solid #262629;color:#9a9aa2;
  transition:background .16s ease, border-color .16s ease,
             color .16s ease, transform .12s ease, box-shadow .18s ease;
}
.provider-form .pv-seg-btn strong{
  font-size:12px;font-weight:640;letter-spacing:-.015em;line-height:1.25;
}
/* Caption is back, under the title, inside each card. */
.provider-form .pv-seg-btn small{
  display:block;font-size:9.5px;font-weight:500;line-height:1.3;
  letter-spacing:.002em;opacity:.85;
}
.provider-form .pv-seg-btn:active{transform:scale(.985)}

/* Anthropic — orange. */
.provider-form .pv-seg-btn[data-dialect="anthropic"].is-active{
  background:linear-gradient(158deg,#e87a44,#cf5626);
  border-color:rgba(255,166,116,.5);
  color:#fff;
  box-shadow:0 3px 12px rgba(186,70,30,.3), inset 0 1px 0 rgba(255,255,255,.18);
}
.provider-form .pv-seg-btn[data-dialect="anthropic"].is-active small{color:rgba(255,255,255,.88);opacity:1}

/* OpenAI — white. */
.provider-form .pv-seg-btn[data-dialect="openai"].is-active{
  background:linear-gradient(178deg,#fafafc,#e9e9ee);
  border-color:rgba(255,255,255,.6);
  color:#15151a;
  box-shadow:0 3px 12px rgba(0,0,0,.3), inset 0 1px 0 #fff;
}
.provider-form .pv-seg-btn[data-dialect="openai"].is-active small{color:#5b5b66;opacity:1}

html[data-app-theme='light'] .provider-form .pv-seg-btn{
  background:#fff;border-color:#dcdce3;color:#5f5f68;
}
html[data-app-theme='light'] .provider-form .pv-seg-btn[data-dialect="openai"].is-active{
  background:linear-gradient(178deg,#fff,#f6f6f9);border-color:#c9c9d4;color:#15151a;
  box-shadow:0 3px 11px rgba(30,30,40,.14), inset 0 1px 0 #fff;
}

"""
    s = s[:i] + NEW_SEG + s[j:]

    # Light-theme well tone follows the darker treatment.
    s = s.replace("""html[data-app-theme='light'] .provider-form .field input,
html[data-app-theme='light'] .provider-form .field select{
  background:linear-gradient(180deg,#fff,#fcfcfe);
  border-color:#cdcdd8;
  box-shadow:0 1px 2px rgba(20,20,30,.045);
}""", """html[data-app-theme='light'] .provider-form .field input,
html[data-app-theme='light'] .provider-form .field select{
  background:#fff;border-color:#dcdce3;box-shadow:none;
}""")

    # ------------------------------------------------------------------------ 2
    # Elastic pull affordance on the sheet body.
    s += """

/* ── elastic pull on the provider sheet ───────────────────────────────────
   Same damped stretch the Home canvas uses (see wireSheetPullStretch): the JS
   writes a transform, these classes own the spring-back and stop the gesture
   from selecting text mid-pull. */
.modal-body.sheet-pull-active{
  transition:none!important;
  user-select:none;-webkit-user-select:none;
}
.modal-body.sheet-pull-releasing{
  transition:transform .26s cubic-bezier(.22,1,.36,1)!important;
}
@media(prefers-reduced-motion:reduce){
  .modal-body.sheet-pull-releasing{transition:none!important}
}
"""

    p.write_text(s, encoding="utf-8")
    print("style.css patched: chrome parity, darker wells, tighter desc, split cards, pull classes")


def patch_js():
    """Add the elastic pull, and restore the per-card captions."""
    p = ROOT / "app3.js"
    s = p.read_text(encoding="utf-8")

    # Captions back inside each dialect card.
    OLD = """    <button class="pv-seg-btn" data-dialect="anthropic" type="button" role="tab">
      <strong>Anthropic Compatible</strong>
    </button>
    <button class="pv-seg-btn" data-dialect="openai" type="button" role="tab">
      <strong>OpenAI Compatible</strong>
    </button>`;"""
    NEW = """    <button class="pv-seg-btn" data-dialect="anthropic" type="button" role="tab">
      <strong>Anthropic Compatible</strong>
      <small>Claude-style, appends /v1/messages</small>
    </button>
    <button class="pv-seg-btn" data-dialect="openai" type="button" role="tab">
      <strong>OpenAI Compatible</strong>
      <small>Chat Completions or Responses</small>
    </button>`;"""
    assert OLD in s, "seg markup not found"
    s = s.replace(OLD, NEW)

    # Wire the elastic pull when the form mounts.
    OLD2 = """  modal({
    title: dialect === 'anthropic' ? 'Add Anthropic Compatible' : 'Add OpenAI Compatible',
    body,
    actions: []
  });
  setHead();
}"""
    NEW2 = """  modal({
    title: dialect === 'anthropic' ? 'Add Anthropic Compatible' : 'Add OpenAI Compatible',
    body,
    actions: []
  });
  setHead();
  wireSheetPullStretch();
}

/* Elastic pull-to-stretch for the modal sheet body, mirroring the Home canvas
   affordance (wireHomePullStretch in app4.js). The sheet body scrolls natively,
   so this only engages at scrollTop 0 on a clearly downward drag; anything else
   — upward scroll, horizontal swipe, a drag starting inside a field — is left
   to the browser. */
function wireSheetPullStretch() {
  const sheet = document.querySelector('.modal-body');
  const PULL_MAX_PX = 14;
  const PULL_INTENT_PX = 7;
  const PULL_RANGE_PX = 64;
  if (!sheet || sheet.dataset.sheetPullWired) return;
  sheet.dataset.sheetPullWired = '1';

  let gesture = null;
  let frame = 0;
  let releaseTimer = 0;

  const clearRelease = () => {
    clearTimeout(releaseTimer);
    releaseTimer = 0;
    sheet.classList.remove('sheet-pull-releasing');
    sheet.style.transform = '';
  };

  const paint = () => {
    frame = 0;
    if (!gesture?.active) return;
    sheet.style.transform = `translate3d(0,${gesture.pull.toFixed(2)}px,0)`;
  };
  const queuePaint = () => { if (!frame) frame = requestAnimationFrame(paint); };

  const release = () => {
    const pulled = gesture?.active && gesture.pull > 0;
    gesture = null;
    if (frame) { cancelAnimationFrame(frame); frame = 0; }
    sheet.classList.remove('sheet-pull-active');
    if (!pulled) { clearRelease(); return; }
    sheet.classList.add('sheet-pull-releasing');
    sheet.style.transform = '';
    const finish = () => clearRelease();
    sheet.addEventListener('transitionend', finish, { once: true });
    releaseTimer = setTimeout(finish, 320);
  };

  sheet.addEventListener('touchstart', event => {
    clearRelease();
    // Only from the very top, and never when a field owns the gesture.
    if (event.touches.length !== 1 || sheet.scrollTop > 0
        || event.target.closest('input,textarea,select,[contenteditable]')) {
      gesture = null;
      return;
    }
    const t = event.touches[0];
    gesture = { startX: t.clientX, startY: t.clientY, pull: 0, active: false, cancelled: false };
  }, { passive: true });

  sheet.addEventListener('touchmove', event => {
    const st = gesture;
    const t = event.touches[0];
    if (!st || !t || st.cancelled) return;
    const dx = t.clientX - st.startX;
    const dy = t.clientY - st.startY;
    if (!st.active) {
      if (Math.max(Math.abs(dx), Math.abs(dy)) < PULL_INTENT_PX) return;
      // Downward, and clearly more vertical than horizontal, or hand it back.
      if (dy <= 0 || Math.abs(dy) <= Math.abs(dx) * 1.15) { st.cancelled = true; return; }
      st.active = true;
      sheet.classList.add('sheet-pull-active');
    }
    const distance = Math.max(0, dy);
    st.pull = PULL_MAX_PX * (1 - Math.exp(-distance / PULL_RANGE_PX));
    queuePaint();
  }, { passive: true });

  sheet.addEventListener('touchend', release, { passive: true });
  sheet.addEventListener('touchcancel', release, { passive: true });
}"""
    assert OLD2 in s, "modal tail not found"
    s = s.replace(OLD2, NEW2)

    p.write_text(s, encoding="utf-8")
    print("app3.js patched: captions restored, elastic pull wired")


patch_css()
patch_js()
