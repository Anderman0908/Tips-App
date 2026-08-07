"""Optional GitHub-backed persistence for Tips on ephemeral hosts.

On hosts like Streamlit Community Cloud, the local filesystem is wiped on
every sleep/redeploy. This module makes the app pull its data from a
GitHub repo on startup and push every change straight back, so a private
repo doubles as free persistent storage.

It is entirely opt-in: if the required environment variables aren't set,
every function here is a silent no-op and Competition.py behaves exactly
as it did before (plain local files). This keeps local development and
the test suite untouched.

Required environment variables to enable it:
    PIRATE_WHIST_GITHUB_TOKEN   - a GitHub token with 'contents: write'
                                   access to the target repo
    PIRATE_WHIST_GITHUB_REPO    - "owner/repo"

Optional:
    PIRATE_WHIST_GITHUB_BRANCH       - defaults to "main"
    PIRATE_WHIST_GITHUB_DATA_PATH    - path *within the repo* for the JSON
                                        file, defaults to "data/competition_data.json"
    PIRATE_WHIST_GITHUB_AVATAR_PATH  - path *within the repo* for the avatars
                                        folder, defaults to "data/avatars"
"""

import base64
import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional

GITHUB_TOKEN = os.environ.get("PIRATE_WHIST_GITHUB_TOKEN")
GITHUB_REPO = os.environ.get("PIRATE_WHIST_GITHUB_REPO")
GITHUB_BRANCH = os.environ.get("PIRATE_WHIST_GITHUB_BRANCH", "main")
DATA_REPO_PATH = os.environ.get("PIRATE_WHIST_GITHUB_DATA_PATH", "data/competition_data.json")
AVATAR_REPO_DIR = os.environ.get("PIRATE_WHIST_GITHUB_AVATAR_PATH", "data/avatars")

_API_ROOT = "https://api.github.com"
_TIMEOUT_SECONDS = 10


def enabled() -> bool:
    """Whether GitHub-backed persistence is configured at all."""
    return bool(GITHUB_TOKEN and GITHUB_REPO)


def _contents_url(repo_path: str) -> str:
    return f"{_API_ROOT}/repos/{GITHUB_REPO}/contents/{repo_path}"


def _request(method: str, url: str, body: Optional[dict] = None) -> Optional[dict]:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    request = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {GITHUB_TOKEN}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "pirate-whist-backup",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=_TIMEOUT_SECONDS) as response:
            raw = response.read()
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return None
        raise RuntimeError(f"GitHub API {method} {url} fejlede: {error.code} {error.reason}") from error
    except urllib.error.URLError as error:
        raise RuntimeError(f"GitHub API {method} {url} kunne ikke nås: {error.reason}") from error


def pull_file(local_path: Path, repo_path: str) -> bool:
    """Download repo_path into local_path. Returns True if a remote copy was found."""
    if not enabled():
        return False
    result = _request("GET", f"{_contents_url(repo_path)}?ref={GITHUB_BRANCH}")
    if not result or "content" not in result:
        return False
    local_path.parent.mkdir(parents=True, exist_ok=True)
    local_path.write_bytes(base64.b64decode(result["content"]))
    return True


def pull_directory(local_dir: Path, repo_dir: str) -> int:
    """Download every file in repo_dir into local_dir. Returns the count fetched."""
    if not enabled():
        return 0
    listing = _request("GET", f"{_contents_url(repo_dir)}?ref={GITHUB_BRANCH}")
    if not listing or not isinstance(listing, list):
        return 0
    local_dir.mkdir(parents=True, exist_ok=True)
    fetched = 0
    for entry in listing:
        if entry.get("type") != "file":
            continue
        if pull_file(local_dir / entry["name"], f"{repo_dir}/{entry['name']}"):
            fetched += 1
    return fetched


def push_file(local_path: Path, repo_path: str, message: str) -> None:
    """Upload local_path to repo_path, creating or updating it as needed."""
    if not enabled() or not local_path.exists():
        return
    existing = _request("GET", f"{_contents_url(repo_path)}?ref={GITHUB_BRANCH}")
    body = {
        "message": message,
        "content": base64.b64encode(local_path.read_bytes()).decode("ascii"),
        "branch": GITHUB_BRANCH,
    }
    if existing and "sha" in existing:
        body["sha"] = existing["sha"]
    _request("PUT", _contents_url(repo_path), body)


def delete_file(repo_path: str, message: str) -> None:
    """Delete repo_path from the repo, if it exists there."""
    if not enabled():
        return
    existing = _request("GET", f"{_contents_url(repo_path)}?ref={GITHUB_BRANCH}")
    if not existing or "sha" not in existing:
        return
    _request(
        "DELETE",
        _contents_url(repo_path),
        {"message": message, "sha": existing["sha"], "branch": GITHUB_BRANCH},
    )
