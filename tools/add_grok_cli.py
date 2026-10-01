#!/usr/bin/env python3
"""Add `grok-cli` to provider_catalog.json.

Source of truth: 9Router v0.5.55, `app/.next-cli-build/server/chunks/4953.js`.
  id        : grok-cli
  name      : "Grok CLI (Grok Build)"
  protocol  : openai-responses / chat via cli-chat-proxy.grok.com/v1
  auth      : oauth ONLY (device code — auth.x.ai/oauth2/device/code)
  credits   : Grok Build subscription (signup https://grok.com/supergrok)

`grok-web` is deliberately NOT added: its auth is a pasted `sso=` browser
cookie, which this catalog's auth whitelist (api_key|oauth|none) cannot express —
it would be silently coerced to api_key and mislead the user.

Add-only: existing rows are left untouched; backs up first; re-verifies after.
"""
import json, os, shutil, sys, time

ROOT = "/data/data/com.termux/files/home/zeline-frontend"
PATH = os.path.join(ROOT, "provider_catalog.json")

ROW = {
    "id": "grok-cli",
    "name": "xAI (SuperGrok)",
    "protocol": "openai",
    "base_url": "https://cli-chat-proxy.grok.com/v1",
    "auth": ["oauth"],
    "category": "oauth",
    "group": "oauth",
}

def main():
    backup = PATH + ".bak-" + time.strftime("%Y%m%d_%H%M%S")
    shutil.copy(PATH, backup)
    before = json.load(open(PATH, encoding="utf-8"))
    rows = before.get("providers") or []
    before_ids = [r.get("id") for r in rows]
    before_map = {r["id"]: r for r in rows}

    if ROW["id"] in before_map:
        print(f"{ROW['id']} already present — nothing to do (backup: {os.path.basename(backup)})")
        os.remove(backup)
        return 0

    rows.append(ROW)
    before["providers"] = rows
    with open(PATH, "w", encoding="utf-8") as fh:
        json.dump(before, fh, indent=2, ensure_ascii=False)
        fh.write("\n")

    after = json.load(open(PATH, encoding="utf-8"))["providers"]
    after_ids = [r.get("id") for r in after]
    after_map = {r["id"]: r for r in after}

    lost = [i for i in before_ids if i not in after_map]
    dupes = [i for i in set(after_ids) if after_ids.count(i) > 1]
    changed = [i for i in before_ids
               if json.dumps(before_map[i], sort_keys=True)
               != json.dumps(after_map[i], sort_keys=True)]

    print(f"backup        : {os.path.basename(backup)}")
    print(f"added         : {ROW['id']}  ({ROW['name']})")
    print(f"count         : {len(before_ids)} -> {len(after_ids)}")
    print(f"rows lost     : {lost or 'NONE'}")
    print(f"rows modified : {changed or 'NONE'}")
    print(f"duplicate ids : {dupes or 'none'}")

    ok = not lost and not changed and not dupes
    print(f"\nRESULT: {'OK' if ok else 'PROBLEM — restore ' + backup}")
    return 0 if ok else 1

if __name__ == "__main__":
    sys.exit(main())
