#!/usr/bin/env python3
"""v384 — premium pass on the Add-Provider screen.

  * Anthropic tab = orange, OpenAI tab = white (as requested)
  * Grid backdrop behind the sheet
  * Larger, tighter type on labels/inputs and on the Back / Check buttons
  * Cards get depth: inner hairline, gradient sheen, press feedback
  * Pull/reveal animation when the form swaps between dialects
"""
import pathlib

CSS = pathlib.Path("/data/data/com.termux/files/home/zeline-frontend/style.css")

BLOCK = r'''

/* ═════════════════════ v384 — Add-Provider premium pass ═════════════════════
   Scope is deliberately narrow: `.provider-form` and the modal chrome while a
   provider form is mounted. Everything is scoped through `.modal:has(...)` so
   no other sheet in the app inherits this treatment.

   Requested: Anthropic = orange, OpenAI = white, nicer cards + fonts, a pull
   animation on swap, and a grid behind it all.                               */

/* ── grid backdrop ─────────────────────────────────────────────────────────
   38px lattice, same cadence as the Home/Usage surfaces so this screen reads
   as part of the same product rather than a bolted-on sheet. Painted on the
   body (not the head/foot) to keep the bars flat and legible. */
.modal-body:has(.provider-form){
  background-color:#0b0b0e;
  background-image:
    linear-gradient(rgba(255,255,255,.030) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255,255,255,.030) 1px, transparent 1px);
  background-size:38px 38px, 38px 38px;
  background-position:-1px -1px, -1px -1px;
}
html[data-app-theme='light'] .modal-body:has(.provider-form){
  background-color:#f4f4f7;
  background-image:
    linear-gradient(rgba(0,0,0,.045) 1px, transparent 1px),
    linear-gradient(90deg, rgba(0,0,0,.045) 1px, transparent 1px);
}

.provider-form{gap:18px;padding:6px 0 10px}

/* ── segmented dialect switcher ────────────────────────────────────────────
   Two tabs, tinted by brand: Anthropic orange, OpenAI white. The active tab
   lifts off the track with a real shadow so the choice is unmistakable at a
   glance on a phone. */
.provider-form .pv-seg{
  grid-template-columns:1fr 1fr;gap:5px;
  padding:5px;border-radius:15px;
  background:linear-gradient(180deg,#131317,#101014);
  border:1px solid #26262d;
  box-shadow:inset 0 1px 0 rgba(255,255,255,.035);
}
.provider-form .pv-seg-btn{
  gap:2px;padding:11px 12px;border-radius:11px;
  letter-spacing:-.01em;
  transition:background .18s ease, color .18s ease,
             border-color .18s ease, transform .12s ease, box-shadow .18s ease;
}
.provider-form .pv-seg-btn strong{font-size:12.5px;font-weight:680;letter-spacing:-.015em}
.provider-form .pv-seg-btn small{font-size:9.5px;font-weight:520;letter-spacing:.01em;opacity:.8}
.provider-form .pv-seg-btn:active{transform:scale(.985)}

/* Anthropic — orange. */
.provider-form .pv-seg-btn[data-dialect="anthropic"].is-active{
  background:linear-gradient(158deg,#f2884f,#dd5f2c);
  border-color:rgba(255,170,120,.55);
  color:#fff;
  box-shadow:0 4px 14px rgba(203,79,36,.34), inset 0 1px 0 rgba(255,255,255,.22);
}
.provider-form .pv-seg-btn[data-dialect="anthropic"].is-active small{color:rgba(255,255,255,.86);opacity:1}

/* OpenAI — white. */
.provider-form .pv-seg-btn[data-dialect="openai"].is-active{
  background:linear-gradient(178deg,#ffffff,#eeeef2);
  border-color:rgba(255,255,255,.7);
  color:#15151a;
  box-shadow:0 4px 14px rgba(0,0,0,.34), inset 0 1px 0 #fff;
}
.provider-form .pv-seg-btn[data-dialect="openai"].is-active small{color:#5b5b66;opacity:1}

html[data-app-theme='light'] .provider-form .pv-seg{
  background:linear-gradient(180deg,#ededf2,#e7e7ee);border-color:#d8d8e1;
}
html[data-app-theme='light'] .provider-form .pv-seg-btn[data-dialect="openai"].is-active{
  background:linear-gradient(178deg,#fff,#fafafc);border-color:#d0d0da;color:#15151a;
  box-shadow:0 3px 12px rgba(30,30,40,.12), inset 0 1px 0 #fff;
}

/* ── field wells ───────────────────────────────────────────────────────────
   Bigger type, tighter tracking, and a hairline highlight on the top edge so
   each well looks cut into the surface rather than pasted on it. */
.provider-form .field>label{
  font-size:12px;font-weight:640;letter-spacing:-.005em;color:#b3b3bd;
}
.provider-form .field input,
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
}
.provider-form .field small{font-size:11.5px;line-height:1.5;letter-spacing:-.002em}
.provider-form .field-req{font-size:12px}

html[data-app-theme='light'] .provider-form .field input,
html[data-app-theme='light'] .provider-form .field select{
  background:linear-gradient(180deg,#fff,#fcfcfe);
  border-color:#cdcdd8;
  box-shadow:0 1px 2px rgba(20,20,30,.045);
}
html[data-app-theme='light'] .provider-form .field input:focus,
html[data-app-theme='light'] .provider-form .field select:focus{
  border-color:#3f7fd6;box-shadow:0 0 0 3px rgba(63,127,214,.16);
}

/* ── swap animation ───────────────────────────────────────────────────────
   The dialect switch rebuilds `#pvFields`; a short pull-in makes the exchange
   legible instead of a jarring content pop. Fields stagger so the eye follows
   the change downward. */
.pv-fields{gap:18px}
.pv-fields>.field{animation:pvPullIn .26s cubic-bezier(.22,1,.36,1) backwards}
.pv-fields>.field:nth-child(1){animation-delay:.00s}
.pv-fields>.field:nth-child(2){animation-delay:.03s}
.pv-fields>.field:nth-child(3){animation-delay:.06s}
.pv-fields>.field:nth-child(4){animation-delay:.09s}
.pv-fields>.field:nth-child(5){animation-delay:.12s}
.pv-fields>.field:nth-child(6){animation-delay:.15s}
@keyframes pvPullIn{
  from{opacity:0;transform:translateY(-7px) scale(.985)}
  to{opacity:1;transform:none}
}

/* ── result banner ────────────────────────────────────────────────────────*/
.provider-form-note:not(:empty){
  padding:12px 14px;border-radius:13px;
  font-size:11.5px;line-height:1.5;letter-spacing:-.002em;
  animation:pvPullIn .24s cubic-bezier(.22,1,.36,1);
}
.provider-form-note.is-set{
  background:linear-gradient(180deg,rgba(77,127,240,.14),rgba(77,127,240,.08));
  box-shadow:inset 0 1px 0 rgba(160,195,255,.14);
}
.provider-form-note.is-bad{
  background:linear-gradient(180deg,rgba(255,112,120,.15),rgba(255,112,120,.08));
  box-shadow:inset 0 1px 0 rgba(255,170,175,.14);
}

/* ── modal chrome while a provider form is open ───────────────────────────
   Bigger Back glyph and a heavier title, and the footer buttons get real
   presence: the primary reads as a solid action, not a chip. */
.modal:has(.provider-form) .modal-head{
  background:linear-gradient(180deg,#101014,#0c0c0f)!important;
  border-bottom-color:#22222a!important;
}
.modal:has(.provider-form) .modal-head h3{
  font-size:15.5px!important;font-weight:700!important;letter-spacing:-.03em!important;
}
.modal:has(.provider-form) .modal-head-subtitle{
  font-size:11.5px;letter-spacing:-.004em;color:#8f8f9a;
}
.modal:has(.provider-form) .modal-back{
  color:#eaeaef!important;
  transition:background .16s ease, transform .12s ease;
}
.modal:has(.provider-form) .modal-back svg{width:25px!important;height:25px!important}
.modal:has(.provider-form) .modal-back:active{background:#25252c!important;transform:scale(.9)}

.modal:has(.provider-form) .modal-foot{
  background:linear-gradient(180deg,#0c0c0f,#0a0a0d)!important;
  border-top-color:#22222a!important;
  gap:10px!important;
}
.modal:has(.provider-form) .modal-foot .btn{
  min-height:48px!important;border-radius:14px!important;
  font-size:13px!important;font-weight:660!important;letter-spacing:-.012em!important;
  transition:transform .12s ease, filter .16s ease, box-shadow .16s ease;
}
.modal:has(.provider-form) .modal-foot .btn:active{transform:scale(.975)}
/* Cancel — quiet, but not invisible. */
.modal:has(.provider-form) .modal-foot .btn:not(.primary){
  flex:0 0 34%!important;
  background:#1c1c22!important;color:#c8c8d2!important;
  border:1px solid #303038!important;
}
/* Check Connection — the affirmative action. */
.modal:has(.provider-form) .modal-foot .btn.primary{
  background:linear-gradient(178deg,#ffffff,#ececf1)!important;color:#101014!important;
  box-shadow:0 4px 16px rgba(0,0,0,.4), inset 0 1px 0 #fff;
}
.modal:has(.provider-form) .modal-foot .btn.primary:active{filter:brightness(.96)}

html[data-app-theme='light'] .modal:has(.provider-form) .modal-head,
html[data-app-theme='light'] .modal:has(.provider-form) .modal-foot{
  background:linear-gradient(180deg,#fff,#fafafd)!important;border-color:#dfdfe6!important;
}
html[data-app-theme='light'] .modal:has(.provider-form) .modal-head-subtitle{color:#63636e}
html[data-app-theme='light'] .modal:has(.provider-form) .modal-foot .btn:not(.primary){
  background:#efeff3!important;color:#40404a!important;border-color:#d8d8e0!important;
}
html[data-app-theme='light'] .modal:has(.provider-form) .modal-foot .btn.primary{
  background:linear-gradient(178deg,#26262c,#16161a)!important;color:#fff!important;
  box-shadow:0 4px 14px rgba(20,20,30,.22);
}

/* ── Add Provider entry card ──────────────────────────────────────────────*/
.pv-add-main{
  background:linear-gradient(150deg,#4a8bfa,#2461e6);
  box-shadow:0 1px 0 rgba(255,255,255,.10) inset;
  transition:transform .12s ease, filter .16s ease;
}
.pv-add-main strong{font-size:13px;font-weight:690;letter-spacing:-.015em}
.pv-add-main small{font-size:10px;font-weight:520;color:rgba(255,255,255,.8)}
.pv-add-main:active{transform:scale(.985)}

@media (prefers-reduced-motion:reduce){
  .pv-fields>.field,
  .provider-form-note:not(:empty){animation:none}
  .provider-form .pv-seg-btn,
  .modal:has(.provider-form) .modal-foot .btn,
  .modal:has(.provider-form) .modal-back,
  .pv-add-main{transition:none}
}
'''

text = CSS.read_text(encoding="utf-8")
if "v384 — Add-Provider premium pass" in text:
    print("v384 block already present — skipping")
else:
    CSS.write_text(text + BLOCK, encoding="utf-8")
    print(f"appended v384 block ({len(BLOCK)} chars)")
