#!/usr/bin/env python3
"""Add the 9 missing providers to provider_catalog.json.

Every base_url / auth mode here was read out of the 9Router v0.5.55 source
(`app/.next-cli-build/server/chunks/4953.js`) — not typed from memory. The
catalog is what `provider_presets()` in server.py serves at
/api/v1/providers/presets, which paints the Add-Provider dropdown.

Scope: ADD-ONLY. The existing 32 rows (including `xai`) are left byte-identical;
this script only appends rows whose id is not already present. It backs the file
up first and re-parses afterwards to prove nothing was mangled.
"""
import json, os, shutil, sys, time

ROOT = "/data/data/com.termux/files/home/zeline-frontend"
PATH = os.path.join(ROOT, "provider_catalog.json")

# id, name, protocol, base_url, auth[], category, group
NEW = [
    ("antigravity", "Antigravity", "openai",
     "https://cloudcode-pa.googleapis.com/v1internal",
     ["oauth"], "oauth", "oauth"),
    ("gemini-cli", "Gemini CLI", "openai",
     "https://cloudcode-pa.googleapis.com/v1internal",
     ["oauth"], "oauth", "oauth"),
    ("kiro", "Kiro AI", "openai",
     "https://runtime.us-east-1.kiro.dev/generateAssistantResponse",
     ["oauth"], "oauth", "oauth"),
    ("cursor", "Cursor IDE", "openai",
     "https://api2.cursor.sh",
     ["oauth"], "oauth", "oauth"),
    ("qoder", "Qoder", "openai",
     "https://api3.qoder.sh/algo/api/v2/service/pro/sse/agent_chat_generation",
     ["oauth", "api_key"], "oauth", "oauth"),
    ("gemini", "Gemini", "openai",
     "https://generativelanguage.googleapis.com/v1beta/openai",
     ["api_key"], "apikey", "apikey"),
    ("mistral", "Mistral", "openai",
     "https://api.mistral.ai/v1",
     ["api_key"], "apikey", "apikey"),
    ("perplexity", "Perplexity", "openai",
     "https://api.perplexity.ai",
     ["api_key"], "apikey", "apikey"),
    ("perplexity-agent", "Perplexity Agent", "openai",
     "https://api.perplexity.ai/v1",
     ["api_key"], "apikey", "apikey"),
]

def main():
    backup = PATH + ".bak-" + time.strftime("%Y%m%d_%H%M%S")
    shutil.copy(PATH, backup)

    before_raw = open(PATH, encoding="utf-8").read()
    data = json.loads(before_raw)
    rows = data.get("providers") or []
    before_ids = [r.get("id") for r in rows]
    before_set = set(before_ids)

    added, skipped = [], []
    for pid, name, proto, url, auth, cat, grp in NEW:
        if pid in before_set:
            skipped.append(pid); continue
        rows.append({"id": pid, "name": name, "protocol": proto,
                     "base_url": url, "auth": auth, "category": cat, "group": grp})
        added.append(pid)

    data["providers"] = rows
    with open(PATH, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
        fh.write("\n")

    # ── prove it ───────────────────────────────────────────────────────────
    after = json.load(open(PATH, encoding="utf-8"))["providers"]
    after_ids = [r.get("id") for r in after]
    after_set = set(after_ids)

    print(f"backup      : {os.path.basename(backup)}")
    print(f"added       : {added}")
    print(f"skipped     : {skipped or 'none'}")
    print(f"count       : {len(before_ids)} -> {len(after_ids)}")

    # every pre-existing row must still be present, unchanged
    lost = [i for i in before_ids if i not in after_set]
    dupes = [i for i in after_set if after_ids.count(i) > 1]
    print(f"pre-existing rows kept : {'YES' if not lost else 'LOST ' + str(lost)}")
    print(f"duplicate ids          : {dupes or 'none'}")

    # and the untouched rows must be byte-identical to before
    before_map = {r["id"]: r for r in json.loads(before_raw)["providers"]}
    changed = [i for i in before_set
               if json.dumps(before_map[i], sort_keys=True)
               != json.dumps(next(r for r in after if r["id"] == i), sort_keys=True)]
    print(f"pre-existing rows modified : {changed or 'NONE'}")

    ok = not lost and not dupes and not changed
    print(f"\nRESULT: {'OK' if ok else 'PROBLEM — restore from ' + backup}")
    return 0 if ok else 1

if __name__ == "__main__":
    sys.exit(main())
