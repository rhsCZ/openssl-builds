param(
    [Parameter(Mandatory = $true)]
    [string] $Version,

    [Parameter(Mandatory = $true)]
    [ValidateSet("x86", "x64")]
    [string] $Arch,

    [Parameter(Mandatory = $true)]
    [ValidateSet("static", "shared")]
    [string] $Linkage
)

$ErrorActionPreference = "Stop"

function Write-Step {
    param([string] $Message)
    Write-Host ("[{0}] {1}" -f (Get-Date -Format "HH:mm:ss"), $Message)
}

$winArch = if ($Arch -eq "x86") { "win32" } else { "win64" }
$installPath = Join-Path $PWD "dist\openssl-$Version-$winArch-$Linkage"
$artifactDir = Join-Path $PWD "artifacts"
$artifactPath = Join-Path $artifactDir "openssl-$Version-$winArch-$Linkage.zip"

Write-Step "Preparing artifact package for OpenSSL $Version $winArch $Linkage"
Write-Step "Install path: $installPath"
Write-Step "Artifact directory: $artifactDir"
Write-Step "Artifact path: $artifactPath"

if (-not (Test-Path $installPath)) {
    throw "Install directory was not found: $installPath"
}

Write-Step "Creating artifact directory"
New-Item -ItemType Directory -Force -Path $artifactDir | Out-Null
if (Test-Path $artifactPath) {
    Write-Step "Removing existing artifact $artifactPath"
    Remove-Item $artifactPath -Force
}

Write-Step "Packing $artifactPath"
Compress-Archive -Path (Join-Path $installPath "*") -DestinationPath $artifactPath

if (-not (Test-Path $artifactPath)) {
    throw "Artifact was not created: $artifactPath"
}

$artifact = Get-Item -Path $artifactPath
Write-Step "Created artifact $($artifact.Name) ($($artifact.Length) bytes)"
