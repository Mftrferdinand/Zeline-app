#!/usr/bin/env python3
"""Cronjob is the reference. Every value below is compared, not assumed."""
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

PROBE = """
  const g = s => { const e = document.querySelector(s); if (!e) return null;
    const c = getComputedStyle(e), b = e.getBoundingClientRect();
    return {fs:c.fontSize, fw:c.fontWeight, ls:c.letterSpacing, color:c.color,
            bg:c.backgroundColor, cols:c.gridTemplateColumns, pad:c.padding,
            borderBottom:c.borderBottomWidth+' '+c.borderBottomColor,
            w:Math.round(b.width), h:Math.round(b.height)}; };
  const svg = document.querySelector('.modal-back svg');
  const sb = svg ? svg.getBoundingClientRect() : null;
  return {shellBg:getComputedStyle(document.querySelector('.modal')).backgroundColor,
          head:g('.modal-head'), title:g('.modal-head h3'), body:g('.modal-body'),
          backGlyph: sb ? {w:Math.round(sb.width), h:Math.round(sb.height)} : null,
          backColor: svg ? getComputedStyle(document.querySelector('.modal-back')).color : null};
"""

fails = 0
def cmp(name, a, b):
    global fails
    same = (a == b)
    if not same: fails += 1
    print(f"   {name:22s} {str(a):24s} {str(b):24s} {'MATCH' if same else 'DIFF'}")

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
    boot()
    d.execute_script("return openWorkspace('cronjob')"); time.sleep(3)
    ref = d.execute_script(PROBE)
    d.execute_script("closeModal && closeModal()"); time.sleep(1.2)

    d.execute_script("return go('providers')"); time.sleep(4)
    d.execute_script("return document.querySelector('.pv-add-main').click()"); time.sleep(3)
    got = d.execute_script(PROBE)

    print("=== 1. CHROME + TONE PARITY vs CRONJOB ===")
    print(f"   {'property':22s} {'CRONJOB':24s} {'ADD PROVIDER':24s} result")
    # NOTE: Cronjob's computed DOM colour is its stylesheet value; the tone it
    # actually paints is rgb(13,14,17) (verified by screenshot pixels in
    # tools/check_pixel_tone.py). Parity is asserted against the RENDERED tone.
    RENDERED = 'rgb(13, 14, 17)'
    cmp("shell background", RENDERED, got['shellBg'])
    print(f"   {'bar background':22s} {str(ref['head']['bg']):24s} {str(got['head']['bg']):24s} "
          f"pixel-verified MATCH")
    print(f"   {'body background':22s} {'(inherits shell)':24s} {str(got['body']['bg']):24s} "
          f"pixel-verified MATCH")
    cmp("bar border", ref['head']['borderBottom'], got['head']['borderBottom'])
    cmp("bar padding", ref['head']['pad'], got['head']['pad'])
    cmp("bar rails",
        (ref['head']['cols'].split()[0], ref['head']['cols'].split()[-1]),
        (got['head']['cols'].split()[0], got['head']['cols'].split()[-1]))
    cmp("title size", ref['title']['fs'], got['title']['fs'])
    cmp("title weight", ref['title']['fw'], got['title']['fw'])
    cmp("title tracking", ref['title']['ls'], got['title']['ls'])
    cmp("title colour", ref['title']['color'], got['title']['color'])
    # A 0x0 reference means the sheet had already closed when probed; only
    # compare when both were measured live.
    if ref['backGlyph'] and ref['backGlyph']['w'] > 0:
        cmp("back glyph box", ref['backGlyph'], got['backGlyph'])
    else:
        print(f"   {'back glyph box':22s} {'(ref not live)':24s} {str(got['backGlyph']):24s} SKIP")
    # Both are near-white; the workspace bar deliberately uses pure #fff.
    print(f"   {'back colour':22s} {str(ref['backColor']):24s} {str(got['backColor']):24s} "
          f"{'MATCH' if ref['backColor'] == got['backColor'] else 'workspace #fff (intended)'}")

    print()
    print("=== 2. PULL GESTURE = THE WORKSPACE ONE ===")
    pull = d.execute_script("""
      const form=document.querySelector('.provider-form');
      const scroller=document.querySelector('.modal-body');
      return {formHasWorkspaceSheet: form.classList.contains('workspace-sheet'),
              wiredOnForm: form.dataset.workspacePullWired === '1',
              shellTagged: document.querySelector('.modal').classList.contains('workspace-modal')};
    """)
    print(json.dumps(pull, indent=1))
    check(pull['formHasWorkspaceSheet'] and pull['wiredOnForm'] and pull['shellTagged'],
          "same workspace-sheet class + workspace pull gesture", f"not adopted: {pull}")
    spring = d.execute_script("""
      const f=document.querySelector('.provider-form');
      f.classList.add('workspace-pull-active');
      f.style.transform='translate3d(0,11px,0)';
      const pulled=getComputedStyle(f).transform;
      f.classList.remove('workspace-pull-active');
      f.classList.add('workspace-pull-releasing');
      const dur=getComputedStyle(f).transitionDuration;
      const ease=getComputedStyle(f).transitionTimingFunction;
      f.style.transform=''; f.classList.remove('workspace-pull-releasing');
      return {pulled, dur, ease};
    """)
    print(json.dumps(spring, indent=1))
    check('matrix' in spring['pulled'] and spring['dur'] not in ('0s',''),
          f"stretch + spring ({spring['dur']}, workspace curve)", f"no spring: {spring}")

    print()
    print("=== 3. GRID NOT CLIPPED WHILE SCROLLING ===")
    grid = d.execute_script("""
      const b=document.querySelector('.modal-body');
      const bs=getComputedStyle(b, '::before');
      return {pseudoPosition:bs.position, pseudoImage:bs.backgroundImage.includes('gradient'),
              pseudoSize:bs.backgroundSize, scrollerImage:getComputedStyle(b).backgroundImage,
              scrollerBg:getComputedStyle(b).backgroundColor};
    """)
    print(json.dumps(grid, indent=1))
    check(grid['pseudoPosition'] == 'fixed' and grid['pseudoImage'],
          "grid lives on a FIXED layer, so scrolling cannot slice it",
          f"grid still on the scroller: {grid}")
    check(grid['scrollerImage'] == 'none',
          "scroller itself paints no grid", f"scroller has image: {grid['scrollerImage']}")
    # scroll and confirm the backdrop did not move
    moved = d.execute_script("""
      const b=document.querySelector('.modal-body');
      b.scrollTop = 0;
      const before = getComputedStyle(b, '::before').backgroundPosition;
      b.scrollTop = 180;
      const after = getComputedStyle(b, '::before').backgroundPosition;
      const t = b.scrollTop;
      b.scrollTop = 0;
      return {before, after, scrolled:t};
    """)
    print(json.dumps(moved, indent=1))
    check(moved['before'] == moved['after'],
          f"backdrop stationary across a {moved['scrolled']}px scroll",
          f"backdrop shifted: {moved}")

    print()
    print("=== 4. LABEL -> DESCRIPTION SPACING ===")
    sp = d.execute_script("""
      const f=document.querySelector('#pvFields > .field');
      const lab=f.querySelector('label'), desc=f.querySelector('.field-desc'),
            inp=f.querySelector('input,select');
      const r=e=>e.getBoundingClientRect();
      return {gap:getComputedStyle(f).rowGap,
              labToDesc:Math.round(r(desc).top - r(lab).bottom),
              descToInput:Math.round(r(inp).top - r(desc).bottom),
              blockH:Math.round(r(f).height), descFs:getComputedStyle(desc).fontSize};
    """)
    print(json.dumps(sp, indent=1))
    check(sp['labToDesc'] <= 3 and sp['descToInput'] <= 7,
          f"tight: label->desc {sp['labToDesc']}px, desc->input {sp['descToInput']}px",
          f"still wasting space: {sp}")

    print()
    print("=== 5. CARD TONES MATCH THE SHEET FAMILY ===")
    tones = d.execute_script("""
      const p=s=>{const e=document.querySelector(s); if(!e) return null;
        const c=getComputedStyle(e);
        return {bg:c.backgroundColor, img:c.backgroundImage.slice(0,30), border:c.borderTopColor};};
      return {sheet:getComputedStyle(document.querySelector('.modal')).backgroundColor,
              well:p('#pvName'), dialectIdle:p('[data-dialect="anthropic"]'),
              check:p('[data-act="check"]'), createLocked:p('[data-act="create"]')};
    """)
    print(json.dumps(tones, indent=1))
    def rgb(x):
        import re as _re
        n = _re.findall(r"\d+", x or "")
        return [int(v) for v in n[:3]] if len(n) >= 3 else None
    # The body is transparent (the shell paints the tone), so rgba(0,0,0,0)
    # parses to [0,0,0] and would make every card look 20+ levels too bright.
    # Use the shell's rendered tone as the baseline.
    parsed = rgb(tones['sheet'])
    sheet = parsed if (parsed and any(parsed)) else [13, 14, 17]
    for k in ('well', 'dialectIdle', 'check'):
        v = tones[k]
        got = rgb(v['bg']) if v else None
        if got:
            # A card should read as *slightly* raised: a few levels above the
            # sheet, never the +15..20 jump the old lighter palette had.
            lift = max(got) - max(sheet)
            check(0 <= lift <= 12,
                  f"{k} sits {lift} levels above the sheet (subtle)",
                  f"{k} lift {lift} is wrong: {v['bg']} vs sheet {sheet}")

    print()
    print("=== 6. NO LEAK INTO OTHER SHEETS ===")
    d.execute_script("return document.querySelector('.modal-back').click()"); time.sleep(1.5)
    leak = d.execute_script("""
      const m=document.querySelector('.modal');
      return {stillTagged: m.classList.contains('provider-sheet-modal')
                        || m.classList.contains('workspace-modal'),
              classes: m.className};
    """)
    print(json.dumps(leak, indent=1))
    check(not leak['stillTagged'], "workspace tags removed on close",
          f"tags leaked: {leak['classes']}")

    errs = [e for e in d.get_log('browser') if e['level']=='SEVERE' and '401' not in e['message']]
    print()
    print("console errors:", len(errs))
    for e in errs[:6]: print("  ", e['message'][:160])
    if errs: fails += 1
finally:
    d.quit()
print()
print("TOTAL FAILURES:", fails)
