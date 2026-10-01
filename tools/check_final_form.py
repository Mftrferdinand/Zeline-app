#!/usr/bin/env python3
"""Verify the final form spec:
  - no '*' markers
  - order: Provider Name / [API Type] / Base URL / API Key / Model ID (optional)
  - Prefix removed
  - description sits BETWEEN label and control
  - Check / Create / Cancel are inside the form, under Model ID
  - Create disabled until Check passes, and re-locks on edit
"""
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

SNAP = """
  const vis = e => e && e.offsetParent !== null;
  const flds = [...document.querySelectorAll('#pvFields > .field')].filter(vis).map(e => {
    const kids = [...e.children].map(c => c.tagName.toLowerCase() + (c.className ? '.'+c.className : ''));
    return {
      label: (e.querySelector('label')?.textContent || '').trim(),
      desc: (e.querySelector('.field-desc')?.textContent || '').trim(),
      id: e.querySelector('input,select')?.id || '',
      order: kids
    };
  });
  const btn = s => { const b = document.querySelector(s); if (!b) return null;
    const c = getComputedStyle(b);
    return {label:b.textContent.trim(), disabled:b.disabled,
            locked:b.classList.contains('is-locked'),
            h:Math.round(b.getBoundingClientRect().height),
            top:Math.round(b.getBoundingClientRect().top),
            bg:c.backgroundColor, vis:vis(b)}; };
  const model = document.getElementById('pvModel');
  return {
    fields: flds,
    stars: document.querySelectorAll('.provider-form .field-req').length,
    prefix: !!document.getElementById('pvPrefix'),
    check: btn('[data-act="check"]'),
    create: btn('[data-act="create"]'),
    cancel: btn('[data-act="cancel"]'),
    modelBottom: model ? Math.round(model.getBoundingClientRect().bottom) : null,
    footVisible: vis(document.querySelector('.modal-foot')),
    headActionVisible: vis(document.querySelector('.modal-head-action')),
    note: document.querySelector('.provider-form-note')?.textContent || ''
  };
"""

def boot():
    d.get("http://localhost:5173/"); time.sleep(2)
    d.execute_script("""
      localStorage.setItem('zeline.token','zln_abcdefghijklmnopqrstuvwxyz1234567890');
      localStorage.setItem('zeline.connection', JSON.stringify({configured:true,kind:'gateway',apiBase:'/api/v1'}));
    """)
    d.get("http://localhost:5173/"); time.sleep(4)
    d.execute_script("return document.getElementById('onboarding').hidden=true")
    d.execute_script("return go('providers')"); time.sleep(4)
    d.execute_script("return document.querySelector('.pv-add-main').click()")
    time.sleep(3)

