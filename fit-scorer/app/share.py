"""
share.py -- helpers for the iOS Share Sheet path (v1.1.0).

  * fetch_posting(url)  -> (title, text): pulls a job posting from a URL, preferring
                           schema.org JobPosting JSON-LD, falling back to page text.
  * stdin_loop(handler) -> reads JSON values that hassio.addon_stdin writes to the
                           add-on's stdin and hands each one to handler().
  * notify(service, title, message, url) -> HA notify service via the Supervisor API.
"""

import html
import json
import os
import re
import sys
import urllib.request
from html.parser import HTMLParser

UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1"
URL_RE = re.compile(r"https?://\S+")


def find_url(text: str) -> str | None:
    """Return the URL if the shared text is essentially just a link."""
    text = text.strip()
    m = URL_RE.search(text)
    if m and len(text) - len(m.group(0)) < 200:
        return m.group(0).rstrip(").,>\"'")
    return None


class _TextParser(HTMLParser):
    SKIP = {"script", "style", "noscript", "svg", "head", "nav", "footer", "form"}
    BLOCK = {"p", "div", "br", "li", "ul", "ol", "h1", "h2", "h3", "h4", "h5", "tr", "section", "article"}

    def __init__(self):
        super().__init__()
        self.out, self.skip, self.ld = [], 0, []
        self._in_ld = False

    def handle_starttag(self, tag, attrs):
        if tag == "script" and dict(attrs).get("type", "").lower() == "application/ld+json":
            self._in_ld = True
            self.ld.append("")
            return
        if tag in self.SKIP:
            self.skip += 1
        elif tag in self.BLOCK:
            self.out.append("\n")
        if tag == "li":
            self.out.append("- ")

    def handle_endtag(self, tag):
        if self._in_ld and tag == "script":
            self._in_ld = False
            return
        if tag in self.SKIP and self.skip:
            self.skip -= 1
        elif tag in self.BLOCK:
            self.out.append("\n")

    def handle_data(self, data):
        if self._in_ld:
            self.ld[-1] += data
        elif not self.skip:
            self.out.append(data)


def html_to_text(raw: str) -> str:
    p = _TextParser()
    p.feed(raw)
    text = html.unescape("".join(p.out))
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    return re.sub(r"\n\s*\n+", "\n\n", text).strip()


def _job_postings(obj):
    if isinstance(obj, list):
        for o in obj:
            yield from _job_postings(o)
    elif isinstance(obj, dict):
        t = obj.get("@type")
        if t == "JobPosting" or (isinstance(t, list) and "JobPosting" in t):
            yield obj
        for k in ("@graph", "mainEntity"):
            if k in obj:
                yield from _job_postings(obj[k])


def fetch_posting(url: str, timeout: int = 20) -> tuple[str, str]:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read(3_000_000).decode(r.headers.get_content_charset() or "utf-8", "replace")

    p = _TextParser()
    p.feed(raw)
    for block in p.ld:
        try:
            data = json.loads(block.strip())
        except Exception:
            continue
        for jp in _job_postings(data):
            desc = html_to_text(jp.get("description", ""))
            if len(desc) > 300:
                org = jp.get("hiringOrganization") or {}
                org = org.get("name", "") if isinstance(org, dict) else str(org)
                title = " at ".join(x for x in (jp.get("title", ""), org) if x)
                header = f"# {title}\n" if title else ""
                return title or url, f"{header}Source: {url}\n\n{desc}"

    text = html_to_text(raw)
    m = re.search(r"<title[^>]*>(.*?)</title>", raw, re.S | re.I)
    title = html.unescape(m.group(1)).strip() if m else url
    if len(text) < 400:
        raise ValueError("Couldn't read the job text from that link (login wall or JavaScript-only page). "
                         "Select the description text and share that instead.")
    return title[:90], f"Source: {url}\n\n{text[:30000]}"


def stdin_loop(handler):
    """hassio.addon_stdin writes JSON (no trailing newline guaranteed); decode a stream of values."""
    dec = json.JSONDecoder()
    buf = ""
    fd = sys.stdin.fileno()
    while True:
        chunk = os.read(fd, 65536)
        if not chunk:
            return
        buf += chunk.decode("utf-8", "replace")
        while True:
            buf = buf.lstrip()
            if not buf:
                break
            try:
                value, end = dec.raw_decode(buf)
            except json.JSONDecodeError:
                # Plain text (not JSON) arriving with a newline: treat the line as the payload.
                if "\n" in buf and not buf.startswith(("{", "[", '"')):
                    line, buf = buf.split("\n", 1)
                    value, end = line, 0
                else:
                    break  # wait for more bytes
            else:
                buf = buf[end:]
            try:
                handler(value)
            except Exception as exc:
                print(f"[fit-scorer] stdin payload failed: {exc}", file=sys.stderr, flush=True)


def notify(service: str, title: str, message: str, url: str | None = None) -> None:
    token = os.environ.get("SUPERVISOR_TOKEN")
    service = (service or "").strip().removeprefix("notify.")
    if not token or not service:
        print(f"[fit-scorer] notify skipped ({'no service set' if token else 'no SUPERVISOR_TOKEN'}): {message}", flush=True)
        return
    payload = {"title": title, "message": message}
    if url:
        payload["data"] = {"url": url, "clickAction": url}
    req = urllib.request.Request(
        f"{os.environ.get('FIT_SUPERVISOR', 'http://supervisor')}/core/api/services/notify/{service}",
        data=json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        urllib.request.urlopen(req, timeout=15).read()
    except Exception as exc:
        print(f"[fit-scorer] notify.{service} failed: {exc}", file=sys.stderr, flush=True)
