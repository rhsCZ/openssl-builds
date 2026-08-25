# OpenSSL Windows Builds

[![Build status](https://ci.appveyor.com/api/projects/status/5seyaa8rts8u0wdr?svg=true)](https://ci.appveyor.com/project/rhsCZ/openssl-builds)

This repository contains CI/CD glue for automated Windows builds of upstream OpenSSL. It does not vendor OpenSSL sources. Every AppVeyor job downloads the official OpenSSL source archive for the requested version, builds it, packages the install output, and uploads the zip file to the matching GitHub Release.

## Build Status

- AppVeyor project: https://ci.appveyor.com/project/rhsCZ/openssl-builds
- AppVeyor build history: https://ci.appveyor.com/project/rhsCZ/openssl-builds/history

## Repository Layout

```text
.github/workflows/check-openssl.yml  GitHub Actions release orchestrator
.github/workflows/check-appveyor-status.yml  Manual AppVeyor status check
.github/workflows/keepalive.yml      Monthly keepalive commit for scheduled workflows
appveyor.yml                         AppVeyor Windows build matrix
config/release.json                  Human-readable release configuration
state/keepalive.json                 Timestamp for monthly keepalive commit
scripts/find_latest_openssl.py       Parses supported upstream OpenSSL branch releases
scripts/plan_release.py              Selects the next pending non-EOL release to build
scripts/create_github_release.py     Creates or reuses the git tag and GitHub Release
scripts/check_appveyor_status.py     Checks whether AppVeyor is idle or already building
scripts/start_appveyor_build.py      Starts AppVeyor without waiting for completion
scripts/update_keepalive.py          Updates keepalive state for scheduled workflow activity
scripts/download_openssl.ps1         Downloads and extracts official OpenSSL source
scripts/build_openssl.ps1            Builds and installs OpenSSL with MSVC
scripts/package_artifacts.ps1        Packs usable install output into zip artifacts
scripts/upload_release_assets.ps1    Uploads AppVeyor artifacts to the GitHub Release
```

## Flow

1. GitHub Actions runs on schedule or through `workflow_dispatch`.
2. `scripts/plan_release.py` reads `config/release.json`, loads the latest release for each currently supported OpenSSL branch from `https://openssl-library.org/source/`, parses the published End-of-Life dates, and ignores branches that are already past EOL.
3. The workflow selects the lowest pending non-EOL version for the current run. This prevents older supported security updates from being skipped when a newer branch also exists, while still respecting that AppVeyor can build only one OpenSSL version at a time.
4. If there is no pending version, the workflow logs the detected state and exits successfully.
5. If there is a pending version, `scripts/check_appveyor_status.py` checks whether AppVeyor is already queued, starting, or running.
6. If AppVeyor is busy, the workflow logs the current AppVeyor state and exits successfully without creating a tag, release, or new build.
7. If AppVeyor is idle, `scripts/create_github_release.py` creates or reuses the tag and GitHub Release.
8. `scripts/start_appveyor_build.py` starts AppVeyor with `OPENSSL_VERSION`, `GITHUB_RELEASE_TAG`, `GITHUB_REPOSITORY`, and `GITHUB_RELEASE_TOKEN`, then exits without waiting for the Windows build.
9. AppVeyor runs four jobs: `x86 static`, `x86 shared`, `x64 static`, and `x64 shared`.
10. Each AppVeyor job downloads the official OpenSSL archive, builds it with Visual Studio, NASM, and Perl, packages the install directory, and uploads the zip as a GitHub Release asset.

## Required Secrets

Configure these secrets in GitHub Actions:

| Secret | Purpose |
| --- | --- |
| `APPVEYOR_API_TOKEN` | AppVeyor API token used by GitHub Actions to check project status and start builds. |
| `APPVEYOR_ACCOUNT_NAME` | AppVeyor account name that owns the project. |
| `APPVEYOR_PROJECT_SLUG` | AppVeyor project slug for this repository. |
| `GH_RELEASE_UPLOAD_TOKEN` | GitHub token passed to AppVeyor for release asset uploads. It needs `contents:write` access to this repository. |

`GITHUB_TOKEN` is provided automatically by GitHub Actions and is used to create tags and releases.

## Manual Run

Open the `Check OpenSSL Release` workflow in GitHub Actions and choose `Run workflow`.

Optional inputs:

| Input | Meaning |
| --- | --- |
| `version` | Force a specific OpenSSL version, for example `3.6.0`. |
| `allow_prereleases` | Allow versions containing `alpha`, `beta`, `rc`, `pre`, or `dev`. |

Forced runs are useful for retrying a release after fixing AppVeyor configuration.

The `Check AppVeyor Status` workflow is also available for manual diagnostics. It only reads AppVeyor state and prints whether the project is idle or busy.

The `Keepalive` workflow runs monthly and creates a small dummy commit in `state/keepalive.json` so GitHub does not disable scheduled workflows due to repository inactivity.

## Artifacts

Release assets are named consistently:

```text
openssl-<version>-win32-static.zip
openssl-<version>-win32-shared.zip
openssl-<version>-win64-static.zip
openssl-<version>-win64-shared.zip
```

Each zip contains the installed OpenSSL output from `nmake install`: headers, libraries, binaries, documentation, and runtime files where applicable.

## Configuration

Edit `config/release.json` to change release behavior:

| Key | Meaning |
| --- | --- |
| `allow_prereleases` | Enables alpha, beta, rc, pre, and dev versions by default. |
| `openssl_source_url` | Downloads page used to discover the latest release for each supported OpenSSL branch and its published End-of-Life date. |
| `tag_pattern` | Tag format. Must contain `{version}`. |
| `release_name_pattern` | Base GitHub Release title format. Must contain `{version}`. Releases from upstream LTS branches automatically get ` (LTS)` appended. |
| `release_body_template` | GitHub Release body template. Must contain `{version}`. |
| `appveyor_branch` | Branch AppVeyor should build when triggered from GitHub Actions. |

To change the scheduled check interval, edit the `schedule` cron expression directly in `.github/workflows/check-openssl.yml`.
To change the keepalive interval, edit the `schedule` cron expression directly in `.github/workflows/keepalive.yml`.

## Build Matrix

The AppVeyor matrix lives in `appveyor.yml`.

Each variant is defined by:

| Variable | Meaning |
| --- | --- |
| `NAME` | AppVeyor variant name, for example `Win32-static`. |
| `ARCH` | `x86` or `x64`. |
| `CONFIG` | OpenSSL Configure target, currently `VC-WIN32` or `VC-WIN64A`. |
| `SHARED` | OpenSSL linkage option, `no-shared` or `shared`. |
| `LINKAGE` | Artifact naming value, `static` or `shared`. |

Add or remove matrix entries to change the output set. Keep artifact naming aligned with `scripts/package_artifacts.ps1`.

## Assumptions and Limitations

- This repository intentionally does not store OpenSSL source archives or extracted source trees.
- The source discovery script reads the latest release for each supported branch from the OpenSSL Downloads page and skips branches whose published End-of-Life is already in the past.
- Tags matching `tag_pattern` are the primary source of truth for processed versions.
- The release planner builds at most one OpenSSL version per workflow run so AppVeyor is never asked to build multiple OpenSSL versions in parallel.
- GitHub Actions checks AppVeyor before creating a release, so a running AppVeyor build does not produce another release or build request.
- GitHub Actions creates the release before starting AppVeyor. If AppVeyor later fails, the release may remain empty or partial for investigation and retry.
- AppVeyor uploads assets directly to GitHub Releases. Use a fine-scoped token for `GH_RELEASE_UPLOAD_TOKEN`.
- GitHub Actions does not wait for AppVeyor by default, so release orchestration does not spend Actions minutes while Windows builds run.
- The workflow schedule is defined in YAML because GitHub Actions does not read cron values dynamically from repository config.
- A separate monthly keepalive commit is used to reduce the chance that GitHub disables scheduled workflows after long repository inactivity.

## Troubleshooting

### NASM is not on PATH

AppVeyor installs NASM with Chocolatey and explicitly prepends `C:\Program Files\NASM` to `PATH`. If `nasm -v` fails, check the AppVeyor image, Chocolatey logs, and PATH in the install phase.

### Perl problem

The build uses Strawberry Perl already available on the Visual Studio 2022 AppVeyor image and explicitly prepends `C:\Strawberry\perl\bin` to `PATH`. If `perl Configure` fails before OpenSSL configuration starts, verify that `perl --version` works and that AppVeyor did not pick up another incompatible Perl first on PATH.

### AppVeyor artifact not found

Check `scripts/package_artifacts.ps1`. The script expects `dist/openssl-<version>-<win32|win64>-<static|shared>` to exist after `nmake install`. If the build completed but packaging failed, inspect the install prefix printed by `scripts/build_openssl.ps1`.

### Release asset upload failed

Verify `GH_RELEASE_UPLOAD_TOKEN` has `contents:write` access and is passed from GitHub Actions to AppVeyor. The upload script deletes an existing asset with the same name before uploading, so retries are idempotent.

### AppVeyor build failed after release creation

Fix the build issue and run the GitHub Actions workflow manually with the same `version`. The tag and release will be reused, and AppVeyor will upload or replace the release assets.
