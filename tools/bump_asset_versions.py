#!/usr/bin/env python3
"""Bump the cache-busting `?v=` on index.html for files that just changed.

index.html references its assets with `?v=N`:

    <link rel="stylesheet" href="style.css?v=387">
    <script src="app3.js?v=354"></script>

The dev server sends `Cache-Control: no-store` for these, but a *mobile*
browser will still serve from its memory/disk cache for the life of the tab and
often across reloads. The `?v=` query is what actually forces a refetch — so if
it is not bumped after an edit, the phone keeps rendering the OLD file no matter
how correct the source is.

That is exactly what happened with the Add-Provider form redesign (v383): the
CSS was correct and served correctly, but `style.css?v=386` and `app3.js?v=353`
had not moved, so the device kept showing the pre-redesign form.

Usage:
    python3 tools/bump_asset_versions.py                 # bump style.css + all app*.js
    python3 tools/bump_asset_versions.py style.css app3.js
    python3 tools/bump_asset_versions.py --dry-run

Run this after ANY edit to a file referenced by index.html.
"""
import re
import sys
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
INDEX = ROOT / "index.html"

# Every asset index.html loads with a cache-busting query.
ASSETS = ["style.css", "icons.js", "app1.js", "app2.js",
          "app3.js", "app4.js", "app5.js"]


def bump(targets, dry=False):
    html = INDEX.read_text(encoding="utf-8")
    report = []
    for name in targets:
        # Match `name?v=<digits>` wherever it appears in index.html.
        pattern = re.compile(r"(" + re.escape(name) + r"\?v=)(\d+)")

        def sub(m):
            old = int(m.group(2))
            new = old + 1
            report.append((name, old, new))
            return f"{m.group(1)}{new}"

        html, n = pattern.subn(sub, html)
        if n == 0:
            report.append((name, None, None))

    if not dry and report:
        INDEX.write_text(html, encoding="utf-8")

    width = max(len(n) for n, _, _ in report) if report else 10
    for name, old, new in report:
        if old is None:
            print(f"  {name:<{width}}  TIDAK ADA di index.html (dilewati)")
        else:
            tag = " (dry-run)" if dry else ""
            print(f"  {name:<{width}}  v{old} -> v{new}{tag}")
    return 0


def main():
    argv = [a for a in sys.argv[1:] if a != "--dry-run"]
    dry = "--dry-run" in sys.argv
    targets = argv or ASSETS
    unknown = [t for t in targets if t not in ASSETS]
    if unknown:
        print(f"nama file tidak dikenal: {unknown}")
        print(f"yang dikenal: {ASSETS}")
        return 1
    print(f"{'DRY-RUN ' if dry else ''}bump cache-bust di index.html:")
    rc = bump(targets, dry)
    if not dry:
        print("\nSelesai. Reload browser HP sekali — versi baru akan dipakai.")
    return rc


if __name__ == "__main__":
    sys.exit(main())
