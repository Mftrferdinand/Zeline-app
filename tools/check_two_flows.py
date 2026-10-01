#!/usr/bin/env python3
"""Verify the two entry points into providerForm() differ correctly:

  A) Generic "Add Provider" card  -> CUSTOM flow
       no provider dropdown, title "Tambah Custom Endpoint",
       both Base URL fields empty, API Type follows the filled URL.

  B) A provider card's "+"        -> PRESET flow
       provider dropdown present (locked), endpoint prefilled from the preset.
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

FIELDS = """
  const vis = e => e && e.offsetParent !== null;
  return {
    title: document.getElementById('modalTitle')?.textContent,
    subtitle: document.querySelector('.modal-head-subtitle')?.textContent || '',
    presetPicker: vis(document.getElementById('pvPreset')),
    presetValue: document.getElementById('pvPreset')?.value || null,
    urlOpenAI: document.getElementById('pvURL')?.value || '',
    urlAnthropic: document.getElementById('pvURLAnthropic')?.value || '',
    apiTypes: [...document.querySelectorAll('#pvApiType option')].map(x => x.value),
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
    # ---- A) custom flow
    boot()
    d.execute_script("return document.querySelector('#providerGrid .pv-add-card').click()")
    time.sleep(3)
    a = d.execute_script(FIELDS)
    print("=== A) Tombol 'Add Provider' (custom) ===")
    print(json.dumps(a, indent=1))
    bad = []
    if a['presetPicker']: bad.append("dropdown masih ada")
    if 'Custom' not in (a['title'] or ''): bad.append(f"judul: {a['title']}")
    if a['urlOpenAI'] or a['urlAnthropic']: bad.append("Base URL harusnya kosong")
    if a['apiTypes'] != ['chat', 'responses']: bad.append(f"apiTypes: {a['apiTypes']}")
    if bad: fails += 1; print("   FAIL:", "; ".join(bad))
    else: print("   PASS: tanpa dropdown, judul Custom, field kosong")

    # API Type ikut dialek
    d.execute_script("""
      const a=document.getElementById('pvURLAnthropic');
      a.value='https://api.anthropic.com'; a.dispatchEvent(new Event('input'));
    """)
    time.sleep(0.6)
    at = d.execute_script("return [...document.querySelectorAll('#pvApiType option')].map(x=>x.value)")
    print(f"   Anthropic diisi -> apiTypes: {at}")
    if at != ['messages', '']: fails += 1; print("   FAIL: apiTypes anthropic salah")
    else: print("   PASS: pindah ke messages + (kosong)")

    # ---- B) preset flow
    boot()
    d.execute_script("""
      // open the form the way a provider card's '+' does
      return providerForm('mistral', 'openai');
    """)
    time.sleep(3)
    b = d.execute_script(FIELDS)
    print()
    print("=== B) Tombol '+' di card provider (preset) ===")
    print(json.dumps(b, indent=1))
    bad = []
    if not b['presetPicker']: bad.append("dropdown hilang")
    if b['presetValue'] != 'mistral': bad.append(f"nilai preset: {b['presetValue']}")
    if 'api.mistral.ai' not in b['urlOpenAI']: bad.append(f"URL belum keisi: {b['urlOpenAI']}")
    if b['urlAnthropic']: bad.append("URL anthropic harusnya kosong")
    if bad: fails += 1; print("   FAIL:", "; ".join(bad))
    else: print("   PASS: dropdown terisi & terkunci, endpoint prefilled")

    errs = [e for e in d.get_log('browser') if e['level'] == 'SEVERE' and '401' not in e['message']]
    print()
    print("console errors:", len(errs))
    for e in errs[:5]: print("  ", e['message'][:160])
finally:
    d.quit()
print()
print("TOTAL FAILURES:", fails)
