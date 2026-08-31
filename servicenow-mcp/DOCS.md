# ServiceNow MCP add-on

Wraps `mcp-server-servicenow` (github.com/jschuller/mcp-server-servicenow) in
streamable-HTTP mode so it's reachable over the network instead of stdio.

## Configuration

Fill in the Options tab after install — instance_url and auth_type are
pre-filled for the dev322229 PDI; leave username/password blank if using
oauth (client_id/client_secret), or vice versa for basic auth.

## Exposing it remotely

This add-on does not publish a host port on purpose — it's only reachable
from other containers on Home Assistant's internal `hassio` Docker network.
Point the Cloudflared add-on's tunnel ingress rule at this add-on's internal
hostname on port 8080 (check the exact container hostname Supervisor assigns
after install, typically `<repo-slug>-servicenow-mcp` or similar — verify via
`ha_get_app`/Supervisor logs rather than assuming).
