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


def appveyor_url(path: str, api_prefix: str) -> str:
    return f"https://ci.appveyor.com/api{api_prefix}{path}"


def appveyor_http(method: str, path: str, token: str, api_prefix: str, payload: dict | None = None) -> tuple[int, str, str]:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    url = appveyor_url(path, api_prefix)
    request = urllib.request.Request(
        url,
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
            body = response.read().decode("utf-8", errors="replace")
            return response.status, response.headers.get("Content-Type", ""), body
    except urllib.error.HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"AppVeyor API {method} {url} failed: {exc.code} {details}") from exc


def appveyor_request(method: str, path: str, token: str, api_prefix: str, payload: dict | None = None) -> dict | list:
    status, content_type, body = appveyor_http(method, path, token, api_prefix, payload)
    if not body.strip():
        return {}
    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        preview = body[:500].replace("\n", "\\n")
        raise RuntimeError(
            f"AppVeyor API {method} {appveyor_url(path, api_prefix)} returned non-JSON response "
            f"(status={status}, content-type={content_type!r}): {preview}"
        ) from exc


def appveyor_text_request(method: str, path: str, token: str, api_prefix: str) -> str:
    _, _, body = appveyor_http(method, path, token, api_prefix)
    return body


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


def print_failed_job_logs(build: dict, token: str, api_prefix: str) -> None:
    jobs = build.get("jobs") or []
    if not jobs:
        print("No AppVeyor jobs found in build response.")
        return

    for job in jobs:
        job_id = job.get("jobId")
        if not job_id:
            continue

        job_name = job.get("name") or job_id
        job_status = job.get("status") or "unknown"
        print(f"--- AppVeyor job {job_name} status={job_status} log tail ---")
        try:
            log = appveyor_text_request("GET", f"/buildjobs/{job_id}/log", token, api_prefix)
        except Exception as exc:
            print(f"Could not download AppVeyor log for job {job_id}: {exc}")
            continue

        lines = log.splitlines()
        for line in lines[-120:]:
            print(line)


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
        project_status = appveyor_request("GET", f"/projects/{account}/{project}/build/{version}", token, api_prefix)
        current_build = project_status.get("build", {})

        status = current_build.get("status", "unknown")
        print(f"AppVeyor build {version} status: {status}")
        if status == "success":
            return 0
        if status in {"failed", "cancelled"}:
            print_failed_job_logs(current_build, token, api_prefix)
            raise RuntimeError(f"AppVeyor build {version} ended with status {status}")
        time.sleep(poll_seconds)

    raise RuntimeError(f"Timed out waiting for AppVeyor build {version}")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1)
