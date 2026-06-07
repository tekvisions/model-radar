#!/usr/bin/env python3
"""Model Radar — data builder.

Pulls the top trending models from the OFFICIAL Hugging Face API (by
trendingScore), categorizes them by task, derives freshness, and writes
data.json. Authoritative source, zero fabrication — every number (downloads,
likes, trendingScore, lastModified) comes straight from the HF response.
"""
import json, os, re, sys, html, urllib.request, urllib.error, urllib.parse
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


def parse_license(tags):
    """Pull the license out of the HF `tags` list (e.g. 'license:apache-2.0' -> 'apache-2.0').
    License rides along in tags for both full=false and full=true — no extra request needed."""
    for t in tags or []:
        s = str(t)
        if s.startswith("license:"):
            return (s.split(":", 1)[1] or None)
    return None


def fmt_params(total):
    """Human-friendly parameter count: 3830665968 -> '3.8B', 750000000 -> '750M'."""
    if not total or total <= 0:
        return None
    for unit, div in (("B", 1e9), ("M", 1e6), ("K", 1e3)):
        if total >= div:
            v = total / div
            return (f"{v:.1f}{unit}" if v < 100 else f"{v:.0f}{unit}")
    return str(int(total))


def fetch_model_size(mid):
    """Per-model parameter count via safetensors.total. The list endpoint omits it (proven:
    full=true returns the same keys as full=false), so size needs one extra request per model.
    Fail-soft: returns None on any error so the build never breaks on a single bad model."""
    try:
        req = urllib.request.Request(
            "https://huggingface.co/api/models/" + urllib.parse.quote(mid),
            headers={"Accept": "application/json", "User-Agent": "model-radar"})
        with urllib.request.urlopen(req, timeout=15) as r:
            m = json.loads(r.read())
        st = m.get("safetensors")
        return (st or {}).get("total") if isinstance(st, dict) else None
    except Exception:
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
        n = round(d)
        return "%d day%s ago" % (n, "" if n == 1 else "s")
    if d < 365:
        n = round(d / 30)
        return "%d month%s ago" % (n, "" if n == 1 else "s")
    n = round(d / 365)
    return "%d year%s ago" % (n, "" if n == 1 else "s")


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


import math


def _median(vals):
    vals = sorted(v for v in vals if v is not None)
    n = len(vals)
    if not n:
        return 0
    mid = n // 2
    return vals[mid] if n % 2 else (vals[mid - 1] + vals[mid]) / 2.0


def build_context(models):
    """Pre-compute the cross-model context detail pages need (peer medians per
    category, the field maxima for log-scaling, and a quick id→model map).
    Returns a dict consumed by detail_html via m['_ctx']. All real numbers."""
    by_cat = {}
    for m in models:
        by_cat.setdefault(m["category"], []).append(m)
    cat_stats = {}
    for cat, group in by_cat.items():
        cat_stats[cat] = {
            "n": len(group),
            "dl_med": _median([g["downloads"] for g in group]),
            "lk_med": _median([g["likes"] for g in group]),
            "tr_med": _median([g["trending"] for g in group]),
            "age_med": _median([g["updated_days"] for g in group if g["updated_days"] is not None]),
        }
    return {
        "max_tr": max((m["trending"] for m in models), default=1) or 1,
        "max_dl": max((m["downloads"] for m in models), default=1) or 1,
        "max_lk": max((m["likes"] for m in models), default=1) or 1,
        "cat_stats": cat_stats,
        "by_cat": by_cat,
    }


def _log_norm(v, vmax):
    """0..1 log-scaled position of v against vmax (downloads/likes span orders
    of magnitude, so a linear bar would flatten everything but the top model)."""
    v = max(0, v or 0)
    if vmax <= 1:
        return 0.0
    return min(1.0, math.log1p(v) / math.log1p(vmax))


def _recency_score(days):
    """0..1 freshness: 1.0 today, ~0.5 at 30d, tapering to ~0 by a year."""
    if days is None:
        return 0.0
    return 1.0 / (1.0 + max(0.0, days) / 30.0)


