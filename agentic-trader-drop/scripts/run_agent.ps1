param(
  [string[]]$EnvFiles = @("env\core.env"),
  [int]$Port = 8001
)

# Load .env-style files in order (later overrides earlier)
$EnvFiles | ForEach-Object {
  if (Test-Path $_) {
    Get-Content $_ | Where-Object { $_ -match '^\s*[^#].+?=' } |
      ForEach-Object {
        $k,$v = $_ -split '=',2
        [System.Environment]::SetEnvironmentVariable($k.Trim(), $v.Trim())
      }
  } else {
    Write-Host "WARN: env file not found: $_"
  }
}

$env:PORT = $Port
Write-Host "Starting Agentic Trader on port $Port with envs: $($EnvFiles -join ', ')"
uvicorn app.main:app --host 0.0.0.0 --port $env:PORT --reload:$env:RELOAD
