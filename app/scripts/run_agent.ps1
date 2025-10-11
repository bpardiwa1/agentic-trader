param(
    [string]$Asset = "FX",
    [string]$Port = "",
    [string]$Env = "app\env\core.env",
    [string]$Log = ""
)

Write-Host "Starting Agentic Trader ($Asset)"

# -----------------------------
# Assign default ports per asset if not specified
# -----------------------------
switch ($Asset.ToUpper()) {
    "FX" { if (-not $Port) { $Port = "8001" } }
    "XAU" { if (-not $Port) { $Port = "8002" } }
    "INDEX" { if (-not $Port) { $Port = "8003" } }
    "EQUITY" { if (-not $Port) { $Port = "8004" } }
    default { if (-not $Port) { $Port = "8010" } } # fallback
}

Write-Host "Assigned Port: $Port"

# -----------------------------
# Resolve paths
# -----------------------------
$Root = Resolve-Path "$PSScriptRoot\..\.."
$EnvDir = Join-Path $Root "app\env"
$MergedDir = Join-Path $EnvDir ".merged"
if (-not (Test-Path $MergedDir)) {
    New-Item -ItemType Directory -Path $MergedDir | Out-Null
}

# -----------------------------
# Merge env files
# -----------------------------
$EnvFiles = $Env -split ","
$MergedFile = Join-Path $MergedDir "env.$Asset.merged.env"

Write-Host "Using env file: $MergedFile"

"# --- merged env for $Asset ---" | Out-File $MergedFile -Encoding UTF8
foreach ($f in $EnvFiles) {
    $fPath = Join-Path $Root $f
    if (Test-Path $fPath) {
        Get-Content $fPath | Out-File $MergedFile -Append -Encoding UTF8
    }
    else {
        Write-Warning "env file not found: $fPath"
    }
}

# -----------------------------
# Ensure logs directory
# -----------------------------
$LogDir = Join-Path $Root "logs"
if (-not (Test-Path $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir | Out-Null
}

# -----------------------------
# Setup timestamped logs
# -----------------------------
$ts = Get-Date -Format "yyyy-MM-dd_HH-mm-ss"
if (-not $Log) {
    $Log = Join-Path $LogDir "$Asset`_$ts.log"
}
$LatestLog = Join-Path $LogDir "$Asset.latest.log"

Write-Host "Logging to $Log"
Write-Host "Latest log link: $LatestLog"

Copy-Item $Log $LatestLog -Force -ErrorAction SilentlyContinue

# -----------------------------
# Build command
# -----------------------------
$cmd = "python.exe"
$uniargs = @(
    "-m", "uvicorn", "app.main:app",
    "--host", "127.0.0.1",
    "--port", $Port
)

# -----------------------------
# Set env vars for Python
# -----------------------------
$env:ASSET = $Asset
$env:DOTENV_FILE = $MergedFile   # <-- NEW: ensure merged env is loaded

Write-Host "Running: $cmd $($uniargs -join ' ')"

# -----------------------------
# Run & mirror logs
# -----------------------------
& $cmd $uniargs | Tee-Object -FilePath $Log -Append
