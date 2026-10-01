#!/usr/bin/env python3
"""Prove the MutationObserver auto-anchor keeps #stream pinned to the bottom
through a burst of mutations (bubble innerHTML rewrite + appended nodes),
exactly what a streaming agent turn does — and that scrolling UP releases it."""
import sys, time, json
sys.path.insert(0, "/data/data/com.termux/files/usr/lib/python3.13/site-packages")
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service

o = Options()
for a in ("--headless=new", "--no-sandbox", "--disable-dev-shm-usage",
          "--disable-gpu", "--window-size=430,720", "--incognito"):
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

    # arm the observer via scrollDown(force) then run a streaming burst
    print("=== 1. PINNED THROUGH A STREAMING BURST (no drift) ===")
    r = d.execute_script("""
      return new Promise(resolve=>{
        const s=document.getElementById('stream');
        s.innerHTML='';
        for(let i=0;i<40;i++){const b=document.createElement('div');b.className='bubble';b.textContent='hist '+i;s.appendChild(b);}
        scrollDown(true);               // arm glue + pin
        // streaming bubble whose innerHTML is rewritten every frame
        const bub=document.createElement('div');bub.className='assistant-plain-content streaming';s.appendChild(bub);
        let acc=''; let frame=0; const drifts=[];
        function step(){
          acc += 'word'+frame+' ';
          bub.innerHTML = '<p>'+acc+'</p>';       // same as paint()
          if(frame%5===0){const t=document.createElement('div');t.className='tool running';t.textContent='tool step '+frame;s.appendChild(t);}
          // measure how far from bottom the observer left us THIS frame
          const gap = (s.scrollHeight - s.scrollTop - s.clientHeight);
          drifts.push(gap);
          frame++;
          if(frame<60){requestAnimationFrame(step);}
          else{
            resolve({maxGap:Math.max(...drifts), finalGap:drifts[drifts.length-1],
                     scrolledOff: drifts.filter(g=>g>4).length});
          }
        }
        requestAnimationFrame(step);
      });
    """)
    print(json.dumps(r, indent=1))
    check(r['maxGap'] <= 4, f"never drifted from bottom (max gap {r['maxGap']}px)",
          f"drifted up to {r['maxGap']}px on {r['scrolledOff']} frames")
    check(r['finalGap'] <= 1, f"ends flush at the bottom (gap {r['finalGap']}px)",
          f"ends {r['finalGap']}px off bottom")

    print()
    print("=== 2. SCROLLING UP RELEASES THE GLUE (history stays put) ===")
    r2 = d.execute_script("""
      return new Promise(resolve=>{
        const s=document.getElementById('stream');
        s.scrollTop = 100;                       // user scrolls up to read
        s.dispatchEvent(new Event('scroll'));
        const parkedAt = s.scrollTop;
        // agent sends a new message while user is reading history
        const g=document.createElement('div');g.className='bubble';g.style.minHeight='80px';g.textContent='NEW agent msg';s.appendChild(g);
        setTimeout(()=>resolve({parkedAt, afterAppend:s.scrollTop, moved: Math.abs(s.scrollTop-parkedAt)}),80);
      });
    """)
    print(json.dumps(r2, indent=1))
    check(r2['moved'] <= 1, f"scroll position held while reading history (moved {r2['moved']}px)",
          f"yanked {r2['moved']}px — should stay put")

    errs = [e for e in d.get_log('browser') if e['level']=='SEVERE' and '401' not in e['message']]
    print("\nconsole errors:", len(errs))
    for e in errs[:5]: print("  ", e['message'][:150])
finally:
    d.quit()
print("\nTOTAL FAILURES:", fails)
