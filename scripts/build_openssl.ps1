param(
    [Parameter(Mandatory = $true)]
    [string] $Version,

    [Parameter(Mandatory = $false)]
    [string] $Name = "",

    [Parameter(Mandatory = $true)]
    [ValidateSet("x86", "x64")]
    [string] $Arch,

    [Parameter(Mandatory = $true)]
    [ValidateSet("static", "shared")]
    [string] $Linkage,

    [Parameter(Mandatory = $true)]
    [string] $Target,

    [Parameter(Mandatory = $false)]
    [ValidateSet("no-shared", "shared")]
    [string] $SharedOption = ""
)

$ErrorActionPreference = "Stop"
if (Get-Variable -Name PSNativeCommandUseErrorActionPreference -ErrorAction SilentlyContinue) {
    $PSNativeCommandUseErrorActionPreference = $false
}

function Require-Command {
    param([string] $Name)
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "$Name is required but was not found on PATH"
    }
}

function Invoke-CheckedCommand {
    param(
        [Parameter(Mandatory = $true)]
        [string] $FilePath,

        [Parameter(ValueFromRemainingArguments = $true)]
        [string[]] $Arguments
    )

    $previousErrorActionPreference = $ErrorActionPreference
    $previousNativePreference = $null
    if (Get-Variable -Name PSNativeCommandUseErrorActionPreference -ErrorAction SilentlyContinue) {
        $previousNativePreference = $PSNativeCommandUseErrorActionPreference
        $PSNativeCommandUseErrorActionPreference = $false
    }

    try {
        $ErrorActionPreference = "Continue"
        & $FilePath @Arguments
        $exitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previousErrorActionPreference
        if ($null -ne $previousNativePreference) {
            $PSNativeCommandUseErrorActionPreference = $previousNativePreference
        }
    }

    if ($exitCode -ne 0) {
        throw "$FilePath $($Arguments -join ' ') failed with exit code $exitCode"
    }
}

function Import-VisualStudioEnvironment {
    param([string] $Arch)

    $vcvarsCandidates = @(
        (Join-Path $env:ProgramFiles "Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvarsall.bat"),
        (Join-Path $env:ProgramFiles "Microsoft Visual Studio\2022\Enterprise\VC\Auxiliary\Build\vcvarsall.bat"),
        (Join-Path $env:ProgramFiles "Microsoft Visual Studio\2022\Professional\VC\Auxiliary\Build\vcvarsall.bat"),
        (Join-Path ${env:ProgramFiles(x86)} "Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvarsall.bat")
    )

    $vcvars = $vcvarsCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1

    if (-not $vcvars) {
        $vswhere = Join-Path ${env:ProgramFiles(x86)} "Microsoft Visual Studio\Installer\vswhere.exe"
        if (-not (Test-Path $vswhere)) {
            throw "vswhere.exe was not found. Visual Studio Build Tools are required."
        }

        $installPath = & $vswhere -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
        if (-not $installPath) {
            throw "Visual Studio installation with C++ tools was not found."
        }

        $vcvars = Join-Path $installPath "VC\Auxiliary\Build\vcvarsall.bat"
    }

    if (-not (Test-Path $vcvars)) {
        throw "vcvarsall.bat was not found at $vcvars"
    }

    $vcArch = if ($Arch -eq "x86") { "x86" } else { "amd64" }
    Write-Host "Loading Visual Studio environment from $vcvars for $vcArch"
    cmd /c "`"$vcvars`" $vcArch && set" | ForEach-Object {
        if ($_ -match "^(.*?)=(.*)$") {
            Set-Item -Path "env:$($matches[1])" -Value $matches[2]
        }
    }
}

$env:PATH = "C:\Strawberry\perl\bin;C:\Program Files\NASM;$env:PATH"

Import-VisualStudioEnvironment -Arch $Arch
Require-Command perl
Require-Command nasm
Require-Command nmake

$sourcePath = Join-Path $PWD "source\openssl-$Version"
$installPath = Join-Path $PWD "dist\openssl-$Version-win$($Arch -replace 'x86','32' -replace 'x64','64')-$Linkage"

if (-not (Test-Path $sourcePath)) {
    throw "OpenSSL source directory was not found: $sourcePath"
}

Push-Location $sourcePath
try {
    if (-not $SharedOption) {
        $SharedOption = if ($Linkage -eq "static") { "no-shared" } else { "shared" }
    }

    Write-Host "===== $Name ====="
    Write-Host "OpenSSL version: $Version"
    Write-Host "Architecture: $Arch"
    Write-Host "Target: $Target"
    Write-Host "Shared option: $SharedOption"
    Write-Host "Install directory: $installPath"
    Invoke-CheckedCommand perl -v
    Invoke-CheckedCommand nasm -v

    New-Item -ItemType Directory -Force -Path $installPath | Out-Null

    $configureArgs = @($Target, $SharedOption, "--prefix=$installPath", "--openssldir=$installPath\ssl", "no-makedepend")

    Write-Host "Configuring OpenSSL $Version for $Arch $Linkage"
    Invoke-CheckedCommand perl @("Configure") @configureArgs

    Write-Host "Building OpenSSL"
    Invoke-CheckedCommand nmake

    Write-Host "Installing OpenSSL into $installPath"
    Invoke-CheckedCommand nmake install
}
finally {
    Pop-Location
}

if (-not (Test-Path $installPath)) {
    throw "Install directory was not created: $installPath"
}