try:
    boot()
    s = d.execute_script(SNAP)

    print("=== 1. FIELD ORDER + NO STARS + NO PREFIX (OpenAI) ===")
    print(json.dumps({'fields': s['fields'], 'stars': s['stars'], 'prefix': s['prefix']}, indent=1))
    labels = [f['label'] for f in s['fields']]
    want = ['Provider Name', 'API Type', 'Base URL', 'API Key', 'Model ID (optional)']
    check(labels == want, f"order correct: {labels}", f"order wrong: {labels}")
    check(s['stars'] == 0, "no '*' markers", f"{s['stars']} stars still present")
    check(not s['prefix'], "Prefix removed", "Prefix still exists")

    print()
    print("=== 2. DESCRIPTION BETWEEN LABEL AND CONTROL ===")
    for f in s['fields']:
        print(f"   {f['label']:24s} order={f['order']}")
    ok = all(f['order'][0].startswith('label')
             and f['order'][1].startswith('small.field-desc')
             and f['order'][2] in ('input', 'select')
             for f in s['fields'])
    check(ok, "every field is label -> desc -> control", "some field has desc after the control")
    nm = next(f for f in s['fields'] if f['id'] == 'pvName')
    check(nm['desc'] == 'A friendly label for this OpenAI-compatible provider.',
          "Provider Name desc matches spec", f"desc: {nm['desc']!r}")
    at = next((f for f in s['fields'] if f['id'] == 'pvApiType'), None)
    check(at and at['desc'] == 'Select an option:', "API Type desc = 'Select an option:'",
          f"api type desc: {at and at['desc']!r}")

    print()
    print("=== 3. BUTTONS INSIDE FORM, UNDER MODEL ID ===")
    print(json.dumps({k: s[k] for k in ('check','create','cancel','modelBottom','footVisible','headActionVisible')}, indent=1))
    check(not s['footVisible'], "no footer navigation bar", "footer bar still visible")
    check(not s['headActionVisible'], "no header action", "header action still visible")
    for k in ('check','create','cancel'):
        b = s[k]
        check(b and b['vis'] and b['top'] > s['modelBottom'],
              f"{b['label']} sits below Model ID (y={b['top']} > {s['modelBottom']})",
              f"{k} misplaced: {b}")
    order = [s['check']['top'], s['create']['top'], s['cancel']['top']]
    check(order == sorted(order), f"stacked Check -> Create -> Cancel {order}", f"wrong order {order}")

    print()
    print("=== 4. CREATE LOCKED UNTIL CHECK PASSES ===")
    check(s['create']['disabled'] and s['create']['locked'],
          "Create starts disabled", f"Create not locked: {s['create']}")

    # invalid endpoint -> stays locked
    d.execute_script("""
      const u=document.getElementById('pvURL'); u.value='https://nope-xyz.invalid/v1';
      u.dispatchEvent(new Event('input'));
      const k=document.getElementById('pvKey'); k.value='sk-x';
      k.dispatchEvent(new Event('input'));
      document.querySelector('[data-act="check"]').click();
    """)
    time.sleep(12)
    bad = d.execute_script(SNAP)
    print(f"   after INVALID check: note={bad['note'][:80]!r}")
    check(bad['create']['disabled'], "Create still locked after invalid check",
          "Create unlocked on an invalid endpoint")

    # valid endpoint -> unlocks
    d.execute_script("""
      const u=document.getElementById('pvURL'); u.value='http://localhost:20128/v1';
      u.dispatchEvent(new Event('input'));
      const k=document.getElementById('pvKey'); k.value='rc_proxy_key';
      k.dispatchEvent(new Event('input'));
      document.querySelector('[data-act="check"]').click();
    """)
    time.sleep(12)
    good = d.execute_script(SNAP)
    print(f"   after VALID check:   note={good['note'][:80]!r}")
    check(not good['create']['disabled'], "Create UNLOCKED after a valid check",
          f"Create still locked: {good['create']}")

    print()
    print("=== 5. EDITING RE-LOCKS CREATE ===")
    d.execute_script("""
      const u=document.getElementById('pvURL'); u.value='http://localhost:20128/v1/changed';
      u.dispatchEvent(new Event('input'));
    """)
    time.sleep(1)
    re_ = d.execute_script(SNAP)
    print(f"   note={re_['note'][:80]!r}")
    check(re_['create']['disabled'], "Create re-locked after editing a field",
          "Create stayed unlocked after an edit")

    print()
    print("=== 6. ANTHROPIC VARIANT ===")
    boot()
    d.execute_script("""document.querySelector('[data-dialect="anthropic"]').click()""")
    time.sleep(1.5)
    a = d.execute_script(SNAP)
    labels = [f['label'] for f in a['fields']]
    want_a = ['Provider Name', 'Base URL', 'API Key', 'Model ID (optional)']
    print(json.dumps({'fields': labels}, indent=1))
    check(labels == want_a, f"Anthropic has no API Type: {labels}", f"wrong: {labels}")
    url = next(f for f in a['fields'] if f['id'] == 'pvURL')
    check('will append /messages' in url['desc'],
          "Anthropic Base URL desc mentions /messages", f"desc: {url['desc']!r}")
    nm = next(f for f in a['fields'] if f['id'] == 'pvName')
    check('Anthropic-compatible' in nm['desc'], "Provider Name desc says Anthropic",
          f"desc: {nm['desc']!r}")

    errs = [e for e in d.get_log('browser') if e['level']=='SEVERE' and '401' not in e['message']]
    print()
    print("console errors:", len(errs))
    for e in errs[:5]: print("  ", e['message'][:160])
finally:
    d.quit()
print()
print("TOTAL FAILURES:", fails)
