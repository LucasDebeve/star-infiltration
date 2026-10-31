@echo off
rem Lance le jeu depuis les sources (Windows). Cree un environnement virtuel au premier lancement.
cd /d "%~dp0"
if not exist .venv (
  py -3 -m venv .venv && .venv\Scripts\pip install -r requirements.txt || exit /b 1
)
.venv\Scripts\python main.py %*
