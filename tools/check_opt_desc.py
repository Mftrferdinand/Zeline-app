#!/usr/bin/env python3
"""Only the selected option shows its description; the other stays hidden."""
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

SNAP = """
  const vis = e => { const c = getComputedStyle(e);
    return c.visibility !== 'hidden' && parseFloat(c.opacity) > 0.9; };
  const r = e => e.getBoundingClientRect();
  const opts = [...document.querySelectorAll('.pv-opt')].map(o => {
    const desc = o.querySelector('.pv-opt-desc'), card = o.querySelector('.pv-seg-btn');
    return {dialect:o.dataset.opt, isActive:o.classList.contains('is-active'),
            desc:desc.textContent.trim(), descShown:vis(desc),
            descOpacity:getComputedStyle(desc).opacity,
            cardActive:card.classList.contains('is-active'),
            cardTop:Math.round(r(card).top), cardH:Math.round(r(card).height)};
  });
  return {opts,
          shown:[...document.querySelectorAll('.pv-opt-desc')].filter(vis).map(e=>e.textContent.trim()),
          cardTops:[...document.querySelectorAll('.pv-seg-btn')].map(c=>Math.round(r(c).top)),
          title:document.getElementById('modalTitle').textContent.trim()};
"""

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

    print("=== 1. DEFAULT STATE (OpenAI active) ===")
    s1 = d.execute_script(SNAP)
    print(json.dumps(s1, indent=1))
    check(s1['shown'] == ['Use /v1/chat/completions or /v1/responses'],
          "only the OpenAI caption is shown", f"shown: {s1['shown']}")
    check(s1['opts'][0]['descShown'] is False and s1['opts'][1]['descShown'] is True,
          "Anthropic hidden / OpenAI visible",
          f"anthropic={s1['opts'][0]['descShown']} openai={s1['opts'][1]['descShown']}")

    print()
    print("=== 2. CLICK ANTHROPIC -> only its caption ===")
    d.execute_script("""document.querySelector('[data-dialect="anthropic"]').click()""")
    time.sleep(1.2)
    s2 = d.execute_script(SNAP)
    print(json.dumps(s2, indent=1))
    check(s2['shown'] == ['Use /v1/messages'],
          "only the Anthropic caption is shown", f"shown: {s2['shown']}")
    check(s2['title'] == 'Custom Endpoint', "title unchanged", f"title: {s2['title']!r}")

    print()
    print("=== 3. CLICK OPENAI AGAIN -> swaps back ===")
    d.execute_script("""document.querySelector('[data-dialect="openai"]').click()""")
    time.sleep(1.2)
    s3 = d.execute_script(SNAP)
    print(json.dumps({k:s3[k] for k in ('shown','cardTops')}, indent=1))
    check(s3['shown'] == ['Use /v1/chat/completions or /v1/responses'],
          "only the OpenAI caption is shown again", f"shown: {s3['shown']}")

    print()
    print("=== 4. NO LAYOUT SHIFT WHEN SWITCHING ===")
    tops = [s1['cardTops'], s2['cardTops'], s3['cardTops']]
    print(f"   card tops across the three states: {tops}")
    check(tops[0] == tops[1] == tops[2],
          "cards never move — space is reserved", f"cards shifted: {tops}")

    errs = [e for e in d.get_log('browser') if e['level']=='SEVERE' and '401' not in e['message']]
    print()
    print("console errors:", len(errs))
    for e in errs[:5]: print("  ", e['message'][:150])
finally:
    d.quit()
print()
print("TOTAL FAILURES:", fails)
