#!/usr/bin/env python3
"""Create or reuse the Git tag and GitHub Release for an OpenSSL version."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request


def load_config(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def request_json(method: str, url: str, token: str, payload: dict | None = None) -> tuple[int, dict]:
    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "openssl-builds-release-orchestrator",
            "X-GitHub-Api-Version": "2022-11-28"
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = response.read().decode("utf-8")
            return response.status, json.loads(body) if body else {}
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return 404, {}
        details = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"GitHub API {method} {url} failed: {exc.code} {details}") from exc


def git_tag_exists(tag: str) -> bool:
    result = subprocess.run(["git", "tag", "--list", tag], check=True, capture_output=True, text=True)
    return bool(result.stdout.strip())


def ensure_git_tag(tag: str, version: str) -> None:
    subprocess.run(["git", "config", "user.name", "github-actions[bot]"], check=True)
    subprocess.run(["git", "config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com"], check=True)
    subprocess.run(["git", "fetch", "--tags", "--force"], check=True)

    if git_tag_exists(tag):
        print(f"Tag {tag} already exists; reusing it.")
        return

    subprocess.run(["git", "tag", "-a", tag, "-m", f"OpenSSL {version} Windows builds"], check=True)
    subprocess.run(["git", "push", "origin", tag], check=True)
    print(f"Created and pushed tag {tag}.")


def ensure_release(repo: str, token: str, tag: str, version: str, config: dict) -> None:
    api_base = f"https://api.github.com/repos/{repo}"
    status, _ = request_json("GET", f"{api_base}/releases/tags/{tag}", token)
    if status == 200:
        print(f"GitHub Release for {tag} already exists; reusing it.")
        return

    release_name = config["release_name_pattern"].format(version=version)
    release_body = config["release_body_template"].format(version=version)
    payload = {
        "tag_name": tag,
        "name": release_name,
        "body": release_body,
        "draft": False,
        "prerelease": any(marker in version.lower() for marker in ("alpha", "beta", "rc", "pre", "dev")),
    }
    request_json("POST", f"{api_base}/releases", token, payload)
    print(f"Created GitHub Release {release_name} for tag {tag}.")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config/release.json")
    parser.add_argument("--version", required=True)
    args = parser.parse_args()

    token = os.environ.get("GITHUB_TOKEN")
    repo = os.environ.get("GITHUB_REPOSITORY")
    if not token:
        raise RuntimeError("GITHUB_TOKEN is required")
    if not repo:
        raise RuntimeError("GITHUB_REPOSITORY is required")

    config = load_config(args.config)
    tag = config["tag_pattern"].format(version=args.version)

    ensure_git_tag(tag, args.version)
    ensure_release(repo, token, tag, args.version, config)
    print(f"release_tag={tag}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1)
