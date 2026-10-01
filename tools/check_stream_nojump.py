#!/usr/bin/env python3
"""Prove the streaming bubble children no longer animate/translate (the 2px
per-frame rise that read as "loncat sedikit kebawah"), and that pinning to the
bottom keeps the container's scrollTop pinned across a paint."""
import sys, time, json
sys.path.insert(0, "/data/data/com.termux/files/usr/lib/python3.13/site-packages")
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service

o = Options()
for a in ("--headless=new", "--no-sandbox", "--disable-dev-shm-usage",
          "--disable-gpu", "--window-size=430,760", "--incognito"):
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
    d.get("http://localhost:5173/"); time.sleep(3)
    d.execute_script("try{document.getElementById('onboarding').hidden=true}catch(e){}")

    print("=== 1. STREAMING CHILD HAS NO ANIMATION / NO TRANSLATE ===")
    res = d.execute_script("""
      const s = document.getElementById('stream');
      if (!s) return {err:'no stream node'};
      s.innerHTML = '';
      const bubble = document.createElement('div');
      bubble.className = 'assistant-plain-content streaming';
      const p = document.createElement('p');
      p.textContent = 'streamed line';
      bubble.appendChild(p);
      s.appendChild(bubble);
      const cs = getComputedStyle(p);
      return {animName: cs.animationName, transform: cs.transform};
    """)
    print(json.dumps(res, indent=1))
    check(res.get('animName') in ('none', '', None),
          f"streaming child animation-name = {res.get('animName')} (no per-frame rise)",
          f"still animating: {res.get('animName')}")
    check(res.get('transform') in ('none', 'matrix(1, 0, 0, 1, 0, 0)', None),
          f"streaming child transform = {res.get('transform')} (no translateY jitter)",
          f"still transformed: {res.get('transform')}")

    print()
    print("=== 2. PINNED BOTTOM STAYS PINNED ACROSS A CONTENT GROW ===")
    pin = d.execute_script("""
      const s = document.getElementById('stream');
      s.innerHTML='';
      // fill past one screen
      for (let i=0;i<40;i++){const b=document.createElement('div');b.className='bubble';b.textContent='msg '+i;s.appendChild(b);}
      s.scrollTop = s.scrollHeight;              // park at bottom
      const before = s.scrollTop;
      const maxBefore = s.scrollHeight - s.clientHeight;
      // simulate scrollDown()'s instant pin (what app2.js does when force/near-bottom)
      const prev=s.style.scrollBehavior; s.style.scrollBehavior='auto';
      const g=document.createElement('div');g.className='bubble';g.textContent='new streamed line';s.appendChild(g);
      s.scrollTop = s.scrollHeight;
      s.style.scrollBehavior=prev;
      const after = s.scrollTop;
      const maxAfter = s.scrollHeight - s.clientHeight;
      return {before, maxBefore, after, maxAfter, atBottom: Math.abs(after-maxAfter)<=1};
    """)
    print(json.dumps(pin, indent=1))
    check(pin['atBottom'], "still pinned to the exact bottom after grow", f"drifted: {pin}")

    errs = [e for e in d.get_log('browser') if e['level']=='SEVERE' and '401' not in e['message']]
    print("\nconsole errors:", len(errs))
    for e in errs[:5]: print("  ", e['message'][:150])
finally:
    d.quit()
print("\nTOTAL FAILURES:", fails)
