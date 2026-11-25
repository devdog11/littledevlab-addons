"""
server.py -- Fit Scorer web front end for Home Assistant ingress.

Wraps the friday_project scorer (scorer/fit_scorer.py + run_fit.py, bundled
unchanged) in a tiny stdlib HTTP server. Scoring runs as background jobs so a
phone that sleeps mid-request can reconnect and pick up the result.

Data lives under FIT_DATA_DIR (the add-on's /config, i.e. /addon_configs/... on
the HA host), never in the image:
    resumes/<id>.md     canned resumes, editable from the page
    results/<id>.json   every finished score (history)
"""

import json
import os
import re
import sys
import threading
import time
import traceback
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

APP_DIR = Path(__file__).parent
sys.path.insert(0, str(APP_DIR / "scorer"))

from fit_scorer import MODEL  # noqa: E402

VERSION = "1.0.1"
DATA = Path(os.environ.get("FIT_DATA_DIR", "/config"))
RESUMES = DATA / "resumes"
RESULTS = DATA / "results"
STATIC = APP_DIR / "static"
PORT = int(os.environ.get("FIT_PORT", "8099"))
SCORE_MODEL = os.environ.get("FIT_MODEL", "").strip() or MODEL
FAKE = os.environ.get("FIT_FAKE") == "1"  # local UI testing without an API key

ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _.-]{0,79}$")
JOBS: dict[str, dict] = {}
JOBS_LOCK = threading.Lock()
_client = None


def get_client():
    global _client
    if _client is None:
        from config import build_client
        _client = build_client()
    return _client


def key_hint() -> str:
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    return f"{key[:10]}…{key[-4:]} ({len(key)} chars)" if len(key) > 16 else ("set" if key else "none")


def safe_id(raw: str) -> str:
    raw = raw.strip()
    if raw.lower().endswith((".md", ".txt")):
        raw = raw.rsplit(".", 1)[0]
    if not ID_RE.match(raw) or ".." in raw:
        raise ValueError("Resume name: letters, numbers, space, dash, underscore, dot (max 80).")
    return raw


def resume_path(rid: str) -> Path:
    rid = safe_id(rid)
    for ext in (".md", ".txt"):
        p = RESUMES / f"{rid}{ext}"
        if p.exists():
            return p
    return RESUMES / f"{rid}.md"


def list_resumes():
    out = []
    for p in sorted(RESUMES.glob("*")):
        if p.suffix.lower() in (".md", ".txt") and p.is_file():
            st = p.stat()
            out.append({"id": p.stem, "chars": st.st_size, "updated": int(st.st_mtime)})
    return out


def jd_title(jd: str) -> str:
    for line in jd.splitlines():
        line = line.strip(" #*\t-")
        if len(line) > 3:
            return line[:90]
    return "Untitled posting"


def fake_assessment(resume: str, jd: str) -> dict:
    time.sleep(3)
    words = {w.lower() for w in re.findall(r"[A-Za-z]{5,}", jd)}
    hits = [w for w in words if w in resume.lower()]
    pct = min(95, int(100 * len(hits) / max(1, len(words))) + 20)
    return {
        "overall_fit_percent": pct,
        "requirement_scores": [
            {"requirement": "FAKE MODE keyword overlap", "score": "strong" if pct >= 60 else "moderate",
             "evidence": ", ".join(sorted(hits)[:12]) or "none"},
            {"requirement": "FAKE MODE placeholder gap", "score": "weak", "evidence": "Not a real score."},
        ],
        "top_gaps": ["FAKE MODE: set FIT_FAKE=0 and an API key for real scoring."],
        "recommendation": "This is a local test result, not a Claude assessment.",
    }


