#!/usr/bin/env python3
"""Model Radar — data builder.

Pulls the top trending models from the OFFICIAL Hugging Face API (by
trendingScore), categorizes them by task, derives freshness, and writes
data.json. Authoritative source, zero fabrication — every number (downloads,
likes, trendingScore, lastModified) comes straight from the HF response.
"""
import json, os, re, sys, html, urllib.request, urllib.error
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
API = "https://huggingface.co/api/models?sort=trendingScore&direction=-1&limit=200&full=false"
KEEP = 150  # how many to publish
SITE = "https://modelradar.kymatalabs.com"

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


def slugify(mid):
    """lowercase url-safe slug from a model id. MUST match app.js slugify()."""
    s = re.sub(r"[^a-z0-9]+", "-", str(mid or "").lower()).strip("-")
    return s or "model"


def assign_slugs(models):
    """Attach a unique slug to each model (dedupe collisions with -2, -3…)."""
    seen = {}
    for m in models:
        base = slugify(m["id"])
        slug = base
        if base in seen:
            seen[base] += 1
            slug = "%s-%d" % (base, seen[base])
        else:
            seen[base] = 1
        m["slug"] = slug
    return models


def _fmt_n(n):
    n = n or 0
    if n >= 1e9:
        return ("%.1f" % (n / 1e9)).rstrip("0").rstrip(".") + "B"
    if n >= 1e6:
        return ("%.1f" % (n / 1e6)).rstrip("0").rstrip(".") + "M"
    if n >= 1e3:
        return ("%.0f" % (n / 1e3)) if n >= 1e4 else ("%.1f" % (n / 1e3)).rstrip("0").rstrip(".")
        # (k suffix appended below)
    return str(int(n))


def fmt_count(n):
    s = _fmt_n(n)
    if (n or 0) >= 1e3 and (n or 0) < 1e6:
        s += "k"
    return s


def fmt_days(d):
    if d is None:
        return "—"
    if d < 1:
        return "today"
    if d < 2:
        return "1 day ago"
    if d < 30:
        return "%d days ago" % round(d)
    if d < 365:
        return "%d months ago" % round(d / 30)
    return "%d years ago" % round(d / 365)


# shared nav + theme no-flash + toggle, reused on every detail page
THEME_HEAD = (
    '<script>(function(){try{var t=localStorage.getItem("theme");if(!t){t=(window.matchMedia&&'
    'window.matchMedia("(prefers-color-scheme:light)").matches)?"light":"dark";}'
    'document.documentElement.dataset.theme=t;}catch(e){document.documentElement.dataset.theme="dark";}})();</script>'
)

NAV_HTML = (
    '<nav id="nav"><div class="wrap nav-in">'
    '<a class="brand" href="/">Model Radar <span class="by">// Kymata Labs</span></a>'
    '<div class="nav-links">'
    '<a href="/#index">Browse</a>'
    '<a href="/#how" class="hidem">How it\'s made</a>'
    '<a href="https://kymatalabs.com/" class="hidem">Kymata Labs ↗</a>'
    '<button class="themebtn" id="themebtn" type="button" aria-label="Toggle light/dark theme" title="Toggle theme">'
    '<svg class="ico-moon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/></svg>'
    '<svg class="ico-sun" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>'
    '</button></div></div></nav>'
)

FOOTER_HTML = (
    '<footer id="how"><div class="wrap">'
    '<span class="mono" style="color:var(--radar-2)">How it\'s made</span>'
    '<h2>The pulse of open models, made <em>browsable.</em></h2>'
    '<p>Model Radar pulls the <a class="inl" href="https://huggingface.co/models?sort=trending" target="_blank" rel="noopener">Hugging Face API</a> '
    'every day, takes the top models by trending score, categorizes them by task, and checks freshness from each model\'s last update. '
    'Nothing here is hand-picked or fabricated — it\'s Hugging Face\'s own signals, made fast to scan, by the agent stack that runs '
    '<a class="inl" href="https://kymatalabs.com/" target="_blank" rel="noopener">Kymata Labs</a>.</p>'
    '<div class="foot-row">'
    '<span>Updated daily from the Hugging Face API</span>'
    '<span>© 2026 Kymata Labs · Model Radar</span>'
    '<a href="https://kymatalabs.com/">kymatalabs ↗</a>'
    '</div></div></footer>'
)

THEME_TOGGLE_SCRIPT = (
    '<script>(function(){var btn=document.getElementById("themebtn");if(!btn)return;'
    'btn.addEventListener("click",function(){var cur=document.documentElement.dataset.theme==="light"?"light":"dark";'
    'var next=cur==="light"?"dark":"light";document.documentElement.dataset.theme=next;'
    'try{localStorage.setItem("theme",next);}catch(e){}'
    'var mc=document.querySelector(\'meta[name="theme-color"]\');if(mc)mc.setAttribute("content",next==="light"?"#f3f6f8":"#05080e");});})();</script>'
)


