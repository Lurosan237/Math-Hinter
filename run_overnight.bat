@echo off
rem Runs the pipeline's test evaluation to the end, waiting out Groq's limits. Leave the window open.
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  echo Setting up Python for Math-Hinter, once...
  py -3 -m venv .venv || python -m venv .venv || (echo Python 3 is needed: https://www.python.org/downloads/ & pause & exit /b 1)
  .venv\Scripts\python -m pip install --quiet -r requirements.txt
)
.venv\Scripts\python scripts\overnight.py --split test --count 25 --name pipeline-test --configs pipeline
pause
