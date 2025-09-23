# tools\run-quality.ps1
$ErrorActionPreference = 'Continue'

# Always write logs next to this script
$here     = Split-Path -Parent $MyInvocation.MyCommand.Path
$ruffLog  = Join-Path $here 'ruff.err.out'
$blackLog = Join-Path $here 'black.err.out'
$mypyLog  = Join-Path $here 'mypy.err.out'

# Clean previous logs
Remove-Item $ruffLog, $blackLog, $mypyLog -ErrorAction Ignore

# Ruff
& python -m ruff check --fix . *>&1 | Out-File -FilePath $ruffLog -Encoding utf8
$ruffCode = $LASTEXITCODE

# Black
& python -m black --check . *>&1 | Out-File -FilePath $blackLog -Encoding utf8
$blackCode = $LASTEXITCODE

# Mypy
& python -m mypy . *>&1 | Out-File -FilePath $mypyLog -Encoding utf8
$mypyCode = $LASTEXITCODE

Write-Host ''
Write-Host '=== Summary ==='

if ($ruffCode -eq 0) {
  Write-Host 'Ruff : OK'
} else {
  Write-Host 'Ruff : Issues (' $ruffCode ') - see tools\ruff.err.out'
}

if ($blackCode -eq 0) {
  Write-Host 'Black: OK'
} else {
  Write-Host 'Black: Issues (' $blackCode ') - see tools\black.err.out'
}

if ($mypyCode -eq 0) {
  Write-Host 'Mypy : OK'
} else {
  Write-Host 'Mypy : Issues (' $mypyCode ') - see tools\mypy.err.out'
}

# Exit non-zero if any failed
$exitCode = 0
if ($ruffCode  -ne 0) { $exitCode = 1 }
if ($blackCode -ne 0) { $exitCode = 1 }
if ($mypyCode  -ne 0) { $exitCode = 1 }
exit $exitCode
