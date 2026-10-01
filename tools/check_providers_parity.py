#!/usr/bin/env python3
"""Verify parity with the Providers page and the new endpoint-picker structure."""
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
def cmp(name, a, b):
    global fails
    same = (a == b)
    if not same: fails += 1
    print(f"   {name:22s} {str(a):24s} {str(b):24s} {'MATCH' if same else 'DIFF'}")

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

    ref = d.execute_script("""
      const g=s=>{const e=document.querySelector(s); if(!e) return null;
        const c=getComputedStyle(e), b=e.getBoundingClientRect();
        return {fs:c.fontSize, fw:c.fontWeight, color:c.color, ls:c.letterSpacing,
                radius:c.borderRadius, pad:c.padding, h:Math.round(b.height)};};
      const page=document.querySelector('#page-providers');
      const pc=getComputedStyle(page);
      return {title:g('.pv-section-head h3'), sub:g('.pv-section-sub'),
              addCard:g('.pv-add-main'), addStrong:g('.pv-add-main strong'),
              addSmall:g('.pv-add-main small'),
              gridImg:pc.backgroundImage, gridSize:pc.backgroundSize,
              gridBg:pc.backgroundColor};
    """)

    d.execute_script("return document.querySelector('.pv-add-main').click()"); time.sleep(3)
    got = d.execute_script("""
      const g=s=>{const e=document.querySelector(s); if(!e) return null;
        const c=getComputedStyle(e), b=e.getBoundingClientRect();
        return {fs:c.fontSize, fw:c.fontWeight, color:c.color, ls:c.letterSpacing,
                radius:c.borderRadius, pad:c.padding, h:Math.round(b.height)};};
      const body=document.querySelector('.modal-body');
      const bs=getComputedStyle(body,'::before');
      return {segHead:g('.pv-seg-head h4'),
              card:g('.pv-seg-btn'), cardStrong:g('.pv-seg-btn strong'),
              cardSmall:g('.pv-seg-btn small'),
              label:g('#pvFields .field label'), desc:g('#pvFields .field .field-desc'),
              gridImg:bs.backgroundImage, gridSize:bs.backgroundSize,
              gridBg:bs.backgroundColor};
    """)

    print("=== 1. GRID IDENTICAL TO PROVIDERS PAGE ===")
    cmp("grid image", ref['gridImg'][:64], got['gridImg'][:64])
    cmp("grid size", ref['gridSize'], got['gridSize'])
    cmp("grid backdrop", ref['gridBg'], got['gridBg'])

    print()
    print("=== 2. TYPE SCALE vs PROVIDERS ===")
    print(f"   {'property':22s} {'PROVIDERS':24s} {'ADD PROVIDER':24s} result")
    cmp("heading size", ref['title']['fs'], got['segHead']['fs'])
    cmp("heading weight", ref['title']['fw'], got['segHead']['fw'])
    cmp("heading colour", ref['title']['color'], got['segHead']['color'])
    cmp("card title size", ref['addStrong']['fs'], got['cardStrong']['fs'])
    cmp("card title weight", ref['addStrong']['fw'], got['cardStrong']['fw'])
    cmp("field label colour", ref['title']['color'], got['label']['color'])
    cmp("caption size", ref['sub']['fs'], got['desc']['fs'])
    cmp("caption weight", ref['sub']['fw'], got['desc']['fw'])
    cmp("caption colour", ref['sub']['color'], got['desc']['color'])

    print()
    print("=== 3. CARD SIZE = PROVIDERS CARD BAND ===")
    cmp("card height", ref['addCard']['h'], got['card']['h'])
    cmp("card radius", ref['addCard']['radius'], got['card']['radius'])
    print(f"   card padding           {ref['addCard']['pad']:24s} {got['card']['pad']:24s} "
          f"{'MATCH' if got['card']['pad'].split()[-1] == ref['addCard']['pad'].split()[-1] else 'note: vertical centring'}")

    print()
    print("=== 4. SELECT ENDPOINT HEADING + CAPTIONS ===")
    st = d.execute_script("""
      const h=document.querySelector('.pv-seg-head h4');
      const bs=[...document.querySelectorAll('.pv-seg-btn')];
      const r=e=>e.getBoundingClientRect();
      return {heading:h?h.textContent.trim():null,
              headingAbove: h && bs[0] ? Math.round(r(bs[0]).top - r(h).bottom) : null,
              cards:bs.map(b=>({t:b.querySelector('strong').textContent.trim(),
                                c:b.querySelector('small').textContent.trim(),
                                h:Math.round(r(b).height),
                                lines:Math.round(r(b.querySelector('small')).height/
                                  parseFloat(getComputedStyle(b.querySelector('small')).lineHeight))}))};
    """)
    print(json.dumps(st, indent=1))
    check(st['heading'] == 'Select Endpoint', "heading is 'Select Endpoint'",
          f"heading: {st['heading']!r}")
    check(st['headingAbove'] is not None and 0 < st['headingAbove'] < 16,
          f"heading sits above the cards ({st['headingAbove']}px)", f"gap: {st['headingAbove']}")
    caps = [c['c'] for c in st['cards']]
    want = ['Use /v1/messages', 'Use /v1/chat/completions or /v1/responses']
    check(caps == want, f"captions exact", f"captions: {caps}")
    check(all(c['h'] == 44 for c in st['cards']),
          "both cards 44px (was 56px)", f"heights: {[c['h'] for c in st['cards']]}")
    check(all(c['lines'] == 1 for c in st['cards']), "captions stay on one line",
          f"line counts: {[c['lines'] for c in st['cards']]}")

    print()
    print("=== 5. BASE URL DESCRIPTION SWAPS PER DIALECT ===")
    def base_desc():
        return d.execute_script("""
          const f=[...document.querySelectorAll('#pvFields > .field')]
            .find(e=>e.querySelector('#pvURL'));
          return f ? f.querySelector('.field-desc').textContent.trim() : null;
        """)
    openai_desc = base_desc()
    print(f"   OpenAI    : {openai_desc!r}")
    check(openai_desc == 'Enter the API endpoint base URL ending in /v1.',
          "OpenAI copy updated", f"got: {openai_desc!r}")
    d.execute_script("""document.querySelector('[data-dialect="anthropic"]').click()""")
    time.sleep(1.2)
    anth_desc = base_desc()
    print(f"   Anthropic : {anth_desc!r}")
    check('append /messages' in (anth_desc or ''),
          "Anthropic copy mentions /messages", f"got: {anth_desc!r}")
    check(openai_desc != anth_desc, "description swaps when the endpoint changes",
          "description identical for both")

    print()
    print("=== 6. LIGHT THEME ===")
    d.execute_script("document.documentElement.setAttribute('data-app-theme','light')")
    time.sleep(0.8)
    lt = d.execute_script("""
      const h=document.querySelector('.pv-seg-head h4');
      const bs=[...document.querySelectorAll('.pv-seg-btn')];
      return {headColor:getComputedStyle(h).color,
              heights:bs.map(b=>Math.round(b.getBoundingClientRect().height))};
    """)
    print(json.dumps(lt, indent=1))
    check(len(set(lt['heights'])) == 1 and lt['heights'][0] == 44,
          "cards stay 44px in light theme", f"heights: {lt['heights']}")

    errs = [e for e in d.get_log('browser') if e['level']=='SEVERE' and '401' not in e['message']]
    print()
    print("console errors:", len(errs))
    for e in errs[:5]: print("  ", e['message'][:150])
    if errs: fails += 1
finally:
    d.quit()
print()
print("TOTAL FAILURES:", fails)
