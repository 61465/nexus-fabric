@echo off
rem Nexus Fabric startup. Opens dashboard tabs then launches the engine.

cd /d %~dp0

echo [Fabric] Opening dashboard tabs...
start "" "dashboard\index.html"
start "" "dashboard\specs.html"

if not exist ".venv\Scripts\python.exe" (
    echo [Fabric] WARNING: no .venv found. Using system Python.
    set PY=python
) else (
    set PY=.venv\Scripts\python.exe
)

echo [Fabric] Starting engine ^(Ctrl+C to stop^)
%PY% core\nexus_engine.py
