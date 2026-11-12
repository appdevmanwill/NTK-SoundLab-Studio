param([switch]$DebugBuild, [switch]$InitializeSigning, [switch]$Bundle, [string]$BundleToolPath)
$ErrorActionPreference = 'Stop'
$arguments = @((Join-Path $PSScriptRoot 'build.py'))
if ($DebugBuild) { $arguments += '--debug' }
if ($InitializeSigning) { $arguments += '--init-signing' }
if ($Bundle) { $arguments += '--bundle' }
if ($BundleToolPath) { $arguments += '--bundletool', $BundleToolPath }
python @arguments
if ($LASTEXITCODE -ne 0) { throw 'Android build failed. Previous artifacts were preserved.' }
