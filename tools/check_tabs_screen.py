#!/usr/bin/env python3
"""Verify: Add Provider opens a NEW screen whose two dialects are tabs, and
switching tabs swaps only the form (values carried, modal never reopens)."""
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

STATE = """
  const vis = e => e && e.offsetParent !== null;
  const seg = [...document.querySelectorAll('.pv-seg-btn')];
  return {
    modalOpen: !!document.querySelector('#pvFields') && vis(document.querySelector('#pvFields')),
    title: document.getElementById('modalTitle')?.textContent,
    subtitle: document.querySelector('.modal-head-subtitle')?.textContent || '',
    tabs: seg.map(b => ({t: b.querySelector('strong')?.textContent,
                         active: b.classList.contains('is-active'),
                         dialect: b.dataset.dialect})),
    fields: [...document.querySelectorAll('#pvFields > .field')]
      .filter(vis).map(e => (e.querySelector('label')?.textContent || '').replace(' *','').trim()),
    values: {
      name: document.getElementById('pvName')?.value ?? null,
      prefix: document.getElementById('pvPrefix')?.value ?? null,
      key: document.getElementById('pvKey')?.value ?? null,
      model: document.getElementById('pvModel')?.value ?? null,
      url: document.getElementById('pvURL')?.value ?? null
    },
    protocol: document.getElementById('pvProtocol')?.value,
    apiTypeExists: !!document.getElementById('pvApiType'),
    inlineChoices: !!document.querySelector('[data-add-choices]'),
    note: document.querySelector('.provider-form-note')?.textContent || ''
  };
"""

fails = 0
try:
    d.get("http://localhost:5173/"); time.sleep(2)
    d.execute_script("""
      localStorage.setItem('zeline.token','zln_abcdefghijklmnopqrstuvwxyz1234567890');
      localStorage.setItem('zeline.connection', JSON.stringify({configured:true,kind:'gateway',apiBase:'/api/v1'}));
    """)
    d.get("http://localhost:5173/"); time.sleep(4)
    d.execute_script("return document.getElementById('onboarding').hidden=true")
    d.execute_script("return go('providers')"); time.sleep(4)

    print("=== 1. SECTION: only ONE card, no inline expansion ===")
    pre = d.execute_script("""
      const vis=e=>e&&e.offsetParent!==null;
      return {addCards:[...document.querySelectorAll('#providerGrid .pv-add-card')].filter(vis).length,
              inlineStack:!!document.querySelector('[data-add-choices]'),
              label:document.querySelector('.pv-add-main strong')?.textContent};
    """)
    print(json.dumps(pre, indent=1))
    if pre['addCards'] != 1: fails += 1; print("  FAIL: expected exactly 1 add card")
    if pre['inlineStack']: fails += 1; print("  FAIL: inline choice stack still in DOM")
    if pre['addCards'] == 1 and not pre['inlineStack']: print("  PASS")

    print()
    print("=== 2. TAP -> opens NEW SCREEN with tabs ===")
    d.execute_script("return document.querySelector('.pv-add-main').click()")
    time.sleep(3)
    s1 = d.execute_script(STATE)
    print(json.dumps({k: s1[k] for k in ('modalOpen','title','tabs','fields','protocol','apiTypeExists')}, indent=1))
    if not s1['modalOpen']: fails += 1; print("  FAIL: no new screen opened")
    if len(s1['tabs']) != 2: fails += 1; print("  FAIL: expected 2 tabs")
    if s1['protocol'] != 'openai': fails += 1; print(f"  FAIL: default dialect {s1['protocol']}")
    exp_openai = ['Name','Prefix','API Type','Base URL','API Key (for Check)','Model ID']
    if s1['fields'] != exp_openai: fails += 1; print(f"  FAIL: fields {s1['fields']}")
    else: print("  PASS: new screen, 2 tabs, OpenAI form by default")

    print()
    print("=== 3. TYPE VALUES, then SWITCH TAB -> only form swaps ===")
    d.execute_script("""
      document.getElementById('pvName').value='My Node';
      document.getElementById('pvPrefix').value='xx-test';
      document.getElementById('pvKey').value='sk-secret-123';
      document.getElementById('pvModel').value='gpt-4o-mini';
      document.getElementById('pvURL').value='https://api.openai.com/v1';
    """)
    d.execute_script("""document.querySelector('[data-dialect="anthropic"]').click()""")
    time.sleep(1.5)
    s2 = d.execute_script(STATE)
    print(json.dumps({k: s2[k] for k in ('modalOpen','title','fields','values','protocol','apiTypeExists')}, indent=1))
    bad = []
    if not s2['modalOpen']: bad.append("screen closed on tab switch")
    exp_anth = ['Name','Prefix','Base URL','API Key (for Check)','Model ID']
    if s2['fields'] != exp_anth: bad.append(f"fields={s2['fields']}")
    if s2['apiTypeExists']: bad.append("API Type must NOT exist on Anthropic")
    if s2['protocol'] != 'anthropic': bad.append(f"protocol={s2['protocol']}")
    if s2['values']['name'] != 'My Node': bad.append(f"name lost: {s2['values']['name']}")
    if not s2['values']['key']: bad.append('key lost (empty)')
    if s2['values']['model'] != 'gpt-4o-mini': bad.append(f"model lost: {s2['values']['model']}")
    if s2['values']['url']: bad.append(f"URL should reset per dialect, got {s2['values']['url']}")
    active = [t['dialect'] for t in s2['tabs'] if t['active']]
    if active != ['anthropic']: bad.append(f"active tab={active}")
    if 'Anthropic' not in (s2['title'] or ''): bad.append(f"title={s2['title']}")
    if bad: fails += 1; print("  FAIL:", "; ".join(bad))
    else: print("  PASS: same screen, form swapped, typed values carried, URL reset")

    print()
    print("=== 4. SWITCH BACK -> OpenAI form returns ===")
    d.execute_script("""document.querySelector('[data-dialect="openai"]').click()""")
    time.sleep(1.5)
    s3 = d.execute_script(STATE)
    print(json.dumps({k: s3[k] for k in ('title','fields','values','protocol','apiTypeExists')}, indent=1))
    bad = []
    if s3['fields'] != exp_openai: bad.append(f"fields={s3['fields']}")
    if not s3['apiTypeExists']: bad.append("API Type missing")
    if s3['values']['name'] != 'My Node': bad.append("name lost on return")
    if 'OpenAI' not in (s3['title'] or ''): bad.append(f"title={s3['title']}")
    if bad: fails += 1; print("  FAIL:", "; ".join(bad))
    else: print("  PASS: switched back cleanly")

    errs = [e for e in d.get_log('browser') if e['level']=='SEVERE' and '401' not in e['message']]
    print()
    print("console errors:", len(errs))
    for e in errs[:6]: print("  ", e['message'][:170])
    if errs: fails += 1
finally:
    d.quit()
print()
print("TOTAL FAILURES:", fails)
