#!/usr/bin/env python3
"""Remove the duplicate `perplexity-agent` entry from provider_catalog.json.

`perplexity-agent` was added alongside `perplexity` in the v382 batch. It is the
same vendor and the same auth (api_key) — only the API surface differs
(/v1/responses vs /chat/completions) — so the user sees two near-identical
Perplexity cards. Keeping exactly one: `perplexity`.

Remove-only: deletes just this row, leaves every other row byte-identical, backs
up first, and re-verifies afterwards.
"""
import json, os, shutil, sys, time

ROOT = "/data/data/com.termux/files/home/zeline-frontend"
PATH = os.path.join(ROOT, "provider_catalog.json")
TARGET = "perplexity-agent"

def main():
    backup = PATH + ".bak-" + time.strftime("%Y%m%d_%H%M%S")
    shutil.copy(PATH, backup)

    data = json.load(open(PATH, encoding="utf-8"))
    rows = data.get("providers") or []
    before_ids = [r.get("id") for r in rows]
    before_map = {r["id"]: r for r in rows}

    if TARGET not in before_map:
        print(f"{TARGET} not present — nothing to do")
        os.remove(backup)
        return 0

    kept = [r for r in rows if r.get("id") != TARGET]
    data["providers"] = kept
    with open(PATH, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
        fh.write("\n")

    after = json.load(open(PATH, encoding="utf-8"))["providers"]
    after_map = {r["id"]: r for r in after}
    after_ids = [r["id"] for r in after]

    removed = [i for i in before_ids if i not in after_map]
    changed = [i for i in before_ids
               if i in after_map and json.dumps(before_map[i], sort_keys=True)
               != json.dumps(after_map[i], sort_keys=True)]
    dupes = [i for i in set(after_ids) if after_ids.count(i) > 1]

    print(f"backup        : {os.path.basename(backup)}")
    print(f"removed       : {removed}")
    print(f"count         : {len(before_ids)} -> {len(after_ids)}")
    print(f"rows modified : {changed or 'NONE'}")
    print(f"duplicate ids : {dupes or 'none'}")
    print(f"perplexity kept: {'yes' if 'perplexity' in after_map else 'NO — PROBLEM'}")
    print(f"grok-cli kept  : {'yes' if 'grok-cli' in after_map else 'MISSING'}")

    ok = removed == [TARGET] and not changed and not dupes and "perplexity" in after_map
    print(f"\nRESULT: {'OK' if ok else 'PROBLEM — restore ' + backup}")
    return 0 if ok else 1

if __name__ == "__main__":
    sys.exit(main())
