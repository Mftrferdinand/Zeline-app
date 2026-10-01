#!/usr/bin/env python3
"""Make the Add-Provider sheet a genuine workspace sheet.

Diagnosis (measured, not guessed):
  * Cronjob's chrome comes from `.workspace-modal` + `.workspace-sheet`, a
    styling package the provider sheet never opted into. That is why the back
    glyph rendered 20px (a stray `.modal-back svg.zi{20px}` won) instead of the
    26px the workspace bar uses, and why the title/tone disagreed.
  * The body background was rgb(11,11,14) with a grid image, against Cronjob's
    flat rgb(19,19,19) — hence "background beda" and the grid slicing on scroll
    (a grid painted on the scrolling box scrolls with the content).

Fixes:
  1. Reuse `.workspace-modal` on the shell and `.workspace-sheet` on the form,
     so back icon, title, bar tone and the pull-to-stretch spring all come from
     the same rules Cronjob uses.
  2. Wire `wireWorkspacePullNudge` — the existing workspace gesture — instead of
     the bespoke one added earlier.
  3. Paint the grid on a FIXED backdrop layer behind the scroller so it cannot
     be clipped or dragged while scrolling.
  4. Match every tone to Cronjob: shell, bar, body, and the card wells.
  5. Tighten label -> description spacing further.
"""
import pathlib

ROOT = pathlib.Path("/data/data/com.termux/files/home/zeline-frontend")


def patch_js():
    p = ROOT / "app3.js"
    s = p.read_text(encoding="utf-8")

    # --- form root also carries workspace-sheet, so the pull CSS applies
    OLD = "  const body = el('div', 'provider-form');"
    NEW = ("  /* `workspace-sheet` opts this form into the same chrome + pull spring the\n"
           "     Project/Session/Cronjob sheets use, rather than a parallel set of rules. */\n"
           "  const body = el('div', 'provider-form workspace-sheet');")
    assert OLD in s, "form root not found"
    s = s.replace(OLD, NEW, 1)

    # --- replace the bespoke pull with the workspace one, and tag the shell
    OLD2 = """  setHead();
  wireSheetPullStretch();
}"""
    NEW2 = """  setHead();
  /* Tag the shell so `.workspace-modal` rules (back glyph 26px, bar tone,
     title metrics) win here exactly as they do on Cronjob. */
  document.querySelector('.modal')?.classList.add('workspace-modal', 'provider-sheet-modal');
  /* Reuse the workspace pull gesture — same damping, same spring-back. The
     scroller is the modal body; the transform is applied to the form itself so
     the fixed grid backdrop behind it never moves (and so never looks cut). */
  const scroller = document.querySelector('.modal-body');
  if (scroller && typeof wireWorkspacePullNudge === 'function') {
    wireWorkspacePullNudge(scroller, body);
  }
}"""
    assert OLD2 in s, "modal tail not found"
    s = s.replace(OLD2, NEW2)

    # --- drop the now-unused bespoke gesture
    start = s.index("/* Elastic pull-to-stretch for the modal sheet body, mirroring the Home canvas")
    end = s.index("\n}", s.index("sheet.addEventListener('touchcancel', release, { passive: true });")) + 2
    s = s[:start] + s[end:]

    # --- clear the workspace classes on close so other sheets are unaffected
    OLD3 = "  btnCancel.onclick = () => closeModal();"
    NEW3 = """  /* Strip the workspace tags on the way out: this shell is shared, and leaving
     them behind would restyle the next modal that reuses it. */
    const shell = document.querySelector('.modal');
  const untag = () => shell?.classList.remove('workspace-modal', 'provider-sheet-modal');
  btnCancel.onclick = () => { untag(); closeModal(); };
  document.querySelector('.modal-back')?.addEventListener('click', untag, { once: true });"""
    assert OLD3 in s
    s = s.replace(OLD3, NEW3)

    # createBtn success path must untag too
    s = s.replace("""      toast(`Provider "${payload.name}" created`, 'ok');
      closeModal();""",
"""      toast(`Provider "${payload.name}" created`, 'ok');
      untag();
      closeModal();""")

    p.write_text(s, encoding="utf-8")
    print("app3.js: workspace-modal/-sheet adopted, workspace pull wired, bespoke gesture removed")


