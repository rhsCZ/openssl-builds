param(
    [Parameter(Mandatory = $true)]
    [string] $Version,

    [Parameter(Mandatory = $true)]
    [string] $Tag,

    [Parameter(Mandatory = $true)]
    [string] $Repository
)

$ErrorActionPreference = "Stop"

$token = $env:GITHUB_RELEASE_TOKEN
if (-not $token) {
    throw "GITHUB_RELEASE_TOKEN is required for uploading release assets"
}

$artifactDir = Join-Path $PWD "artifacts"
if (-not (Test-Path $artifactDir)) {
    throw "Artifact directory was not found: $artifactDir"
}

$headers = @{
    Authorization = "Bearer $token"
    Accept = "application/vnd.github+json"
    "X-GitHub-Api-Version" = "2022-11-28"
}

$releaseUrl = "https://api.github.com/repos/$Repository/releases/tags/$Tag"
Write-Host "Loading GitHub Release for $Repository tag $Tag"
$release = Invoke-RestMethod -Method Get -Uri $releaseUrl -Headers $headers

$assets = @(Get-ChildItem -Path $artifactDir -Filter "*.zip")
if ($assets.Count -eq 0) {
    throw "No zip artifacts found in $artifactDir"
}

foreach ($asset in $assets) {
    $existing = @($release.assets | Where-Object { $_.name -eq $asset.Name })
    foreach ($item in $existing) {
        Write-Host "Deleting existing release asset $($item.name)"
        Invoke-RestMethod -Method Delete -Uri $item.url -Headers $headers | Out-Null
    }

    $uploadUrl = "https://uploads.github.com/repos/$Repository/releases/$($release.id)/assets?name=$([uri]::EscapeDataString($asset.Name))"
    Write-Host "Uploading $($asset.Name) to release $Tag"
    Invoke-RestMethod -Method Post -Uri $uploadUrl -Headers $headers -ContentType "application/zip" -InFile $asset.FullName | Out-Null
}

Write-Host "Uploaded $($assets.Count) release asset(s) for OpenSSL $Version"
