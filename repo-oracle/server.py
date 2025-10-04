# server.py — Repo Oracle (MCP stdio)
import os, time, json, base64, re
from typing import Dict, Any, List, Tuple, Optional
from collections import OrderedDict

import requests
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("Repo Oracle")
# Support GitHub.com and GitHub Enterprise via env var
# e.g., set GITHUB_BASE="https://ghe.myco.com/api/v3"
BASE = os.getenv("GITHUB_BASE", "https://api.github.com").rstrip("/")

# ------------------ Session memory ------------------
SESSION = {"owner": None, "repo": None}

def _use_repo(owner: Optional[str], repo: Optional[str]) -> Tuple[str, str]:
    o = owner or SESSION["owner"]
    r = repo or SESSION["repo"]
    if not o or not r:
        raise ValueError("No repo set. Call connect_repo(owner, repo) first or pass owner/repo.")
    return o, r

# ------------------ Tiny LRU cache ------------------
class LRU:
    def __init__(self, maxsize: int = 128):
        self.maxsize = maxsize
        self._d: "OrderedDict[str, Any]" = OrderedDict()

    def get(self, k: str):
        if k in self._d:
            self._d.move_to_end(k)
            return self._d[k]
        return None

    def set(self, k: str, v: Any):
        self._d[k] = v
        self._d.move_to_end(k)
        if len(self._d) > self.maxsize:
            self._d.popitem(last=False)

CACHE = LRU(128)

def _hdrs():
    token = os.getenv("GITHUB_TOKEN", "")
    return {
        "Authorization": f"Bearer {token}" if token else "",
        "Accept": "application/vnd.github+json",
        "User-Agent": "repo-oracle"
    }

def _cache_key(path: str, params: Dict[str, Any]) -> str:
    return f"{path}?{json.dumps(params, sort_keys=True)}"

def _get(path: str, params: Dict[str, Any] = None, use_cache: bool = True):
    params = params or {}
    key = _cache_key(path, params)
    if use_cache:
        hit = CACHE.get(key)
        if hit is not None:
            return {"data": hit, "from_cache": True}
    r = requests.get(BASE + path, headers=_hdrs(), params=params, timeout=12)
    if not r.ok:
        return {
            "error": f"{r.status_code}: {r.text[:200]}",
            "path": path,
            "ratelimit-remaining": r.headers.get("X-RateLimit-Remaining", ""),
            "ratelimit-reset": r.headers.get("X-RateLimit-Reset", "")
        }
    data = r.json()
    if use_cache:
        CACHE.set(key, data)
    return {
        "data": data,
        "from_cache": False,
        "link": r.headers.get("Link", ""),
        "ratelimit": r.headers.get("X-RateLimit-Remaining", "")
    }

def _get_all(path: str, params: Dict[str, Any] = None, max_pages: int = 5, sleep_s: float = 0.0):
    """
    Simple paginator for endpoints that return either a list or {items: []}.
    Follows 'page' param up to max_pages; optional small sleep to be nice to the API.
    Light retry on 403 secondary rate limit.
    """
    params = params or {}
    all_items, page = [], 1
    while page <= max_pages:
        res = _get(path, {**params, "page": page})
        if "error" in res:
            err = res["error"].lower()
            if err.startswith("403:") and "rate limit" in err:
                time.sleep(2.0)
                res = _get(path, {**params, "page": page})
                if "error" in res:
                    return res
            else:
                return res

        data = res["data"]
        if isinstance(data, list):
            if not data:
                break
            all_items.extend(data)
        else:
            items = data.get("items", [])
            if not items:
                break
            all_items.extend(items)

        link = (res.get("link") or "")
        if 'rel="next"' not in link:
            break
        page += 1
        if sleep_s:
            time.sleep(sleep_s)
    return {"data": all_items}

# ------------------ Tools ------------------
@mcp.tool()
def connect_repo(owner: str, repo: str) -> dict:
    """Stores default owner/repo in session memory."""
    SESSION["owner"], SESSION["repo"] = owner, repo
    return {"connected": True, "owner": owner, "repo": repo}

