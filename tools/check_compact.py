#!/usr/bin/env python3
"""Verify the compaction pass: 1-line tabs, no header overflow bug,
Check Connection at the BOTTOM, smaller cards."""
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

try:
    d.get("http://localhost:5173/"); time.sleep(2)
    d.execute_script("""
      localStorage.setItem('zeline.token','zln_abcdefghijklmnopqrstuvwxyz1234567890');
      localStorage.setItem('zeline.connection', JSON.stringify({configured:true,kind:'gateway',apiBase:'/api/v1'}));
    """)
    d.get("http://localhost:5173/"); time.sleep(4)
    d.execute_script("return document.getElementById('onboarding').hidden=true")
    d.execute_script("return go('providers')"); time.sleep(4)

    print("=== 1. ADD CARD + PROVIDER ROWS COMPACT ===")
    c = d.execute_script("""
      const g=e=>{if(!e)return null;const b=e.getBoundingClientRect();const s=getComputedStyle(e);
        return {h:Math.round(b.height), pad:s.padding, radius:s.borderRadius};};
      const add=document.querySelector('.pv-add-main');
      const row=document.querySelector('.pv-card-row');
      return {addCard:g(add),
              addStrongFs:add?getComputedStyle(add.querySelector('strong')).fontSize:null,
              row:g(row),
              rowNameFs:row?getComputedStyle(row.querySelector('.pv-name')).fontSize:null,
              rowIcon:row?getComputedStyle(row.querySelector('.pv-icon')).width:null};
    """)
    print(json.dumps(c, indent=1))
    check(c['addCard'] and c['addCard']['h'] <= 46 and c['addStrongFs'] == '12px',
          f"add card {c['addCard']['h']}px / 12px text", f"add card too big: {c['addCard']}")
    if c['row']:
        check(c['row']['h'] <= 52 and c['rowNameFs'] == '12.5px',
              f"provider rows {c['row']['h']}px / 12.5px", f"rows off: {c['row']}")

    print()
    print("=== 2. OPEN SCREEN: header must NOT overflow ===")
    d.execute_script("return document.querySelector('.pv-add-main').click()")
    time.sleep(3)
    h = d.execute_script("""
      const head=document.querySelector('.modal-head');
      const sub=document.querySelector('.modal-head-subtitle');
      const hb=head.getBoundingClientRect();
      const kids=[...head.children].map(e=>{const b=e.getBoundingClientRect();
        return {cls:e.className.slice(0,24), bottom:Math.round(b.bottom), vis:e.offsetParent!==null};});
      return {headBottom:Math.round(hb.bottom), headH:Math.round(hb.height),
              subVisible: sub ? (sub.offsetParent!==null) : false,
              subDisplay: sub ? getComputedStyle(sub).display : 'absent',
              overflowing: kids.filter(k=>k.vis && k.bottom > Math.round(hb.bottom)+1)};
    """)
    print(json.dumps(h, indent=1))
    check(not h['subVisible'], "subtitle hidden (no line-cut bug)", f"subtitle still visible: {h['subDisplay']}")
    check(len(h['overflowing']) == 0, "nothing overflows the header",
          f"overflowing: {h['overflowing']}")

    print()
    print("=== 3. TABS: 1 LINE, SMALLER ===")
    t = d.execute_script("""
      const b=document.querySelector('.pv-seg-btn');
      const seg=document.querySelector('.pv-seg');
      const st=b.querySelector('strong'); const sm=b.querySelector('small');
      return {segH:Math.round(seg.getBoundingClientRect().height),
              btnH:Math.round(b.getBoundingClientRect().height),
              strongFs:getComputedStyle(st).fontSize,
              smallDisplay: sm?getComputedStyle(sm).display:'absent',
              label:st.textContent.trim(),
              lines: Math.round(b.getBoundingClientRect().height / parseFloat(getComputedStyle(b).lineHeight))};
    """)
    print(json.dumps(t, indent=1))
    check(t['btnH'] <= 36 and t['smallDisplay'] == 'none' and t['strongFs'] == '11.5px',
          f"tabs single line {t['btnH']}px / 11.5px", f"tabs off: {t}")

    print()
    print("=== 4. CHECK CONNECTION AT THE BOTTOM ===")
    f = d.execute_script("""
      const foot=document.querySelector('.modal-foot');
      const act=document.querySelector('.modal-head-action');
      const fb=foot.getBoundingClientRect();
      const btns=[...foot.querySelectorAll('.btn')].map(b=>({t:b.textContent.trim(),
        h:Math.round(b.getBoundingClientRect().height),
        top:Math.round(b.getBoundingClientRect().top),
        primary:b.classList.contains('primary')}));
      return {footDisplay:getComputedStyle(foot).display,
              footTop:Math.round(fb.top), footH:Math.round(fb.height),
              viewportH:window.innerHeight,
              headActionVisible: act ? (act.offsetParent!==null) : false,
              buttons:btns};
    """)
    print(json.dumps(f, indent=1))
    check(f['footDisplay'] != 'none', "footer is visible", "footer still hidden")
    check(not f['headActionVisible'], "header action hidden", "action still in header")
    prim = [b for b in f['buttons'] if b['primary']]
    check(prim and prim[0]['t'] == 'Check Connection',
          "Check Connection is in the bottom bar", f"buttons: {f['buttons']}")
    check(f['footTop'] > f['viewportH'] * 0.6,
          f"footer sits at the bottom (y={f['footTop']} of {f['viewportH']})",
          f"footer not at bottom: y={f['footTop']}")

    print()
    print("=== 5. GRID + TAB COLOURS STILL OK ===")
    v = d.execute_script("""
      const b=document.querySelector('.modal-body');
      const oa=document.querySelector('[data-dialect="openai"]');
      return {grid:getComputedStyle(b).backgroundImage.includes('gradient'),
              size:getComputedStyle(b).backgroundSize,
              openaiBg:getComputedStyle(oa).backgroundImage.slice(0,60)};
    """)
    print(json.dumps(v, indent=1))
    check(v['grid'] and '38px' in v['size'], "grid intact", f"grid lost: {v}")

    d.execute_script("""document.querySelector('[data-dialect="anthropic"]').click()""")
    time.sleep(1.2)
    oc = d.execute_script("""
      const a=document.querySelector('[data-dialect="anthropic"]');
      return getComputedStyle(a).backgroundImage.slice(0,60);
    """)
    print("anthropic active bg:", oc)
    check('242, 136' in oc or '221, 95' in oc, "Anthropic still orange", f"not orange: {oc}")

    errs = [e for e in d.get_log('browser') if e['level']=='SEVERE' and '401' not in e['message']]
    print()
    print("console errors:", len(errs))
    for e in errs[:5]: print("  ", e['message'][:150])
    if errs: fails += 1
finally:
    d.quit()
print()
print("TOTAL FAILURES:", fails)