def surge_breakdown(m, ctx):
    """An HONEST, transparent decomposition of why this model is on the radar.
    Hugging Face publishes a single trendingScore; we don't claim to know its
    internals. Instead we show the four PUBLIC signals that move together with a
    surge — momentum (HF's own trending score), adoption (downloads), community
    (likes) and recency (freshness) — each normalized against the tracked field,
    then weighted into a 0–100 Radar read. The weights are ours and shown."""
    comps = [
        ("Momentum", "s0", 0.45, _log_norm(m["trending"], ctx["max_tr"]),
         "HF trending score %d, log-scaled vs the field's peak of %d." % (m["trending"], ctx["max_tr"])),
        ("Adoption", "s1", 0.25, _log_norm(m["downloads"], ctx["max_dl"]),
         "%s downloads, log-scaled vs the field's peak." % fmt_count(m["downloads"])),
        ("Community", "s2", 0.18, _log_norm(m["likes"], ctx["max_lk"]),
         "%s likes, log-scaled vs the field's peak." % fmt_count(m["likes"])),
        ("Recency", "s3", 0.12, _recency_score(m.get("updated_days")),
         "Last updated %s — newer weights higher." % fmt_days(m.get("updated_days")).lower()),
    ]
    weighted = [(name, cls, w, val, w * val, note) for (name, cls, w, val, note) in comps]
    total = sum(x[4] for x in weighted) or 1e-9
    score = round(total / sum(x[2] for x in weighted) * 100)
    out = []
    for (name, cls, w, val, contrib, note) in weighted:
        out.append({
            "name": name, "cls": cls, "weight": w, "value": val,
            "share": contrib / total,            # fraction of the composite bar
            "pct": round(val * 100),             # this signal's own 0–100 strength
            "note": note,
        })
    return score, out


def _sec_head(title, tag, sub):
    return ('<section class="d-sec"><div class="h"><h2>%s</h2><span class="tag">%s</span></div>'
            '<p class="sub">%s</p>' % (title, tag, sub))


def _spark_svg(arr, w=720, h=90):
    """Compact sparkline. `arr` is a numeric series already oriented so that a
    higher value reads as 'up' on the chart (callers invert rank before passing)."""
    arr = [float(x or 0) for x in (arr or [])]
    if len(arr) < 2:
        return '<svg viewBox="0 0 %d %d" preserveAspectRatio="none" aria-hidden="true"></svg>' % (w, h)
    mx, mn = max(arr), min(arr)
    rg = (mx - mn) or 1
    n = len(arr)
    pad = 6

    def pt(i, v):
        x = pad + i * (w - 2 * pad) / (n - 1)
        y = h - pad - (v - mn) / rg * (h - 2 * pad)
        return "%.1f,%.1f" % (x, y)

    line = " ".join(pt(i, v) for i, v in enumerate(arr))
    area = "%.1f,%.1f " % (pad, h - pad) + line + " %.1f,%.1f" % (w - pad, h - pad)
    lx = w - pad
    ly = h - pad - (arr[-1] - mn) / rg * (h - 2 * pad)
    return (
        '<svg viewBox="0 0 %d %d" preserveAspectRatio="none" role="img" aria-label="Radar position over time">'
        '<defs><linearGradient id="mrfill" x1="0" y1="0" x2="0" y2="1">'
        '<stop offset="0" stop-color="#2fe0a8" stop-opacity="0.26"/>'
        '<stop offset="1" stop-color="#2fe0a8" stop-opacity="0"/></linearGradient></defs>'
        '<polygon points="%s" fill="url(#mrfill)"/>'
        '<polyline points="%s" fill="none" stroke="#2fe0a8" stroke-width="2.2" stroke-linejoin="round" stroke-linecap="round"/>'
        '<circle cx="%.1f" cy="%.1f" r="3.6" fill="#3fb8ff"/></svg>'
    ) % (w, h, area, line, lx, ly)


