#!/usr/bin/env python3
"""One-time backfill: reconstruct each model's `rank_history` from the daily data.json
snapshots already committed to git, then write it back into the live data.json.

The movement-tracking feature persists rank_history going forward, but the radar has
been refreshing daily for days already — those snapshots are sitting in git history.
This mines them so position movement (▲/▼) is real and visible immediately, instead of
waiting days for the series to fill in from scratch.

Keyed on the stable model id (`m["id"]`, e.g. "nvidia/LocateAnything-3B"). Each point
is (date, rank, score) where score is the model's trending score (the primary metric
the radar is sorted by). Older snapshots may lack a `rank` field — if so, rank is
derived from the model's position in that snapshot's `models` list (it's already
trending-sorted, so list order == rank).

Run from the repo dir:  python3 backfill_history.py
Idempotent: rebuilds rank_history purely from git + merges into the current file.
After running, build_data.py reads this as prior history and extends it with today.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data.json")


def _git(*args) -> str:
    return subprocess.run(["git", "-C", HERE, *args], capture_output=True, text=True).stdout


def _snapshots() -> list[dict]:
    """Every committed revision of data.json, oldest→newest, parsed."""
    shas = _git("log", "--format=%H", "--reverse", "--", "data.json").split()
    out = []
    for sha in shas:
        raw = _git("show", f"{sha}:data.json")
        if not raw.strip():
            continue
        try:
            out.append(json.loads(raw))
        except json.JSONDecodeError:
            continue
    return out


def main() -> int:
    if not os.path.exists(DATA):
        print("no data.json — run build_data.py first", file=sys.stderr)
        return 1
    cur = json.load(open(DATA))

    snaps = _snapshots()

    # id -> {date: {date, rank, score}}  (dict keyed by date dedupes same-day re-runs)
    hist: dict[str, dict] = {}
    for snap in snaps:
        date = snap.get("generated_date") or (snap.get("generated_at") or "")[:10]
        if not date:
            continue
        models = snap.get("models", [])
        for pos, r in enumerate(models):
            key = r.get("id")
            if not key:
                continue
            # prefer the snapshot's own rank; fall back to 1-based list position
            rank = r.get("rank")
            if not isinstance(rank, int):
                rank = pos + 1
            # primary score = trending; older snapshots have always carried it
            score = r.get("trending")
            if not isinstance(score, int):
                try:
                    score = int(score or 0)
                except (TypeError, ValueError):
                    score = 0
            hist.setdefault(key, {})[date] = {"date": date, "rank": rank, "score": score}

    injected = 0
    for r in cur.get("models", []):
        key = r.get("id")
        if not key:
            continue
        # MERGE git-derived points with any rank_history already on the live record,
        # keyed by date — never overwrite. The live points are canonical (a daily build
        # may have run without being committed to git), so they win on a same-date clash.
        merged: dict = {}
        for p in hist.get(key, {}).values():
            if p.get("date"):
                merged[p["date"]] = p
        for p in (r.get("rank_history") or []):
            if isinstance(p, dict) and p.get("date"):
                merged[p["date"]] = p   # live wins
        series = sorted(merged.values(), key=lambda p: p["date"])[-90:]
        if series:
            r["rank_history"] = series
            injected += 1

    json.dump(cur, open(DATA, "w"), indent=2)
    print(f"backfilled rank_history for {injected}/{len(cur.get('models', []))} models "
          f"from {len(snaps)} git snapshots", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
