param(
    [Parameter(Mandatory = $true)]
    [string] $Version
)

$ErrorActionPreference = "Stop"

function Write-Step {
    param([string] $Message)
    Write-Host ("[{0}] {1}" -f (Get-Date -Format "HH:mm:ss"), $Message)
}

$sourceDir = Join-Path $PWD "source"
$archiveName = "openssl-$Version.tar.gz"
$archivePath = Join-Path $PWD $archiveName
$extractPath = Join-Path $sourceDir "openssl-$Version"
$downloadUrls = @(
    "https://www.openssl.org/source/$archiveName",
    "https://github.com/openssl/openssl/releases/download/openssl-$Version/$archiveName"
)

Write-Step "Preparing OpenSSL source download for version $Version"
Write-Step "Source directory: $sourceDir"
Write-Step "Archive path: $archivePath"
Write-Step "Extract path: $extractPath"

if (Test-Path $extractPath) {
    Write-Step "OpenSSL source already extracted at $extractPath"
    exit 0
}

Write-Step "Creating source directory"
New-Item -ItemType Directory -Force -Path $sourceDir | Out-Null

if (Test-Path $archivePath) {
    Write-Step "Removing existing archive $archivePath"
    Remove-Item $archivePath -Force
}

$downloadSucceeded = $false
foreach ($downloadUrl in $downloadUrls) {
    try {
        Write-Step "Downloading $downloadUrl"
        Invoke-WebRequest -Uri $downloadUrl -OutFile $archivePath
        Write-Step "Download finished from $downloadUrl"
        $downloadSucceeded = $true
        break
    }
    catch {
        Write-Step "Download failed from $downloadUrl"
        Write-Step $_.Exception.Message
        if (Test-Path $archivePath) {
            Write-Step "Removing partial archive $archivePath"
            Remove-Item $archivePath -Force
        }
    }
}

if (-not $downloadSucceeded) {
    throw "Failed to download $archiveName from all configured URLs"
}

Write-Step "Extracting $archiveName"
tar -xzf $archivePath -C $sourceDir
Write-Step "Extraction finished"

if (-not (Test-Path $extractPath)) {
    throw "Expected extracted directory was not found: $extractPath"
}

Write-Step "OpenSSL source is ready at $extractPath"