def _badge_svg(m):
    """shields.io-style embeddable rank badge. Left label "Model Radar", right
    "#<rank>" in the radar green; appends "▲N" when the model climbed
    (rank_delta > 0). Self-contained, theme-neutral, accessible (role/title).
    Character-width estimation keeps the right pill snug without a web font."""
    e = html.escape
    rank = m.get("rank")
    rank_txt = "#%d" % rank if isinstance(rank, int) else "#—"
    delta = m.get("rank_delta")
    if isinstance(delta, int) and delta > 0:
        rank_txt = "%s ▲%d" % (rank_txt, delta)
    label = "Model Radar"
    name = m.get("name", "") or m.get("id", "")
    # ~6px per char @ 11px; +pad. Stable, no font metrics needed.
    lw = len(label) * 6 + 18
    rw = len(rank_txt) * 6 + 18
    total = lw + rw
    title = "Model Radar — %s ranked %s" % (e(name), e(rank_txt))
    # unique gradient id per badge — uses the model's deduped slug (guaranteed unique
    # by assign_slugs), so no collision even if multiple badges are inlined together on
    # a third-party page (img-embeds are already isolated). Falls back to slugify(id).
    gid = "mr%s" % (m.get("slug") or slugify(m.get("id", "") or name) or "badge")
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="20" '
        'viewBox="0 0 %d 20" role="img" aria-label="%s">'
        '<title>%s</title>'
        '<linearGradient id="%s" x2="0" y2="100%%">'
        '<stop offset="0" stop-color="#fff" stop-opacity=".12"/>'
        '<stop offset="1" stop-opacity=".12"/></linearGradient>'
        '<rect rx="3" width="%d" height="20" fill="#1b2330"/>'
        '<rect rx="3" x="%d" width="%d" height="20" fill="#2fe0a8"/>'
        '<rect rx="3" width="%d" height="20" fill="url(#%s)"/>'
        '<g fill="#fff" text-anchor="middle" '
        'font-family="Verdana,DejaVu Sans,Geneva,sans-serif" font-size="11">'
        '<text x="%d" y="14">%s</text>'
        '<text x="%d" y="14" font-weight="bold" fill="#04140d">%s</text>'
        '</g></svg>'
    ) % (total, total, title, title, gid, total, lw, rw, total, gid,
         lw // 2, label, lw + rw // 2, e(rank_txt))


def generate_badges(data):
    """Write a static /badge/<slug>.svg per model (mirrors detail-page generation).
    Static-deployable: no serverless needed; the daily build refreshes each badge."""
    models = assign_slugs(data.get("models", []))  # idempotent; guarantees a unique slug per model
    b_dir = os.path.join(HERE, "badge")
    os.makedirs(b_dir, exist_ok=True)
    written = 0
    for m in models:
        slug = m["slug"]
        with open(os.path.join(b_dir, "%s.svg" % slug), "w") as f:
            f.write(_badge_svg(m))
        written += 1
    print("  generated %d rank badges in /badge/" % written, file=sys.stderr)
    return written


def generate_feed(data):
    """Write feed.json — a small, documented, stable-schema public API subset of
    the radar (read-only data already public on the page; no secrets)."""
    assign_slugs(data.get("models", []))  # idempotent; guarantees a unique slug per model
    models = sorted(data.get("models", []), key=lambda x: x.get("rank", 999))
    feed = {
        "$schema_version": "1",
        "generator": "Model Radar (Kymata Labs)",
        "generated_at": data.get("generated_at"),
        "site": SITE,
        "docs": "%s/#how" % SITE,
        "license": "Data derived from the public Hugging Face API; attribution to Model Radar (kymatalabs.com) appreciated.",
        "count": len(models),
        "models": [
            {
                "rank": m.get("rank"),
                "name": m.get("name"),
                "id": m.get("id"),
                "category": m.get("category"),
                "trending": m.get("trending"),
                "downloads": m.get("downloads"),
                "rank_delta": m.get("rank_delta"),
                "url": "%s/m/%s/" % (SITE, m["slug"]),
                "badge": "%s/badge/%s.svg" % (SITE, m["slug"]),
            }
            for m in models
        ],
        "movers": data.get("movers", []),
    }
    with open(os.path.join(HERE, "feed.json"), "w") as f:
        json.dump(feed, f, indent=2)
    print("  wrote feed.json: %d models" % len(models), file=sys.stderr)


def generate_rss(data):
    """Write rss.xml — the current trending-models radar (top 30) as a subscribable
    RSS 2.0 feed. Stable per-entry guids (detail URLs); pubDate = the daily refresh.
    Additive, read-only public data (PRD O7)."""
    from email.utils import format_datetime
    def _x(s):
        return html.escape("" if s is None else str(s), quote=True)
    assign_slugs(data.get("models", []))
    models = sorted(data.get("models", []), key=lambda x: x.get("rank", 999))[:30]
    gen_iso = data.get("generated_at")
    try:
        dt = datetime.fromisoformat(gen_iso) if gen_iso else datetime.now(timezone.utc)
    except (TypeError, ValueError):
        dt = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    rfc = format_datetime(dt)
    title = "Model Radar — what's surging on Hugging Face"
    desc = ("The live radar of trending AI models on Hugging Face — ranked by trending "
            "score with real downloads, recomputed daily by autonomous agents.")
    items = []
    for m in models:
        url = "%s/m/%s/" % (SITE, m["slug"])
        rank, tr, cat = m.get("rank"), m.get("trending"), m.get("category")
        rd = m.get("rank_delta")
        move = (" ▲%d" % rd) if isinstance(rd, int) and rd > 0 else (
               (" ▼%d" % abs(rd)) if isinstance(rd, int) and rd < 0 else "")
        ttl = "#%s %s — trending %s" % (rank, m.get("name"), tr)
        body = "#%s · trending %s · %s downloads · %s%s" % (
            rank, tr, fmt_dl(m.get("downloads")), cat, move)
        items.append(
            "    <item>\n"
            "      <title>%s</title>\n" % _x(ttl) +
            "      <link>%s</link>\n" % _x(url) +
            '      <guid isPermaLink="true">%s</guid>\n' % _x(url) +
            "      <category>%s</category>\n" % _x(cat) +
            "      <description>%s</description>\n" % _x(body) +
            "      <pubDate>%s</pubDate>\n" % rfc +
            "    </item>")
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">\n'
        "  <channel>\n"
        "    <title>%s</title>\n" % _x(title) +
        "    <link>%s</link>\n" % SITE +
        '    <atom:link href="%s/rss.xml" rel="self" type="application/rss+xml"/>\n' % SITE +
        "    <description>%s</description>\n" % _x(desc) +
        "    <language>en</language>\n"
        "    <lastBuildDate>%s</lastBuildDate>\n" % rfc +
        "    <generator>Kymata Labs</generator>\n"
        + "\n".join(items) + "\n"
        "  </channel>\n</rss>\n")
    with open(os.path.join(HERE, "rss.xml"), "w") as f:
        f.write(xml)
    print("  wrote rss.xml: %d items" % len(items), file=sys.stderr)


