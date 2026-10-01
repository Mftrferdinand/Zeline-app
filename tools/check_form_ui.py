#!/usr/bin/env python3
"""UI check: does the Cek-koneksi result show a clear valid/invalid + reason?"""
import sys, time
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

def open_form():
    d.get("http://localhost:5173/"); time.sleep(2)
    d.execute_script("""
      localStorage.setItem('zeline.token','zln_abcdefghijklmnopqrstuvwxyz1234567890');
      localStorage.setItem('zeline.connection', JSON.stringify({configured:true,kind:'gateway',apiBase:'/api/v1'}));
    """)
    d.get("http://localhost:5173/"); time.sleep(4)
    d.execute_script("return document.getElementById('onboarding').hidden=true")
    d.execute_script("return go('providers')"); time.sleep(4)
    d.execute_script("return document.querySelector('#providerGrid .pv-add-card').click()")
    time.sleep(3)

def run(url, key, model, label):
    d.execute_script("""
      const u=document.getElementById('pvURL'); u.value=arguments[0];
      u.dispatchEvent(new Event('input'));
      document.getElementById('pvKey').value=arguments[1];
      document.getElementById('pvModel').value=arguments[2];
      const b=[...document.querySelectorAll('button')].find(x=>/cek koneksi/i.test(x.textContent||''));
      if(b) b.click();
    """, url, key, model)
    time.sleep(10)
    r = d.execute_script("""
      const n=document.querySelector('.provider-form-note');
      return {txt:n.textContent, cls:n.className, h:Math.round(n.getBoundingClientRect().height)};
    """)
    print(f"--- {label}")
    print(f"    class : {r['cls']}")
    print(f"    tinggi: {r['h']}")
    print(f"    pesan : {r['txt'][:300]}")
    print()

try:
    open_form()
    run("http://localhost:20128/v1", "rc_proxy_key", "", "VALID (tanpa model)")
    run("http://localhost:20128/v1", "rc_proxy_key", "model-ngawur-999", "VALID tapi model nggak ada")
    run("https://endpoint-palsu-xyz.invalid/v1", "sk-x", "", "Endpoint MATI")
    run("https://api.anthropic.com", "sk-ant-invalid-salah", "", "Key SALAH (401 asli)")
    run("", "sk-x", "", "Base URL kosong")
    errs = [e for e in d.get_log('browser') if e['level'] == 'SEVERE' and '401' not in e['message']]
    print("console errors:", len(errs))
finally:
    d.quit()
