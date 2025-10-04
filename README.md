# Repo Oracle - MCP Hackathon Project

**Repo Oracle** is an **MCP (Model Context Protocol)** server built for the **Cursor Hackathon**.  
It acts as an intelligent GitHub assistant that lets you query any public repository directly from **Cursor Chat** which list issues, summarize pull requests, search code, and surface TODOs all without leaving your editor.

---

## Features

| Tool | Description |
|------|--------------|
| `connect_repo` | Set a default `owner/repo` for the session |
| `list_issues` | Fetch and filter issues (state, labels, assignee) |
| `summarize_pr` | Summarize pull requests - changes, risks, next steps |
| `search` | Search issues, PRs, or code via the GitHub Search API |
| `find_todos` | Scan text files for TODO/FIXME/HACK/NOTE comments |
| `health_check` | Check server health and rate-limit status |

All endpoints are powered by the **GitHub REST API** and wrapped in a lightweight **FastMCP** stdio server.

---

## Tech Stack

- **Python 3.11+**
- [`mcp`](https://pypi.org/project/mcp/) - Model Context Protocol server
- [`requests`](https://pypi.org/project/requests/) - HTTP client for GitHub API
- **LRU Cache** for lightweight response caching  
- **Cursor IDE** as the client runtime

---

## Installation

```bash
git clone https://github.com/<your-username>/repo-oracle.git
cd repo-oracle
pip install -r requirements.txt
```

---

## Configuration

Add this configuration inside your **`.cursor/mcp.json`** file:

```json
{
  "mcpServers": {
    "repo-oracle": {
      "command": "path to your python.exe",
      "args": [
        "path to your server.py"
      ],
      "env": {
        "GITHUB_TOKEN": "YOUR_GITHUB_TOKEN"
      }
    }
  }
}
```

If you’re on **GitHub Enterprise**, you can also set:

```bash
GITHUB_BASE=https://ghe.company.com/api/v3
```

---

##  Usage

After restarting **Cursor**, open **Cursor Chat** and run the following commands:

```
connect_repo owner="ray-project" repo="ray"
list_issues state="open" limit=5
summarize_pr number=49184
search query="actor scheduling" type="issues" limit=5
find_todos paths=["src"] max_files=30
health_check
```

Each tool returns structured JSON data directly inside Cursor Chat.

---

##  Team

**Repo Oracle** was created during the **Cursor MCP Hackathon - Denver 2025** by:  
-  **Pranit Katwe**  
-  **Ratnakshi Gore**  
-  **Taahaa Dawe**

---

> “Bringing GitHub to Cursor Chat — one repo at a time.” ⚡