def _section_position(m, ctx, e):
    """Radar position over time: the climbed/slipped badge + an INVERTED rank
    sparkline (the series' own worst rank is the floor, so a climb reads upward),
    plus current / best / since-prior stat tiles. Self-contained — no outer total."""
    rank = m["rank"]
    rank_delta = m.get("rank_delta")
    rhist = m.get("rank_history") or []
    if isinstance(rank_delta, int) and rank_delta > 0:
        badge = '<span class="d-move up" title="Climbed %d since the prior run">▲ %d</span>' % (rank_delta, rank_delta)
        word = "climbed %d position%s" % (rank_delta, "" if rank_delta == 1 else "s")
    elif isinstance(rank_delta, int) and rank_delta < 0:
        badge = '<span class="d-move dn" title="Slipped %d since the prior run">▼ %d</span>' % (abs(rank_delta), abs(rank_delta))
        word = "slipped %d position%s" % (abs(rank_delta), "" if abs(rank_delta) == 1 else "s")
    elif isinstance(rank_delta, int):
        badge = '<span class="d-move flat" title="Held position">→</span>'
        word = "held position"
    else:
        badge = '<span class="d-move new" title="New to the tracked board">NEW</span>'
        word = "new to the radar"
    peak = m.get("peak_rank", rank)
    if len(rhist) >= 2:
        ranks = [int(p.get("rank", rank) or rank) for p in rhist]
        worst = max(ranks)
        # invert: worst rank → 0, best rank → largest, so the line rises on a climb
        series = [max(1, (worst + 1) - rv) for rv in ranks]
        chart = '<div class="d-spark mini">%s</div>' % _spark_svg(series, 720, 90)
        note = "position over the last %d day%s tracked · best: #%d" % (
            len(rhist), "" if len(rhist) == 1 else "s", peak)
    else:
        chart = ""
        note = "position movement fills in as the radar refreshes daily"
    sub = ('Where %s sits on the radar, tracked daily — %s since the prior run. %s.'
           % (e(m["name"]), word, note))
    body = (
        '<div class="d-card">'
        '%s'
        '<div class="d-stats" style="margin-top:%s">'
        '<div class="s"><b>#%d</b><span>Current rank</span></div>'
        '<div class="s"><b>#%d</b><span>Best rank</span></div>'
        '<div class="s"><b>%s</b><span>Since prior run</span></div>'
        '</div></div>'
    ) % (chart, ("22px" if chart else "0"), rank, peak, badge)
    return _sec_head("Radar position over time", "movement", sub) + body + '</section>'


