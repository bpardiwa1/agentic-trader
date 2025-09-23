param(
  [string]$src = (Resolve-Path ".").Path,
  [string]$destRoot = "$env:USERPROFILE\AgenticAI_Backups",
  [string]$label = (Get-Date -Format "yyyyMMdd-HHmm")
)
$dest = Join-Path $destRoot "agentic-trader-$label"
New-Item -ItemType Directory -Force -Path $dest | Out-Null
# Copy everything except .venv, __pycache__, .git
robocopy $src $dest /MIR /XD ".venv" ".git" "__pycache__" "app\__pycache__" "app\agents\__pycache__" "app\strategies\__pycache__" | Out-Null
Write-Host "Copied to: $dest"
