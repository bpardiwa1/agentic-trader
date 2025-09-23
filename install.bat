@echo off
SETLOCAL
py -3.11 -m venv .venv
IF ERRORLEVEL 1 (
  echo Python 3.11 not found via 'py -3.11'. Falling back to 'python'...
  python -m venv .venv
)
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip setuptools wheel
pip install -r requirements.txt
echo Install complete. Next: copy .env.example .env and edit it.
ENDLOCAL