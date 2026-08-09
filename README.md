# InferenceIndexer MCP Server

Model Context Protocol server exposing InferenceIndexer's live + historical
inference pricing as agent callable tools. Instead of an agent assembling
inference pricing itself (slow, incomplete), it can call these tools to get
complete pricing, historical trends, provider comparison, and the SIT index.

## Tools

| Tool | Description |
|---|---|
| `search_models` | Search/list models with current pricing (by text, tier, sort) |
| `get_model` | Full detail + current price for one model |
| `get_model_history` | **Historical** price trends for one model (the differentiator) |
| `list_providers` | All providers with model counts + price stats |
| `get_provider` | Detail for one provider (models, tiers, price range) |
| `get_composite_latest` | Current SIT-Composite index value + tier breakdown |
| `get_composite_history` | SIT-Composite index history / trend |
| `compare_providers` | Price of one model across all providers that host it |

## Config (env)

- `II_API_BASE` - InferenceIndexer API base (default `http://34.246.208.210:8000`)
- `II_API_KEY` - Optional `Bearer` key (use to raise rate limits)
- `II_SSR_SECRET` - Optional first-party SSR secret (higher rate tier)

## Run

stdio (recommended for local/agent-run):
```bash
uv sync
uv run inferenceindexer-mcp
```

Serve over HTTP/SSE (for remote clients, e.g. on the VPS):
```bash
II_SSR_SECRET=... uv run inferenceindexer-mcp --transport streamable-http --port 8899
```

## Connect an agent / MCP client

Claude Desktop / generic MCP client (stdio):
```json
{
  "mcpServers": {
    "inferenceindexer": {
      "command": "uvx",
      "args": ["inferenceindexer-mcp", "--transport", "stdio"]
    }
  }
}
```

Updated Aug 2026.