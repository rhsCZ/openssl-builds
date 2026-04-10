#!/usr/bin/env python3
"""Find the latest OpenSSL version from the official source directory."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
import urllib.request


VERSION_RE = re.compile(r"openssl-([0-9]+\.[0-9]+\.[0-9]+[a-z]?(?:[-A-Za-z0-9.]+)?)\.tar\.gz")
PRERELEASE_RE = re.compile(r"(alpha|beta|rc|pre|dev)", re.IGNORECASE)


def log(message: str) -> None:
    timestamp = dt.datetime.now(dt.UTC).strftime("%H:%M:%S")
    print(f"[{timestamp}] INFO {message}", flush=True)


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
    log(f"Loading config from {path}")
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def find_latest(source_url: str, allow_prereleases: bool) -> str:
    log(f"Fetching OpenSSL source index from {source_url}")
    request = urllib.request.Request(source_url, headers={"User-Agent": "openssl-builds-release-checker"})
    with urllib.request.urlopen(request, timeout=30) as response:
        html = response.read().decode("utf-8", errors="replace")

    log("Parsing OpenSSL tarball versions from source index")
    versions = sorted(set(VERSION_RE.findall(html)), key=version_key)
    log(f"Found {len(versions)} OpenSSL version candidate(s)")
    if not allow_prereleases:
        versions = [version for version in versions if not is_prerelease(version)]
        log(f"Filtered prereleases; {len(versions)} stable candidate(s) remain")

    if not versions:
        raise RuntimeError(f"No OpenSSL versions found at {source_url}")

    log(f"Latest selected OpenSSL version is {versions[-1]}")
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
    log(f"Prerelease versions allowed: {str(allow_prereleases).lower()}")
    latest = find_latest(config["openssl_source_url"], allow_prereleases)

    log(f"latest_version={latest}")
    write_output("latest_version", latest)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR {exc}", file=sys.stderr, flush=True)
        raise SystemExit(1)