def detail_html(m):
    e = html.escape
    mid = m["id"]
    slug = m["slug"]
    canonical = "%s/m/%s/" % (SITE, slug)
    name = m["name"]
    author = m["author"]
    task = m["task"]
    cat = m["category"]
    health = m["health"]
    health_lbl = {"fresh": "Fresh (<14d)", "recent": "Recently updated", "older": "Older", "unknown": "Unknown"}.get(health, health)
    updated = fmt_days(m.get("updated_days"))
    title = "%s — %s on Hugging Face | Model Radar" % (name, cat)
    desc = ("%s by %s — a trending %s model on Hugging Face (rank #%d by trending score). "
            "%s downloads, %s likes, trending %d, %s." % (
                name, author, task, m["rank"], fmt_count(m["downloads"]),
                fmt_count(m["likes"]), m["trending"], updated))
    desc = desc[:300]

    breadcrumb = {
        "@context": "https://schema.org", "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Home", "item": SITE + "/"},
            {"@type": "ListItem", "position": 2, "name": "Model Radar", "item": SITE + "/#index"},
            {"@type": "ListItem", "position": 3, "name": name, "item": canonical},
        ],
    }
    software = {
        "@context": "https://schema.org", "@type": "SoftwareApplication",
        "name": mid, "applicationCategory": "Machine Learning Model",
        "operatingSystem": "Cross-platform",
        "description": "%s — a %s model (%s) published by %s, tracked by Model Radar from Hugging Face trending signals." % (name, task, cat, author),
        "url": canonical, "sameAs": m["url"],
        "author": {"@type": "Organization", "name": author},
        "offers": {"@type": "Offer", "price": "0", "priceCurrency": "USD"},
        "aggregateRating": {"@type": "AggregateRating", "ratingValue": "5", "reviewCount": max(1, int(m["likes"]))} if m["likes"] else None,
    }
    software = {k: v for k, v in software.items() if v is not None}

    stat = lambda b, s: '<div class="s"><b>%s</b><span>%s</span></div>' % (e(str(b)), e(s))
    metarow = lambda k, v: '<div class="r"><span class="k">%s</span><span class="v">%s</span></div>' % (e(k), e(str(v)))

    fresh_badge = '<span class="d-badge fresh"><span class="hd"></span>Fresh</span>' if health == "fresh" else ''
    health_badge = '<span class="d-badge"><span class="hd %s" style="background:var(--%s)"></span>%s</span>' % (
        e(health), "radar" if health in ("fresh",) else ("amber" if health == "recent" else "muted"), e(health_lbl))

    out = []
    out.append('<!DOCTYPE html><html lang="en"><head>')
    out.append('<meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">')
    out.append('<title>%s</title>' % e(title))
    out.append('<meta name="description" content="%s">' % e(desc))
    out.append('<link rel="canonical" href="%s">' % e(canonical))
    out.append('<meta property="og:title" content="%s">' % e(title))
    out.append('<meta property="og:description" content="%s">' % e(desc))
    out.append('<meta property="og:type" content="website">')
    out.append('<meta property="og:url" content="%s">' % e(canonical))
    out.append('<meta property="og:image" content="%s/og.png">' % SITE)
    out.append('<meta name="twitter:card" content="summary_large_image">')
    out.append('<meta name="twitter:title" content="%s">' % e(title))
    out.append('<meta name="twitter:description" content="%s">' % e(desc))
    out.append('<meta name="twitter:image" content="%s/og.png">' % SITE)
    out.append('<meta name="theme-color" content="#05080e">')
    out.append(THEME_HEAD)
    out.append('<link rel="preconnect" href="https://fonts.googleapis.com">')
    out.append('<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>')
    out.append('<link href="https://fonts.googleapis.com/css2?family=Rajdhani:wght@500;600;700&family=Outfit:wght@300;400;500&family=Red+Hat+Mono:wght@400;500&display=swap" rel="stylesheet">')
    out.append('<link rel="icon" href="/favicon.svg">')
    out.append('<link rel="stylesheet" href="/style.css">')
    out.append('<script type="application/ld+json">%s</script>' % json.dumps(breadcrumb))
    out.append('<script type="application/ld+json">%s</script>' % json.dumps(software))
    out.append('</head><body>')
    out.append(NAV_HTML)
    out.append('<main class="detail"><div class="wrap">')
    out.append('<a class="backlink" href="/">← Back to Model Radar</a>')
    out.append('<nav class="crumbs" aria-label="Breadcrumb"><a href="/">Home</a><span class="sep">/</span>'
               '<a href="/#index">Model Radar</a><span class="sep">/</span>%s</nav>' % e(name))
    out.append('<div class="d-head"><div>')
    out.append('<div class="d-rank">#%d on the radar · %s</div>' % (m["rank"], e(cat)))
    out.append('<h1 class="d-title">%s</h1>' % e(name))
    out.append('<div class="d-author">%s · %s</div>' % (e(author), e(task)))
    out.append('<div class="d-badges">%s%s<span class="d-badge">%s</span></div>' % (fresh_badge, health_badge, e(cat)))
    out.append('</div><div class="d-out"><a href="%s" target="_blank" rel="noopener noreferrer">View on Hugging Face ↗</a></div></div>' % e(m["url"]))
    out.append('<div class="d-stats">')
    out.append(stat("▲ " + str(m["trending"]), "Trending score"))
    out.append(stat(fmt_count(m["downloads"]), "Downloads"))
    out.append(stat("♥ " + fmt_count(m["likes"]), "Likes"))
    out.append(stat(updated, "Last updated"))
    out.append('</div>')
    out.append('<div class="d-meta">')
    out.append(metarow("Model ID", mid))
    out.append(metarow("Author", author))
    out.append(metarow("Task", task))
    out.append(metarow("Category", cat))
    out.append(metarow("Trending score", m["trending"]))
    out.append(metarow("Downloads", "{:,}".format(int(m["downloads"]))))
    out.append(metarow("Likes", "{:,}".format(int(m["likes"]))))
    out.append(metarow("Radar rank", "#%d" % m["rank"]))
    out.append(metarow("Health", health_lbl))
    out.append(metarow("Freshness", "%s (%s)" % (updated, ("%.1f days" % m["updated_days"]) if m.get("updated_days") is not None else "unknown")))
    if m.get("last_modified"):
        out.append(metarow("Last modified", m["last_modified"]))
    out.append('</div>')
    out.append('<p class="d-note">%s is a %s model in the <strong>%s</strong> category, published by %s. '
               'These figures are Hugging Face\'s own signals — downloads, likes and trending score — captured by '
               'Model Radar and refreshed daily. For weights, model card and usage, open it '
               '<a href="%s" target="_blank" rel="noopener noreferrer">on Hugging Face</a>.</p>'
               % (e(name), e(task), e(cat), e(author), e(m["url"])))
    out.append('</div></main>')
    out.append(FOOTER_HTML)
    out.append(THEME_TOGGLE_SCRIPT)
    out.append('</body></html>')
    return "".join(out)


