#!/usr/bin/env python3
"""Verify the new endpoint-picker layout."""
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

    # reference gap: bar -> section title on Providers
    d.execute_script("return go('providers')"); time.sleep(4)
    ref = d.execute_script("""
      const r=e=>e.getBoundingClientRect();
      const bar=document.querySelector('.pv-appbar');
      const h3=document.querySelector('.pv-section-head h3');
      return {gap:Math.round(r(h3).top-r(bar).bottom),
              h3Fs:getComputedStyle(h3).fontSize, h3Fw:getComputedStyle(h3).fontWeight,
              h3Color:getComputedStyle(h3).color};
    """)

    d.execute_script("return document.querySelector('.pv-add-main').click()"); time.sleep(3)
    got = d.execute_script("""
      const r=e=>e.getBoundingClientRect();
      const bar=document.querySelector('.modal-head');
      const h4=document.querySelector('.pv-seg-head h4');
      const opts=[...document.querySelectorAll('.pv-opt')].map(o=>{
        const desc=o.querySelector('.pv-opt-desc'), card=o.querySelector('.pv-seg-btn');
        const dc=getComputedStyle(desc), cc=getComputedStyle(card);
        return {desc:desc.textContent.trim(), descFs:dc.fontSize, descFw:dc.fontWeight,
                descColor:dc.color,
                card:card.querySelector('strong').textContent.trim(),
                cardH:Math.round(r(card).height), cardTop:Math.round(r(card).top),
                cardLeft:Math.round(r(card).left), cardW:Math.round(r(card).width),
                descTop:Math.round(r(desc).top), descBottom:Math.round(r(desc).bottom),
                descAboveCard: r(desc).bottom <= r(card).top,
                descToCard: Math.round(r(card).top - r(desc).bottom),
                insideCard: !!card.querySelector('small')};
      });
      const fields=[...document.querySelectorAll('#pvFields > .field')];
      const firstField=fields[0];
      const cards=[...document.querySelectorAll('.pv-seg-btn')];
      return {
        title: document.getElementById('modalTitle').textContent.trim(),
        barBottom: Math.round(r(bar).bottom),
        h4: h4.textContent.trim(), h4Fs:getComputedStyle(h4).fontSize,
        h4Fw:getComputedStyle(h4).fontWeight, h4Color:getComputedStyle(h4).color,
        gapBarToH4: Math.round(r(h4).top - r(bar).bottom),
        opts,
        cardHeights: cards.map(c=>Math.round(r(c).height)),
        cardWidths: cards.map(c=>Math.round(r(c).width)),
        cardTops: cards.map(c=>Math.round(r(c).top)),
        gapCardsToFirstField: firstField
          ? Math.round(r(firstField).top - Math.max(...cards.map(c=>r(c).bottom))) : null
      };
    """)
    print("=== LAYOUT ===")
    print(json.dumps(got, indent=1))
    print()

    print("=== 1. ONE TITLE ===")
    check(got['title'] == 'Custom Endpoint', "title is 'Custom Endpoint'", f"title: {got['title']!r}")

    print()
    print("=== 2. 'Select Endpoint' + GAP vs PROVIDERS ===")
    print(f"   providers gap={ref['gap']}px   add-provider gap={got['gapBarToH4']}px")
    check(got['h4'] == 'Select Endpoint', "heading is 'Select Endpoint'", f"h4: {got['h4']!r}")
    check(abs(got['gapBarToH4'] - ref['gap']) <= 2,
          f"gap {got['gapBarToH4']}px matches Providers {ref['gap']}px",
          f"gap {got['gapBarToH4']} vs Providers {ref['gap']}")
    check(got['h4Fs'] == ref['h3Fs'] and got['h4Fw'] == ref['h3Fw'] and got['h4Color'] == ref['h3Color'],
          f"heading type matches Providers ({ref['h3Fs']}/{ref['h3Fw']})",
          f"heading {got['h4Fs']}/{got['h4Fw']}/{got['h4Color']} vs {ref['h3Fs']}/{ref['h3Fw']}/{ref['h3Color']}")

    print()
    print("=== 3. DESCRIPTION ABOVE CARD, NOT INSIDE ===")
    for o_ in got['opts']:
        print(f"   {o_['desc']!r}")
        print(f"      -> card {o_['card']!r}")
    check(all(o['descAboveCard'] for o in got['opts']),
          "both descriptions sit above their card",
          f"descriptions misplaced: {[o['descAboveCard'] for o in got['opts']]}")
    check(not any(o['insideCard'] for o in got['opts']),
          "no caption left inside a card", "a card still contains its caption")
    caps = [o['desc'] for o in got['opts']]
    check(caps == ['Use /v1/messages', 'Use /v1/chat/completions or /v1/responses'],
          "descriptions exact", f"descriptions: {caps}")

    print()
    print("=== 4. CARDS EQUAL SIZE ===")
    check(len(set(got['cardHeights'])) == 1, f"equal heights {got['cardHeights']}",
          f"heights differ: {got['cardHeights']}")
    check(len(set(got['cardWidths'])) == 1, f"equal widths {got['cardWidths']}",
          f"widths differ: {got['cardWidths']}")
    check(len(set(got['cardTops'])) == 1, f"aligned on one row (y={got['cardTops'][0]})",
          f"tops differ: {got['cardTops']}")

    print()
    print("=== 5. DESCRIPTION TO CARD SPACING ===")
    for o_ in got['opts']:
        print(f"   {o_['descToCard']}px between caption and card")
    check(all(o['descToCard'] >= 0 for o in got['opts']),
          "captions do not collide with cards",
          f"negative gap: {[o['descToCard'] for o in got['opts']]}")

    print()
    print("=== 6. SWITCHING STILL WORKS ===")
    d.execute_script("""document.querySelector('[data-dialect="anthropic"]').click()""")
    time.sleep(1.2)
    sw = d.execute_script("""
      const a=[...document.querySelectorAll('.pv-seg-btn')].find(b=>b.classList.contains('is-active'));
      const f=[...document.querySelectorAll('#pvFields > .field')]
        .map(e=>(e.querySelector('label')?.textContent||'').replace(' *','').trim());
      return {active:a?a.dataset.dialect:null, title:document.getElementById('modalTitle').textContent.trim(),
              fields:f, protocol:document.getElementById('pvProtocol').value};
    """)
    print(json.dumps(sw, indent=1))
    check(sw['active'] == 'anthropic', "Anthropic becomes active", f"active: {sw['active']}")
    check(sw['title'] == 'Custom Endpoint', "title stays 'Custom Endpoint' after switching",
          f"title changed to {sw['title']!r}")
    check('API Type' not in sw['fields'], "Anthropic form drops API Type", f"fields: {sw['fields']}")

    errs = [e for e in d.get_log('browser') if e['level']=='SEVERE' and '401' not in e['message']]
    print()
    print("console errors:", len(errs))
    for e in errs[:5]: print("  ", e['message'][:150])
finally:
    d.quit()
print()
print("TOTAL FAILURES:", fails)
