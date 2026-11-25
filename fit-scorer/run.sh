#!/usr/bin/with-contenv bashio
set -e

# Trim whitespace/newlines and stray quotes that sneak in when pasting on a phone.
RAW_KEY="$(bashio::config 'anthropic_api_key')"
export ANTHROPIC_API_KEY="$(printf '%s' "${RAW_KEY}" | tr -d '[:space:]"'"'"'')"
export FIT_MODEL="$(bashio::config 'model')"
export FIT_DATA_DIR=/config
export FIT_PORT=8099

if [ -z "${ANTHROPIC_API_KEY}" ]; then
  bashio::log.warning "anthropic_api_key is empty; scoring will fail until you set it in Configuration."
fi
mkdir -p /config/resumes /config/results
bashio::log.info "Resumes live in /addon_configs/<repo>_fit_scorer/resumes on the HA host."

exec python3 -u /app/server.py