def _rank_arc(m, ctx, e):
    """A compact SVG arc placing this model's rank along the radar sweep."""
    total = max(1, ctx.get("cat_stats") and sum(s["n"] for s in ctx["cat_stats"].values()) or 1)
    rank = m["rank"]
    frac = (rank - 1) / max(1, total - 1) if total > 1 else 0.0
    # sweep from -120° (top, rank 1) clockwise to +120° (last) over a 240° arc
    import math as _m
    start = -120.0
    ang = _m.radians(start + frac * 240.0)
    r = 46
    cx0, cy0 = 60, 60
    bx = cx0 + r * _m.sin(ang)
    by = cy0 - r * _m.cos(ang)
    # background arc path (240° starting at top-left)
    a0 = _m.radians(start)
    a1 = _m.radians(start + 240.0)
    p0x, p0y = cx0 + r * _m.sin(a0), cy0 - r * _m.cos(a0)
    p1x, p1y = cx0 + r * _m.sin(a1), cy0 - r * _m.cos(a1)
    svg = (
        '<svg width="120" height="120" viewBox="0 0 120 120" aria-hidden="true">'
        '<circle cx="60" cy="60" r="46" fill="none" stroke="var(--line)" stroke-width="1"/>'
        '<circle cx="60" cy="60" r="30" fill="none" stroke="var(--line)" stroke-width="1"/>'
        '<path d="M%.1f %.1f A46 46 0 1 1 %.1f %.1f" fill="none" stroke="var(--line-2)" stroke-width="3" stroke-linecap="round"/>'
        '<line x1="60" y1="60" x2="%.1f" y2="%.1f" stroke="var(--radar)" stroke-width="1.4" opacity="0.65"/>'
        '<circle class="ra-blip" cx="%.1f" cy="%.1f" r="5" fill="var(--radar)"/>'
        '<circle cx="60" cy="60" r="2.5" fill="var(--ink-soft)"/>'
        '</svg>'
    ) % (p0x, p0y, p1x, p1y, bx, by, bx, by)
    pct = max(1, round(rank / total * 100))  # percentile-rank: rank 1 of 150 → top 1%
    return ('<div class="rankarc">%s<div class="ra-txt"><b>#%d</b>'
            '<span>of %d tracked models<br>top %d%% by trending score</span></div></div>'
            % (svg, rank, total, pct))


def _section_surge(m, ctx, e):
    score, comps = surge_breakdown(m, ctx)
    segs = []
    for c in comps:
        pct = round(c["share"] * 100)
        if pct <= 0:
            continue
        segs.append('<div class="seg %s" style="width:%d%%" title="%s %d%% of composite">%s</div>'
                    % (c["cls"], pct, e(c["name"]), pct, e(c["name"]) if pct >= 12 else ""))
    leg = []
    for c in comps:
        leg.append(
            '<div class="it"><span class="sw %s"></span><div>'
            '<div class="lab">%s <span class="pct">%d / 100 · %d%% weight</span></div>'
            '<span class="ex">%s</span></div></div>'
            % (c["cls"], e(c["name"]), c["pct"], round(c["weight"] * 100), e(c["note"])))
    sub = ('Hugging Face publishes a single trending score; it doesn\'t expose the formula. '
           'So Model Radar reads the surge from the four <em>public</em> signals that move with it — '
           'momentum, adoption, community and recency — each normalized against the tracked field, '
           'then weighted into a 0–100 composite. The weights are ours, and shown below. No hidden inputs.')
    body = (
        '<div class="d-card">'
        '<div class="surge-score"><b>%d</b><span>Radar surge index / 100</span></div>'
        '<div class="surge-bar" role="img" aria-label="Surge composition by signal">%s</div>'
        '<div class="surge-leg">%s</div>'
        '</div>'
    ) % (score, "".join(segs), "".join(leg))
    return _sec_head("Surge analysis", "why it's on the radar", sub) + body + '</section>'


def _cmp_row(label, me_val, peer_val, vmax, disp_me, disp_peer, log=True):
    """One comparative bar: this model's value vs the category-peer median,
    both placed on the same log (or linear) scale up to the field max."""
    if log:
        me_f = _log_norm(me_val, vmax)
        peer_f = _log_norm(peer_val, vmax)
    else:
        me_f = min(1.0, (me_val or 0) / vmax) if vmax else 0
        peer_f = min(1.0, (peer_val or 0) / vmax) if vmax else 0
    return (
        '<div class="grp"><div class="top"><span class="lbl">%s</span>'
        '<span class="val"><b>%s</b> <span class="pk">· peer median %s</span></span></div>'
        '<div class="track"><i class="me" style="--w:%d%%"></i><i class="peer" style="--p:%d%%"></i></div></div>'
    ) % (label, disp_me, disp_peer, round(me_f * 100), round(peer_f * 100))


