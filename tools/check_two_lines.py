#!/usr/bin/env python3
"""Verify: cards are exactly 2 lines with the short endpoint captions, and the
dialect switch animates cleanly — including under a rapid double-tap."""
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

    print("=== 1. CAPTIONS + EXACTLY 2 LINES ===")
    c = d.execute_script("""
      const bs=[...document.querySelectorAll('.pv-seg-btn')];
      return bs.map(b=>{
        const st=b.querySelector('strong'), sm=b.querySelector('small');
        const lh=parseFloat(getComputedStyle(st).lineHeight);
        const r=e=>e.getBoundingClientRect();
        return {
          title:st.textContent.trim(), caption:sm.textContent.trim(),
          cardH:Math.round(r(b).height),
          titleLines:Math.round(r(st).height/lh),
          capLines:Math.round(r(sm).height/parseFloat(getComputedStyle(sm).lineHeight)),
          titleClipped: st.scrollWidth > st.clientWidth + 1,
          capClipped: sm.scrollWidth > sm.clientWidth + 1,
          whiteSpace:getComputedStyle(st).whiteSpace,
          top:Math.round(r(b).top), left:Math.round(r(b).left)
        };});
    """)
    print(json.dumps(c, indent=1))
    caps = [x['caption'] for x in c]
    check(caps == ['/v1/messages', '/v1/chat · /v1/responses'],
          f"captions exact: {caps}", f"captions wrong: {caps}")
    check(all(x['titleLines'] == 1 and x['capLines'] == 1 for x in c),
          "every card is exactly 2 lines (1 title + 1 caption)",
          f"line counts off: {[(x['titleLines'], x['capLines']) for x in c]}")
    check(len({x['cardH'] for x in c}) == 1,
          f"both cards identical height ({c[0]['cardH']}px)",
          f"heights differ: {[x['cardH'] for x in c]}")
    check(not any(x['titleClipped'] or x['capClipped'] for x in c),
          "no text is clipped at this width",
          f"clipped: {[(x['title'], x['titleClipped'], x['capClipped']) for x in c]}")
    check(c[0]['top'] == c[1]['top'], "still one row", "cards not aligned")

    print()
    print("=== 2. SWITCH ANIMATION PRESENT + RE-ARMS ===")
    for n in (1, 2, 3):
        target = 'anthropic' if n % 2 else 'openai'
        d.execute_script(f"""document.querySelector('[data-dialect="{target}"]').click()""")
        time.sleep(0.06)
        mid = d.execute_script("""
          const f=document.getElementById('pvFields');
          const c=getComputedStyle(f);
          return {cls:f.className, anim:c.animationName, dur:c.animationDuration,
                  opacity:c.opacity};
        """)
        time.sleep(0.5)
        after = d.execute_script("""
          const f=document.getElementById('pvFields');
          const c=getComputedStyle(f);
          return {opacity:c.opacity, transform:c.transform,
                  fields:[...f.querySelectorAll('.field')].length,
                  anyHidden:[...f.querySelectorAll('.field')]
                    .some(e=>parseFloat(getComputedStyle(e).opacity) < 0.99)};
        """)
        print(f"   switch {n} -> {target}")
        print(f"     mid-flight : anim={mid['anim']} dur={mid['dur']} opacity={mid['opacity']}")
        print(f"     settled    : opacity={after['opacity']} fields={after['fields']} anyHidden={after['anyHidden']}")
        check(mid['anim'] == 'pvFieldsIn', f"animation fires on switch {n}",
              f"no animation on switch {n}: {mid['anim']}")
        check(after['opacity'] == '1' and not after['anyHidden'],
              f"settles fully opaque after switch {n}",
              f"stuck translucent after switch {n}: {after}")

    print()
    print("=== 3. RAPID DOUBLE-TAP (bug hunt) ===")
    d.execute_script("""
      // hammer both tabs with no delay — the old stagger left fields at
      // partial opacity when a second switch landed mid-animation
      const a=document.querySelector('[data-dialect="anthropic"]');
      const o=document.querySelector('[data-dialect="openai"]');
      a.click(); o.click(); a.click(); o.click(); a.click();
    """)
    time.sleep(1.2)
    st = d.execute_script("""
      const f=document.getElementById('pvFields');
      const fl=[...f.querySelectorAll('.field')];
      const act=[...document.querySelectorAll('.pv-seg-btn')]
        .filter(b=>b.classList.contains('is-active')).map(b=>b.dataset.dialect);
      return {
        opacity:getComputedStyle(f).opacity,
        transform:getComputedStyle(f).transform,
        fieldCount:fl.length,
        translucent:fl.filter(e=>parseFloat(getComputedStyle(e).opacity)<0.99).length,
        activeTabs:act,
        labels:fl.map(e=>(e.querySelector('label')?.textContent||'').trim()),
        protocol:document.getElementById('pvProtocol').value
      };
    """)
    print(json.dumps(st, indent=1))
    check(st['opacity'] == '1' and st['translucent'] == 0,
          "no field left translucent after hammering",
          f"{st['translucent']} fields stuck translucent")
    check(len(st['activeTabs']) == 1, f"exactly one tab active ({st['activeTabs']})",
          f"active tabs: {st['activeTabs']}")
    expect = {'anthropic': ['Provider Name','Base URL','API Key','Model ID (optional)'],
              'openai': ['Provider Name','API Type','Base URL','API Key','Model ID (optional)']}
    want = expect[st['activeTabs'][0]]
    check(st['labels'] == want, f"field set matches the active tab",
          f"desync: tab={st['activeTabs']} fields={st['labels']}")
    check(st['protocol'] == st['activeTabs'][0],
          f"hidden protocol matches the tab ({st['protocol']})",
          f"protocol={st['protocol']} tab={st['activeTabs']}")

    print()
    print("=== 4. LIGHT THEME CARDS ===")
    d.execute_script("document.documentElement.setAttribute('data-app-theme','light')")
    time.sleep(0.8)
    lt = d.execute_script("""
      const bs=[...document.querySelectorAll('.pv-seg-btn')];
      return bs.map(b=>({d:b.dataset.dialect, active:b.classList.contains('is-active'),
        bg:getComputedStyle(b).backgroundColor,
        bgImg:getComputedStyle(b).backgroundImage.slice(0,44),
        h:Math.round(b.getBoundingClientRect().height)}));
    """)
    print(json.dumps(lt, indent=1))
    check(len({x['h'] for x in lt}) == 1, "heights consistent in light theme",
          f"heights: {[x['h'] for x in lt]}")

    errs = [e for e in d.get_log('browser') if e['level']=='SEVERE' and '401' not in e['message']]
    print()
    print("console errors:", len(errs))
    for e in errs[:6]: print("  ", e['message'][:160])
    if errs: fails += 1
finally:
    d.quit()
print()
print("TOTAL FAILURES:", fails)
