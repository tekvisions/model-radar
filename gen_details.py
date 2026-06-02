#!/usr/bin/env python3
"""Standalone detail-page generator.

Reads the EXISTING data.json (no network fetch) and regenerates:
  - m/<slug>/index.html for every model
  - sitemap.xml (homepage + every /m/<slug>)
  - llms.txt
Reuses the exact generators in build_data.py so the hub and detail pages
stay byte-for-byte consistent.

Usage: python3 gen_details.py
"""
import json, os, sys

import build_data as bd

HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    path = os.path.join(HERE, "data.json")
    if not os.path.exists(path):
        print("data.json not found — run build_data.py first", file=sys.stderr)
        return 1
    data = json.load(open(path))
    models = data.get("models") or []
    if not models:
        print("data.json has no models", file=sys.stderr)
        return 1

    slugs = bd.generate_details(data)
    bd.write_sitemap(slugs, data.get("generated_date"))
    bd.write_llms(data)
    # persist slugs back into data.json so app.js/JSON-LD and pages agree
    json.dump(data, open(path, "w"), indent=2)

    print("generated %d detail pages under m/" % len(slugs), file=sys.stderr)
    print("wrote sitemap.xml (%d urls) + llms.txt" % (len(slugs) + 1), file=sys.stderr)
    print("sample: m/%s/index.html" % slugs[0], file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
