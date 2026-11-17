param(
    [ValidatePattern('^\d{4}\.\d{1,2}\.\d{1,2}\.\d+$')]
    [string]$Version = '2026.11.17.1',
    [string]$Distro = 'Ubuntu-26.04',
    [string]$OutputDirectory = (Join-Path $PSScriptRoot '..\..\SOFTWARE\LINUX'),
    [switch]$Flatpak
)
$ErrorActionPreference = 'Stop'
$desktopRoot = Split-Path $PSScriptRoot -Parent
$stage = Join-Path $desktopRoot ('linux-build-' + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $stage -Force | Out-Null
New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null

function LinuxPath([string]$Path) {
    $absolute = [IO.Path]::GetFullPath($Path)
    if ($absolute -notmatch '^([A-Za-z]):\\') { throw 'Use a Windows drive path.' }
    return '/mnt/' + $Matches[1].ToLowerInvariant() + '/' + $absolute.Substring(3).Replace('\','/')
}

$priorOS = $env:GOOS; $priorArch = $env:GOARCH; $priorCGO = $env:CGO_ENABLED
try {
    $env:GOOS = 'linux'; $env:CGO_ENABLED = '0'
    foreach ($arch in @('amd64', 'arm64')) {
        $env:GOARCH = $arch
        $binary = Join-Path $stage "soundlab-$arch"
        go -C $desktopRoot build -buildvcs=false -trimpath -ldflags "-s -w -X main.desktopVersion=$Version" -o $binary .
        if ($LASTEXITCODE -ne 0) { throw "Go build failed for $arch." }
    }
} finally {
    $env:GOOS = $priorOS; $env:GOARCH = $priorArch; $env:CGO_ENABLED = $priorCGO
}

$flatpakMode = if ($Flatpak) { 'flatpak' } else { 'standard' }
wsl -d $Distro --exec bash (LinuxPath (Join-Path $PSScriptRoot 'package-extras.sh')) $Version (LinuxPath $stage) (LinuxPath $OutputDirectory) $flatpakMode
if ($LASTEXITCODE -ne 0) { throw "Linux packaging failed. Build files are in $stage." }