def patch_css():
    p = ROOT / "style.css"
    s = p.read_text(encoding="utf-8")

    # ---- remove the old chrome block; workspace rules now provide it
    start = s.index("/* ── modal chrome: matched to Project/Session/Cronjob ─")
    end = s.index("/* Action cards inside the form", start)
    s = s[:start] + s[end:]

    # ---- remove the bespoke pull classes
    i = s.index("/* ── elastic pull on the provider sheet ─")
    j = s.index("\n", s.index("}", s.index(".modal-body.sheet-pull-releasing"))) + 1
    s = s[:i] + s[j:]

    # ---- grid must NOT live on the scroller (that is what looked cut)
    OLD_GRID_START = "/* `.modal:not(.compact-confirm-modal) .modal-body` sets `background:#131313"
    gi = s.index(OLD_GRID_START)
    gj = s.index(".provider-form{", gi)
    NEW_GRID = """/* Grid backdrop as a FIXED layer, not a background on the scroller.
   Painting it on `.modal-body` meant it scrolled with the content and got
   visibly sliced at the top edge on every drag. A fixed pseudo-element behind
   the form stays put while the fields move over it.

   Tones are taken from Cronjob: shell/bar/body all rgb(19,19,19) = #131313. */
.modal.provider-sheet-modal,
.modal.provider-sheet-modal .modal-head,
.modal.provider-sheet-modal .modal-body{
  background-color:#131313!important;
  background-image:none!important;
}
.modal.provider-sheet-modal .modal-body{
  position:relative!important;
  isolation:isolate;
}
.modal.provider-sheet-modal .modal-body::before{
  content:'';
  position:fixed;
  inset:0;
  z-index:0;
  pointer-events:none;
  background-color:#131313;
  background-image:
    linear-gradient(rgba(255,255,255,.030) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255,255,255,.030) 1px, transparent 1px);
  background-size:38px 38px, 38px 38px;
  background-position:-1px -1px, -1px -1px;
}
.modal.provider-sheet-modal .provider-form{position:relative;z-index:1}

html[data-app-theme='light'] .modal.provider-sheet-modal,
html[data-app-theme='light'] .modal.provider-sheet-modal .modal-head,
html[data-app-theme='light'] .modal.provider-sheet-modal .modal-body{
  background-color:#f3f3f5!important;
}
html[data-app-theme='light'] .modal.provider-sheet-modal .modal-body::before{
  background-color:#f3f3f5;
  background-image:
    linear-gradient(rgba(0,0,0,.045) 1px, transparent 1px),
    linear-gradient(90deg, rgba(0,0,0,.045) 1px, transparent 1px);
}

/* The workspace title rule is 18px/720; this sheet keeps Cronjob's own 16px/500
   app-bar metric, which is what the reference measurement showed. */
.modal.provider-sheet-modal .modal-head h3{
  font-size:16px!important;font-weight:500!important;letter-spacing:normal!important;
}
/* Cronjob's bar uses a 64px rail either side. */
.modal.provider-sheet-modal .modal-head{
  grid-template-columns:64px minmax(0,1fr) 64px!important;
  padding:env(safe-area-inset-top) 8px 0!important;
  border-bottom:1px solid #1f1f1f!important;
}

"""
    s = s[:gi] + NEW_GRID + s[gj:]

    # ---- wells: sit just above the #131313 sheet, like workspace rows
    s = s.replace("""  background:#171719;
  border:1px solid #262629;
  box-shadow:none;""",
"""  background:#191919;
  border:1px solid #272727;
  box-shadow:none;""")
    s = s.replace("""  background:#1a1a1d;
  border-color:#3f6fd0;""",
"""  background:#1c1c1c;
  border-color:#3f6fd0;""")
    # dialect cards + action cards follow the same tone
    s = s.replace("  background:#171719;border:1px solid #262629;color:#9a9aa2;",
                  "  background:#191919;border:1px solid #272727;color:#9a9aa2;")
    s = s.replace(""".pv-act-check{
  background:linear-gradient(180deg,#22222a,#1b1b22);
  border-color:#383842;color:#e9e9ef;
}""",
""".pv-act-check{
  background:#1f1f1f;border-color:#2e2e2e;color:#e9e9ef;
}""")
    s = s.replace(""".pv-act-create.is-locked,
.pv-act-create:disabled{
  background:#1a1a20;color:#5a5a66;border-color:#2b2b34;""",
""".pv-act-create.is-locked,
.pv-act-create:disabled{
  background:#1c1c1c;color:#5a5a5a;border-color:#292929;""")
    s = s.replace(".pv-act-cancel{\n  background:transparent;border-color:#2e2e37;color:#9a9aa6;\n}",
                  ".pv-act-cancel{\n  background:transparent;border-color:#2c2c2c;color:#9a9a9a;\n}")

    # ---- tighter label -> description
    s = s.replace(""".provider-form .field{gap:3px}
.provider-form .field>label{margin:0}
.provider-form .field-desc{
  margin:0 0 5px;color:#8a8a92;
  font-size:11px;line-height:1.4;letter-spacing:-.002em;
}""",
""".provider-form .field{gap:0}
.provider-form .field>label{margin:0 0 1px;line-height:1.3}
/* Caption hugs its title: 1px under the label, 5px above the control. Any more
   and the block reads as three separate things stacked in empty space. */
.provider-form .field-desc{
  margin:0 0 5px;color:#8a8a8a;
  font-size:10.5px;line-height:1.35;letter-spacing:-.002em;
}""")

    p.write_text(s, encoding="utf-8")
    print("style.css: fixed grid backdrop, Cronjob tones, tighter captions, old blocks removed")


patch_js()
patch_css()
