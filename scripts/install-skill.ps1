$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$SourceDir = Join-Path $RepoRoot "skills/koushare-cli"
$DefaultRoot = if ($env:USERPROFILE) { $env:USERPROFILE } else { [Environment]::GetFolderPath("UserProfile") }
$TargetDir = if ($args.Count -gt 0) { $args[0] } else { Join-Path $DefaultRoot ".agents/skills/koushare-cli" }

if (Test-Path -LiteralPath $TargetDir) {
    Write-Error "Refusing to replace existing skill: $TargetDir"
}

$TargetParent = Split-Path -Parent $TargetDir
New-Item -ItemType Directory -Force -Path $TargetParent | Out-Null
Copy-Item -LiteralPath $SourceDir -Destination $TargetDir -Recurse
Write-Output "Installed koushare-cli skill -> $TargetDir"