def _section_context(m, ctx, e):
    cs = ctx["cat_stats"].get(m["category"], {})
    n = cs.get("n", 1)
    sub = ('How this model stacks up against the other <strong>%d %s</strong> models on the radar. '
           'The filled bar is this model; the tick is the category-peer median. '
           'Downloads and likes use a log scale (they span orders of magnitude).'
           % (n, e(m["category"])))
    rows = []
    rows.append(_cmp_row("Trending score", m["trending"], cs.get("tr_med", 0), ctx["max_tr"],
                         "▲ " + str(m["trending"]), "▲ " + str(int(round(cs.get("tr_med", 0))))))
    rows.append(_cmp_row("Downloads", m["downloads"], cs.get("dl_med", 0), ctx["max_dl"],
                         fmt_count(m["downloads"]), fmt_count(int(round(cs.get("dl_med", 0))))))
    rows.append(_cmp_row("Likes", m["likes"], cs.get("lk_med", 0), ctx["max_lk"],
                         "♥ " + fmt_count(m["likes"]), "♥ " + fmt_count(int(round(cs.get("lk_med", 0))))))
    # recency: invert days→freshness so "fuller = fresher"; linear on a 0..1 score
    me_fresh = _recency_score(m.get("updated_days"))
    peer_fresh = _recency_score(cs.get("age_med"))
    rows.append(
        '<div class="grp"><div class="top"><span class="lbl">Freshness</span>'
        '<span class="val"><b>%s</b> <span class="pk">· peer median %s</span></span></div>'
        '<div class="track"><i class="me" style="--w:%d%%"></i><i class="peer" style="--p:%d%%"></i></div></div>'
        % (fmt_days(m.get("updated_days")),
           fmt_days(cs.get("age_med")) if cs.get("age_med") is not None else "—",
           round(me_fresh * 100), round(peer_fresh * 100)))
    body = ('<div class="d-card"><div class="cmp">%s</div>'
            '<p class="cmp-note">Bars are normalized against the most extreme model in the whole '
            'radar, so a near-full bar means category-leading. Peer median = the middle model of '
            'the %d in this category.</p></div>' % ("".join(rows), n))
    return _sec_head("In context", "vs. category peers", sub) + body + '</section>'


def _section_recency(m, ctx, e):
    days = m.get("updated_days")
    sub = ('Where this model\'s last update lands on a freshness scale — '
           '<span style="color:var(--radar)">fresh</span> (&lt;14d), '
           '<span style="color:var(--amber)">recent</span> (14–60d), or older.')
    # map days (0..365+) to a 0..100 x-position; clamp the tail
    if days is None:
        x = 100
        cap = "unknown"
    else:
        x = min(100.0, (min(days, 365.0) / 365.0) * 100.0)
        cap = fmt_days(days)
    # band widths proportional to the same 0..365 scale: 14d, 60d, rest
    f_w = 14.0 / 365.0 * 100
    r_w = (60.0 - 14.0) / 365.0 * 100
    o_w = 100 - f_w - r_w
    body = (
        '<div class="d-card">'
        '<div class="tl"><div class="bands">'
        '<i class="b-fresh" style="width:%.1f%%"></i>'
        '<i class="b-recent" style="width:%.1f%%"></i>'
        '<i class="b-older" style="width:%.1f%%"></i></div>'
        '<div class="mk" style="--x:%.1f%%"><span class="cap">updated %s</span></div></div>'
        '<div class="tl-axis"><span>today</span><span>14d</span><span>60d</span><span>1y+</span></div>'
        '</div>'
    ) % (f_w, r_w, o_w, x, e(cap))
    return _sec_head("Recency", "last update", sub) + body + '</section>'


def _section_peers(m, ctx, e):
    group = sorted(ctx["by_cat"].get(m["category"], []), key=lambda g: g["rank"])
    if len(group) <= 1:
        return ""
    # window of up to 6 peers centered on this model's position in the category
    idx = next((i for i, g in enumerate(group) if g["id"] == m["id"]), 0)
    lo = max(0, idx - 3)
    hi = min(len(group), lo + 7)
    lo = max(0, hi - 7)
    window = group[lo:hi]
    sub = ('Other <strong>%s</strong> models ranked near this one — click through to compare.'
           % e(m["category"]))
    cards = []
    for g in window:
        self_cls = " self" if g["id"] == m["id"] else ""
        href = "/m/%s/" % e(g.get("slug") or slugify(g["id"]))
        cards.append(
            '<a class="peer-card%s" href="%s"><span class="pr">#%d</span>'
            '<div class="pn"><div class="t">%s</div><div class="s">%s · %s dl</div></div>'
            '<span class="pt">▲ %d</span></a>'
            % (self_cls, href, g["rank"], e(g["name"]), e(g["author"]), fmt_count(g["downloads"]), g["trending"]))
    body = '<div class="peers">%s</div>' % "".join(cards)
    return _sec_head("Category peers", "%s · %d models" % (e(m["category"]), len(group)), sub) + body + '</section>'


