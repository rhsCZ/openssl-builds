#!/usr/bin/env python3
"""Plan whether a new OpenSSL release should be processed."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys

from find_latest_openssl import find_latest, is_prerelease, version_key


def load_config(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def bool_input(value: str | None) -> bool | None:
    if value is None or value == "":
        return None
    return value.lower() in {"1", "true", "yes", "on"}


def git_tags() -> list[str]:
    result = subprocess.run(["git", "tag", "--list"], check=True, capture_output=True, text=True)
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


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

    forced_version = args.version.strip()
    upstream_version = forced_version or find_latest(config["openssl_source_url"], allow_prereleases)
    if is_prerelease(upstream_version) and not allow_prereleases:
        raise RuntimeError(f"Version {upstream_version} is a prerelease and prereleases are disabled")

    tag = config["tag_pattern"].format(version=upstream_version)
    tags = git_tags()
    processed = latest_processed_version(tags, config["tag_pattern"], allow_prereleases)
    tag_exists = tag in tags

    should_build = bool(forced_version) or not processed or version_key(upstream_version) > version_key(processed)
    if tag_exists and not forced_version:
        should_build = False

    print(f"Upstream OpenSSL version: {upstream_version}")
    print(f"Last processed version: {processed or 'none'}")
    print(f"Target tag: {tag}")
    print(f"Target tag already exists: {str(tag_exists).lower()}")
    print(f"Build required: {str(should_build).lower()}")

    write_output("version", upstream_version)
    write_output("last_processed_version", processed)
    write_output("tag", tag)
    write_output("should_build", str(should_build).lower())
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1)