@mcp.tool()
def list_issues(owner: str = "", repo: str = "", state: str = "open",
                labels: str = "", assignee: str = "", limit: int = 20) -> dict:
    """List issues with filters; returns normalized payload (paginated, truncated if needed)."""
    o, r = _use_repo(owner or None, repo or None)
    params = {"state": state, "per_page": min(max(1, limit), 100)}
    if labels:
        params["labels"] = labels
    if assignee:
        params["assignee"] = assignee

    res = _get_all(f"/repos/{o}/{r}/issues", params, max_pages=5)
    if "error" in res:
        return res
    # exclude PRs
    items = [i for i in res["data"] if "pull_request" not in i]

    clipped = items[:limit]
    issues = [{
        "number": i.get("number"),
        "title": i.get("title"),
        "labels": [l["name"] for l in i.get("labels", [])],
        "state": i.get("state"),
        "assignee": (i.get("assignee") or {}).get("login"),
        "updated_at": i.get("updated_at"),
        "url": i.get("html_url")
    } for i in clipped]
    return {"count": len(issues), "issues": issues, "truncated": len(items) > len(clipped)}

@mcp.tool()
def summarize_pr(number: int, owner: str = "", repo: str = "") -> dict:
    """Summarize a PR: header/changes/risks/next_steps."""
    o, r = _use_repo(owner or None, repo or None)
    pr = _get(f"/repos/{o}/{r}/pulls/{number}", {})
    if "error" in pr:
        return pr
    files = _get(f"/repos/{o}/{r}/pulls/{number}/files", {})
    if "error" in files:
        files = {"data": []}
    p = pr["data"]
    header = {
        "title": p.get("title"),
        "author": (p.get("user") or {}).get("login"),
        "state": p.get("state"),
        "mergeable": p.get("mergeable")
    }
    changes = {
        "files_changed": p.get("changed_files"),
        "additions": p.get("additions"),
        "deletions": p.get("deletions"),
        "filenames": [f.get("filename") for f in files["data"]]
    }
    # Heuristic risks
    risks: List[str] = []
    if p.get("draft"):
        risks.append("Draft PR")
    if p.get("mergeable") is False:
        risks.append("Merge conflicts")
    if (p.get("additions") or 0) + (p.get("deletions") or 0) > 1500:
        risks.append("Large diff (>1500 LOC)")
    if any(fn.endswith((".yaml", ".yml", ".json")) for fn in changes["filenames"] or []):
        risks.append("Config changes included")
    # Next steps
    next_steps: List[str] = []
    if p.get("mergeable") is False:
        next_steps.append("Rebase/resolve conflicts")
    if p.get("draft"):
        next_steps.append("Mark ready for review")
    if not next_steps:
        next_steps.append("Request/collect reviews")

    return {"header": header, "changes": changes, "risks": risks, "next_steps": next_steps}

_TEXT_EXTS = (".md",".txt",".py",".js",".ts",".tsx",".jsx",".java",".go",".rb",".rs",".cpp",".c",".cs",
              ".json",".yml",".yaml",".toml",".ini",".sh",".bat",".ps1")
_TODO_RE = re.compile(r"(TODO|FIXME|HACK|NOTE)\b[:\- ]?(.*)", re.IGNORECASE)