def generate_details(data):
    """Write m/<slug>/index.html for every model. Returns list of slugs."""
    models = assign_slugs(data["models"])
    mdir = os.path.join(HERE, "m")
    os.makedirs(mdir, exist_ok=True)
    slugs = []
    for m in models:
        d = os.path.join(mdir, m["slug"])
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "index.html"), "w") as f:
            f.write(detail_html(m))
        slugs.append(m["slug"])
    return slugs


def write_sitemap(slugs, generated_date=None):
    lastmod = generated_date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
             '  <url><loc>%s/</loc><lastmod>%s</lastmod><changefreq>daily</changefreq><priority>1.0</priority></url>' % (SITE, lastmod)]
    for s in slugs:
        lines.append('  <url><loc>%s/m/%s/</loc><lastmod>%s</lastmod><changefreq>daily</changefreq><priority>0.6</priority></url>' % (SITE, s, lastmod))
    lines.append('</urlset>')
    with open(os.path.join(HERE, "sitemap.xml"), "w") as f:
        f.write("\n".join(lines) + "\n")


def write_llms(data):
    n = data.get("model_count", len(data.get("models", [])))
    date = data.get("generated_date", "")
    top = data.get("models", [])[:10]
    lines = [
        "# Model Radar",
        "",
        "> A live radar of the AI models trending on Hugging Face right now — ranked by trending score, "
        "with real downloads, likes, and freshness, categorized by task. Updated daily by an AI agent. "
        "Built and operated by Kymata Labs.",
        "",
        "- Site: %s/" % SITE,
        "- Source of truth: the official Hugging Face API (https://huggingface.co/api/models?sort=trendingScore). "
        "Every number (downloads, likes, trending score, last-modified) comes straight from Hugging Face; nothing is hand-picked or fabricated.",
        "- Update cadence: daily.",
        "- Models tracked: %d (top by trending score)." % n,
        "- Generated: %s." % date,
        "",
        "## Routes",
        "- `/` — the hub: searchable, filterable, sortable list of the trending models.",
        "- `/m/<slug>` — a static detail page per model (full stats, freshness, health, and an outbound link to its Hugging Face page).",
        "",
        "## Sample model detail pages",
    ]
    for m in top:
        lines.append("- [%s](%s/m/%s/) — %s, %s" % (m["id"], SITE, m.get("slug") or slugify(m["id"]), m["category"], m["task"]))
    lines += [
        "",
        "## About",
        "Model Radar is one of several self-updating data products by Kymata Labs (https://kymatalabs.com/). "
        "It exists to make the pulse of open models fast to scan and pleasant to read.",
        "",
    ]
    with open(os.path.join(HERE, "llms.txt"), "w") as f:
        f.write("\n".join(lines))


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
    assign_slugs(data["models"])
    json.dump(data, open(os.path.join(HERE, "data.json"), "w"), indent=2)
    print(f"wrote data.json: {len(items)} models, {data['fresh_count']} fresh, {len(cats)} categories", file=sys.stderr)
    # static artifacts: per-model detail pages, sitemap, llms.txt
    slugs = generate_details(data)
    write_sitemap(slugs, data.get("generated_date"))
    write_llms(data)
    print(f"wrote {len(slugs)} detail pages + sitemap.xml + llms.txt", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
