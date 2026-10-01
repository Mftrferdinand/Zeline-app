#!/usr/bin/env python3
"""Verify the v384 premium pass actually lands in the browser."""
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
    if cond:
        print(f"   PASS: {ok}")
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
    d.execute_script("return document.querySelector('.pv-add-main').click()")
    time.sleep(3)

    print("=== 1. GRID BACKDROP ===")
    g = d.execute_script("""
      const b=document.querySelector('.modal-body');const c=getComputedStyle(b);
      return {img:c.backgroundImage.slice(0,90), size:c.backgroundSize, color:c.backgroundColor};
    """)
    print(json.dumps(g, indent=1))
    check('gradient' in g['img'] and '38px' in g['size'],
          "grid 38px painted behind the form", f"no grid: {g}")

    print()
    print("=== 2. TAB COLOURS (OpenAI active = WHITE) ===")
    t = d.execute_script("""
      const a=document.querySelector('[data-dialect="anthropic"]');
      const o=document.querySelector('[data-dialect="openai"]');
      const g=e=>{const c=getComputedStyle(e);return {
        bgImage:c.backgroundImage.slice(0,70), color:c.color,
        shadow:c.boxShadow.slice(0,50), active:e.classList.contains('is-active'),
        fs:getComputedStyle(e.querySelector('strong')).fontSize};};
      return {anthropic:g(a), openai:g(o)};
    """)
    print(json.dumps(t, indent=1))
    check(t['openai']['active'] and ('255, 255, 255' in t['openai']['bgImage'] or 'rgb(255' in t['openai']['bgImage']),
          "OpenAI tab is white when active", f"OpenAI not white: {t['openai']['bgImage']}")

    print()
    print("=== 3. SWITCH TO ANTHROPIC (should be ORANGE) ===")
    d.execute_script("""document.querySelector('[data-dialect="anthropic"]').click()""")
    time.sleep(1.5)
    t2 = d.execute_script("""
      const a=document.querySelector('[data-dialect="anthropic"]');
      const c=getComputedStyle(a);
      return {bgImage:c.backgroundImage.slice(0,80), color:c.color,
              shadow:c.boxShadow.slice(0,60), active:a.classList.contains('is-active')};
    """)
    print(json.dumps(t2, indent=1))
    orange = any(x in t2['bgImage'] for x in ('242, 136', '221, 95', '242,136', '221,95'))
    check(t2['active'] and orange, "Anthropic tab is orange when active",
          f"Anthropic not orange: {t2['bgImage']}")

    print()
    print("=== 4. FIELD TYPOGRAPHY & WELLS ===")
    f = d.execute_script("""
      const i=document.getElementById('pvName');const c=getComputedStyle(i);
      const l=document.querySelector('#pvFields .field label');const lc=getComputedStyle(l);
      return {inputH:Math.round(i.getBoundingClientRect().height), inputFs:c.fontSize,
              radius:c.borderRadius, bgImage:c.backgroundImage.slice(0,50),
              labelFs:lc.fontSize, labelWeight:lc.fontWeight};
    """)
    print(json.dumps(f, indent=1))
    check(f['inputH'] == 48 and f['inputFs'] == '14.5px' and f['labelFs'] == '12px',
          f"inputs 48px / 14.5px, labels 12px", f"typography off: {f}")

    print()
    print("=== 5. PULL ANIMATION ON SWAP ===")
    anim = d.execute_script("""
      const f=document.querySelector('#pvFields > .field');
      const c=getComputedStyle(f);
      return {name:c.animationName, dur:c.animationDuration, timing:c.animationTimingFunction.slice(0,30)};
    """)
    print(json.dumps(anim, indent=1))
    check(anim['name'] == 'pvPullIn' and anim['dur'] != '0s',
          f"fields animate in ({anim['name']} {anim['dur']})", f"no animation: {anim}")

    print()
    print("=== 6. BACK + CHECK BUTTON POLISH ===")
    btn = d.execute_script("""
      const back=document.querySelector('.modal-back');
      const svg=back?.querySelector('svg');
      // On mobile the footer is display:none by design; the primary action is
      // promoted into .modal-head-action. Assert the control the user sees.
      const act=document.querySelector('.modal-head-action');
      const g=e=>{const c=getComputedStyle(e);return {
        h:Math.round(e.getBoundingClientRect().height), fs:c.fontSize, fw:c.fontWeight,
        radius:c.borderRadius, bgImage:c.backgroundImage.slice(0,55),
        shadow:c.boxShadow.slice(0,40), label:e.textContent.trim()};};
      return {backSvg: svg?getComputedStyle(svg).width:null,
              headAction: act?g(act):null,
              footVisible: getComputedStyle(document.querySelector('.modal-foot')).display !== 'none'};
    """)
    print(json.dumps(btn, indent=1))
    a = btn['headAction']
    check(a and a['label'] == 'Check Connection' and a['radius'] == '11px'
          and 'gradient' in a['bgImage'] and a['fs'] == '12.5px',
          "Check Connection is a styled pill in the header", f"head action off: {a}")
    check(btn['backSvg'] == '25px', "back glyph 25px", f"back glyph {btn['backSvg']}")

    print()
    print("=== 7. LIGHT THEME ===")
    d.execute_script("document.documentElement.setAttribute('data-app-theme','light')")
    time.sleep(1)
    lt = d.execute_script("""
      const b=document.querySelector('.modal-body');
      const i=document.getElementById('pvName');
      return {bodyBg:getComputedStyle(b).backgroundColor,
              gridImg:getComputedStyle(b).backgroundImage.includes('gradient'),
              inputBg:getComputedStyle(i).backgroundImage.slice(0,45)};
    """)
    print(json.dumps(lt, indent=1))
    check(lt['gridImg'], "grid present in light theme", "grid missing in light")

    errs = [e for e in d.get_log('browser') if e['level']=='SEVERE' and '401' not in e['message']]
    print()
    print("console errors:", len(errs))
    for e in errs[:5]: print("  ", e['message'][:150])
    if errs: fails += 1
finally:
    d.quit()
print()
print("TOTAL FAILURES:", fails)
