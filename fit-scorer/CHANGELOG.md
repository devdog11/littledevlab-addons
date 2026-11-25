# Changelog

| Version | Date | Type | Change |
|---|---|---|---|
| 1.1.0 | 2026-11-25 | MINOR | iOS Share Sheet support: accepts JD text or a link via hassio.addon_stdin, fetches postings from links (schema.org JobPosting first, page text fallback), scores against share_resumes and sends one HA push with all scores (notify_service). JD box also accepts a link. History shows in-progress and failed jobs. |
| 1.0.1 | 2026-11-25 | PATCH | Trim whitespace/quotes from pasted API key; 401 error now explains the fix and shows a masked key hint (first 10 + last 4 chars, length); /api/info returns key_hint. |
| 1.0.0 | 2026-11-25 | MAJOR | Initial add-on: ingress web page, multi-resume scoring with side-by-side compare, background jobs, history, in-page resume editor/upload. Bundles fit_scorer.py, config.py, run_fit.py from the fit-scorer skill v1.0.0 unchanged. |