@mcp.tool()
def find_todos(paths: List[str] = None, ref: str = "", max_files: int = 120,
               owner: str = "", repo: str = "") -> dict:
    """Walk repo tree, fetch text files, scan lines for TODO/FIXME/HACK/NOTE."""
    o, r = _use_repo(owner or None, repo or None)
    # Resolve branch
    if not ref:
        repo_meta = _get(f"/repos/{o}/{r}", {})
        if "error" in repo_meta:
            return repo_meta
        ref = repo_meta["data"].get("default_branch", "main")
    # Get tree
    tree = _get(f"/repos/{o}/{r}/git/trees/{ref}", {"recursive": 1})
    if "error" in tree:
        return tree
    wanted = set(paths or ["src", "app", "."])
    blobs = [e for e in tree["data"].get("tree", []) if e.get("type") == "blob"]

    def _wanted(path: str) -> bool:
        return path.endswith(_TEXT_EXTS) and any(
            path == p or path.startswith(p.rstrip("/") + "/") for p in wanted
        )

    todos, scanned = [], 0
    for e in blobs:
        if scanned >= max_files:
            break
        path = e.get("path", "")
        if not _wanted(path):
            continue
        # fetch content
        c = _get(f"/repos/{o}/{r}/contents/{path}", {"ref": ref})
        if "error" in c:
            continue
        data = c["data"]
        if isinstance(data, list):  # directory
            continue
        if data.get("encoding") != "base64":
            continue
        try:
            text = base64.b64decode(data["content"]).decode("utf-8", errors="replace")
        except Exception:
            continue
        scanned += 1
        for idx, line in enumerate(text.splitlines(), start=1):
            m = _TODO_RE.search(line)
            if m:
                todos.append({
                    "file": path,
                    "line": idx,
                    "tag": m.group(1).upper(),
                    "text": m.group(2).strip() or line.strip()
                })
    note = None
    if scanned >= max_files:
        note = "max_files limit reached; results truncated"
    return {"count": len(todos), "ref": ref, "scanned_files": scanned, "todos": todos, "note": note}

@mcp.tool()
def search(query: str, type: str = "issues", limit: int = 10,
           owner: str = "", repo: str = "") -> dict:
    """Wrap GitHub Search API; type = issues|prs|code. Normalized output (paginated)."""
    kind = type.lower()
    q = query.strip()
    if kind in ("issues", "prs"):
        # Use /search/issues; add qualifiers
        if kind == "prs":
            q = f"{q} is:pr"
        elif "is:issue" not in q and "is:pr" not in q:
            q = f"{q} is:issue"
        if owner or repo:
            o, r = _use_repo(owner or None, repo or None)
            q = f"{q} repo:{o}/{r}"
        res = _get_all("/search/issues", {"q": q, "per_page": min(max(1, limit), 100)}, max_pages=3)
        if "error" in res:
            return res
        items = res["data"][:limit]
        norm = [{
            "type": ("pr" if i.get("pull_request") else "issue"),
            "number": i.get("number"),
            "title": i.get("title"),
            "state": i.get("state"),
            "score": i.get("score"),
            "url": i.get("html_url")
        } for i in items]
        return {"count": len(norm), "items": norm, "query": q, "truncated": len(res["data"]) > len(items)}
    elif kind == "code":
        if owner or repo:
            o, r = _use_repo(owner or None, repo or None)
            q = f"{q} repo:{o}/{r}"
        res = _get_all("/search/code", {"q": q, "per_page": min(max(1, limit), 100)}, max_pages=3)
        if "error" in res:
            return res
        items = res["data"][:limit]
        norm = [{
            "path": i.get("path"),
            "repo": i.get("repository", {}).get("full_name"),
            "url": i.get("html_url"),
            "score": i.get("score")
        } for i in items]
        return {"count": len(norm), "items": norm, "query": q, "truncated": len(res["data"]) > len(items)}
    else:
        return {"error": "type must be one of: issues | prs | code", "query": q}

# Optional: quick health check
@mcp.tool()
def health_check() -> dict:
    return {
        "status": "ok" if os.getenv("GITHUB_TOKEN") else "degraded",
        "has_token": bool(os.getenv("GITHUB_TOKEN")),
        "cached_keys": len(CACHE._d)
    }

# ------------------ Entrypoint ------------------
if __name__ == "__main__":
    print("[startup] Repo Oracle MCP starting…", flush=True)
    print("[startup] Tools: connect_repo, list_issues, summarize_pr, find_todos, search, health_check", flush=True)
    mcp.run()  # stdio
