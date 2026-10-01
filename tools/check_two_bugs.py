#!/usr/bin/env python3
"""Verify the two reported bugs:
  1. Tapping the gutter above/below a card must dismiss the keyboard only —
     never switch endpoint. A tap physically inside a card must still switch.
  2. The sheet must scroll freely, including while a field has focus.
"""
import sys, time, json
sys.path.insert(0, "/data/data/com.termux/files/usr/lib/python3.13/site-packages")
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service

o = Options()
for a in ("--headless=new", "--no-sandbox", "--disable-dev-shm-usage",
          "--disable-gpu", "--window-size=430,700", "--incognito"):
    o.add_argument(a)
o.binary_location = "/data/data/com.termux/files/usr/lib/chromium/chrome"
o.set_capability("goog:loggingPrefs", {"browser": "ALL"})
d = webdriver.Chrome(service=Service("/data/data/com.termux/files/usr/bin/chromedriver"), options=o)

fails = 0
def check(cond, ok, bad):
    global fails
    if cond: print(f"   PASS: {ok}")
    else:
        fails += 1
        print(f"   FAIL: {bad}")

# Tap at explicit coordinates, as a finger would. Uses the real element under
# the point so the event path matches the browser's own hit-test.
TAP_AT = """
  const tapAt = (x, y) => {
    const el = document.elementFromPoint(x, y) || document.body;
    const opts = {bubbles:true, cancelable:true, pointerType:'touch', isPrimary:true,
                  clientX:x, clientY:y};
    const touchInit = {identifier:1, target:el, clientX:x, clientY:y};
    el.dispatchEvent(new PointerEvent('pointerdown', opts));
    el.dispatchEvent(new TouchEvent('touchstart', {bubbles:true,cancelable:true,
      touches:[new Touch(touchInit)], changedTouches:[new Touch(touchInit)]}));
    el.dispatchEvent(new PointerEvent('pointerup', opts));
    el.dispatchEvent(new TouchEvent('touchend', {bubbles:true,cancelable:true,
      touches:[], changedTouches:[new Touch(touchInit)]}));
    el.dispatchEvent(new MouseEvent('click', {bubbles:true,cancelable:true,
      clientX:x, clientY:y}));
  };
  const name = document.getElementById('pvName');
  name.focus();
  const before = document.querySelector('.pv-seg-btn.is-active').dataset.dialect;
  %BODY%
  return {before,
          after: document.querySelector('.pv-seg-btn.is-active').dataset.dialect,
          focused: document.activeElement === name};
"""

