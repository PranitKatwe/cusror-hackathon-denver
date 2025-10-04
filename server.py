# server.py
import os, json, duckdb, pandas as pd
from typing import Any, Dict, List
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("Data Quick Answers")

@mcp.tool()
def health_check() -> dict:
    return {"status": "ok", "cwd": os.getcwd()}

@mcp.tool()
def summarize_csv(path: str) -> dict:
    if not os.path.exists(path):
        return {"error": f"File not found: {path}"}
    con = duckdb.connect(database=":memory:")
    con.execute(f"CREATE TABLE t AS SELECT * FROM read_csv_auto('{path}', IGNORE_ERRORS=true)")
    rows = con.execute("SELECT COUNT(*) FROM t").fetchone()[0]
    cols = con.execute("PRAGMA table_info('t')").fetchall()
    return {
        "rows": rows,
        "cols": len(cols),
        "columns": [{"name": c[1], "dtype": c[2]} for c in cols]
    }

@mcp.tool()
def csv_query(path: str, sql: str, limit: int = 10) -> dict:
    if not os.path.exists(path):
        return {"error": f"File not found: {path}"}
    con = duckdb.connect(database=":memory:")
    con.execute(f"CREATE TABLE t AS SELECT * FROM read_csv_auto('{path}', IGNORE_ERRORS=true)")
    df = con.execute(f"{sql} LIMIT {limit}").df()
    return {"rows": len(df), "data": json.loads(df.to_json(orient="records"))}

if __name__ == "__main__":
    print("[startup] Data Quick Answers MCP starting...", flush=True)
    mcp.run()   # stdio transport for Cursor
