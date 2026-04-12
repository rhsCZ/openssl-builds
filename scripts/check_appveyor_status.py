#!/usr/bin/env python3
"""Check whether the AppVeyor project is currently building."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request


RUNNING_STATUSES = {"queued", "starting", "running"}


def log(message: str) -> None:
    timestamp = dt.datetime.now(dt.UTC).strftime("%H:%M:%S")
    print(f"[{timestamp}] INFO {message}", flush=True)


def write_output(name: str, value: str) -> None:
    output_path = os.environ.get("GITHUB_OUTPUT")
    if output_path:
        with open(output_path, "a", encoding="utf-8") as handle:
            handle.write(f"{name}={value}\n")


def require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is required")
    log(f"Environment variable {name} is set")
    return value


def appveyor_api_prefix(token: str, account: str) -> str:
    if token.startswith("v2."):
        return f"/account/{urllib.parse.quote(account)}"
    return ""


def appveyor_url(path: str, api_prefix: str) -> str:
    return f"https://ci.appveyor.com/api{api_prefix}{path}"


def appveyor_request(method: str, path: str, token: str, api_prefix: str) -> dict | list:
    url = appveyor_url(path, api_prefix)
    log(f"AppVeyor API {method} {url}")
    request = urllib.request.Request(
        url,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "User-Agent": "openssl-builds-appveyor-status-checker",
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = response.read().decode("utf-8", errors="replace")
            return json.loads(body) if body.strip() else {}
    except urllib.error.HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"AppVeyor API {method} {url} failed: {exc.code} {details}") from exc
    except json.JSONDecodeError as exc:
        preview = body[:500].replace("\n", "\\n")
        raise RuntimeError(f"AppVeyor API {method} {url} returned non-JSON response: {preview}") from exc


def project_summary(project: dict) -> str:
    account = project.get("accountName") or "unknown-account"
    slug = project.get("slug") or "unknown-slug"
    repository = project.get("repositoryName") or "unknown-repository"
    branch = project.get("repositoryBranch") or "unknown-branch"
    return f"{account}/{slug} repo={repository} branch={branch}"


def find_project(projects: list[dict], project_slug: str) -> dict:
    for project in projects:
        if project.get("slug") == project_slug:
            return project
    visible = ", ".join(sorted(item.get("slug", "") for item in projects if item.get("slug"))) or "none"
    raise RuntimeError(f"AppVeyor project slug '{project_slug}' was not found. Visible projects: {visible}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--account", default=os.environ.get("APPVEYOR_ACCOUNT_NAME", ""))
    parser.add_argument("--project", default=os.environ.get("APPVEYOR_PROJECT_SLUG", ""))
    args = parser.parse_args()

    token = require_env("APPVEYOR_API_TOKEN")
    account = args.account.strip() or require_env("APPVEYOR_ACCOUNT_NAME")
    project_slug = args.project.strip() or require_env("APPVEYOR_PROJECT_SLUG")
    api_prefix = appveyor_api_prefix(token, account)

    log(f"AppVeyor account: {account}")
    log(f"AppVeyor project slug: {project_slug}")
    log(f"AppVeyor API mode: {'v2 user-level token' if api_prefix else 'classic account token'}")

    projects_response = appveyor_request("GET", "/projects", token, api_prefix)
    projects = projects_response if isinstance(projects_response, list) else []
    project = find_project(projects, project_slug)
    log(f"Found AppVeyor project: {project_summary(project)}")

    build = project.get("build") or {}
    builds = project.get("builds") or []
    if not build and builds:
        build = builds[0]

    status = build.get("status") or "unknown"
    version = build.get("version") or "unknown"
    branch = build.get("branch") or project.get("repositoryBranch") or "unknown"
    commit_id = build.get("commitId") or "unknown"
    jobs = build.get("jobs") or []
    is_busy = status.lower() in RUNNING_STATUSES

    log(f"Latest AppVeyor build version: {version}")
    log(f"Latest AppVeyor build branch: {branch}")
    log(f"Latest AppVeyor build commit: {commit_id}")
    log(f"Latest AppVeyor build status: {status}")
    log(f"AppVeyor is busy: {str(is_busy).lower()}")

    if jobs:
        log(f"Latest build contains {len(jobs)} job(s)")
        for job in jobs:
            log(f"Job {job.get('name') or job.get('jobId')}: {job.get('status') or 'unknown'}")

    write_output("status", status)
    write_output("version", version)
    write_output("is_busy", str(is_busy).lower())
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR {exc}", file=sys.stderr, flush=True)
        raise SystemExit(1)
