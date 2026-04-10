#!/usr/bin/env python3
"""Start an AppVeyor build and wait for the result."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request


def load_config(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def appveyor_api_prefix(token: str, account: str) -> str:
    if token.startswith("v2."):
        return f"/account/{urllib.parse.quote(account)}"
    return ""


def appveyor_request(method: str, path: str, token: str, api_prefix: str, payload: dict | None = None) -> dict:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(
        f"https://ci.appveyor.com/api{api_prefix}{path}",
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "openssl-builds-release-orchestrator",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = response.read().decode("utf-8")
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"AppVeyor API {method} {path} failed: {exc.code} {details}") from exc


def require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is required")
    return value


def project_summary(project: dict) -> str:
    repository = project.get("repositoryName") or "unknown-repository"
    branch = project.get("repositoryBranch") or "unknown-branch"
    slug = project.get("slug") or "unknown-slug"
    account = project.get("accountName") or "unknown-account"
    return f"{account}/{slug} repo={repository} branch={branch}"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--config", default="config/release.json")
    args = parser.parse_args()

    config = load_config(args.config)
    token = require_env("APPVEYOR_API_TOKEN")
    account = require_env("APPVEYOR_ACCOUNT_NAME")
    project = require_env("APPVEYOR_PROJECT_SLUG")
    repository = require_env("GITHUB_REPOSITORY")
    release_token = require_env("GITHUB_RELEASE_TOKEN")
    api_prefix = appveyor_api_prefix(token, account)

    print(f"AppVeyor account: {account}")
    print(f"AppVeyor project slug: {project}")
    print(f"AppVeyor API mode: {'v2 user-level token' if api_prefix else 'classic account token'}")
    print(f"AppVeyor branch: {config.get('appveyor_branch', 'master')}")

    projects_response = appveyor_request("GET", "/projects", token, api_prefix)
    projects = projects_response if isinstance(projects_response, list) else []
    matching_projects = [item for item in projects if item.get("slug") == project]
    if not matching_projects:
        visible = ", ".join(sorted(item.get("slug", "") for item in projects if item.get("slug"))) or "none"
        raise RuntimeError(
            f"AppVeyor project slug '{project}' was not found for account '{account}'. "
            f"Projects visible to this token: {visible}"
        )

    print(f"Found AppVeyor project: {project_summary(matching_projects[0])}")

    payload = {
        "accountName": account,
        "projectSlug": project,
        "branch": config.get("appveyor_branch", "main"),
        "environmentVariables": {
            "OPENSSL_VERSION": args.version,
            "GITHUB_RELEASE_TAG": args.tag,
            "GITHUB_REPOSITORY": repository,
            "GITHUB_RELEASE_TOKEN": release_token,
        },
    }

    build = appveyor_request("POST", "/builds", token, api_prefix, payload)
    build_id = build.get("buildId") or build.get("version")
    version = build.get("version")
    print(f"Started AppVeyor build version={version} buildId={build_id} for OpenSSL {args.version}.")

    timeout_seconds = int(config.get("appveyor_timeout_minutes", 120)) * 60
    poll_seconds = int(config.get("appveyor_poll_seconds", 30))
    deadline = time.time() + timeout_seconds

    while time.time() < deadline:
        project_status = appveyor_request("GET", f"/projects/{account}/{project}", token, api_prefix)
        current_build = project_status.get("build", {})
        if version and current_build.get("version") != version:
            time.sleep(poll_seconds)
            continue

        status = current_build.get("status", "unknown")
        print(f"AppVeyor build {version} status: {status}")
        if status == "success":
            return 0
        if status in {"failed", "cancelled"}:
            raise RuntimeError(f"AppVeyor build {version} ended with status {status}")
        time.sleep(poll_seconds)

    raise RuntimeError(f"Timed out waiting for AppVeyor build {version}")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1)
