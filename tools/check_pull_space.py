#!/usr/bin/env python3
"""Verify: description->card gap matches fields, real trailing space past the
last button, and the elastic top pull works."""
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

    print("=== 1. SELECT ENDPOINT DESC -> CARD GAP == FIELDS ===")
    g = d.execute_script("""
      const r=e=>e.getBoundingClientRect();
      const sd=document.getElementById('pvSegDesc');
      const card=document.querySelector('.pv-seg-btn');
      const f=document.querySelector('#pvFields > .field');
      const fd=f.querySelector('.field-desc'), fi=f.querySelector('input,select');
      return {seg:Math.round(r(card).top-r(sd).bottom),
              field:Math.round(r(fi).top-r(fd).bottom)};
    """)
    print(json.dumps(g, indent=1))
    check(g['seg'] == g['field'], f"gap {g['seg']}px matches fields ({g['field']}px)",
          f"gap {g['seg']} vs fields {g['field']}")

    print()
    print("=== 2. TRAILING SPACE PAST THE CANCEL BUTTON ===")
    t = d.execute_script("""
      const b=document.querySelector('.modal-body');
      const cancel=document.querySelector('[data-act="cancel"]');
      const form=document.querySelector('.provider-form');
      b.scrollTop = 99999;
      const reached = b.scrollTop;
      const max = b.scrollHeight - b.clientHeight;
      const cr = cancel.getBoundingClientRect();
      const br = b.getBoundingClientRect();
      return {maxScroll:max, reached,
              cancelBottomAfterScroll:Math.round(cr.bottom),
              bodyBottom:Math.round(br.bottom),
              spaceBelowCancel:Math.round(br.bottom - cr.bottom),
              formAfterHeight:getComputedStyle(form,'::after').height};
    """)
    print(json.dumps(t, indent=1))
    check(t['spaceBelowCancel'] > 20,
          f"{t['spaceBelowCancel']}px of space below Cancel when scrolled to the end",
          f"only {t['spaceBelowCancel']}px — Cancel is flush/stuck")
    check(t['reached'] == t['maxScroll'], "reaches the very end", f"{t['reached']} vs {t['maxScroll']}")

    print()
    print("=== 3. ELASTIC TOP PULL ===")
    p = d.execute_script("""
      const form=document.querySelector('.provider-form');
      const b=document.querySelector('.modal-body');
      b.scrollTop = 0;
      form.classList.add('sheet-pull-active');
      form.style.transform='translate3d(0,12px,0)';
      const pulled=getComputedStyle(form).transform;
      form.classList.remove('sheet-pull-active');
      form.classList.add('sheet-pull-releasing');
      const dur=getComputedStyle(form).transitionDuration;
      const ease=getComputedStyle(form).transitionTimingFunction;
      form.style.transform=''; form.classList.remove('sheet-pull-releasing');
      return {pulled, dur, ease, wired: form.dataset.pullWired};
    """)
    print(json.dumps(p, indent=1))
    check('matrix' in p['pulled'], "form translates when pulled",
          f"no transform: {p['pulled']}")
    check(p['dur'] not in ('0s',), f"springs back over {p['dur']}", f"no transition: {p['dur']}")
    check(p['wired'] == '1', "gesture is wired", "gesture not wired")

    print()
    print("=== 4. SCROLL STILL WORKS ===")
    sc = d.execute_script("""
      const b=document.querySelector('.modal-body');
      b.scrollTop=0; const a=b.scrollTop;
      b.scrollTop=120; const c=b.scrollTop;
      b.scrollTop=0;
      return {at0:a, at120:c, max:b.scrollHeight-b.clientHeight};
    """)
    print(json.dumps(sc, indent=1))
    check(sc['at120'] == 120, "scrolls to 120", f"got {sc['at120']}")

    errs = [e for e in d.get_log('browser') if e['level']=='SEVERE' and '401' not in e['message']]
    print()
    print("console errors:", len(errs))
    for e in errs[:5]: print("  ", e['message'][:150])
finally:
    d.quit()
print()
print("TOTAL FAILURES:", fails)
