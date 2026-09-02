-- Migration 004: MCP server call logging
-- Captures every tools/call on the MCP server: who, what, how long, did it succeed.
CREATE TABLE IF NOT EXISTS mcp_call_log (
    id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ts            TIMESTAMPTZ NOT NULL DEFAULT now(),
    session_id    TEXT,
    tool_name     TEXT NOT NULL,
    args_summary  TEXT,
    duration_ms   INTEGER,
    is_error      BOOLEAN NOT NULL DEFAULT FALSE,
    client_ip     TEXT,
    client_ua     TEXT,
    transport     TEXT NOT NULL DEFAULT 'streamable-http'
);
CREATE INDEX IF NOT EXISTS idx_mcp_call_log_ts ON mcp_call_log (ts DESC);
CREATE INDEX IF NOT EXISTS idx_mcp_call_log_tool ON mcp_call_log (tool_name);

-- Daily rollup for the digest
CREATE MATERIALIZED VIEW IF NOT EXISTS mcp_daily_stats AS
SELECT
    date_trunc('day', ts) AS day,
    tool_name,
    count(*) AS calls,
    count(*) FILTER (WHERE is_error) AS errors,
    round(avg(duration_ms)) AS avg_ms,
    count(DISTINCT session_id) AS sessions
FROM mcp_call_log
GROUP BY 1, 2;
CREATE UNIQUE INDEX IF NOT EXISTS idx_mcp_daily_stats_day_tool ON mcp_daily_stats (day, tool_name);
