"""
fit_scorer.py

Scores a resume against a job description using the Claude API and returns
a structured fit assessment (JSON). This is the core tool -- eval_static.py and
eval_dynamic.py build an evaluation layer on top of this to benchmark prompt quality.

Setup:
    pip install -r requirements.txt
    export ANTHROPIC_API_KEY="sk-ant-..."

Usage:
    python fit_scorer.py --resume data/static/resume.md --jd data/static/jd.md
    python fit_scorer.py --resume data/static/resume.md --jd data/static/jd.md \\
        --out outputs/static/result.json
"""

import argparse
# from http import client
import json
import sys

import anthropic

from config import MissingCredentialError, build_client

MODEL = "claude-sonnet-5"

# The actual prompt sent to claude. 
# It instructs the model to compare the resume and job description, derive requirements from the JD, 
# score each requirement based on evidence in the resume, and produce a JSON output with a specific 
# structure. The prompt emphasizes honesty, evidence-based scoring, and strict adherence to the 
# requirements explicitly stated in the job description.
SYSTEM_PROMPT = """You are an experienced technical recruiter and career coach. Compare the \
candidate resume to the job description and produce an honest, evidence-based fit assessment. \
Do not inflate scores -- cite specific resume language to justify each score.

Derive the requirement list ONLY from what the job description explicitly states. Do not add \
adjacent requirements it does not mention, and do not split one requirement into several \
overlapping entries -- each must be materially distinct from the others. A single gap restated \
under three headings must not be counted three times.

Set overall_fit_percent on this scale, weighting each requirement equally:

  80-100  meets essentially every core requirement, with direct evidence
  66-79   meets most core requirements; the gaps are secondary ones
  30-65   meets some core requirements with real evidence, but has material gaps in others
  0-29    meets few or none of the core requirements

A candidate with genuine, well-evidenced strength in at least one core requirement belongs in \
the 30-65 band or higher, even when the remaining gaps are serious.

Respond with ONLY valid JSON, no markdown fences, no commentary:
"""


# FIT_SCHEMA to ensure we have proper JSON structure. This schema is used to validate the model's 
# output and ensure it conforms to the expected format. It defines the required fields, their types, 
# and any constraints on their values. If the model's output does not match this schema, the code 
# can re-prompt or handle the error accordingly.
FIT_SCHEMA = {
    "type": "object",
    "properties": {
        "overall_fit_percent": {"type": "integer"},
        "requirement_scores": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "requirement": {"type": "string"},
                    "score": {"type": "string", "enum": ["strong", "moderate", "weak"]},
                    "evidence": {"type": "string"},
                },
                "required": ["requirement", "score", "evidence"],
                "additionalProperties": False,
            },
        },
        "top_gaps": {"type": "array", "items": {"type": "string"}},
        "recommendation": {"type": "string"},
    },
    "required": ["overall_fit_percent", "requirement_scores", "top_gaps", "recommendation"],
    "additionalProperties": False,
}


# The load_txt function reads the contents of a text file and returns it as a string. It is used to load the resume and job description text files specified by the user when running the script. The function opens the file in read mode with UTF-8 encoding, reads all its content, and returns it. This allows the script to easily access the text data needed for scoring the fit between the resume and job description.
def load_text(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


# The real working block of code
def score_fit(resume_text: str, jd_text: str, client: anthropic.Anthropic, model: str = MODEL) -> dict:
    """Call Claude to score a resume against a job description. Returns a parsed dict.
    DONE (Day 2): add retry logic for transient API errors.
    DONE (Day 3): validate the returned JSON against a schema (see eval_static.py) and
    re-prompt if the shape is wrong instead of letting json.loads() raise.
    """
    # simple concatenation of resume and job description into a single prompt for the model. The model is instructed to return a JSON assessment of the fit between the resume and job description.
    user_prompt = (
        f"RESUME:\n{resume_text}\n\n"
        f"JOB DESCRIPTION:\n{jd_text}\n\n"
    )


    # On day 5 added this becasue the FIT_SCHEMA is a cleaner way to confirm we have a JSON format without "fencing"
    # This is the reall call to the Claude API. It sends the system prompt, user prompt, and output configuration (including the JSON schema) to the model. The response is expected to contain a JSON block that conforms to the FIT_SCHEMA. If the response does not contain a text block or if it does not conform to the schema, an error is raised.
    response = client.messages.create(
        model=model,
        max_tokens=8192,
        system=SYSTEM_PROMPT,
        output_config={"format": {"type": "json_schema", "schema": FIT_SCHEMA}},
        messages=[{"role": "user", "content": user_prompt}],
        )
    if response.stop_reason != "end_turn":
        raise RuntimeError(
            f"There was an error returned from Claude : {response.stop_reason} , "
            f"usage={response.usage} , {response.content}"
        )

    # The response may contain thinking blocks before the text block (e.g. when
    # extended thinking is enabled), so pick the first actual text block rather
    # than assuming it is at index 0.
    raw_text = next(
        (block.text for block in response.content if block.type == "text"),
        None,
    )
    if raw_text is None:
        raise RuntimeError(
            "No text block found in the model response "
            f"(content types: {[block.type for block in response.content]})."
        )
#    raw_text = raw_text.strip()
    return json.loads(raw_text.strip())

def main():
# Uses argparse (see import above) to parse command-line arguments for resume and job description file paths, calls score_fit, and prints or saves the result.
    parser = argparse.ArgumentParser(description="Score a resume against a job description via Claude.")
    parser.add_argument("--resume", required=True, help="Path to a resume text file")
    parser.add_argument("--jd", required=True, help="Path to a job description text file")
    parser.add_argument("--out", default=None, help="Optional path to write the JSON result")
    parser.add_argument("--model", default=MODEL, help="Claude model to use")
    args = parser.parse_args()

    # Credential resolution lives in config.py so every entry point in the
    # project agrees on where the key comes from. It raises rather than exits;
    # the __main__ block below turns that into a clean CLI message.
    client = build_client()

# Reads in the text of the resume and job description files, calls score_fit to get the assessment, and prints or saves the result.
    resume_text = load_text(args.resume)
    jd_text = load_text(args.jd)
# calls score_fit with the loaded resume and job description text, the Anthropic client, and the specified model. It then formats the result as pretty-printed JSON and prints it to stdout. If an output file path is provided, it writes the JSON to that file as well.
    result = score_fit(resume_text, jd_text, client, model=args.model)
    output_json = json.dumps(result, indent=2)
    print(output_json)

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(output_json)
        print(f"\nSaved to {args.out}")


if __name__ == "__main__":
    try:
        main()
    except MissingCredentialError as exc:
        sys.exit(str(exc))