def run_job(job_id: str):
    from run_fit import build_result, to_markdown
    with JOBS_LOCK:
        job = JOBS[job_id]
    try:
        resume_text = resume_path(job["resume_id"]).read_text(encoding="utf-8")
        if FAKE:
            assessment = fake_assessment(resume_text, job["jd"])
        else:
            from fit_scorer import score_fit
            assessment = score_fit(resume_text, job["jd"], get_client(), model=SCORE_MODEL)
        result = build_result(assessment)
        record = {
            "id": job_id, "status": "done", "resume_id": job["resume_id"], "title": job["title"],
            "created": job["created"], "finished": int(time.time()), "model": SCORE_MODEL if not FAKE else "fake",
            "jd": job["jd"], "result": result, "markdown": to_markdown(result),
        }
        (RESULTS / f"{job_id}.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
        with JOBS_LOCK:
            JOBS[job_id] = record
    except Exception as exc:  # surface everything to the phone
        name = type(exc).__name__
        msg = str(exc)
        if name == "AuthenticationError":
            msg = ("Anthropic rejected the API key (401). Re-paste it in the add-on Configuration tab, "
                   "Save, then Restart. Key in use: " + key_hint())
        if name == "MissingCredentialError":
            msg = "No Anthropic API key. Add it in the add-on's Configuration tab, then restart the add-on."
        traceback.print_exc()
        with JOBS_LOCK:
            job.update(status="error", error=f"{name}: {msg}", finished=int(time.time()))


def load_record(job_id: str):
    with JOBS_LOCK:
        if job_id in JOBS:
            return dict(JOBS[job_id])
    p = RESULTS / f"{job_id}.json"
    if re.fullmatch(r"[a-f0-9]{12}", job_id) and p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return None


def history(limit=40):
    rows = []
    for p in sorted(RESULTS.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True)[:limit]:
        try:
            r = json.loads(p.read_text(encoding="utf-8"))
            rows.append({
                "id": r["id"], "title": r["title"], "resume_id": r["resume_id"], "created": r["created"],
                "fit": r["result"]["overall_fit_percent"], "verdict": r["result"]["verdict"],
            })
        except Exception:
            continue
    return rows


class Handler(BaseHTTPRequestHandler):
    server_version = f"FitScorer/{VERSION}"

    def log_message(self, fmt, *args):
        sys.stderr.write("[fit-scorer] " + (fmt % args) + "\n")

    # ---- helpers
    def send_json(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def body_json(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n > 2_000_000:
            raise ValueError("Request too large (2 MB max).")
        return json.loads(self.rfile.read(n) or b"{}")

    def route(self):
        # Ingress strips its prefix, but be tolerant of a leading path anyway.
        path = self.path.split("?", 1)[0]
        return [p for p in path.split("/") if p]

    # ---- verbs
    def do_GET(self):
        parts = self.route()
        try:
            if not parts or parts == ["index.html"]:
                body = (STATIC / "index.html").read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            elif parts == ["api", "info"]:
                key = os.environ.get("ANTHROPIC_API_KEY", "")
                hint = f"{key[:10]}…{key[-4:]} ({len(key)} chars)" if len(key) > 16 else ("set" if key else "none")
                self.send_json({"version": VERSION, "model": SCORE_MODEL, "fake": FAKE,
                                "has_key": bool(key) or FAKE, "key_hint": hint})
            elif parts == ["api", "resumes"]:
                self.send_json(list_resumes())
            elif len(parts) == 3 and parts[:2] == ["api", "resumes"]:
                p = resume_path(parts[2])
                if not p.exists():
                    return self.send_json({"error": "Not found"}, 404)
                self.send_json({"id": p.stem, "text": p.read_text(encoding="utf-8")})
            elif parts == ["api", "history"]:
                self.send_json(history())
            elif len(parts) == 3 and parts[:2] in (["api", "jobs"], ["api", "history"]):
                rec = load_record(parts[2])
                if rec is None:
                    return self.send_json({"error": "Not found"}, 404)
                self.send_json(rec)
            else:
                self.send_json({"error": "Not found"}, 404)
        except ValueError as exc:
            self.send_json({"error": str(exc)}, 400)

    def do_PUT(self):
        parts = self.route()
        try:
            if len(parts) == 3 and parts[:2] == ["api", "resumes"]:
                text = self.body_json().get("text", "")
                if not text.strip():
                    raise ValueError("Resume text is empty.")
                p = resume_path(parts[2])
                p.write_text(text, encoding="utf-8")
                return self.send_json({"id": p.stem, "chars": len(text)})
            self.send_json({"error": "Not found"}, 404)
        except ValueError as exc:
            self.send_json({"error": str(exc)}, 400)

    def do_DELETE(self):
        parts = self.route()
        try:
            if len(parts) == 3 and parts[:2] == ["api", "resumes"]:
                p = resume_path(parts[2])
                if p.exists():
                    p.unlink()
                return self.send_json({"deleted": p.stem})
            if len(parts) == 3 and parts[:2] == ["api", "history"] and re.fullmatch(r"[a-f0-9]{12}", parts[2]):
                (RESULTS / f"{parts[2]}.json").unlink(missing_ok=True)
                return self.send_json({"deleted": parts[2]})
            self.send_json({"error": "Not found"}, 404)
        except ValueError as exc:
            self.send_json({"error": str(exc)}, 400)

    def do_POST(self):
        parts = self.route()
        try:
            if parts == ["api", "score"]:
                data = self.body_json()
                jd = (data.get("jd") or "").strip()
                ids = data.get("resume_ids") or []
                if len(jd) < 40:
                    raise ValueError("Paste the full job description (at least a few lines).")
                if not ids:
                    raise ValueError("Pick at least one resume.")
                title = (data.get("title") or "").strip()[:90] or jd_title(jd)
                jobs = []
                for rid in ids[:6]:
                    if not resume_path(rid).exists():
                        raise ValueError(f"Resume '{rid}' not found.")
                    job_id = uuid.uuid4().hex[:12]
                    with JOBS_LOCK:
                        JOBS[job_id] = {"id": job_id, "status": "running", "resume_id": safe_id(rid),
                                        "title": title, "jd": jd, "created": int(time.time())}
                    threading.Thread(target=run_job, args=(job_id,), daemon=True).start()
                    jobs.append({"id": job_id, "resume_id": safe_id(rid)})
                return self.send_json({"jobs": jobs, "title": title})
            self.send_json({"error": "Not found"}, 404)
        except (ValueError, json.JSONDecodeError) as exc:
            self.send_json({"error": str(exc)}, 400)


def main():
    RESUMES.mkdir(parents=True, exist_ok=True)
    RESULTS.mkdir(parents=True, exist_ok=True)
    print(f"[fit-scorer] v{VERSION} on :{PORT} model={SCORE_MODEL} data={DATA} fake={FAKE}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