try:
    d.get("http://localhost:5173/"); time.sleep(2)
    d.execute_script("""
      localStorage.setItem('zeline.token','zln_abcdefghijklmnopqrstuvwxyz1234567890');
      localStorage.setItem('zeline.connection', JSON.stringify({configured:true,kind:'gateway',apiBase:'/api/v1'}));
    """)
    d.get("http://localhost:5173/"); time.sleep(4)
    d.execute_script("return document.getElementById('onboarding').hidden=true")
    d.execute_script("return go('providers')"); time.sleep(4)
    d.execute_script("return document.querySelector('.pv-add-main').click()"); time.sleep(3)

    # coordinates of the gutter between description and cards, and of a card
    pts = d.execute_script("""
      const r=e=>e.getBoundingClientRect();
      const card=document.querySelector('[data-dialect="anthropic"]');
      const other=document.querySelector('[data-dialect="openai"]');
      const desc=document.getElementById('pvSegDesc');
      const cr=r(card);
      return {
        gutterAbove:[cr.left+30, cr.top-3],
        gutterBelow:[cr.left+30, cr.bottom+3],
        betweenCards:[cr.right+4, cr.top+cr.height/2],
        outsideLeft:[Math.max(2,cr.left-8), cr.top+cr.height/2],
        onCard:[cr.left+cr.width/2, cr.top+cr.height/2],
        onOther:[r(other).left+r(other).width/2, r(other).top+r(other).height/2],
        onInactive:[r(card).left+r(card).width/2, r(card).top+cr.height/2]
      };
    """)
    print("probe points:", json.dumps(pts))

    for label, key in [("gutter ABOVE the card", 'gutterAbove'),
                       ("gutter BELOW the card", 'gutterBelow'),
                       ("gutter BETWEEN the cards", 'betweenCards'),
                       ("outside to the LEFT", 'outsideLeft')]:
        print()
        print(f"=== 1. TAP {label} (with keyboard open) ===")
        r = d.execute_script(TAP_AT.replace(
            "%BODY%", f"tapAt({pts[key][0]}, {pts[key][1]});"))
        print(json.dumps(r, indent=1))
        check(r['before'] == r['after'],
              f"endpoint stayed {r['after']}", f"SWITCHED {r['before']} -> {r['after']}")
        check(not r['focused'], "keyboard dismissed", "still focused")

    print()
    print("=== 2. TAP INSIDE A CARD -> still switches ===")
    # `other` is whichever card is NOT active at this moment; tap that one.
    tgt = d.execute_script("""
      const active=document.querySelector('.pv-seg-btn.is-active');
      const other=[...document.querySelectorAll('.pv-seg-btn')]
        .find(b=>b!==active);
      const r=other.getBoundingClientRect();
      return {dialect:other.dataset.dialect,
              x:r.left+r.width/2, y:r.top+r.height/2};
    """)
    r = d.execute_script(TAP_AT.replace("%BODY%", f"tapAt({tgt['x']}, {tgt['y']});"))
    print(json.dumps({'target':tgt['dialect'], **r}, indent=1))
    check(r['after'] == tgt['dialect'],
          f"switched to the tapped card ({r['after']})",
          f"expected {tgt['dialect']}, got {r['after']}")

    print()
    print("=== 3. SCROLL WORKS WITH A FIELD FOCUSED ===")
    sc = d.execute_script("""
      const b=document.querySelector('.modal-body');
      const name=document.getElementById('pvName');
      b.scrollTop=0;
      name.focus();
      const focused = document.activeElement===name;
      b.scrollTop=120; const mid=b.scrollTop;
      b.scrollTop=99999; const bot=b.scrollTop, max=b.scrollHeight-b.clientHeight;
      b.scrollTop=0; const top=b.scrollTop;
      name.blur();
      return {focused, mid, bot, max, top};
    """)
    print(json.dumps(sc, indent=1))
    check(sc['focused'], "field was focused", "could not focus the field")
    check(sc['mid'] == 120, "scrolled to 120 while focused", f"got {sc['mid']}")
    check(abs(sc['bot'] - sc['max']) <= 1, f"reached the bottom ({sc['max']})", f"stuck at {sc['bot']}")
    check(sc['top'] == 0, "scrolled back to top", f"got {sc['top']}")

    print()
    print("=== 4. ELASTIC PULL STILL WIRED ===")
    pull = d.execute_script("""
      const form=document.querySelector('.provider-form');
      const b=document.querySelector('.modal-body');
      b.scrollTop=0;
      form.classList.add('sheet-pull-active');
      form.style.transform='translate3d(0,12px,0)';
      const t=getComputedStyle(form).transform;
      form.classList.remove('sheet-pull-active');
      form.classList.add('sheet-pull-releasing');
      const dur=getComputedStyle(form).transitionDuration;
      form.style.transform=''; form.classList.remove('sheet-pull-releasing');
      return {transform:t, dur, wired:form.dataset.pullWired};
    """)
    print(json.dumps(pull, indent=1))
    check('matrix' in pull['transform'] and pull['dur'] != '0s' and pull['wired'] == '1',
          "elastic pull intact", f"pull broken: {pull}")

    errs = [e for e in d.get_log('browser') if e['level']=='SEVERE' and '401' not in e['message']]
    print()
    print("console errors:", len(errs))
    for e in errs[:5]: print("  ", e['message'][:150])
finally:
    d.quit()
print()
print("TOTAL FAILURES:", fails)
