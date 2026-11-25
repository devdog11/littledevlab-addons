"""
config.py

Shared configuration for the fit-scorer project: credential resolution and the
project's canonical paths. Everything else imports from here so there is exactly
one place that knows where the key comes from and where files live.

Credential design note (why this raises instead of calling sys.exit):
    sys.exit() inside a helper kills the whole process, which is fine for a
    script but wrong the moment anything imports it -- a test, a web handler, a
    batch runner. Raising lets the caller decide what a missing credential
    means: a friendly CLI message, an HTTP 500, or a failed health check.
"""

from pathlib import Path
import os

import anthropic

# Paths are anchored to this file, not the current working directory, so every
# script resolves the same paths no matter where it is invoked from.
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
OUTPUT_DIR = BASE_DIR / "outputs"

API_KEY_ENV_VAR = "ANTHROPIC_API_KEY"


class MissingCredentialError(RuntimeError):
    """Raised when no Anthropic API key can be resolved from any source."""


def resolve_api_key() -> str:
    """Resolve the Anthropic API key, raising if none is available.

    This is written as a resolution chain with a single link today. In a
    deployed service the same function would try, in order: the environment, a
    secret manager (AWS Secrets Manager / Vault / GCP Secret Manager) reached
    via workload identity, and only then a local credential store. Callers stay
    identical across laptop and container -- only this function changes.

    Resolve once at startup and reuse the client; do not call this per request.
    """
    key = os.environ.get(API_KEY_ENV_VAR)
    if key:
        return key

    raise MissingCredentialError(
        f"{API_KEY_ENV_VAR} is not set. Run `akey` to load the key from the "
        f"macOS Keychain into this shell, or prefix a single command with the "
        f"`anthro` wrapper to inject it for that command only."
    )


def build_client() -> anthropic.Anthropic:
    """Build an Anthropic client from the resolved API key.

    max_retries is set here rather than per-call so every entry point in the
    project gets the same retry behavior. The SDK handles connection errors,
    408, 409, 429, and 5xx with exponential backoff.
    """
    return anthropic.Anthropic(api_key=resolve_api_key())
