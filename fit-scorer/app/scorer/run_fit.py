"""
run_fit.py

Skill entry point for fit-scorer. Wraps fit_scorer.score_fit() -- the scoring
logic itself is untouched -- and adds the two things the skill reports on top of
the raw assessment: a list of strengths and a three-way verdict.

Both are derived, not re-scored:
  strengths -- requirement_scores entries the model rated "strong"
  verdict   -- overall_fit_percent mapped onto fit_scorer's own bands
               (80+ Strong Fit, 30-79 Worth Exploring, 0-29 Explore with Caution)

Usage:
    python run_fit.py --resume resume.md --jd jd.md --out-dir ./fit-out
    pbpaste | python run_fit.py --resume resume.md --jd - --out-dir ./fit-out
"""

import argparse
import json
import sys
from pathlib import Path

from config import MissingCredentialError, build_client
from fit_scorer import MODEL, load_text, score_fit

# Lower bound of each verdict, highest first. These sit on fit_scorer's
# SYSTEM_PROMPT bands so the verdict never disagrees with the number's meaning.
VERDICT_BANDS = [
    (80, "Strong Fit"),
    (30, "Worth Exploring"),
    (0, "Explore with Caution"),
]


def verdict_for(percent: int) -> str:
    return next(label for floor, label in VERDICT_BANDS if percent >= floor)


def build_result(assessment: dict) -> dict:
    """Add strengths and verdict to the raw score_fit() output."""
    strengths = [
        {"requirement": r["requirement"], "evidence": r["evidence"]}
        for r in assessment["requirement_scores"]
        if r["score"] == "strong"
    ]
    return {
        "overall_fit_percent": assessment["overall_fit_percent"],
        "verdict": verdict_for(assessment["overall_fit_percent"]),
        "strengths": strengths,
        "gaps": assessment["top_gaps"],
        "recommendation": assessment["recommendation"],
        "requirement_scores": assessment["requirement_scores"],
    }


def to_markdown(result: dict) -> str:
    lines = [
        f"# Fit: {result['overall_fit_percent']}% · {result['verdict']}",
        "",
        "## Strengths",
    ]
    lines += [f"- **{s['requirement']}** — {s['evidence']}" for s in result["strengths"]] or ["- None rated strong."]
    lines += ["", "## Gaps"]
    lines += [f"- {g}" for g in result["gaps"]] or ["- None identified."]
    lines += ["", "## Requirement scores", "", "| Requirement | Score | Evidence |", "|---|---|---|"]
    lines += [
        f"| {r['requirement']} | {r['score']} | {r['evidence'].replace('|', '/')} |"
        for r in result["requirement_scores"]
    ]
    lines += ["", "## Recommendation", "", result["recommendation"], ""]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Score a resume against a JD and write markdown + JSON.")
    parser.add_argument("--resume", required=True, help="Resume file (.md or .txt)")
    parser.add_argument("--jd", required=True, help="JD file, or '-' to read pasted JD text from stdin")
    parser.add_argument("--out-dir", default=".", help="Where to write fit_result.json and fit_summary.md")
    parser.add_argument("--model", default=MODEL, help="Claude model to use")
    args = parser.parse_args()

    resume_text = load_text(args.resume)
    jd_text = sys.stdin.read() if args.jd == "-" else load_text(args.jd)
    if not jd_text.strip():
        sys.exit("JD is empty.")

    assessment = score_fit(resume_text, jd_text, build_client(), model=args.model)
    result = build_result(assessment)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "fit_result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    (out_dir / "fit_summary.md").write_text(to_markdown(result), encoding="utf-8")

    print(to_markdown(result))
    print(f"Saved {out_dir / 'fit_result.json'} and {out_dir / 'fit_summary.md'}")


if __name__ == "__main__":
    try:
        main()
    except MissingCredentialError as exc:
        sys.exit(str(exc))
