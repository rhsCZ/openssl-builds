#!/usr/bin/env python3
"""Find supported OpenSSL releases from the official downloads page."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
import urllib.request
from dataclasses import dataclass
from datetime import date
from html.parser import HTMLParser


VERSION_RE = re.compile(r"openssl-([0-9]+\.[0-9]+\.[0-9]+[a-z]?(?:[-A-Za-z0-9.]+)?)\.tar\.gz")
PRERELEASE_RE = re.compile(r"(alpha|beta|rc|pre|dev)", re.IGNORECASE)
DATE_FORMAT = "%d %b %Y"


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


def version_series(version: str) -> str:
    main = version.partition("-")[0]
    match = re.match(r"^([0-9]+)\.([0-9]+)\.", main)
    if not match:
        raise ValueError(f"Unsupported OpenSSL version format: {version}")
    return f"{match.group(1)}.{match.group(2)}"


@dataclass(frozen=True)
class SupportedRelease:
    series: str
    version: str
    release_date: date
    end_of_life: date
    is_lts: bool


class DownloadsTableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.in_tbody = False
        self.in_tr = False
        self.in_td = False
        self.current_cell: list[str] = []
        self.current_row: list[str] = []
        self.rows: list[list[str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "tbody":
            self.in_tbody = True
        elif tag == "tr" and self.in_tbody:
            self.in_tr = True
            self.current_row = []
        elif tag == "td" and self.in_tr:
            self.in_td = True
            self.current_cell = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "td" and self.in_td:
            self.current_row.append("".join(self.current_cell).strip())
            self.in_td = False
        elif tag == "tr" and self.in_tr:
            if self.current_row:
                self.rows.append(self.current_row)
            self.in_tr = False
        elif tag == "tbody":
            self.in_tbody = False

    def handle_data(self, data: str) -> None:
        if self.in_td:
            self.current_cell.append(data)


def load_config(path: str) -> dict:
    log(f"Loading config from {path}")
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def fetch_html(source_url: str) -> str:
    log(f"Fetching OpenSSL source index from {source_url}")
    request = urllib.request.Request(source_url, headers={"User-Agent": "openssl-builds-release-checker"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8", errors="replace")


def parse_release_date(value: str) -> date:
    return dt.datetime.strptime(value.strip(), DATE_FORMAT).date()


def parse_supported_releases(html: str, allow_prereleases: bool) -> list[SupportedRelease]:
    parser = DownloadsTableParser()
    parser.feed(html)

    releases: list[SupportedRelease] = []
    for row in parser.rows:
        if len(row) < 5:
            continue

        series_label, filename, _, release_text, eol_text = row[:5]
        match = VERSION_RE.search(filename)
        if not match:
            continue

        version = match.group(1)
        if not allow_prereleases and is_prerelease(version):
            continue

        series = series_label.replace("[LTS]", "").strip()
        releases.append(
            SupportedRelease(
                series=series,
                version=version,
                release_date=parse_release_date(release_text),
                end_of_life=parse_release_date(eol_text),
                is_lts="[LTS]" in series_label,
            )
        )

    releases.sort(key=lambda item: version_key(item.version))
    return releases


def supported_versions_from_html(html: str, allow_prereleases: bool) -> list[str]:
    log("Parsing OpenSSL releases from source index")
    versions = [release.version for release in parse_supported_releases(html, allow_prereleases)]
    log(f"Found {len(versions)} OpenSSL release candidate(s)")

    if not versions:
        raise RuntimeError("No OpenSSL versions found in source index")

    return versions


def find_supported_releases(source_url: str, allow_prereleases: bool) -> list[SupportedRelease]:
    html = fetch_html(source_url)
    releases = parse_supported_releases(html, allow_prereleases)
    if not releases:
        raise RuntimeError("No supported OpenSSL releases found in source index")
    log(
        "Supported branch releases: "
        + ", ".join(
            f"{release.series}->{release.version} (EOL {release.end_of_life.isoformat()})"
            for release in releases
        )
    )
    return releases


def find_supported_versions(source_url: str, allow_prereleases: bool) -> list[str]:
    versions = [release.version for release in find_supported_releases(source_url, allow_prereleases)]
    log(f"Supported branch versions: {', '.join(versions)}")
    return versions


def find_release_by_version(source_url: str, version: str, allow_prereleases: bool) -> SupportedRelease | None:
    for release in find_supported_releases(source_url, allow_prereleases):
        if release.version == version:
            return release
    return None


def find_latest(source_url: str, allow_prereleases: bool) -> str:
    versions = find_supported_versions(source_url, allow_prereleases)
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
