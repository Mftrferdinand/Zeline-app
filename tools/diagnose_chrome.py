#!/usr/bin/env python3
"""Find out WHICH css rule actually wins on the provider sheet chrome, and
capture the full reference tone set from Cronjob."""
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
d = webdriver.Chrome(service=Service("/data/data/com.termux/files/usr/bin/chromedriver"), options=o)

TONES = """
  const g = s => { const e = document.querySelector(s); if (!e) return null;
    const c = getComputedStyle(e), b = e.getBoundingClientRect();
    return {fs:c.fontSize, fw:c.fontWeight, ls:c.letterSpacing, color:c.color,
            bg:c.backgroundColor, bgImg:c.backgroundImage.slice(0,46),
            cols:c.gridTemplateColumns, pad:c.padding,
            w:Math.round(b.width), h:Math.round(b.height),
            left:Math.round(b.left), top:Math.round(b.top),
            borderBottom:c.borderBottomWidth+' '+c.borderBottomColor}; };
  const svg = document.querySelector('.modal-back svg');
  const sb = svg ? svg.getBoundingClientRect() : null;
  return {
    modal:g('.modal'), head:g('.modal-head'), title:g('.modal-head h3'),
    back:g('.modal-back'),
    backSvg: svg ? {cssW:getComputedStyle(svg).width, cssH:getComputedStyle(svg).height,
                    rectW:Math.round(sb.width), rectH:Math.round(sb.height)} : null,
    body:g('.modal-body')
  };
"""

def boot():
    d.get("http://localhost:5173/"); time.sleep(2)
    d.execute_script("""
      localStorage.setItem('zeline.token','zln_abcdefghijklmnopqrstuvwxyz1234567890');
      localStorage.setItem('zeline.connection', JSON.stringify({configured:true,kind:'gateway',apiBase:'/api/v1'}));
      localStorage.setItem('zeline.agents', JSON.stringify([{id:'vf',name:'verify-agent'}]));
    """)
    d.get("http://localhost:5173/"); time.sleep(4)
    d.execute_script("return document.getElementById('onboarding').hidden=true")

try:
    boot()
    d.execute_script("return openWorkspace('cronjob')"); time.sleep(2.5)
    ref = d.execute_script(TONES)
    print("===== CRONJOB (REFERENCE) =====")
    print(json.dumps(ref, indent=1))
    # every card-ish surface inside cronjob
    print()
    print("--- cronjob inner surfaces ---")
    print(json.dumps(d.execute_script("""
      const out = {};
      const seen = new Set();
      document.querySelectorAll('.modal-body *').forEach(e => {
        const c = getComputedStyle(e);
        const bg = c.backgroundColor;
        if (bg === 'rgba(0, 0, 0, 0)' || bg === 'transparent') return;
        const key = e.className.toString().split(' ')[0] || e.tagName.toLowerCase();
        if (seen.has(key)) return;
        seen.add(key);
        out[key] = {bg: bg, border: c.borderTopColor, radius: c.borderRadius,
                    h: Math.round(e.getBoundingClientRect().height)};
      });
      return out;
    """), indent=1))
    d.execute_script("closeModal && closeModal()"); time.sleep(1)

    d.execute_script("return go('providers')"); time.sleep(4)
    d.execute_script("return document.querySelector('.pv-add-main').click()"); time.sleep(3)
    got = d.execute_script(TONES)
    print()
    print("===== ADD PROVIDER (CURRENT) =====")
    print(json.dumps(got, indent=1))

    print()
    print("===== WHICH RULES WIN =====")
    print(json.dumps(d.execute_script("""
      const report = {};
      const targets = {title:'.modal-head h3', back:'.modal-back',
                       head:'.modal-head', body:'.modal-body'};
      for (const [name, sel] of Object.entries(targets)) {
        const el = document.querySelector(sel);
        if (!el) continue;
        const hits = [];
        for (const sheet of document.styleSheets) {
          let rules;
          try { rules = sheet.cssRules; } catch (e) { continue; }
          const walk = list => {
            for (const r of list) {
              if (r.cssRules) { walk(r.cssRules); continue; }
              if (!r.selectorText) continue;
              let matches = false;
              try { matches = el.matches(r.selectorText); } catch (e) { continue; }
              if (!matches) continue;
              const props = ['font-size','font-weight','letter-spacing',
                             'background','background-color','width','height',
                             'grid-template-columns','padding'];
              const set = props.filter(p => r.style.getPropertyValue(p));
              if (set.length) hits.push({sel: r.selectorText.slice(0,90),
                props: set.map(p => p + ':' + r.style.getPropertyValue(p)
                  + (r.style.getPropertyPriority(p) ? '!' : '')).join('; ').slice(0,140)});
            }
          };
          walk(rules);
        }
        report[name] = hits.slice(-8);
      }
      return report;
    """), indent=1))
finally:
    d.quit()
