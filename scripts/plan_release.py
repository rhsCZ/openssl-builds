#!/usr/bin/env python3
"""Plan whether a new OpenSSL release should be processed."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys

from find_latest_openssl import SupportedRelease, find_supported_releases, is_prerelease, version_key


def log(message: str) -> None:
    timestamp = dt.datetime.now(dt.UTC).strftime("%H:%M:%S")
    print(f"[{timestamp}] INFO {message}", flush=True)


def load_config(path: str) -> dict:
    log(f"Loading config from {path}")
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def bool_input(value: str | None) -> bool | None:
    if value is None or value == "":
        return None
    return value.lower() in {"1", "true", "yes", "on"}


def git_tags() -> list[str]:
    log("Reading existing git tags")
    result = subprocess.run(["git", "tag", "--list"], check=True, capture_output=True, text=True)
    tags = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    log(f"Found {len(tags)} git tag(s)")
    return tags


def pattern_to_regex(pattern: str) -> re.Pattern[str]:
    escaped = re.escape(pattern)
    return re.compile("^" + escaped.replace(re.escape("{version}"), r"(?P<version>.+)") + "$")


def latest_processed_version(tags: list[str], tag_pattern: str, allow_prereleases: bool) -> str:
    regex = pattern_to_regex(tag_pattern)
    versions = []
    for tag in tags:
        match = regex.match(tag)
        if not match:
            continue
        version = match.group("version")
        if allow_prereleases or not is_prerelease(version):
            versions.append(version)
    if not versions:
        return ""
    return sorted(versions, key=version_key)[-1]


def processed_versions(tags: list[str], tag_pattern: str, allow_prereleases: bool) -> list[str]:
    regex = pattern_to_regex(tag_pattern)
    versions = []
    for tag in tags:
        match = regex.match(tag)
        if not match:
            continue
        version = match.group("version")
        if allow_prereleases or not is_prerelease(version):
            versions.append(version)
    return sorted(set(versions), key=version_key)


def non_eol_supported_versions(releases: list[SupportedRelease]) -> list[str]:
    today = dt.datetime.now(dt.timezone.utc).date()
    versions = [release.version for release in releases if release.end_of_life >= today]
    return versions


def write_output(name: str, value: str) -> None:
    output_path = os.environ.get("GITHUB_OUTPUT")
    if output_path:
        with open(output_path, "a", encoding="utf-8") as handle:
            handle.write(f"{name}={value}\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config/release.json")
    parser.add_argument("--version", default="")
    parser.add_argument("--allow-prereleases-input", default="")
    args = parser.parse_args()

    config = load_config(args.config)
    allow_override = bool_input(args.allow_prereleases_input)
    allow_prereleases = bool(config.get("allow_prereleases", False) if allow_override is None else allow_override)
    log(f"Prerelease versions allowed: {str(allow_prereleases).lower()}")

    forced_version = args.version.strip()
    if forced_version:
        log(f"Using manually requested OpenSSL version {forced_version}")
    else:
        log("No manual version provided; detecting supported upstream versions")
    tags = git_tags()
    processed = processed_versions(tags, config["tag_pattern"], allow_prereleases)
    latest_processed = processed[-1] if processed else ""

    if forced_version:
        selected_version = forced_version
        supported_versions = []
        buildable_versions = []
        pending_versions = []
        selected_is_lts = False
    else:
        supported_releases = find_supported_releases(config["openssl_source_url"], allow_prereleases)
        supported_versions = [release.version for release in supported_releases]
        buildable_versions = non_eol_supported_versions(supported_releases)
        if not buildable_versions:
            raise RuntimeError("No supported non-EOL OpenSSL releases are currently available")
        pending_versions = [version for version in buildable_versions if version not in processed]
        selected_version = pending_versions[0] if pending_versions else buildable_versions[-1]
        selected_is_lts = next(
            (release.is_lts for release in supported_releases if release.version == selected_version),
            False,
        )

    if is_prerelease(selected_version) and not allow_prereleases:
        raise RuntimeError(f"Version {selected_version} is a prerelease and prereleases are disabled")

    tag = config["tag_pattern"].format(version=selected_version)
    log(f"Computed target tag {tag}")
    tag_exists = tag in tags

    should_build = bool(forced_version) or (selected_version in pending_versions and not tag_exists)

    log(f"Supported upstream versions: {', '.join(supported_versions) if supported_versions else 'manual override'}")
    log(f"Buildable non-EOL versions: {', '.join(buildable_versions) if buildable_versions else 'manual override'}")
    log(f"Pending supported versions: {', '.join(pending_versions) if pending_versions else 'none'}")
    log(f"Selected version for this run: {selected_version}")
    log(f"Selected version is LTS: {str(selected_is_lts).lower()}")
    log(f"Last processed version: {latest_processed or 'none'}")
    log(f"Target tag already exists: {str(tag_exists).lower()}")
    log(f"Build required: {str(should_build).lower()}")

    write_output("version", selected_version)
    write_output("is_lts", str(selected_is_lts).lower())
    write_output("last_processed_version", latest_processed)
    write_output("tag", tag)
    write_output("should_build", str(should_build).lower())
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR {exc}", file=sys.stderr, flush=True)
        raise SystemExit(1)
