param(
    [Parameter(Mandatory = $true)]
    [string] $Version,

    [Parameter(Mandatory = $true)]
    [string] $Tag,

    [Parameter(Mandatory = $true)]
    [string] $Repository
)

$ErrorActionPreference = "Stop"

function Write-Step {
    param([string] $Message)
    Write-Host ("[{0}] {1}" -f (Get-Date -Format "HH:mm:ss"), $Message)
}

Write-Step "Preparing GitHub Release asset upload for OpenSSL $Version"
Write-Step "Repository: $Repository"
Write-Step "Release tag: $Tag"

$token = $env:GITHUB_RELEASE_TOKEN
if (-not $token) {
    throw "GITHUB_RELEASE_TOKEN is required for uploading release assets"
}
Write-Step "GITHUB_RELEASE_TOKEN is set"

$artifactDir = Join-Path $PWD "artifacts"
if (-not (Test-Path $artifactDir)) {
    throw "Artifact directory was not found: $artifactDir"
}
Write-Step "Artifact directory: $artifactDir"

$headers = @{
    Authorization = "Bearer $token"
    Accept = "application/vnd.github+json"
    "X-GitHub-Api-Version" = "2022-11-28"
}

$releaseUrl = "https://api.github.com/repos/$Repository/releases/tags/$Tag"
Write-Step "Loading GitHub Release for $Repository tag $Tag"
$release = Invoke-RestMethod -Method Get -Uri $releaseUrl -Headers $headers
Write-Step "Loaded GitHub Release id=$($release.id)"

$assets = @(Get-ChildItem -Path $artifactDir -Filter "*.zip")
if ($assets.Count -eq 0) {
    throw "No zip artifacts found in $artifactDir"
}
Write-Step "Found $($assets.Count) artifact(s) to upload"

foreach ($asset in $assets) {
    Write-Step "Processing asset $($asset.Name) ($($asset.Length) bytes)"
    $existing = @($release.assets | Where-Object { $_.name -eq $asset.Name })
    foreach ($item in $existing) {
        Write-Step "Deleting existing release asset $($item.name)"
        Invoke-RestMethod -Method Delete -Uri $item.url -Headers $headers | Out-Null
    }

    $uploadUrl = "https://uploads.github.com/repos/$Repository/releases/$($release.id)/assets?name=$([uri]::EscapeDataString($asset.Name))"
    Write-Step "Uploading $($asset.Name) to release $Tag"
    Invoke-RestMethod -Method Post -Uri $uploadUrl -Headers $headers -ContentType "application/zip" -InFile $asset.FullName | Out-Null
    Write-Step "Uploaded $($asset.Name)"
}

Write-Step "Uploaded $($assets.Count) release asset(s) for OpenSSL $Version"