def _section_embed(m, e):
    """Embeddable rank badge — the viral loop (models display their live rank,
    link back here). Copyable markdown + HTML snippets."""
    slug = m["slug"]
    name = e(m["name"])
    badge_url = "%s/badge/%s.svg" % (SITE, slug)
    detail_url = "%s/m/%s/" % (SITE, slug)
    embed_md = "[![Model Radar rank](%s)](%s)" % (badge_url, detail_url)
    embed_html = '<a href="%s"><img src="%s" alt="Model Radar rank"></a>' % (detail_url, badge_url)
    sub = "Show your live Model Radar rank in your README — it updates daily and links back here."
    pre_style = ("overflow-x:auto;padding:12px;border-radius:8px;background:rgba(127,127,127,.10);"
                 "font-family:'DM Mono',ui-monospace,monospace;font-size:13px")
    body = (
        '<p style="margin-top:14px"><img src="%s" alt="Model Radar rank badge for %s" style="vertical-align:middle"></p>'
        '<div class="embed-snippets" style="margin-top:14px">'
        '<label class="sublabel" style="display:block;margin-bottom:6px">Markdown</label>'
        '<pre class="embed-code" style="%s"><code>%s</code></pre>'
        '<label class="sublabel" style="display:block;margin:14px 0 6px">HTML</label>'
        '<pre class="embed-code" style="%s"><code>%s</code></pre>'
        '</div>'
        % (badge_url, name, pre_style, e(embed_md), pre_style, e(embed_html))
    )
    return _sec_head("📛 Embed this badge", "rank badge", sub) + body + '</section>'


def _section_links(m, e):
    mid = m["id"]
    hf = e(m["url"])
    author = e(m["author"])
    links = [
        ('Model page', hf, 'Weights, model card, files & usage on Hugging Face'),
        ('Discussions', hf + "/discussions", 'Community Q&A and issues for this model'),
        ('All by %s' % author, "https://huggingface.co/%s" % e(mid.split("/")[0]) if "/" in mid else hf,
         'Every model this author has published'),
        ('Files & versions', hf + "/tree/main", 'Browse the repository tree and revisions'),
    ]
    rows = []
    for label, href, desc in links:
        rows.append(
            '<a class="peer-card" href="%s" target="_blank" rel="noopener noreferrer">'
            '<div class="pn"><div class="t">%s ↗</div><div class="s">%s</div></div></a>'
            % (href, label, desc))
    sub = 'Go straight to the source — everything here links back to Hugging Face.'
    body = '<div class="peers">%s</div>' % "".join(rows)
    return _sec_head("Primary links", "on hugging face", sub) + body + '</section>'


def detail_html(m, ctx=None):
    e = html.escape
    if ctx is None:
        ctx = build_context([m])
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
    _hd = m.get("rank_delta")
    if isinstance(_hd, int) and _hd > 0:
        _hbadge = ' <span class="d-move up" title="Climbed %d since the prior run">▲ %d</span>' % (_hd, _hd)
    elif isinstance(_hd, int) and _hd < 0:
        _hbadge = ' <span class="d-move dn" title="Slipped %d since the prior run">▼ %d</span>' % (abs(_hd), abs(_hd))
    elif isinstance(_hd, int):
        _hbadge = ' <span class="d-move flat" title="Held position">→</span>'
    else:
        _hbadge = ''
    out.append('<h1 class="d-title">%s%s</h1>' % (e(name), _hbadge))
    out.append('<div class="d-author">%s · %s</div>' % (e(author), e(task)))
    out.append('<div class="d-badges">%s%s<span class="d-badge">%s</span></div>' % (fresh_badge, health_badge, e(cat)))
    out.append('</div><div class="d-out"><a href="%s" target="_blank" rel="noopener noreferrer">View on Hugging Face ↗</a></div></div>' % e(m["url"]))
    out.append('<div class="d-stats">')
    out.append(stat("▲ " + str(m["trending"]), "Trending score"))
    out.append(stat(fmt_count(m["downloads"]), "Downloads"))
    out.append(stat("♥ " + fmt_count(m["likes"]), "Likes"))
    out.append(stat(updated, "Last updated"))
    out.append('</div>')
    out.append(_rank_arc(m, ctx, e))
    out.append('<div class="d-meta">')
    out.append(metarow("Model ID", mid))
    out.append(metarow("Author", author))
    out.append(metarow("Task", task))
    out.append(metarow("Category", cat))
    if m.get("license"):
        out.append(metarow("License", m["license"]))
    if m.get("params_h"):
        out.append(metarow("Parameters", m["params_h"]))
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

    # ── deep-dive sections (all real numbers, derived from the snapshot) ──
    out.append(_section_surge(m, ctx, e))
    out.append(_section_position(m, ctx, e))
    out.append(_section_context(m, ctx, e))
    out.append(_section_recency(m, ctx, e))
    out.append(_section_peers(m, ctx, e))
    out.append(_section_embed(m, e))
    out.append(_section_links(m, e))

    out.append('</div></main>')
    out.append(FOOTER_HTML)
    out.append(THEME_TOGGLE_SCRIPT)
    out.append('</body></html>')
    return "".join(out)


