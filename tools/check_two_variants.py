#!/usr/bin/env python3
"""Verify the two Add cards produce the two documented forms."""
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

FORM = """
  const vis = e => e && e.offsetParent !== null;
  return {
    title: document.getElementById('modalTitle')?.textContent,
    subtitle: document.querySelector('.modal-head-subtitle')?.textContent || '',
    fields: [...document.querySelectorAll('.provider-form > .field')]
      .filter(vis)
      .map(e => ({
        label: (e.querySelector('label')?.textContent || '').trim(),
        id: e.querySelector('input,select')?.id || '',
        value: e.querySelector('input,select')?.value || '',
        ph: e.querySelector('input')?.placeholder || '',
        hint: (e.querySelector('small')?.textContent || '').slice(0, 70)
      })),
    apiTypeVisible: vis(document.getElementById('pvApiTypeWrap')),
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

fails = 0
try:
    boot()
    cards = d.execute_script("""
      return [...document.querySelectorAll('#providerGrid .pv-add-card')]
        .map(b => ({label: b.querySelector('strong')?.textContent.trim(),
                    sub: b.querySelector('small')?.textContent.trim(),
                    proto: b.dataset.addProtocol}));
    """)
    print("=== CARD DI SECTION CUSTOM ===")
    for c in cards: print("  ", c)
    if len(cards) != 2: fails += 1; print("   FAIL: harusnya 2 card")
    else: print("   PASS: 2 card terpisah")

    # --- Anthropic
    d.execute_script("""[...document.querySelectorAll('#providerGrid .pv-add-card')]
      .find(b=>b.dataset.addProtocol==='anthropic').click()""")
    time.sleep(3)
    a = d.execute_script(FORM)
    print()
    print("=== Form ANTHROPIC ===")
    print(json.dumps(a, indent=1))
    labels = [f['label'].replace(' *','') for f in a['fields']]
    expect = ['Name','Prefix','Base URL','API Key (for Check)','Model ID']
    bad = []
    if labels != expect: bad.append(f"field={labels}")
    if a['apiTypeVisible']: bad.append("API Type harusnya TIDAK ada di Anthropic")
    if 'Anthropic' not in (a['title'] or ''): bad.append(f"judul={a['title']}")
    pfx = next((f for f in a['fields'] if f['id']=='pvPrefix'), {})
    if pfx.get('value') != 'ac-prod': bad.append(f"prefix={pfx.get('value')}")
    if bad: fails += 1; print("   FAIL:", "; ".join(bad))
    else: print("   PASS: field & prefix sesuai")

    # --- OpenAI
    boot()
    d.execute_script("""[...document.querySelectorAll('#providerGrid .pv-add-card')]
      .find(b=>b.dataset.addProtocol==='openai').click()""")
    time.sleep(3)
    b2 = d.execute_script(FORM)
    print()
    print("=== Form OPENAI ===")
    print(json.dumps(b2, indent=1))
    labels = [f['label'].replace(' *','') for f in b2['fields']]
    expect = ['Name','Prefix','API Type','Base URL','API Key (for Check)','Model ID']
    bad = []
    if labels != expect: bad.append(f"field={labels}")
    if not b2['apiTypeVisible']: bad.append("API Type harusnya ADA di OpenAI")
    if 'OpenAI' not in (b2['title'] or ''): bad.append(f"judul={b2['title']}")
    pfx = next((f for f in b2['fields'] if f['id']=='pvPrefix'), {})
    if pfx.get('value') != 'oc-prod': bad.append(f"prefix={pfx.get('value')}")
    at = d.execute_script("return [...document.querySelectorAll('#pvApiType option')].map(o=>o.text)")
    if at != ['Chat Completions','Responses']: bad.append(f"apiType={at}")
    if bad: fails += 1; print("   FAIL:", "; ".join(bad))
    else: print("   PASS: field, prefix, API Type sesuai")

    errs = [e for e in d.get_log('browser') if e['level']=='SEVERE' and '401' not in e['message']]
    print()
    print("console errors:", len(errs))
    for e in errs[:5]: print("  ", e['message'][:160])
finally:
    d.quit()
print()
print("TOTAL FAILURES:", fails)
