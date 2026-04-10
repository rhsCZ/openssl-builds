#!/usr/bin/env python3
"""Find the latest OpenSSL version from the official source directory."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.request
from pathlib import Path


VERSION_RE = re.compile(r"openssl-([0-9]+\.[0-9]+\.[0-9]+[a-z]?(?:[-A-Za-z0-9.]+)?)\.tar\.gz")
PRERELEASE_RE = re.compile(r"(alpha|beta|rc|pre|dev)", re.IGNORECASE)


def is_prerelease(version: str) -> bool:
    return bool(PRERELEASE_RE.search(version))


def version_key(version: str) -> tuple[tuple[int, ...], int, int, str]:
    main, sep, suffix = version.partition("-")
    match = re.match(r"^([0-9]+)\.([0-9]+)\.([0-9]+)([a-z]?)$", main)
    if not match:
        raise ValueError(f"Unsupported OpenSSL version format: {version}")
    numbers = tuple(int(part) for part in match.group(1, 2, 3))
    patch_letter = ord(match.group(4)) if match.group(4) else 0
    stable_rank = 1 if not sep else 0
    return numbers, patch_letter, stable_rank, suffix


def load_config(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def find_latest(source_url: str, allow_prereleases: bool) -> str:
    request = urllib.request.Request(source_url, headers={"User-Agent": "openssl-builds-release-checker"})
    with urllib.request.urlopen(request, timeout=30) as response:
        html = response.read().decode("utf-8", errors="replace")

    versions = sorted(set(VERSION_RE.findall(html)), key=version_key)
    if not allow_prereleases:
        versions = [version for version in versions if not is_prerelease(version)]

    if not versions:
        raise RuntimeError(f"No OpenSSL versions found at {source_url}")

    return versions[-1]


def write_output(name: str, value: str) -> None:
    output_path = os.environ.get("GITHUB_OUTPUT")
    if output_path:
        with open(output_path, "a", encoding="utf-8") as handle:
            handle.write(f"{name}={value}\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config/release.json")
    parser.add_argument("--allow-prereleases", action="store_true")
    args = parser.parse_args()

    config = load_config(args.config)
    allow_prereleases = args.allow_prereleases or bool(config.get("allow_prereleases", False))
    latest = find_latest(config["openssl_source_url"], allow_prereleases)

    print(f"latest_version={latest}")
    write_output("latest_version", latest)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1)