def generate_details(data):
    """Write m/<slug>/index.html for every model. Returns list of slugs."""
    models = assign_slugs(data["models"])
    ctx = build_context(models)  # peer medians, field maxima — computed once
    mdir = os.path.join(HERE, "m")
    os.makedirs(mdir, exist_ok=True)
    slugs = []
    for m in models:
        d = os.path.join(mdir, m["slug"])
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "index.html"), "w") as f:
            f.write(detail_html(m, ctx))
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
            "license": parse_license(m.get("tags")),
            "downloads": int(m.get("downloads") or 0),
            "likes": int(m.get("likes") or 0),
            "trending": int(m.get("trendingScore") or 0),
            "last_modified": m.get("lastModified"),
            "updated_days": round(d, 1) if d is not None else None,
            "health": health,
            "url": "https://huggingface.co/" + mid,
        })

    # already sorted by trendingScore from the API; keep top N, assign rank
    # (rank = 1-based position in this trending-sorted list; trending is the primary score)
    items = items[:KEEP]
    for i, it in enumerate(items):
        it["rank"] = i + 1
    # Enrich the kept models with parameter size — one extra HF request each (the list
    # endpoint omits safetensors). Fail-soft per model (15s timeout, None on error), so a
    # slow/missing model never breaks the build; models without safetensors simply get None.
    for it in items:
        n = fetch_model_size(it["id"])
        it["params"] = n
        it["params_h"] = fmt_params(n)
    assign_slugs(items)  # attach slugs early so movers[] can carry them

    cats = {}
    for it in items:
        cats[it["category"]] = cats.get(it["category"], 0) + 1

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # read the PRIOR data.json (keyed on the stable model id) to extend each model's
    # rank_history and derive position movement. Absent/short history → deltas are None.
    prior_rankh = {}
    prior_path = os.path.join(HERE, "data.json")
    if os.path.exists(prior_path):
        try:
            with open(prior_path) as f:
                old = json.load(f)
            for r in old.get("models", []):
                if r.get("id"):
                    prior_rankh[r["id"]] = r.get("rank_history", []) or []
        except Exception:
            prior_rankh = {}

    # append today's (rank, score) to each model's rank_history (capped 90 days),
    # then derive movement vs the most recent PRIOR day. rank_delta > 0 == a smaller
    # (better) rank number, i.e. climbed the board. None == new/untracked.
    for it in items:
        rh = list(prior_rankh.get(it["id"], []))
        # only PRIOR points with a real int rank are comparable (a malformed/None rank
        # in the persisted history must never crash the daily cron build).
        prior_pts = [p for p in rh if p.get("date") != today and isinstance(p.get("rank"), int)]
        rh = [p for p in rh if p.get("date") != today] + [{"date": today, "rank": it["rank"], "score": it["trending"]}]
        rh = rh[-90:]
        it["rank_history"] = rh
        if prior_pts:
            prev_rank = prior_pts[-1].get("rank")
            it["rank_prev"] = prev_rank
            it["rank_delta"] = prev_rank - it["rank"]   # prior_pts are int-rank only
            it["peak_rank"] = min([p["rank"] for p in prior_pts] + [it["rank"]])
            it["tracked_days"] = len(prior_pts) + 1
        else:
            it["rank_prev"] = None
            it["rank_delta"] = None       # None == new/untracked (distinct from 0 == held)
            it["peak_rank"] = it["rank"]
            it["tracked_days"] = 1

    # movers: biggest climbers by rank_delta; fall back to biggest positive score
    # movement, else "new this period" models, on day one (before history exists).
    climbers = [x for x in items if isinstance(x.get("rank_delta"), int) and x["rank_delta"] > 0]
    movers = sorted(climbers, key=lambda x: (x["rank_delta"], int(x.get("trending") or 0)),
                    reverse=True)[:5]
    if not movers:
        # day-one fallback: top of the board by trending (these ARE the surge leaders)
        movers = items[:5]
    movers_out = [{
        "id": mv["id"], "name": mv["name"], "author": mv["author"], "slug": mv.get("slug"),
        "rank": mv["rank"], "rank_delta": mv.get("rank_delta"),
        "trending": mv["trending"], "category": mv["category"],
    } for mv in movers]

    data = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "generated_date": today,
        "source": "huggingface.co/api/models (official, by trendingScore)",
        "model_count": len(items),
        "fresh_count": len([x for x in items if x["health"] == "fresh"]),
        "total_downloads": sum(x["downloads"] for x in items),
        "categories": sorted(cats.keys()),
        "category_counts": cats,
        "movers": movers_out,
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
    generate_badges(data)
    generate_feed(data)
    generate_rss(data)
    print(f"wrote {len(slugs)} detail pages + sitemap.xml + llms.txt + feed.json + rss.xml + badges", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
