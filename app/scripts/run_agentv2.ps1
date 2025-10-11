param(
    [string]$Asset = "FX",
    [string]$Port = "",
    [string]$Env = "app\env\core.env",
    [string]$Log = "",
    [switch]$Experimental  # optional CLI switch
)

Write-Host "Starting Agentic Trader ($Asset Momentum v2)"

# -----------------------------
# Assign default ports
# -----------------------------
switch ($Asset.ToUpper()) {
    "FX" { if (-not $Port) { $Port = "9101" } }
    "XAU" { if (-not $Port) { $Port = "9102" } }
    "INDEX" { if (-not $Port) { $Port = "9103" } }
    "EQUITY" { if (-not $Port) { $Port = "9104" } }
    default { if (-not $Port) { $Port = "9110" } }
}
Write-Host "Assigned Port: $Port"

# -----------------------------
# Resolve paths
# -----------------------------
$Root = Resolve-Path "$PSScriptRoot\..\.."
$EnvDir = Join-Path $Root "app\env"
$MergedDir = Join-Path $EnvDir ".merged"
if (-not (Test-Path $MergedDir)) { New-Item -ItemType Directory -Path $MergedDir | Out-Null }

# -----------------------------
# Merge env files
# -----------------------------
$EnvFiles = $Env -split ","
$MergedFile = Join-Path $MergedDir "env.$Asset.merged.env"
Write-Host "Using env file: $MergedFile"

"# --- merged env for $Asset (v2) ---" | Out-File $MergedFile -Encoding UTF8
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
if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir | Out-Null }

# -----------------------------
# Setup timestamped logs
# -----------------------------
$ts = Get-Date -Format "yyyy-MM-dd_HH-mm-ss"
if (-not $Log) { $Log = Join-Path $LogDir "$Asset`_v2_$ts.log" }
$LatestLog = Join-Path $LogDir "$Asset.latest.log"

Write-Host "Logging to $Log"
Write-Host "Latest log link: $LatestLog"
Copy-Item $Log $LatestLog -Force -ErrorAction SilentlyContinue

# -----------------------------
# Build command
# -----------------------------
$cmd = "python.exe"
$uniargs = @("-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", $Port)

# -----------------------------
# Environment variables
# -----------------------------
$env:ASSET = $Asset
$env:DOTENV_FILE = $MergedFile

# Auto-enable experimental flag based on asset or -Experimental flag
switch ($Asset.ToUpper()) {
    "FX" {
        $env:USE_EXPERIMENTAL_FX = "true"
        $env:USE_EXPERIMENTAL_XAU = "false"
        $env:USE_EXPERIMENTAL_INDEX = "false"
        Write-Host "USE_EXPERIMENTAL_FX set to true"
    }
    "XAU" {
        $env:USE_EXPERIMENTAL_FX = "false"
        $env:USE_EXPERIMENTAL_XAU = "true"
        $env:USE_EXPERIMENTAL_INDEX = "false"
        Write-Host "USE_EXPERIMENTAL_XAU set to true"
    }
    "INDEX" {
        $env:USE_EXPERIMENTAL_FX = "false"
        $env:USE_EXPERIMENTAL_XAU = "false"
        $env:USE_EXPERIMENTAL_INDEX = "true"
        Write-Host "USE_EXPERIMENTAL_INDEX set to true"
    }
    Default {
        if ($Experimental) {
            $env:USE_EXPERIMENTAL_FX = "true"
            Write-Host "Generic Experimental mode enabled"
        }
        else {
            $env:USE_EXPERIMENTAL_FX = "false"
        }
    }
}

Write-Host "Running: $cmd $($uniargs -join ' ')"
Write-Host "Merged env: $MergedFile"
Write-Host "Experimental flags -> FX: $env:USE_EXPERIMENTAL_FX | XAU: $env:USE_EXPERIMENTAL_XAU | INDEX: $env:USE_EXPERIMENTAL_INDEX"

# -----------------------------
# Run & mirror logs
# -----------------------------
& $cmd $uniargs | Tee-Object -FilePath $Log -Append
