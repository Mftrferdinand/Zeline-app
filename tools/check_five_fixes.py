#!/usr/bin/env python3
"""Verify the five fixes, with the workspace sheets as the measured reference."""
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

CHROME = """
  const g = s => { const e = document.querySelector(s); if (!e) return null;
    const c = getComputedStyle(e);
    return {fs:c.fontSize, fw:c.fontWeight, ls:c.letterSpacing, color:c.color,
            cols:c.gridTemplateColumns, bg:c.backgroundColor}; };
  const svg = document.querySelector('.modal-back svg');
  return {head:g('.modal-head'), title:g('.modal-head h3'), back:g('.modal-back'),
          backSvg: svg ? getComputedStyle(svg).width : null,
          bodyBg: getComputedStyle(document.querySelector('.modal-body')).backgroundColor};
"""

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
      localStorage.setItem('zeline.agents', JSON.stringify([{id:'vf',name:'verify-agent'}]));
    """)
    d.get("http://localhost:5173/"); time.sleep(4)
    d.execute_script("return document.getElementById('onboarding').hidden=true")

try:
    # -------- reference
    boot()
    d.execute_script("return openWorkspace('project')"); time.sleep(2.5)
    ref = d.execute_script(CHROME)
    print("=== REFERENCE (Project) ===")
    print(json.dumps(ref, indent=1))
    d.execute_script("closeModal && closeModal()"); time.sleep(1)

    # -------- provider screen
    d.execute_script("return go('providers')"); time.sleep(4)
    d.execute_script("return document.querySelector('.pv-add-main').click()"); time.sleep(3)
    got = d.execute_script(CHROME)
    print()
    print("=== ADD PROVIDER ===")
    print(json.dumps(got, indent=1))

    print()
    print("=== 1. CHROME PARITY ===")
    rows = [("title font-size", ref['title']['fs'], got['title']['fs']),
            ("title weight",    ref['title']['fw'], got['title']['fw']),
            ("title tracking",  ref['title']['ls'], got['title']['ls']),
            ("title colour",    ref['title']['color'], got['title']['color']),
            ("back svg",        ref['backSvg'], got['backSvg']),
            # `1fr` resolves to a pixel width, so compare only the fixed rails.
            ("head rails",
             (ref['head']['cols'].split()[0], ref['head']['cols'].split()[-1]),
             (got['head']['cols'].split()[0], got['head']['cols'].split()[-1]))]
    print(f"   {'property':18s} {'reference':26s} {'provider':26s} match")
    for name, a, b in rows:
        same = (a == b)
        if not same: fails += 1
        print(f"   {name:18s} {str(a):26s} {str(b):26s} {'MATCH' if same else 'DIFF'}")

    print()
    print("=== 2. ELASTIC PULL WIRED ===")
    pull = d.execute_script("""
      const b=document.querySelector('.modal-body');
      return {wired: b.dataset.sheetPullWired === '1',
              fnExists: typeof wireSheetPullStretch === 'function'};
    """)
    print(json.dumps(pull, indent=1))
    check(pull['wired'] and pull['fnExists'], "pull gesture wired on the sheet body",
          f"not wired: {pull}")
    # simulate the transform path the gesture writes
    sim = d.execute_script("""
      const b=document.querySelector('.modal-body');
      b.classList.add('sheet-pull-active');
      b.style.transform='translate3d(0,12px,0)';
      const t1=getComputedStyle(b).transform;
      b.classList.remove('sheet-pull-active');
      b.classList.add('sheet-pull-releasing');
      const tr=getComputedStyle(b).transitionDuration;
      b.style.transform=''; b.classList.remove('sheet-pull-releasing');
      return {pulled:t1, releaseTransition:tr};
    """)
    print(json.dumps(sim, indent=1))
    check('matrix' in sim['pulled'] and sim['releaseTransition'] not in ('0s',''),
          f"stretch + spring-back active ({sim['releaseTransition']})", f"no spring: {sim}")

    print()
    print("=== 3. LABEL -> DESC SPACING TIGHT ===")
    sp = d.execute_script("""
      const f=document.querySelector('#pvFields > .field');
      const lab=f.querySelector('label'), desc=f.querySelector('.field-desc'),
            inp=f.querySelector('input,select');
      const r=e=>e.getBoundingClientRect();
      return {fieldGap:getComputedStyle(f).rowGap,
              descMargin:getComputedStyle(desc).margin,
              labToDesc:Math.round(r(desc).top - r(lab).bottom),
              descToInput:Math.round(r(inp).top - r(desc).bottom),
              descFs:getComputedStyle(desc).fontSize};
    """)
    print(json.dumps(sp, indent=1))
    check(sp['labToDesc'] <= 6 and sp['descToInput'] <= 10,
          f"tight: label->desc {sp['labToDesc']}px, desc->input {sp['descToInput']}px",
          f"still loose: {sp}")

    print()
    print("=== 4. WELLS DARKER (near the sheet tone) ===")
    tone = d.execute_script("""
      const b=document.querySelector('.modal-body');
      const i=document.getElementById('pvName');
      const c=getComputedStyle(i);
      const parse=s=>s.match(/\\d+/g)?.slice(0,3).map(Number);
      return {sheet:getComputedStyle(b).backgroundColor,
              well:c.backgroundColor, wellImg:c.backgroundImage,
              sheetRgb:parse(getComputedStyle(b).backgroundColor),
              wellRgb:parse(c.backgroundColor)};
    """)
    print(json.dumps(tone, indent=1))
    # well must be a flat colour (no gradient) and within ~14 levels of the sheet
    delta = None
    if tone['wellRgb'] and tone['sheetRgb']:
        delta = max(abs(a-b) for a, b in zip(tone['wellRgb'], tone['sheetRgb']))
    check(tone['wellImg'] == 'none' and delta is not None and delta <= 16,
          f"well is flat and close to the sheet (delta {delta})",
          f"well too bright / still gradient: img={tone['wellImg']} delta={delta}")

    print()
    print("=== 5. TWO SEPARATE CARDS, ONE ROW, WITH CAPTIONS ===")
    cards = d.execute_script("""
      const seg=document.querySelector('.pv-seg');
      const bs=[...seg.querySelectorAll('.pv-seg-btn')];
      const c=getComputedStyle(seg);
      return {segBg:c.backgroundColor, segBorder:c.borderTopWidth, segPad:c.padding,
              gap:c.columnGap, cols:c.gridTemplateColumns,
              cards:bs.map(b=>{const bb=b.getBoundingClientRect();
                const bc=getComputedStyle(b);
                const sm=b.querySelector('small');
                return {label:b.querySelector('strong')?.textContent.trim(),
                        caption:sm?sm.textContent.trim():null,
                        captionShown: sm ? getComputedStyle(sm).display !== 'none' : false,
                        top:Math.round(bb.top), left:Math.round(bb.left),
                        w:Math.round(bb.width), h:Math.round(bb.height),
                        radius:bc.borderRadius, border:bc.borderTopWidth};})};
    """)
    print(json.dumps(cards, indent=1))
    cs = cards['cards']
    check(len(cs) == 2, "two cards", f"{len(cs)} cards")
    check(cs[0]['top'] == cs[1]['top'], f"same row (y={cs[0]['top']})",
          f"not aligned: {cs[0]['top']} vs {cs[1]['top']}")
    check(cs[0]['left'] < cs[1]['left'], "side by side", "not side by side")
    check(all(c['captionShown'] and c['caption'] for c in cs),
          f"captions visible: {[c['caption'] for c in cs]}", "captions missing")
    check(cards['segBg'] == 'rgba(0, 0, 0, 0)' and cards['segPad'] == '0px',
          "wrapper is transparent — cards are genuinely separate",
          f"wrapper still a fused track: bg={cards['segBg']} pad={cards['segPad']}")
    check(all(c['border'] != '0px' for c in cs), "each card has its own border",
          "cards have no border")

    print()
    print("=== 6. ACTION CARDS + CREATE GATE INTACT ===")
    acts = d.execute_script("""
      const g=s=>{const b=document.querySelector(s); if(!b) return null;
        return {label:b.textContent.trim(), disabled:b.disabled,
                h:Math.round(b.getBoundingClientRect().height)};};
      return {check:g('[data-act="check"]'), create:g('[data-act="create"]'),
              cancel:g('[data-act="cancel"]')};
    """)
    print(json.dumps(acts, indent=1))
    check(all(acts[k] for k in ('check','create','cancel')) and acts['create']['disabled'],
          "Check / Create / Cancel present, Create locked", f"actions off: {acts}")

    errs = [e for e in d.get_log('browser') if e['level']=='SEVERE' and '401' not in e['message']]
    print()
    print("console errors:", len(errs))
    for e in errs[:5]: print("  ", e['message'][:150])
    if errs: fails += 1
finally:
    d.quit()
print()
print("TOTAL FAILURES:", fails)
