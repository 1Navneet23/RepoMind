import os
import time
import base64
from typing import Optional

import requests
from dotenv import load_dotenv

load_dotenv()

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
HEADERS: dict = {"Authorization": f"Token {GITHUB_TOKEN}"}
ALLOWED_EXTENSIONS = {".py"}


# FIX #1: now correctly uses the passed-in `headers` param (was using global HEADERS)
def make_request(url: str, headers: dict, retries: int = 3) -> Optional[dict | list]:
    for i in range(retries):
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            return response.json()
        elif response.status_code == 403:
            print("Rate limit hit — sleeping 60s")
            time.sleep(60)
        elif response.status_code == 404:
            print(f"{url} not found")
            return None
        elif response.status_code == 502:
            print(f"502 server error — sleeping 30s")
            time.sleep(30)
        else:
            print(f"Error {response.status_code} on attempt {i + 1}")
            time.sleep(5)
    return None


# FIX #5: rebuild URL cleanly to avoid doubling query params like per_page
def get_page(url: str, headers: dict) -> list:
    page = 1
    all_items = []
    base = url.split("?")[0]
    existing_params = url.split("?")[1] if "?" in url else ""
    while True:
        if existing_params:
            paginated_url = f"{base}?{existing_params}&page={page}&per_page=100"
        else:
            paginated_url = f"{base}?page={page}&per_page=100"
        data = make_request(paginated_url, headers)
        if not data:
            break
        all_items.extend(data)
        if len(data) < 100:
            break
        page += 1
    return all_items


def get_meta_data(owner: str, repo: str) -> dict:
    url = f"https://api.github.com/repos/{owner}/{repo}"
    data = make_request(url, HEADERS)
    if data:
        return {
            "language": data.get("language", "unknown"),
            "watchers": data.get("watchers_count", 0),
            "stars":    data.get("stargazers_count", 0),
            "created":  data.get("created_at"),
        }
    return {}


def get_issues(owner: str, repo: str) -> list:
    url = f"https://api.github.com/repos/{owner}/{repo}/issues?state=all"
    data = get_page(url, HEADERS)
    issues = []
    for item in data:
        user = item.get("user") or {}
        issues.append({
            "issue_no":      item.get("number"),
            "creator_login": user.get("login", "unknown"),
            "created_at":    item.get("created_at"),
            "state":         item.get("state"),
            "comment_count": item.get("comments", 0),
        })
    return issues


def get_prs(owner: str, repo: str) -> list:
    url = f"https://api.github.com/repos/{owner}/{repo}/pulls?state=all"
    raw_data = get_page(url, HEADERS)
    prs = []
    for item in raw_data:
        user = item.get("user") or {}
        prs.append({
            "pr_number":     item.get("number"),
            "creator_login": user.get("login", "unknown"),
            "created_at":    item.get("created_at"),
            "merged_at":     item.get("merged_at"),
            "state":         item.get("state"),
        })
    return prs


def get_all_commits(owner: str, repo: str) -> list:
    url = f"https://api.github.com/repos/{owner}/{repo}/commits"
    raw_data = get_page(url, HEADERS)
    commits = []
    for c in raw_data:
        commit_info = c.get("commit", {})
        author      = c.get("author") or {}
        author_info = commit_info.get("author", {})
        commits.append({
            "sha":           c.get("sha"),
            "creator_login": author.get("login", "unknown"),
            "created_at":    author_info.get("date"),
        })
    return commits


# FIX #4: fallback from "main" → "master" so repos with either branch name work
def get_file_tree(owner: str, repo: str, branch: str = "main") -> list:
    data = None
    for attempt_branch in [branch, "master"]:
        url = f"https://api.github.com/repos/{owner}/{repo}/git/trees/{attempt_branch}?recursive=1"
        data = make_request(url, HEADERS)
        if data:
            break
    if not data:
        print("Could not fetch repository tree for 'main' or 'master'")
        return []

    files = []
    for item in data.get("tree", []):
        path = item.get("path", "")
        if item.get("type") == "blob" and any(path.endswith(ext) for ext in ALLOWED_EXTENSIONS):
            files.append({
                "path": path,
                "type": item.get("type"),
                "size": item.get("size"),
            })
    return files


# FIX #2: replaced bare `except` with specific exceptions and proper error logging
def get_file_content(owner: str, repo: str, file_path: str) -> Optional[str]:
    url = f"https://api.github.com/repos/{owner}/{repo}/contents/{file_path}"
    data = make_request(url, HEADERS)
    if not data:
        return None
    try:
        return base64.b64decode(data["content"]).decode("utf-8")
    except (KeyError, ValueError) as e:
        print(f"Failed to decode content for {file_path}: {e}")
        return None


def get_contributor(owner: str, repo: str) -> list:
    url = f"https://api.github.com/repos/{owner}/{repo}/contributors"
    data = get_page(url, HEADERS)
    contributors = []
    for item in data:
        if item.get("type") != "Bot":
            contributors.append({
                "login":         item.get("login"),
                "contributions": item.get("contributions"),
            })
    return contributors