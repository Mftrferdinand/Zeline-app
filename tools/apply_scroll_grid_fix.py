#!/usr/bin/env python3
"""Three fixes on the Add-Provider sheet, all matched to the Providers page.

1. Grid alignment — the Providers page offsets the lattice by the app-bar
   height (`background-position:-1px var(--pv-bar-h)`) so the first visible row
   is a whole cell instead of a slice cut off behind the bar. The provider sheet
   started at -1px -1px, so its top row read as cropped.

2. Scroll was capped. `wireWorkspacePullNudge` was handed `.modal-body`; that
   helper assumes its first argument is the element that scrolls AND that it has
   a fixed, usually short content area (the workspace lists sit inside a
   non-scrolling sheet with `overflow:hidden`). On this sheet the body IS the
   scroller, so the gesture fought the native pan and the sheet appeared stuck.

3. Bottom breathing room — the Providers page leaves space below the last card;
   this sheet ended flush.
"""
import pathlib

ROOT = pathlib.Path("/data/data/com.termux/files/home/zeline-frontend")


def patch_js():
    p = ROOT / "app3.js"
    s = p.read_text(encoding="utf-8")

    OLD = """  /* Reuse the workspace pull gesture — same damping, same spring-back. The
     scroller is the modal body; the transform is applied to the form itself so
     the fixed grid backdrop behind it never moves (and so never looks cut). */
  const scroller = document.querySelector('.modal-body');
  if (scroller && typeof wireWorkspacePullNudge === 'function') {
    wireWorkspacePullNudge(scroller, body);
  }
}"""
    NEW = """  /* Intentionally NO pull-to-stretch gesture on this sheet.
     `wireWorkspacePullNudge` is built for the workspace sheets, whose lists sit
     inside a sheet with `overflow:hidden` and never scroll themselves; there the
     gesture is the only vertical affordance. Here `.modal-body` IS the scroller,
     so attaching the gesture to it both fought the native pan and left the sheet
     feeling stuck at the top — it could not be dragged up or down. Native
     scrolling is the correct behaviour for a long form, so the gesture stays off.
     The grid backdrop is already `position:fixed`, so it needs no pull to stay
     put. */
}"""
    assert OLD in s, "pull wiring block not found"
    s = s.replace(OLD, NEW)
    p.write_text(s, encoding="utf-8")
    print("app3.js: removed the conflicting pull gesture from this sheet")


def patch_css():
    p = ROOT / "style.css"
    s = p.read_text(encoding="utf-8")

    # ---- 1: offset the lattice by the bar height, exactly like Providers
    OLD = """.modal.provider-sheet-modal .modal-body::before{
  content:'';
  position:fixed;
  inset:0;
  z-index:0;
  pointer-events:none;
  background-color:#0d0e11;
  /* .03 alpha over #0d0e11 — the exact pair the Providers page paints. */
  background-image:
    linear-gradient(rgba(255,255,255,.03) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255,255,255,.03) 1px, transparent 1px);
  background-size:38px 38px, 38px 38px;
  background-position:-1px -1px, -1px -1px;
}"""
    NEW = """.modal.provider-sheet-modal .modal-body::before{
  content:'';
  position:fixed;
  inset:0;
  z-index:0;
  pointer-events:none;
  background-color:#0d0e11;
  /* .03 alpha over #0d0e11 — the exact pair the Providers page paints.
     The vertical origin is offset by the app-bar height (53px = 52 + 1px
     border) exactly as `#page-providers` does, so the first row below the bar
     is a whole 38px cell rather than a slice clipped by the bar. */
  background-image:
    linear-gradient(rgba(255,255,255,.03) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255,255,255,.03) 1px, transparent 1px);
  background-size:38px 38px, 38px 38px;
  background-position:-1px calc(53px + env(safe-area-inset-top)), -1px 0;
  background-repeat:repeat, repeat;
}"""
    assert OLD in s, "grid block not found"
    s = s.replace(OLD, NEW)

    # ---- 3: bottom breathing room, matching the Providers page
    OLD2 = """html[data-app-theme='light'] .modal.provider-sheet-modal .modal-body::before{
  background-color:#f3f3f5;
  background-image:
    linear-gradient(rgba(0,0,0,.045) 1px, transparent 1px),
    linear-gradient(90deg, rgba(0,0,0,.045) 1px, transparent 1px);
}"""
    NEW2 = """html[data-app-theme='light'] .modal.provider-sheet-modal .modal-body::before{
  background-color:#f3f3f5;
  background-image:
    linear-gradient(rgba(0,0,0,.045) 1px, transparent 1px),
    linear-gradient(90deg, rgba(0,0,0,.045) 1px, transparent 1px);
  background-position:-1px calc(53px + env(safe-area-inset-top)), -1px 0;
}

/* Room below the last control so the form can be scrolled a little past its
   content — the Providers page leaves the same trailing space. Applied to the
   form rather than the body so the padding scrolls with the content. */
.modal.provider-sheet-modal .provider-form{
  padding-bottom:calc(64px + env(safe-area-inset-bottom))!important;
}
/* Native vertical panning must win on this sheet; nothing here should swallow
   the gesture. */
.modal.provider-sheet-modal .modal-body{
  overscroll-behavior-y:contain!important;
  -webkit-overflow-scrolling:touch;
  touch-action:pan-y;
}"""
    assert OLD2 in s, "light grid block not found"
    s = s.replace(OLD2, NEW2)

    p.write_text(s, encoding="utf-8")
    print("style.css: grid offset by bar height, bottom space, pan enabled")


patch_js()
patch_css()
