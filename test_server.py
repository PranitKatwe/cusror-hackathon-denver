import os
from dotenv import load_dotenv
from mcp_server import list_issues, summarize_pr

# Load .env file
load_dotenv()

# Test list_issues
print("Testing list_issues for ray-project/ray...")
result = list_issues(
    owner="ray-project",
    repo="ray",
    state="open",
    per_page=5
)
print(f"✓ Found {result['count']} open issues")
if result['items']:
    print(f"  Latest: #{result['items'][0]['number']} - {result['items'][0]['title']}")

# Test summarize_pr
print("\nTesting summarize_pr...")
result = summarize_pr(
    owner="ray-project",
    repo="ray",
    pr_number=57176

)
print(f"✓ PR: {result['header']['title']}")
print(f"  Files changed: {result['stats']['files_changed']}")
print(f"  Changes: +{result['stats']['additions']} -{result['stats']['deletions']}")
print(f"  Risks: {result['risks']}")
