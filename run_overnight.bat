@echo off
rem Runs the night's evaluation jobs to the end, waiting out Groq's free limits. Leave the window open.
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  echo Setting up Python for Math-Hinter, once...
  py -3 -m venv .venv || python -m venv .venv || (echo Python 3 is needed: https://www.python.org/downloads/ & pause & exit /b 1)
  .venv\Scripts\python -m pip install --quiet "numpy>=1.26,<3" "scipy>=1.11,<2" "sympy>=1.13,<2" "snowballstemmer>=2.2,<4"
)
.venv\Scripts\python scripts\night.py
pause
