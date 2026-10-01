#!/usr/bin/env python3
"""Two catalogue label fixes.

1. grok-cli  : "xAI (SuperGrok)" -> "xAI (Grok) CLI"   (user's naming)
2. cline     : add a tier hint so it is not confused with `clinepass`
   clinepass : same — they are the SAME vendor (api.cline.bot, identical OAuth
               endpoints). The real difference is the account tier:
                 cline     = standard account
                 clinepass = ClinePass subscription (its own id surfaces as a
                             *model* inside cline's model list)
   Both stay as separate cards (they are genuinely different tiers), just
   labelled so the distinction is readable at a glance.

Targeted edit: only `name` is touched on the affected rows. Every other field
and every other row stays byte-identical. Backs up + re-verifies.
"""
import json, os, shutil, sys, time

ROOT = "/data/data/com.termux/files/home/zeline-frontend"
PATH = os.path.join(ROOT, "provider_catalog.json")

RENAMES = {
    "grok-cli":  "xAI (Grok) CLI",
    "cline":     "Cline",
    "clinepass": "ClinePass (Subscription)",
}

def main():
    backup = PATH + ".bak-" + time.strftime("%Y%m%d_%H%M%S")
    shutil.copy(PATH, backup)

    data = json.load(open(PATH, encoding="utf-8"))
    rows = data.get("providers") or []
    before_map = {r["id"]: dict(r) for r in rows}

    changed = []
    for r in rows:
        if r.get("id") in RENAMES and r.get("name") != RENAMES[r["id"]]:
            changed.append((r["id"], r.get("name"), RENAMES[r["id"]]))
            r["name"] = RENAMES[r["id"]]
    data["providers"] = rows
    with open(PATH, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
        fh.write("\n")

    after_map = {r["id"]: r for r in json.load(open(PATH, encoding="utf-8"))["providers"]}

    print(f"backup  : {os.path.basename(backup)}")
    for pid, old, new in changed:
        print(f"renamed : {pid:12s} {old!r} -> {new!r}")
    if not changed:
        print("renamed : nothing to change")

    # every non-name field must be untouched, and no row may appear/disappear
    lost = [i for i in before_map if i not in after_map]
    field_drift = []
    for pid, before in before_map.items():
        after = after_map.get(pid)
        if not after:
            continue
        for k, v in before.items():
            if k == "name":
                continue
            if after.get(k) != v:
                field_drift.append((pid, k, v, after.get(k)))
    count_before, count_after = len(before_map), len(after_map)

    print(f"count   : {count_before} -> {count_after}")
    print(f"rows lost          : {lost or 'NONE'}")
    print(f"non-name field drift: {field_drift or 'NONE'}")

    ok = not lost and not field_drift and count_before == count_after
    print(f"\nRESULT: {'OK' if ok else 'PROBLEM — restore ' + backup}")
    return 0 if ok else 1

if __name__ == "__main__":
    sys.exit(main())
