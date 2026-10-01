#!/usr/bin/env python3
"""Verify: one Add Provider card that reveals two dialect cards in place, and
no Indonesian text left in the provider UI."""
import sys, time, json, re, pathlib
sys.path.insert(0, "/data/data/com.termux/files/usr/lib/python3.13/site-packages")
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service

ROOT = pathlib.Path("/data/data/com.termux/files/home/zeline-frontend")
o = Options()
for a in ("--headless=new", "--no-sandbox", "--disable-dev-shm-usage",
          "--disable-gpu", "--window-size=430,900", "--incognito"):
    o.add_argument(a)
o.binary_location = "/data/data/com.termux/files/usr/lib/chromium/chrome"
o.set_capability("goog:loggingPrefs", {"browser": "ALL"})
d = webdriver.Chrome(service=Service("/data/data/com.termux/files/usr/bin/chromedriver"), options=o)

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

    print("=== 1. COLLAPSED (initial) ===")
    st = d.execute_script("""
      const main=document.querySelector('.pv-add-main');
      const ch=document.querySelector('[data-add-choices]');
      const vis=e=>e&&e.offsetParent!==null;
      return {mainVisible:vis(main), mainText:main?.querySelector('strong')?.textContent,
              mainSub:main?.querySelector('small')?.textContent,
              choicesHidden:ch?.hidden,
              choicesVisible:vis(ch),
              dialectCardsVis:[...document.querySelectorAll('.pv-add-stack .pv-add-card')].filter(vis).length};
    """)
    print(json.dumps(st, indent=1))
    if not st['mainVisible']: fails += 1; print("  FAIL: main card not visible")
    if not st['choicesHidden']: fails += 1; print("  FAIL: choices should start hidden")
    if st['dialectCardsVis'] != 0: fails += 1; print("  FAIL: dialect cards visible while collapsed")
    if st['dialectCardsVis'] == 0: print("  PASS: 1 card only, choices hidden")

    print()
    print("=== 2. AFTER TAP ===")
    d.execute_script("return document.querySelector('.pv-add-main').click()")
    time.sleep(1.2)
    st2 = d.execute_script("""
      const main=document.querySelector('.pv-add-main');
      const ch=document.querySelector('[data-add-choices]');
      const vis=e=>e&&e.offsetParent!==null;
      return {mainText:main?.querySelector('strong')?.textContent,
              mainSub:main?.querySelector('small')?.textContent,
              isOpen:main?.classList.contains('is-open'),
              choicesVisible:vis(ch),
              cards:[...document.querySelectorAll('.pv-add-stack .pv-add-card')]
                .map(b=>({t:b.querySelector('strong')?.textContent.trim(),
                          s:b.querySelector('small')?.textContent.trim(),
                          proto:b.dataset.addProtocol, vis:vis(b)}))};
    """)
    print(json.dumps(st2, indent=1))
    shown = [c for c in st2['cards'] if c['vis']]
    if len(shown) != 2: fails += 1; print(f"  FAIL: expected 2 revealed cards, got {len(shown)}")
    else: print("  PASS: both dialect cards now visible")

    print()
    print("=== 3. AFTER TAP AGAIN (collapse) ===")
    d.execute_script("return document.querySelector('.pv-add-main').click()")
    time.sleep(1.0)
    st3 = d.execute_script("""
      const ch=document.querySelector('[data-add-choices]');
      const main=document.querySelector('.pv-add-main');
      return {hidden:ch.hidden, text:main.querySelector('strong').textContent,
              isOpen:main.classList.contains('is-open')};
    """)
    print(json.dumps(st3, indent=1))
    if not st3['hidden']: fails += 1; print("  FAIL: should collapse again")
    else: print("  PASS: collapses back")

    print()
    print("=== 4. FORM PER DIALECT ===")
    for proto, expect in [('anthropic', ['Name','Prefix','Base URL','API Key (for Check)','Model ID']),
                          ('openai', ['Name','Prefix','API Type','Base URL','API Key (for Check)','Model ID'])]:
        d.execute_script("closeModal&&closeModal()")
        d.execute_script(f"return providerForm('', '{proto}')")
        time.sleep(2.5)
        r = d.execute_script("""
          return {title:document.getElementById('modalTitle').textContent,
                  labels:[...document.querySelectorAll('.provider-form > .field')]
                    .filter(e=>e.offsetParent!==null)
                    .map(e=>(e.querySelector('label')?.textContent||'').replace(' *','').trim())};
        """)
        ok = r['labels'] == expect
        if not ok: fails += 1
        print(f"  {proto:10s} title={r['title']!r}")
        print(f"             fields={r['labels']}  {'PASS' if ok else 'FAIL expected ' + str(expect)}")

    print()
    print("=== 5. INDONESIAN STRING SCAN (source) ===")
    ID = re.compile(r"\b(wajib|belum|Belum|Batal|Mengecek|tersedia|Pakai |Ganti |Hapus|Gagal|Mulai |Simpan|Cari |Masukkan|Tidak ada|tidak ada|dengan |untuk |kalau |kalo |yang |Dipakai|dipakai|Opsional|otomatis|terisi|nyambung|salah|mati)\b")
    hits = []
    for f in ["app1.js","app2.js","app3.js","app4.js","app5.js","index.html"]:
        txt = (ROOT/f).read_text(encoding="utf-8")
        for i, line in enumerate(txt.split("\n"), 1):
            # only lines that look like UI copy (quoted/backticked strings or JSX text)
            if not re.search(r"['\"`>].*[a-zA-Z]", line):
                continue
            if line.strip().startswith(("//","*","/*")):
                continue
            m = ID.search(line)
            if m:
                hits.append(f"{f}:{i}: {m.group(0)} :: {line.strip()[:95]}")
    if hits:
        fails += 1
        print(f"  {len(hits)} possible Indonesian UI strings:")
        for h in hits[:15]: print("   ", h)
    else:
        print("  PASS: no Indonesian UI strings found")

    errs = [e for e in d.get_log('browser') if e['level']=='SEVERE' and '401' not in e['message']]
    print()
    print("console errors:", len(errs))
    for e in errs[:5]: print("  ", e['message'][:150])
finally:
    d.quit()
print()
print("TOTAL FAILURES:", fails)
