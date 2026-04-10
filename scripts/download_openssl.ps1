param(
    [Parameter(Mandatory = $true)]
    [string] $Version
)

$ErrorActionPreference = "Stop"

$sourceDir = Join-Path $PWD "source"
$archiveName = "openssl-$Version.tar.gz"
$archivePath = Join-Path $PWD $archiveName
$extractPath = Join-Path $sourceDir "openssl-$Version"
$downloadUrl = "https://www.openssl.org/source/$archiveName"

if (Test-Path $extractPath) {
    Write-Host "OpenSSL source already extracted at $extractPath"
    exit 0
}

New-Item -ItemType Directory -Force -Path $sourceDir | Out-Null

Write-Host "Downloading $downloadUrl"
Invoke-WebRequest -Uri $downloadUrl -OutFile $archivePath

Write-Host "Extracting $archiveName"
tar -xzf $archivePath -C $sourceDir

if (-not (Test-Path $extractPath)) {
    throw "Expected extracted directory was not found: $extractPath"
}

Write-Host "OpenSSL source is ready at $extractPath"
