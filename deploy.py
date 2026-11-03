#!/usr/bin/env python3
"""Deploy this static directory to Vercel via the REST API.

Used both for manual ships and by the daily GitHub Action. Avoids the Vercel
CLI (which hangs in some headless/CC environments). Uploads each file by SHA,
then creates a production deployment.

Env:
  VERCEL_TOKEN   (required)
  VERCEL_TEAM_ID (default: techtalevisions-projects team)
  VERCEL_PROJECT (default: model-radar; exact verified project only)
"""
import hashlib, json, os, sys, urllib.request, urllib.error
from public_assets import collect_public_files
import http.client, socket, ssl, time
from urllib.parse import urlsplit

ROOT = os.path.dirname(os.path.abspath(__file__))
TOKEN = os.environ.get("VERCEL_TOKEN", "").strip()
TEAM = os.environ.get("VERCEL_TEAM_ID", "team_L6hpqgg8pEHznOzrnU66JuoW").strip()
PROJECT = os.environ.get("VERCEL_PROJECT", "model-radar").strip()
EXPECTED_PROJECT_ID = "prj_pZDhKVQlE2lGpF2UTXx9zfgEyk7T"
EXPECTED_PROJECT_NAME = "model-radar"


def req(url, data=None, headers=None, method=None):
    # File uploads are content-addressed and safe to repeat. Deployment creation
    # is not: after an uncertain response, inspect native state before retrying.
    parsed = urlsplit(url)
    effective_method = method or ("POST" if data is not None else "GET")
    safe_retry = effective_method == "GET" or (
        effective_method == "POST" and parsed.hostname == "api.vercel.com"
        and parsed.path == "/v2/files"
    )
    attempts = 4 if safe_retry else 1
    for attempt in range(attempts):
        r = urllib.request.Request(url, data=data, headers=headers or {}, method=method)
        try:
            with urllib.request.urlopen(r, timeout=60) as resp:
                return resp.status, resp.read()
        except urllib.error.HTTPError as e:
            body = e.read()
            if e.code not in (429, 500, 502, 503, 504) or attempt == attempts - 1:
                return e.code, body
            retry_after = e.headers.get("Retry-After", "")
            delay = min(60, max(1, int(retry_after))) if retry_after.isdigit() else 2 ** attempt
        except (urllib.error.URLError, TimeoutError, ConnectionError, http.client.RemoteDisconnected) as e:
            reason = e.reason if isinstance(e, urllib.error.URLError) else e
            transient = isinstance(reason, (TimeoutError, ConnectionError, socket.timeout, http.client.RemoteDisconnected))
            if isinstance(reason, ssl.SSLError) or not transient or attempt == attempts - 1:
                raise
            delay = 2 ** attempt
        time.sleep(delay)



def _preflight_overwrite_guard():
    """Bind this uploader to its verified existing project before any mutation."""
    if PROJECT not in (EXPECTED_PROJECT_NAME, EXPECTED_PROJECT_ID):
        print("REFUSING: configured project differs from this site's verified target", file=sys.stderr)
        raise SystemExit(2)
    st, response = req(f"https://api.vercel.com/v9/projects/{PROJECT}?teamId={TEAM}",
                       headers={"Authorization": f"Bearer {TOKEN}"})
    if st >= 400:
        print(f"REFUSING: could not verify existing project (HTTP {st})", file=sys.stderr)
        raise SystemExit(2)
    try:
        project = json.loads(response)
    except Exception:
        raise SystemExit("REFUSING: project response is unparseable")
    if project.get("id") != EXPECTED_PROJECT_ID:
        print("REFUSING: returned project identity differs from verified target", file=sys.stderr)
        raise SystemExit(2)
    # Existing framework override never bypasses the exact project binding.
    if os.environ.get("ALLOW_OVERWRITE") == "1":
        return
    production = (project.get("targets") or {}).get("production") or {}
    if project.get("framework") or (production.get("meta") or {}).get("githubCommitRef"):
        print("REFUSING: target is a framework/Git deployment; review existing override separately", file=sys.stderr)
        raise SystemExit(2)


def main():
    if not TOKEN:
        print("VERCEL_TOKEN not set", file=sys.stderr)
        return 1
    # Validate every selected path and its fresh offline build receipt first.
    files = collect_public_files(ROOT)
    _preflight_overwrite_guard()

    payload = []
    for rel in files:
        with open(os.path.join(ROOT, rel), "rb") as source_file:
            body = source_file.read()
        sha = hashlib.sha1(body).hexdigest()
        st, _ = req(f"https://api.vercel.com/v2/files?teamId={TEAM}", data=body,
                    headers={"Authorization": f"Bearer {TOKEN}",
                             "Content-Type": "application/octet-stream",
                             "x-vercel-digest": sha}, method="POST")
        print(f"  upload {rel}: {st}", file=sys.stderr)
        if st >= 400:
            print(f"Upload failed for {rel}; no deployment created.", file=sys.stderr)
            return 1
        payload.append({"file": rel, "sha": sha, "size": len(body)})

    dep = {"name": PROJECT, "project": PROJECT, "target": "production", "files": payload,
           "projectSettings": {"framework": None, "buildCommand": None,
                               "installCommand": None, "outputDirectory": None}}
    st, resp = req(f"https://api.vercel.com/v13/deployments?teamId={TEAM}&forceNew=1",
                   data=json.dumps(dep).encode(),
                   headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"},
                   method="POST")
    d = json.loads(resp)
    if st >= 400:
        print("deploy error:", json.dumps(d, indent=2)[:600], file=sys.stderr)
        return 1
    print(f"deployed: https://{d.get('url')}  state={d.get('readyState')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
