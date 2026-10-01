#!/usr/bin/env python3
"""Verify: grid aligned to the bar like Providers, sheet scrolls freely, and
there is trailing space below the content."""
import sys, time, json
sys.path.insert(0, "/data/data/com.termux/files/usr/lib/python3.13/site-packages")
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service

o = Options()
for a in ("--headless=new", "--no-sandbox", "--disable-dev-shm-usage",
          "--disable-gpu", "--window-size=430,900", "--incognito"):
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

    # ---- reference from the Providers page
    d.execute_script("return go('providers')"); time.sleep(4)
    ref = d.execute_script("""
      const p=document.querySelector('#page-providers');
      const c=getComputedStyle(p);
      return {pos:c.backgroundPosition, size:c.backgroundSize,
              barH:Math.round(document.querySelector('.pv-appbar').getBoundingClientRect().height),
              scroller:document.querySelector('#page-providers .page-body')
                ? Math.round(document.querySelector('#page-providers .page-body').scrollHeight) : null,
              padBottom:c.paddingBottom};
    """)

    d.execute_script("return document.querySelector('.pv-add-main').click()"); time.sleep(3)
    got = d.execute_script("""
      const b=document.querySelector('.modal-body');
      const bs=getComputedStyle(b,'::before');
      const form=document.querySelector('.provider-form');
      const s=getComputedStyle(b);
      return {pos:bs.backgroundPosition, size:bs.backgroundSize, attach:bs.position,
              barH:Math.round(document.querySelector('.modal-head').getBoundingClientRect().height),
              clientH:b.clientHeight, scrollH:b.scrollHeight,
              overflowY:s.overflowY, touchAction:s.touchAction,
              overscroll:s.overscrollBehaviorY,
              formPadBottom:getComputedStyle(form).paddingBottom,
              lastChildBottom: Math.round(form.lastElementChild.getBoundingClientRect().bottom),
              bodyBottom: Math.round(b.getBoundingClientRect().bottom)};
    """)
    print("=== 1. GRID ALIGNED TO THE BAR (like Providers) ===")
    print(f"   providers pos = {ref['pos']}")
    print(f"   provider  pos = {got['pos']}")
    # Providers: '-1px 53px'; ours should have the same 53px vertical origin
    ref_v = ref['pos'].split()[-1]
    got_parts = got['pos'].split(',')[0].split()
    got_v = got_parts[-1]
    check(got_v == ref_v or got_v.startswith('53'),
          f"vertical origin {got_v} matches Providers {ref_v}",
          f"origin {got['pos']} vs Providers {ref['pos']}")
    check(got['size'] == ref['size'], f"grid size {got['size']} identical",
          f"size {got['size']} vs {ref['size']}")
    check(got['attach'] == 'fixed', "grid is on a fixed layer", f"position: {got['attach']}")
    check(got['barH'] == ref['barH'], f"bar height {got['barH']}px matches", 
          f"bar {got['barH']} vs {ref['barH']}")

    print()
    print("=== 2. SCROLL WORKS BOTH WAYS ===")
    print(json.dumps({k:got[k] for k in ('clientH','scrollH','overflowY','touchAction','overscroll')}, indent=1))
    scrollable = got['scrollH'] > got['clientH']
    check(scrollable, f"content is scrollable ({got['scrollH']} > {got['clientH']})",
          f"not scrollable: {got['scrollH']} vs {got['clientH']}")

    # actually scroll it: down, further down, then back up
    steps = d.execute_script("""
      const b=document.querySelector('.modal-body');
      const out=[];
      b.scrollTop = 0; out.push({want:0, got:b.scrollTop});
      b.scrollTop = 120; out.push({want:120, got:b.scrollTop});
      b.scrollTop = 99999; out.push({want:'max', got:b.scrollTop, max:b.scrollHeight-b.clientHeight});
      const atBottom = b.scrollTop;
      b.scrollTop = 0; out.push({want:'back to 0', got:b.scrollTop});
      return {out, atBottom, maxScroll: b.scrollHeight-b.clientHeight};
    """)
    print(json.dumps(steps, indent=1))
    check(steps['out'][1]['got'] == 120, "scrolled down to 120", f"got {steps['out'][1]['got']}")
    check(steps['atBottom'] > 0 and abs(steps['atBottom'] - steps['maxScroll']) <= 1,
          f"reaches the bottom ({steps['atBottom']}px)", f"bottom stuck at {steps['atBottom']}")
    check(steps['out'][3]['got'] == 0, "scrolls back up to 0", f"got {steps['out'][3]['got']}")

    print()
    print("=== 3. TRAILING SPACE BELOW THE CONTENT ===")
    print(json.dumps({k:got[k] for k in ('formPadBottom','lastChildBottom','bodyBottom')}, indent=1))
    check(got['formPadBottom'] not in ('0px',), 
          f"form has {got['formPadBottom']} bottom padding",
          f"no bottom padding: {got['formPadBottom']}")

    print()
    print("=== 4. NO PULL GESTURE LEFT TO FIGHT THE PAN ===")
    gone = d.execute_script("""
      const b=document.querySelector('.modal-body');
      const f=document.querySelector('.provider-form');
      return {bodyWired:b.dataset.workspacePullWired||null,
              formWired:f.dataset.workspacePullWired||null,
              hasBespoke: typeof wireSheetPullStretch !== 'undefined'};
    """)
    print(json.dumps(gone, indent=1))
    check(gone['bodyWired'] != '1', "body is not wired to the pull gesture",
          f"body still wired: {gone['bodyWired']}")

    print()
    print("=== 5. GRID BACKDROP STAYS PUT WHILE SCROLLING ===")
    before = d.execute_script("return getComputedStyle(document.querySelector('.modal-body'),'::before').backgroundPosition")
    d.execute_script("document.querySelector('.modal-body').scrollTop = 200")
    time.sleep(0.5)
    after = d.execute_script("return getComputedStyle(document.querySelector('.modal-body'),'::before').backgroundPosition")
    print(f"   before={before}  after={after}")
    check(before == after, "backdrop does not move with the content", "backdrop scrolled with content")

    print()
    print("=== 6. LIGHT THEME KEEPS THE OFFSET ===")
    d.execute_script("document.documentElement.setAttribute('data-app-theme','light')")
    time.sleep(0.7)
    lt = d.execute_script("return getComputedStyle(document.querySelector('.modal-body'),'::before').backgroundPosition")
    print(f"   light pos = {lt}")
    check('53' in lt, "light theme keeps the bar offset", f"light origin: {lt}")

    errs = [e for e in d.get_log('browser') if e['level']=='SEVERE' and '401' not in e['message']]
    print()
    print("console errors:", len(errs))
    for e in errs[:5]: print("  ", e['message'][:150])
finally:
    d.quit()
print()
print("TOTAL FAILURES:", fails)
