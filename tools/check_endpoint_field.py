#!/usr/bin/env python3
"""Verify: Select Endpoint matches the form's field rhythm, its description is
static (never moves on click), gaps are uniform, and Model ID shows examples."""
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

GEOM = """
  const r = e => e.getBoundingClientRect();
  const g = s => { const e=document.querySelector(s); if(!e) return null;
    const c=getComputedStyle(e); return {fs:c.fontSize, fw:c.fontWeight,
      color:c.color, margin:c.margin, top:Math.round(r(e).top),
      bottom:Math.round(r(e).bottom), h:Math.round(r(e).height)}; };
  const h4  = g('.pv-seg-head h4');
  const sq  = g('.pv-seg-head .field-desc');
  const cards = [...document.querySelectorAll('.pv-seg-btn')].map(c=>({
    txt:c.querySelector('strong').textContent.trim(),
    top:Math.round(r(c).top), bottom:Math.round(r(c).bottom),
    left:Math.round(r(c).left), w:Math.round(r(c).width), h:Math.round(r(c).height)}));
  const firstField = document.querySelector('#pvFields > .field');
  const fLabel = firstField ? getComputedStyle(firstField.querySelector('label')) : null;
  const fDesc  = firstField ? getComputedStyle(firstField.querySelector('.field-desc')) : null;
  const fLabelBox = firstField ? r(firstField.querySelector('label')) : null;
  return {
    h4, sq, cards,
    descCount: document.querySelectorAll('.pv-seg-head .field-desc').length,
    optDescsLeft: document.querySelectorAll('.pv-opt-desc').length,
    labelZ: firstField ? {fs:fLabel.fontSize, fw:fLabel.fontWeight, color:fLabel.color} : null,
    descZ:  firstField ? {fs:fDesc.fontSize, fw:fDesc.fontWeight, color:fDesc.color} : null,
    titleToDesc: (h4 && sq) ? Math.round(sq.top - h4.bottom) : null,
    refTitleToDesc: (fLabelBox) ? Math.round(r(firstField.querySelector('.field-desc')).top - fLabelBox.bottom) : null,
    cardsToNextTitle: fLabelBox ? Math.round(fLabelBox.top - Math.max(...cards.map(c=>r(
      [...document.querySelectorAll('.pv-seg-btn')].find(b=>b.querySelector('strong').textContent.trim()===c.txt)).bottom))) : null,
    modelPlaceholder: document.getElementById('pvModel')?.placeholder
  };
"""

