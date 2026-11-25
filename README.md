# littledevlab-addons

Home Assistant Supervisor add-on repository for Tyson's littledevlab home-lab
agentic AI track. Add via Settings > Add-ons > Add-on Store > (⋮) >
Repositories, using this repo's URL.

## Add-ons

- **servicenow-mcp** — streamable-HTTP ServiceNow MCP server
  (`mcp-server-servicenow`), meant to sit behind a Cloudflare Tunnel so it can
  be registered as a remote MCP connector at claude.ai/customize/connectors.
- **fit-scorer** — phone-friendly ingress page (HA sidebar) that scores a pasted
  job description against canned resumes with the friday_project fit-scorer
  (Claude API). Resumes and results stay on the HA host in `/addon_configs`.
