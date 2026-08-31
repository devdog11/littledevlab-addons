#!/usr/bin/with-contenv bashio
set -e

INSTANCE_URL=$(bashio::config 'instance_url')
AUTH_TYPE=$(bashio::config 'auth_type')
PORT=$(bashio::config 'port')

export SERVICENOW_INSTANCE_URL="${INSTANCE_URL}"
export SERVICENOW_AUTH_TYPE="${AUTH_TYPE}"
export SERVICENOW_USERNAME="$(bashio::config 'username')"
export SERVICENOW_PASSWORD="$(bashio::config 'password')"
export SERVICENOW_CLIENT_ID="$(bashio::config 'client_id')"
export SERVICENOW_CLIENT_SECRET="$(bashio::config 'client_secret')"
export MCP_STATIC_TOKENS="$(bashio::config 'static_token')"

bashio::log.info "Starting ServiceNow MCP server (streamable-http) on port ${PORT}..."

exec uvx --prerelease allow --index-strategy unsafe-best-match --with 'mcp>=2.1.1' mcp-server-servicenow \
    --transport streamable-http \
    --port "${PORT}" \
    --instance-url "${INSTANCE_URL}" \
    --auth-type "${AUTH_TYPE}"
