#!/usr/bin/env python3
"""Verify: tapping empty space only dismisses the keyboard (never switches
endpoint), and the action row is Check | Create on one line with no Cancel."""
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

# Dispatch a realistic tap: pointerdown + pointerup + click, at a chosen node.
TAP = """
  const tap = (node) => {
    const opts = {bubbles:true, cancelable:true, pointerType:'touch', isPrimary:true};
    node.dispatchEvent(new PointerEvent('pointerdown', opts));
    node.dispatchEvent(new PointerEvent('pointerup', opts));
    node.dispatchEvent(new MouseEvent('click', {bubbles:true, cancelable:true}));
  };
  const name = document.getElementById('pvName');
  name.focus();
  const wasFocused = document.activeElement === name;
  const before = document.querySelector('.pv-seg-btn.is-active').dataset.dialect;
  %TARGET%
  return {wasFocused, before,
          after: document.querySelector('.pv-seg-btn.is-active').dataset.dialect,
          stillFocused: document.activeElement === name,
          desc: document.getElementById('pvSegDesc').textContent.trim()};
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

    print("=== 1. TAP ON EMPTY SPACE ABOVE THE CARDS ===")
    r1 = d.execute_script(TAP.replace("%TARGET%", "tap(document.querySelector('.pv-seg-head'))"))
    print(json.dumps(r1, indent=1))
    check(r1['before'] == r1['after'],
          f"endpoint stayed {r1['after']} (empty space did not switch it)",
          f"endpoint switched {r1['before']} -> {r1['after']}")
    check(not r1['stillFocused'], "keyboard dismissed (field blurred)",
          "field still focused")

    print()
    print("=== 2. TAP ON EMPTY SPACE BELOW THE CARDS ===")
    r2 = d.execute_script(TAP.replace("%TARGET%", "tap(document.querySelector('.pv-seg-group'))"))
    print(json.dumps(r2, indent=1))
    check(r2['before'] == r2['after'],
          f"endpoint stayed {r2['after']}", f"switched to {r2['after']}")
    check(not r2['stillFocused'], "keyboard dismissed", "still focused")

    print()
    print("=== 3. TAP ON THE FORM BACKGROUND ===")
    r3 = d.execute_script(TAP.replace("%TARGET%", "tap(document.querySelector('.provider-form'))"))
    print(json.dumps(r3, indent=1))
    check(r3['before'] == r3['after'], "endpoint unchanged", f"switched to {r3['after']}")
    check(not r3['stillFocused'], "keyboard dismissed", "still focused")

    print()
    print("=== 4. TAP DIRECTLY ON THE OTHER CARD -> should switch ===")
    r4 = d.execute_script(TAP.replace("%TARGET%",
        "tap(document.querySelector('[data-dialect=\"anthropic\"]'))"))
    print(json.dumps(r4, indent=1))
    check(r4['after'] == 'anthropic', "tapping the card itself switches endpoint",
          f"endpoint {r4['after']}")
    check(r4['desc'] == 'Use /v1/messages', "description follows", f"desc {r4['desc']!r}")

    print()
    print("=== 5. ACTION ROW: CHECK | CREATE, NO CANCEL ===")
    a = d.execute_script("""
      const acts=document.querySelector('.pv-actions');
      const btns=[...acts.querySelectorAll('.pv-act')];
      const r=e=>e.getBoundingClientRect();
      const c=getComputedStyle(acts);
      return {count:btns.length,
              labels:btns.map(b=>b.textContent.trim()),
              hasCancel: !!document.querySelector('[data-act="cancel"]'),
              display:c.display, cols:c.gridTemplateColumns,
              tops:btns.map(b=>Math.round(r(b).top)),
              widths:btns.map(b=>Math.round(r(b).width)),
              heights:btns.map(b=>Math.round(r(b).height)),
              createDisabled: btns.find(b=>b.textContent.trim()==='Create')?.disabled};
    """)
    print(json.dumps(a, indent=1))
    check(a['count'] == 2 and a['labels'] == ['Check', 'Create'],
          f"two buttons: {a['labels']}", f"labels: {a['labels']}")
    check(not a['hasCancel'], "Cancel is gone", "Cancel still present")
    check(len(set(a['tops'])) == 1, f"same row (y={a['tops'][0]})", f"tops: {a['tops']}")
    check(len(set(a['widths'])) == 1, f"equal widths ({a['widths'][0]}px)", f"widths: {a['widths']}")
    check(a['createDisabled'], "Create still locked until Check passes",
          "Create is enabled without a check")

    errs = [e for e in d.get_log('browser') if e['level']=='SEVERE' and '401' not in e['message']]
    print()
    print("console errors:", len(errs))
    for e in errs[:5]: print("  ", e['message'][:150])
finally:
    d.quit()
print()
print("TOTAL FAILURES:", fails)
