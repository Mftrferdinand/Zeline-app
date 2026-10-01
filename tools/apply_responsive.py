#!/usr/bin/env python3
"""Make every sheet behave on tablet/desktop instead of stretching.

Measured problem (tools/probe_widths.py):
    tablet    bar 768px wide, body 560px, bodyLeft 0   -> bar and body disagree
    desktop   bar 1280px wide, body 560px, bodyLeft 0  -> content jammed left
              with ~700px of dead space, and the bar looks like a stray ribbon

Native Android apps run a single-column, centred column on large screens; they
do not stretch a phone sheet to 1280px. These rules give the whole app that
shape:

  * One shared max content width, so the bar and the body always agree.
  * The bar's inner grid is centred at that width, so its back button and title
    line up with the body's content instead of hugging the screen edge.
  * The scrim backdrop dims the empty area so the sheet reads as a panel rather
    than a broken full-bleed layout.

Everything is scoped to `min-width: 700px` so phones are bit-for-bit unchanged.
"""
import pathlib

CSS = pathlib.Path("/data/data/com.termux/files/home/zeline-frontend/style.css")

BLOCK = r'''

/* ═════════════════ v386 — tablet / desktop layout ════════════════════════════
   A phone sheet stretched across a 1280px window reads as broken: the app bar
   becomes a thin ribbon while the content stays a narrow column pinned to the
   left. These rules give every full-screen surface one centred column, the way
   a native Android app lays out on a large display.

   Scoped to >=700px: the phone layout is untouched. */

@media (min-width: 700px) {
  /* One shared content width. Both the bar's inner grid and the body use it, so
     the back button, title and every field sit on the same vertical rails. */
  :root { --app-content-max: 640px; }

  /* The sheet itself stops being edge-to-edge and becomes a centred panel. */
  .modal-root:not(:has(.compact-confirm-modal)) {
    align-items: center !important;
    justify-content: center !important;
    padding: 24px !important;
  }
  .modal:not(.compact-confirm-modal) {
    position: relative !important;
    inset: auto !important;
    width: 100% !important;
    max-width: var(--app-content-max) !important;
    height: min(92dvh, 960px) !important;
    max-height: 92dvh !important;
    margin: 0 auto !important;
    border: 1px solid #1f1f22 !important;
    border-radius: 18px !important;
    overflow: hidden !important;
    box-shadow: 0 24px 70px rgba(0, 0, 0, .55) !important;
  }

  /* Bar spans the panel, with its grid centred inside it. */
  html body .modal:not(.compact-confirm-modal) .modal-head,
  html body .modal.workspace-modal .modal-head {
    width: 100% !important;
    max-width: none !important;
    padding-left: 8px !important;
    padding-right: 8px !important;
    border-radius: 17px 17px 0 0 !important;
  }

  /* Body keeps the same rail width as the bar's columns. */
  .modal:not(.compact-confirm-modal) .modal-body,
  .modal.workspace-modal .modal-body {
    width: 100% !important;
    max-width: none !important;
    margin: 0 !important;
    padding-left: 16px !important;
    padding-right: 16px !important;
  }

  /* The page surfaces (Home, Usage, Settings, Providers) get the same
     treatment: a centred column instead of a full-bleed stretch. */
  .pv-appbar {
    width: 100% !important;
  }
  .pv-appbar > * {
    /* keeps the bar's own 44/1fr/44 grid, just inset from the panel edge */
    max-width: none !important;
  }
  #page-providers .page-body,
  .usage-page,
  .settings-page,
  .chat-home {
    width: 100% !important;
    max-width: var(--app-content-max) !important;
    margin-left: auto !important;
    margin-right: auto !important;
  }
  /* Providers bar is a page-level element, so centre its grid too. */
  #page-providers .pv-appbar {
    max-width: var(--app-content-max) !important;
    margin-left: auto !important;
    margin-right: auto !important;
    border-left: 1px solid #1f1f22;
    border-right: 1px solid #1f1f22;
  }
  /* The grid backdrop belongs to the page, not the column. */
  #page-providers {
    background-attachment: fixed !important;
  }

  /* Two-column option cards and action buttons stay sane and equal. */
  .provider-form .pv-seg,
  .provider-form .pv-actions {
    max-width: 100%;
  }

  /* Dim the empty space so the centred column reads as intentional. */
  .modal-root:not(:has(.compact-confirm-modal))::before {
    content: '';
    position: absolute;
    inset: 0;
    background: rgba(0, 0, 0, .45);
    pointer-events: none;
  }
  .modal:not(.compact-confirm-modal) { z-index: 1; }
}

/* Very wide: give the panel a little more room, still centred. */
@media (min-width: 1200px) {
  :root { --app-content-max: 700px; }
}

/* Light theme keeps the same geometry with its own edges. */
@media (min-width: 700px) {
  html[data-app-theme='light'] .modal:not(.compact-confirm-modal) {
    border-color: #dedee3 !important;
    box-shadow: 0 24px 70px rgba(30, 30, 40, .18) !important;
  }
  html[data-app-theme='light'] #page-providers .pv-appbar {
    border-left-color: #dedee3;
    border-right-color: #dedee3;
  }
}
'''

text = CSS.read_text(encoding="utf-8")
if "v386 — tablet / desktop layout" in text:
    print("v386 block already present")
else:
    CSS.write_text(text + BLOCK, encoding="utf-8")
    print(f"appended v386 responsive block ({len(BLOCK)} chars)")
