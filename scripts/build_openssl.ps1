param(
    [Parameter(Mandatory = $true)]
    [string] $Version,

    [Parameter(Mandatory = $true)]
    [ValidateSet("x86", "x64")]
    [string] $Arch,

    [Parameter(Mandatory = $true)]
    [ValidateSet("static", "shared")]
    [string] $Linkage,

    [Parameter(Mandatory = $true)]
    [string] $Target
)

$ErrorActionPreference = "Stop"

function Require-Command {
    param([string] $Name)
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "$Name is required but was not found on PATH"
    }
}

function Import-VisualStudioEnvironment {
    param([string] $Arch)

    $vswhere = Join-Path ${env:ProgramFiles(x86)} "Microsoft Visual Studio\Installer\vswhere.exe"
    if (-not (Test-Path $vswhere)) {
        throw "vswhere.exe was not found. Visual Studio Build Tools are required."
    }

    $installPath = & $vswhere -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
    if (-not $installPath) {
        throw "Visual Studio installation with C++ tools was not found."
    }

    $vcvars = Join-Path $installPath "VC\Auxiliary\Build\vcvarsall.bat"
    if (-not (Test-Path $vcvars)) {
        throw "vcvarsall.bat was not found at $vcvars"
    }

    $vcArch = if ($Arch -eq "x86") { "x86" } else { "x64" }
    Write-Host "Loading Visual Studio environment from $vcvars for $vcArch"
    cmd /c "`"$vcvars`" $vcArch && set" | ForEach-Object {
        if ($_ -match "^(.*?)=(.*)$") {
            Set-Item -Path "env:$($matches[1])" -Value $matches[2]
        }
    }
}

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
    $configureArgs = @($Target, "--prefix=$installPath", "--openssldir=$installPath\ssl")
    if ($Linkage -eq "static") {
        $configureArgs += "no-shared"
    }

    Write-Host "Configuring OpenSSL $Version for $Arch $Linkage"
    & perl Configure @configureArgs
    if ($LASTEXITCODE -ne 0) {
        throw "OpenSSL Configure failed with exit code $LASTEXITCODE"
    }

    Write-Host "Building OpenSSL"
    & nmake /S
    if ($LASTEXITCODE -ne 0) {
        throw "nmake failed with exit code $LASTEXITCODE"
    }

    Write-Host "Installing OpenSSL into $installPath"
    & nmake /S install_sw
    if ($LASTEXITCODE -ne 0) {
        throw "nmake install_sw failed with exit code $LASTEXITCODE"
    }
}
finally {
    Pop-Location
}

if (-not (Test-Path $installPath)) {
    throw "Install directory was not created: $installPath"
}
