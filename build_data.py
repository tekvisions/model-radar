#!/usr/bin/env python3
"""Model Radar — data builder.

Pulls the top trending models from the OFFICIAL Hugging Face API (by
trendingScore), categorizes them by task, derives freshness, and writes
data.json. Authoritative source, zero fabrication — every number (downloads,
likes, trendingScore, lastModified) comes straight from the HF response.
"""
import json, os, sys, urllib.request, urllib.error
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
API = "https://huggingface.co/api/models?sort=trendingScore&direction=-1&limit=200&full=false"
KEEP = 150  # how many to publish

# pipeline_tag → friendly category
CAT = {
    "text-generation": "Text", "text2text-generation": "Text", "translation": "Text",
    "summarization": "Text", "question-answering": "Text", "fill-mask": "Text",
    "token-classification": "Text", "text-classification": "Text",
    "text-to-image": "Image", "image-to-image": "Image", "unconditional-image-generation": "Image",
    "image-text-to-text": "Vision", "image-to-text": "Vision", "visual-question-answering": "Vision",
    "image-classification": "Vision", "object-detection": "Vision", "image-segmentation": "Vision",
    "mask-generation": "Vision", "depth-estimation": "Vision", "zero-shot-image-classification": "Vision",
    "automatic-speech-recognition": "Audio", "text-to-speech": "Audio", "text-to-audio": "Audio",
    "audio-classification": "Audio", "audio-to-audio": "Audio",
    "text-to-video": "Video", "image-to-video": "Video", "video-text-to-text": "Video",
    "feature-extraction": "Embeddings", "sentence-similarity": "Embeddings",
    "any-to-any": "Multimodal", "image-to-3d": "3D", "text-to-3d": "3D",
}


def fetch(url):
    req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "model-radar"})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=40) as r:
                return json.loads(r.read())
        except Exception:
            import time
            time.sleep(1 + attempt)
    return None


def days_since(iso):
    if not iso:
        return None
    try:
        dt = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
        return (datetime.now(timezone.utc) - dt).total_seconds() / 86400.0
    except Exception:
        return None


def fmt_dl(n):
    return n  # frontend formats; keep raw int


def main():
    raw = fetch(API)
    if not isinstance(raw, list) or not raw:
        print("HF API returned no data", file=sys.stderr)
        return 1

    items = []
    for m in raw:
        mid = m.get("id")
        if not mid:
            continue
        tag = m.get("pipeline_tag")
        cat = CAT.get(tag, "Other")
        d = days_since(m.get("lastModified"))
        if d is None:
            health = "unknown"
        elif d <= 14:
            health = "fresh"
        elif d <= 60:
            health = "recent"
        else:
            health = "older"
        items.append({
            "id": mid,
            "name": mid.split("/")[-1],
            "author": mid.split("/")[0] if "/" in mid else mid,
            "task": tag or "—",
            "category": cat,
            "downloads": int(m.get("downloads") or 0),
            "likes": int(m.get("likes") or 0),
            "trending": int(m.get("trendingScore") or 0),
            "last_modified": m.get("lastModified"),
            "updated_days": round(d, 1) if d is not None else None,
            "health": health,
            "url": "https://huggingface.co/" + mid,
        })

    # already sorted by trendingScore from the API; keep top N, assign rank
    items = items[:KEEP]
    for i, it in enumerate(items):
        it["rank"] = i + 1

    cats = {}
    for it in items:
        cats[it["category"]] = cats.get(it["category"], 0) + 1

    data = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "generated_date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "source": "huggingface.co/api/models (official, by trendingScore)",
        "model_count": len(items),
        "fresh_count": len([x for x in items if x["health"] == "fresh"]),
        "total_downloads": sum(x["downloads"] for x in items),
        "categories": sorted(cats.keys()),
        "category_counts": cats,
        "models": items,
    }
    # resilience guard: HF trending always returns a full page; a short result = API
    # hiccup. Check BEFORE writing so a partial run never overwrites a good data.json.
    if len(items) < 80:
        print(f"GUARD: only {len(items)} models (< 80); refusing to publish a partial radar (data.json left untouched).", file=sys.stderr)
        return 1
    json.dump(data, open(os.path.join(HERE, "data.json"), "w"), indent=2)
    print(f"wrote data.json: {len(items)} models, {data['fresh_count']} fresh, {len(cats)} categories", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
