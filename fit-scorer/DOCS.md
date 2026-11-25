# Fit Scorer add-on

Phone-friendly page (HA sidebar → **Fit Scorer**) that scores a pasted job
description against one or more canned resumes, using the friday_project
`fit_scorer.py` (bundled unchanged in `app/scorer/`).

## Setup

1. Configuration tab → paste your Anthropic API key into `anthropic_api_key`.
   Leave `model` blank to use the scorer's default (`MODEL` in fit_scorer.py).
2. Start the add-on, enable **Show in sidebar**.
3. Open Fit Scorer → **Resumes** tab → **Upload .md/.txt** (or New + paste).

## Where data lives

Resumes and results are stored on the HA host only, never in this repo:

- `/addon_configs/<repo-hash>_fit_scorer/resumes/*.md`
- `/addon_configs/<repo-hash>_fit_scorer/results/*.json` (history)

Edit them with the Samba or File editor add-on, or from the page itself.

## Using it

- **Score**: paste the JD, tap one or more resume chips (or **All**), tap
  **Score fit**. Jobs run in the background; locking the phone is fine, the page
  picks the result back up when you return.
- **History**: every result, with the JD, **Re-use this JD** and **Copy markdown**.

## Verdict bands

80–100 Strong Fit · 30–79 Worth Exploring · 0–29 Explore with Caution
(from `run_fit.py`).

## Security

Ingress only: no host port is published, and HA authentication gates access.
The API key is held in add-on options and passed to the process as an env var.
