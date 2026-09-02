"""Per-call usage logging for the InferenceIndexer MCP server.

Wraps FastMCP.call_tool so every tools/call writes one row to the
`mcp_call_log` Postgres table (Supabase): session, tool, summarized args,
latency, error status, transport. Logging NEVER breaks a tool call: DB
failures are swallowed after one console warning.
"""

from __future__ import annotations

import os
import threading
import time
import uuid
from typing import Any

try:
    import psycopg2
except ImportError:  # pragma: no cover - psycopg2 ships in the runtime env
    psycopg2 = None

DB_URL = os.environ.get("SUPABASE_DB_URL", "")

_INSERT_SQL = """
INSERT INTO mcp_call_log
    (session_id, tool_name, args_summary, duration_ms, is_error, transport)
VALUES (%s, %s, %s, %s, %s, %s)
"""

_local = threading.local()
_warned = False


def _conn():
    """One psycopg2 connection per thread, reconnecting on failure."""
    c = getattr(_local, "conn", None)
    if c is not None and not c.closed:
        return c
    if not DB_URL:
        raise RuntimeError("SUPABASE_DB_URL not set; call logging disabled")
    _local.conn = psycopg2.connect(DB_URL, connect_timeout=5)
    _local.conn.autocommit = True
    return _local.conn


def _summarize_args(arguments: dict[str, Any]) -> str:
    """Short summary of the tool arguments (all args are public lookups, safe to log)."""
    try:
        parts = [f"{k}={repr(v)[:80]}" for k, v in arguments.items()]
        s = ", ".join(parts)
        return s[:200]
    except Exception:
        return "<unprintable>"


class CallLogWrapper:
    """Wraps FastMCP.call_tool; one mcp_call_log row per invocation."""

    def __init__(self) -> None:
        # One session id per server process lifetime. A single long-lived HTTP
        # process serves many clients; session granularity at the process level
        # is honest about what we can attribute without request-context plumbing.
        self.session_id = f"proc-{uuid.uuid4().hex[:12]}"

    def install(self, mcp: Any) -> None:
        original = mcp.call_tool
        print(f"[call-logger] installed on {type(mcp).__name__}", flush=True)

        async def logged_call_tool(name: str, arguments: dict[str, Any], *a: Any, **kw: Any):
            global _warned
            t0 = time.monotonic()
            is_error = False
            try:
                return await original(name, arguments, *a, **kw)
            except Exception:
                is_error = True
                raise
            finally:
                duration_ms = int((time.monotonic() - t0) * 1000)
                row = (
                    self.session_id,
                    name,
                    _summarize_args(arguments),
                    duration_ms,
                    is_error,
                    "streamable-http",
                )
                try:
                    c = _conn()
                    cur = c.cursor()
                    cur.execute(_INSERT_SQL, row)
                    cur.close()
                except Exception as e:  # logging must never break a tool call
                    if not _warned:
                        print(f"[call-logger] DB logging disabled: {e}", flush=True)
                        _warned = True

        mcp.call_tool = logged_call_tool
        # FastMCP.__init__ registered the ORIGINAL call_tool as the low-level
        # handler (`self._mcp_server.call_tool()(self.call_tool)`), so swapping
        # the attribute alone is not enough for the HTTP transport: re-register
        # the wrapped function on the low-level server.
        try:
            mcp._mcp_server.call_tool(validate_input=False)(logged_call_tool)
            print("[call-logger] low-level handler re-registered", flush=True)
        except Exception as e:
            print(f"[call-logger] handler re-registration failed: {e}", flush=True)
