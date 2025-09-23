param(
  [string]$src = (Resolve-Path ".").Path,
  [string]$destDir = "$env:USERPROFILE\AgenticAI_Backups",
  [string]$label = (Get-Date -Format "yyyyMMdd-HHmm")
)
$new = Join-Path $destDir "agentic-trader-$label.zip"
New-Item -ItemType Directory -Force -Path $destDir | Out-Null
# Include everything, but feel free to exclude .venv if size is huge:
#   -Exclude parameter doesn't recurse; use -Filter + custom list OR 7zip if you prefer.
# Simple approach: temporarily rename .venv if you want to exclude, or just include it for a true full backup.
Compress-Archive -Path "$src\*" -DestinationPath $new -CompressionLevel Optimal -Force
Write-Host "Backup created: $new"