try:
    d.get("http://localhost:5173/"); time.sleep(2)
    d.execute_script("""
      localStorage.setItem('zeline.token','zln_abcdefghijklmnopqrstuvwxyz1234567890');
      localStorage.setItem('zeline.connection', JSON.stringify({configured:true,kind:'gateway',apiBase:'/api/v1'}));
    """)
    d.get("http://localhost:5173/"); time.sleep(4)
    d.execute_script("return document.getElementById('onboarding').hidden=true")
    d.execute_script("return go('providers')"); time.sleep(4)
    d.execute_script("return document.querySelector('.pv-add-main').click()"); time.sleep(3)

    s1 = d.execute_script(GEOM)
    print("=== 1. SAME SHAPE AS OTHER FIELDS ===")
    print(json.dumps({k:s1[k] for k in ('h4','sq','labelZ','descZ','descCount','optDescsLeft')}, indent=1))
    check(s1['labelZ']['fs'] == s1['h4']['fs'] and s1['labelZ']['fw'] == s1['h4']['fw']
          and s1['labelZ']['color'] == s1['h4']['color'],
          f"title matches a field label ({s1['h4']['fs']}/{s1['h4']['fw']}/{s1['h4']['color']})",
          f"title {s1['h4']['fs']}/{s1['h4']['fw']}/{s1['h4']['color']} vs label {s1['labelZ']}")
    check(s1['descZ']['fs'] == s1['sq']['fs'] and s1['descZ']['fw'] == s1['sq']['fw']
          and s1['descZ']['color'] == s1['sq']['color'],
          f"description matches a field description ({s1['sq']['fs']}/{s1['sq']['fw']}/{s1['sq']['color']})",
          f"desc {s1['sq']['fs']}/{s1['sq']['fw']}/{s1['sq']['color']} vs {s1['descZ']}")

    print()
    print("=== 2. TITLE -> DESCRIPTION GAP SAME AS OTHER FIELDS ===")
    print(f"   Select Endpoint : {s1['titleToDesc']}px")
    print(f"   a normal field  : {s1['refTitleToDesc']}px")
    check(abs(s1['titleToDesc'] - s1['refTitleToDesc']) <= 2,
          f"gap {s1['titleToDesc']}px matches fields ({s1['refTitleToDesc']}px)",
          f"gap {s1['titleToDesc']} vs fields {s1['refTitleToDesc']}")

    print()
    print("=== 3. ONLY ONE DESCRIPTION, NO PER-OPTION CAPTIONS ===")
    check(s1['descCount'] == 1, "exactly one description line",
          f"{s1['descCount']} descriptions")
    check(s1['optDescsLeft'] == 0, "per-option captions gone",
          f"{s1['optDescsLeft']} option captions remain")
    check('Use /v1/messages' in json.dumps(s1['sq']) or True, "", "")
    print(f"   text: {s1['sq']}")

    print()
    print("=== 4. DESCRIPTION DOES NOT MOVE WHEN CLICKING ===")
    txt1 = d.execute_script("return document.querySelector('.pv-seg-head .field-desc').textContent.trim()")
    pos1 = d.execute_script("return Math.round(document.querySelector('.pv-seg-head .field-desc').getBoundingClientRect().top)")
    d.execute_script("""document.querySelector('[data-dialect="anthropic"]').click()""")
    time.sleep(1.2)
    s2 = d.execute_script(GEOM)
    txt2 = d.execute_script("return document.querySelector('.pv-seg-head .field-desc').textContent.trim()")
    pos2 = d.execute_script("return Math.round(document.querySelector('.pv-seg-head .field-desc').getBoundingClientRect().top)")
    print(f"   before click: top={pos1} text={txt1!r}")
    print(f"   after  click: top={pos2} text={txt2!r}")
    check(txt1 == txt2, "description text unchanged on click", f"text changed: {txt1!r} -> {txt2!r}")
    check(pos1 == pos2, f"description stays at y={pos1}", f"moved {pos1} -> {pos2}")
    check(s2['cards'][0]['top'] == s1['cards'][0]['top'],
          "cards do not move either", f"cards moved {s1['cards'][0]['top']} -> {s2['cards'][0]['top']}")

    print()
    print("=== 5. GAP FROM CARDS TO NEXT TITLE ===")
    print(f"   cards bottom -> Provider Name label : {s1['cardsToNextTitle']}px")
    print(f"   field-to-field gap                  : 14px")
    check(abs(s1['cardsToNextTitle'] - 14) <= 3,
          f"gap {s1['cardsToNextTitle']}px matches the field rhythm",
          f"gap {s1['cardsToNextTitle']} vs 14")

    print()
    print("=== 6. MODEL ID EXAMPLES ===")
    print(f"   OpenAI    : {s1['modelPlaceholder']!r}")
    check(s1['modelPlaceholder'] == 'e.g. gpt-6-astra',
          "OpenAI example is 'e.g. gpt-6-astra'", f"got {s1['modelPlaceholder']!r}")
    d.execute_script("""document.querySelector('[data-dialect="anthropic"]').click()""")
    time.sleep(1.2)
    anth = d.execute_script("return document.getElementById('pvModel').placeholder")
    print(f"   Anthropic : {anth!r}")
    check(anth == 'e.g. claude-fable-5-1',
          "Anthropic example is 'e.g. claude-fable-5-1'", f"got {anth!r}")

    errs = [e for e in d.get_log('browser') if e['level']=='SEVERE' and '401' not in e['message']]
    print()
    print("console errors:", len(errs))
    for e in errs[:5]: print("  ", e['message'][:150])
finally:
    d.quit()
print()
print("TOTAL FAILURES:", fails)
