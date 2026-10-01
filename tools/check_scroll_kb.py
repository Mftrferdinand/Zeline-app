#!/usr/bin/env python3
"""Verify the scroll unlock and the keyboard-dismiss behaviour."""
import sys, time, json
sys.path.insert(0, "/data/data/com.termux/files/usr/lib/python3.13/site-packages")
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service

o = Options()
for a in ("--headless=new", "--no-sandbox", "--disable-dev-shm-usage",
          "--disable-gpu", "--window-size=430,560", "--incognito"):
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

    print("=== 1. SCROLL CONTAINER UNLOCKED ===")
    cs = d.execute_script("""
      const b=document.querySelector('.modal-body');
      const c=getComputedStyle(b);
      return {overflowY:c.overflowY, overscroll:c.overscrollBehaviorY,
              touchAction:c.touchAction, webkitScroll:c.webkitOverflowScrolling,
              scrollH:b.scrollHeight, clientH:b.clientHeight,
              max:b.scrollHeight-b.clientHeight};
    """)
    print(json.dumps(cs, indent=1))
    check(cs['overflowY'] == 'auto', "body overflow-y is auto", f"overflow-y: {cs['overflowY']}")
    check(cs['overscroll'] != 'none', "overscroll is not 'none' (elastic feel restored)",
          f"overscroll: {cs['overscroll']}")
    check(cs['touchAction'] == 'pan-y', "touch-action allows vertical pan", f"touch-action: {cs['touchAction']}")
    # Chromium DESKTOP reports null for -webkit-overflow-scrolling (it is an
    # iOS/Android-only property). Declared in CSS; assert the source instead.
    import pathlib as _pl
    _css = (_pl.Path(__file__).parent.parent / "style.css").read_text()
    check('-webkit-overflow-scrolling:touch' in _css.replace(' ', ''),
          "momentum scrolling declared in CSS (desktop reports null)",
          "no -webkit-overflow-scrolling declaration")

    print()
    print("=== 2. ACTUALLY SCROLLS, INCLUDING FROM A CARD ===")
    steps = d.execute_script("""
      const b=document.querySelector('.modal-body');
      const out=[];
      b.scrollTop=0; out.push(['start',b.scrollTop]);
      b.scrollTop=100; out.push(['down100',b.scrollTop]);
      b.scrollTop=99999; out.push(['bottom',b.scrollTop, b.scrollHeight-b.clientHeight]);
      b.scrollTop=0; out.push(['top',b.scrollTop]);
      return out;
    """)
    print(json.dumps(steps, indent=1))
    check(steps[1][1] == 100, "scrolls down to 100", f"got {steps[1][1]}")
    check(abs(steps[2][1] - steps[2][2]) <= 1, f"reaches the bottom ({steps[2][2]})",
          f"bottom stuck at {steps[2][1]}")
    check(steps[3][1] == 0, "scrolls back to top", f"got {steps[3][1]}")

    # a pointerdown starting on a card must not be able to block the pan
    blocked = d.execute_script("""
      const card=document.querySelector('.pv-seg-btn');
      const b=document.querySelector('.modal-body');
      const c=getComputedStyle(card);
      const parents=[];
      let e=card;
      while(e && e!==b.parentElement){
        const s=getComputedStyle(e);
        if(s.touchAction==='none'||s.pointerEvents==='none') parents.push(e.className);
        e=e.parentElement;
      }
      return {cardTouchAction:c.touchAction, cardPointerEvents:c.pointerEvents,
              blockers:parents};
    """)
    print(json.dumps(blocked, indent=1))
    check(blocked['cardPointerEvents'] != 'none', "cards accept pointer events",
          "cards have pointer-events:none")
    check(not blocked['blockers'], "nothing between the card and scroller blocks the gesture",
          f"blockers: {blocked['blockers']}")

    print()
    print("=== 3. KEYBOARD DISMISS ON OUTSIDE TAP ===")
    kb = d.execute_script("""
      const name=document.getElementById('pvName');
      name.focus();
      const focusedBefore = document.activeElement === name;
      const card=document.querySelector('[data-dialect="anthropic"]');
      const activeBefore = document.querySelector('.pv-seg-btn.is-active').dataset.dialect;
      // an outside tap, as a touch would deliver it
      card.dispatchEvent(new PointerEvent('pointerdown',{bubbles:true,cancelable:true,pointerType:'touch'}));
      const focusedAfter = document.activeElement === name;
      card.dispatchEvent(new PointerEvent('pointerup',{bubbles:true,cancelable:true,pointerType:'touch'}));
      card.dispatchEvent(new MouseEvent('click',{bubbles:true,cancelable:true}));
      const activeAfter = document.querySelector('.pv-seg-btn.is-active').dataset.dialect;
      return {focusedBefore, focusedAfter, activeBefore, activeAfter};
    """)
    print(json.dumps(kb, indent=1))
    check(kb['focusedBefore'], "field was focused first", "field did not take focus")
    check(not kb['focusedAfter'], "outside tap blurs the field (keyboard closes)",
          "field still focused — keyboard would stay open")
    check(kb['activeAfter'] == kb['activeBefore'],
          f"endpoint unchanged ({kb['activeBefore']}) — tap only dismissed",
          f"endpoint switched {kb['activeBefore']} -> {kb['activeAfter']}")

    print()
    print("=== 4. A SECOND TAP DOES SELECT ===")
    second = d.execute_script("""
      const card=document.querySelector('[data-dialect="anthropic"]');
      const before=document.querySelector('.pv-seg-btn.is-active').dataset.dialect;
      card.dispatchEvent(new PointerEvent('pointerdown',{bubbles:true,cancelable:true,pointerType:'touch'}));
      card.dispatchEvent(new PointerEvent('pointerup',{bubbles:true,cancelable:true,pointerType:'touch'}));
      card.click();
      return {before, after:document.querySelector('.pv-seg-btn.is-active').dataset.dialect,
              desc:document.getElementById('pvSegDesc').textContent.trim()};
    """)
    print(json.dumps(second, indent=1))
    check(second['after'] == 'anthropic', "second tap switches endpoint",
          f"endpoint {second['after']}")
    check(second['desc'] == 'Use /v1/messages', "description follows",
          f"desc: {second['desc']!r}")

    errs = [e for e in d.get_log('browser') if e['level'] == 'SEVERE' and '401' not in e['message']]
    print()
    print("console errors:", len(errs))
    for e in errs[:5]: print("  ", e['message'][:150])
finally:
    d.quit()
print()
print("TOTAL FAILURES:", fails)
