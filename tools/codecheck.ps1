python -m ruff check --fix . *>&1 | Out-File -FilePath ruff.err.out -Encoding utf8
python -m black check . *>&1 | Out-File -FilePath black.err.out -Encoding utf8
python -m mypy . *>&1 | Out-File -FilePath mypy.err.out -Encoding utf8