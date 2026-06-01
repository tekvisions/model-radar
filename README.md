# Model Radar

**What's surging on Hugging Face right now.** A live radar of trending AI models —
ranked by Hugging Face's trending score, with real downloads, likes, and freshness,
categorized by task. Refreshed daily by an AI agent. A [Kymata Labs](https://kymatalabs-techtalevisions-projects.vercel.app/) product.

`build_data.py` pulls the official HF API → `data.json`; `deploy.py` ships to Vercel;
a daily GitHub Action recomputes + redeploys. Zero fabrication — every number is HF's own.
