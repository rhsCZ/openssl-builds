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

$winArch = if ($Arch -eq "x86") { "win32" } else { "win64" }
$installPath = Join-Path $PWD "dist\openssl-$Version-$winArch-$Linkage"
$artifactDir = Join-Path $PWD "artifacts"
$artifactPath = Join-Path $artifactDir "openssl-$Version-$winArch-$Linkage.zip"

if (-not (Test-Path $installPath)) {
    throw "Install directory was not found: $installPath"
}

New-Item -ItemType Directory -Force -Path $artifactDir | Out-Null
if (Test-Path $artifactPath) {
    Remove-Item $artifactPath -Force
}

Write-Host "Packing $artifactPath"
Compress-Archive -Path (Join-Path $installPath "*") -DestinationPath $artifactPath

if (-not (Test-Path $artifactPath)) {
    throw "Artifact was not created: $artifactPath"
}
