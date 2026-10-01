#!/usr/bin/env python3
"""Every menu's app bar must match the Providers page bar. All values measured.

The Providers bar (`.pv-appbar`) is the reference. Workspace sheets need an
agent present before they will open, so the app's own state is seeded first.
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

MEASURE = """
  const bar = arguments[0] === 'page'
    ? document.querySelector('.pv-appbar')
    : document.querySelector('#modalRoot:not([hidden]) .modal-head');
  if (!bar) return {missing:true, arg:arguments[0]};
  const cb = getComputedStyle(bar);
  const back = bar.querySelector('.pv-appbar-back, .modal-back');
  const title = bar.querySelector('.pv-appbar-title, h3');
  const svg = back ? back.querySelector('svg') : null;
  const box = e => e ? [Math.round(e.getBoundingClientRect().width),
                        Math.round(e.getBoundingClientRect().height)] : null;
  const t = title ? getComputedStyle(title) : null;
  return {
    barH: Math.round(bar.getBoundingClientRect().height),
    barBg: cb.backgroundColor,
    cols: cb.gridTemplateColumns, pad: cb.padding,
    backBox: box(back),
    backRadius: back ? getComputedStyle(back).borderRadius : null,
    glyph: svg ? getComputedStyle(svg).width : null,
    titleText: title ? title.textContent.trim().slice(0,24) : null,
    titleFs: t ? t.fontSize : null,
    titleFw: t ? t.fontWeight : null,
    titleLs: t ? t.letterSpacing : null,
    titleColor: t ? t.color : null,
    titleAlign: t ? t.textAlign : null
  };
"""

def measure(where):
    return d.execute_script(MEASURE, where)

fails = 0
def check(cond, ok, bad):
    global fails
    if cond: print(f"      PASS {ok}")
    else:
        fails += 1
        print(f"      FAIL {bad}")

try:
    d.get("http://localhost:5173/"); time.sleep(2)
    d.execute_script("""
      localStorage.setItem('zeline.token','zln_abcdefghijklmnopqrstuvwxyz1234567890');
      localStorage.setItem('zeline.connection', JSON.stringify({configured:true,kind:'gateway',apiBase:'/api/v1'}));
      localStorage.setItem('zeline.agents', JSON.stringify([{id:'vf',name:'verify-agent',role:'agent',status:'idle'}]));
    """)
    d.get("http://localhost:5173/"); time.sleep(4)
    d.execute_script("return document.getElementById('onboarding').hidden=true")

    d.execute_script("return go('providers')"); time.sleep(4)
    ref = measure('page')
    print("=== REFERENCE (Providers page bar) ===")
    print(json.dumps(ref, indent=1))
    if ref.get('missing') or not ref.get('barH'):
        print("!! reference bar not measurable — aborting")
        raise SystemExit(1)

    scenarios = [
        ("Cronjob",      "cronjob"),
        ("Project",      "project"),
        ("Session",      "session"),
        ("Workflow",     "workflow"),
    ]
    rows = []
    for name, kind in scenarios:
        d.execute_script("closeModal&&closeModal()")
        time.sleep(0.8)
        d.execute_script(f"return openWorkspace('{kind}')")
        time.sleep(3)
        rows.append((name, measure('sheet')))

    # menus that are plain modals
    for name, opener in [("More", "openMoreMenu()"),
                         ("Add Provider", "go('providers')")]:
        d.execute_script("closeModal&&closeModal()"); time.sleep(0.8)
        if name == "Add Provider":
            d.execute_script("return go('providers')"); time.sleep(3)
            d.execute_script("return document.querySelector('.pv-add-main').click()")
        else:
            d.execute_script(f"return {opener}")
        time.sleep(3)
        rows.append((name, measure('sheet')))

    print()
    print("=== PARITY ===")
    print(f"   {'menu':14s} {'h':4s} {'bg':18s} {'back':10s} {'glyph':6s} "
          f"{'title':22s} {'size':7s} {'wt':5s} result")
    for name, r in rows:
        if r.get('missing'):
            print(f"   {name:14s} !! bar not found")
            fails += 1
            continue
        ok = (r['barH'] == ref['barH'] and r['barBg'] == ref['barBg']
              and r['backBox'] == ref['backBox'] and r['glyph'] == ref['glyph']
              and r['titleFs'] == ref['titleFs'] and r['titleFw'] == ref['titleFw']
              and r['titleLs'] == ref['titleLs']
              and r['backRadius'] == ref['backRadius'])
        if not ok: fails += 1
        print(f"   {name:14s} {r['barH']:<4} {r['barBg']:18s} {str(r['backBox']):10s} "
              f"{str(r['glyph']):6s} {str(r['titleText']):22s} {r['titleFs']:7s} "
              f"{r['titleFw']:5s} {'MATCH' if ok else 'DIFF'}")

    print()
    for name, r in rows:
        if r.get('missing'): continue
        print(f"   --- {name} ({r['titleText']})")
        for k, label in [('barH','height'), ('barBg','bar background'),
                         ('backBox','back box'), ('backRadius','back radius'),
                         ('glyph','glyph size')]:
            check(r[k] == ref[k], f"{label} {r[k]}", f"{label} {r[k]} vs ref {ref[k]}")
        for k, label in [('titleFs','title size'), ('titleFw','title weight'),
                         ('titleLs','title tracking'), ('titleColor','title colour')]:
            check(r[k] == ref[k], f"{label} {r[k]}", f"{label} {r[k]} vs ref {ref[k]}")

    errs = [e for e in d.get_log('browser') if e['level']=='SEVERE' and '401' not in e['message']]
    print()
    print("console errors:", len(errs))
    for e in errs[:6]: print("  ", e['message'][:150])
finally:
    d.quit()
print()
print("TOTAL FAILURES:", fails)
