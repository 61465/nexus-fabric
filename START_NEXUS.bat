@echo off
echo.
echo  ╔══════════════════════════════════════════════════════╗
echo  ║        PROJECT NEXUS v0.9 — Starting Engine         ║
echo  ╚══════════════════════════════════════════════════════╝
echo.
echo  [1/3] Opening Dashboard in browser...
start "" "dashboard\index.html"
timeout /t 1 /nobreak >nul

echo  [2/3] Starting Nexus Engine (Python backend)...
echo  Dashboard: file://dashboard/index.html
echo  Backend  : ws://localhost:9001
echo.
echo  Press Ctrl+C to stop the engine.
echo  ─────────────────────────────────────────────────────────
cd core
python nexus_engine.py
