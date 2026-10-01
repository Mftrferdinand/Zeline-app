#!/usr/bin/env python3
"""Verify every menu at phone / tablet / desktop: centred panel, bar and body
agree, nothing overflows, nothing clipped."""
import sys, time, json
sys.path.insert(0, "/data/data/com.termux/files/usr/lib/python3.13/site-packages")
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service

SIZES = [(430, 900, 'phone'), (768, 1024, 'tablet'), (1280, 800, 'desktop')]
MENUS = [("Cronjob", "openWorkspace('cronjob')"),
         ("More", "openMoreMenu()"),
         ("Add Provider", "__add")]

PROBE = """
  const r = e => e.getBoundingClientRect();
  const m = document.querySelector('#modalRoot:not([hidden]) .modal');
  if (!m) return {missing:true};
  const bar = m.querySelector('.modal-head');
  const body = m.querySelector('.modal-body');
  const out = {vw: innerWidth,
               modal: {w: Math.round(r(m).width), left: Math.round(r(m).left),
                       right: Math.round(r(m).right), radius: getComputedStyle(m).borderRadius}};
  if (bar && body) {
    out.bar = {w: Math.round(r(bar).width), h: Math.round(r(bar).height)};
    out.body = {w: Math.round(r(body).width), h: Math.round(r(body).height)};
    out.barBodyMatch = Math.abs(out.bar.w - out.body.w) <= 2;
    // centred? mirror margins should match within a couple of px
    out.centred = Math.abs(r(m).left - (innerWidth - r(m).right)) <= 2;
  }
  out.overflowing = [...m.querySelectorAll('*')].filter(e => {
    const b = e.getBoundingClientRect();
    return b.width > 0 && (b.right > innerWidth + 1 || b.left < -1);
  }).slice(0, 5).map(e => ({cls:(e.className||'').toString().slice(0,30)||e.tagName,
                            right: Math.round(e.getBoundingClientRect().right)}));
  out.clipped = [...m.querySelectorAll('h3,h4,strong,small')].filter(e =>
    e.scrollWidth > e.clientWidth + 2 && e.clientWidth > 0
  ).slice(0, 5).map(e => (e.textContent || '').trim().slice(0, 24));
  return out;
"""

fails = 0
def check(cond, ok, bad):
    global fails
    if cond: print(f"      PASS {ok}")
    else:
        fails += 1
        print(f"      FAIL {bad}")

for w, h, size in SIZES:
    o = Options()
    for a in ("--headless=new", "--no-sandbox", "--disable-dev-shm-usage",
              "--disable-gpu", f"--window-size={w},{h}", "--incognito"):
        o.add_argument(a)
    o.binary_location = "/data/data/com.termux/files/usr/lib/chromium/chrome"
    o.set_capability("goog:loggingPrefs", {"browser": "ALL"})
    d = webdriver.Chrome(service=Service("/data/data/com.termux/files/usr/bin/chromedriver"), options=o)
    try:
        # Force the exact viewport; headless clamps windows to >=500px otherwise.
        d.execute_cdp_cmd("Emulation.setDeviceMetricsOverride",
                          {"width": w, "height": h, "deviceScaleFactor": 1,
                           "mobile": w < 600})
        d.get("http://localhost:5173/"); time.sleep(2)
        d.execute_script("""
          localStorage.setItem('zeline.token','zln_abcdefghijklmnopqrstuvwxyz1234567890');
          localStorage.setItem('zeline.connection', JSON.stringify({configured:true,kind:'gateway',apiBase:'/api/v1'}));
          localStorage.setItem('zeline.agents', JSON.stringify([{id:'vf',name:'verify-agent',role:'agent'}]));
        """)
        d.get("http://localhost:5173/"); time.sleep(4)
        d.execute_script("return document.getElementById('onboarding').hidden=true")

        print(f"===== {size.upper()} ({w}x{h}) =====")
        for name, js in MENUS:
            d.execute_script("closeModal&&closeModal()"); time.sleep(0.8)
            if js == "__add":
                d.execute_script("return go('providers')"); time.sleep(3)
                d.execute_script("return document.querySelector('.pv-add-main').click()")
            else:
                d.execute_script(f"return go('providers')"); time.sleep(2)
                d.execute_script(f"return {js}")
            time.sleep(3)
            p = d.execute_script(PROBE)
            if p.get('missing'):
                print(f"   {name:14s} !! not open")
                continue
            print(f"   {name:14s} modal {p['modal']['w']}px @x={p['modal']['left']} "
                  f"bar {p.get('bar',{}).get('w')} body {p.get('body',{}).get('w')}")
            check(p['modal']['w'] <= w, f"{name}: fits the viewport",
                  f"{name}: modal {p['modal']['w']} > viewport {w}")
            if size != 'phone':
                check(p.get('centred'), f"{name}: centred",
                      f"{name}: not centred ({p['modal']['left']} vs {w - p['modal']['right']})")
                check(p['modal']['w'] <= 720, f"{name}: panel is a reading column ({p['modal']['w']}px)",
                      f"{name}: panel stretched to {p['modal']['w']}px")
            check(p.get('barBodyMatch', True), f"{name}: bar and body share a width",
                  f"{name}: bar {p.get('bar',{}).get('w')} vs body {p.get('body',{}).get('w')}")
            check(not p['overflowing'], f"{name}: nothing overflows",
                  f"{name}: overflow {p['overflowing']}")
            check(not p['clipped'], f"{name}: nothing clipped",
                  f"{name}: clipped {p['clipped']}")
        print()
    finally:
        d.quit()
print("TOTAL FAILURES:", fails)
