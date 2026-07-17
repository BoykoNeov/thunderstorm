@echo off
rem ============================================================
rem  Storm Diorama launcher
rem  Double-click this file to open the diorama in your default
rem  browser, starting a dev server only if one is not already
rem  running.
rem ============================================================

title Storm Diorama
cd /d "%~dp0diorama"

where npm >nul 2>nul
if errorlevel 1 (
  echo.
  echo   Node.js / npm was not found on your PATH.
  echo   Install Node.js from https://nodejs.org and try again.
  echo.
  pause
  exit /b 1
)

rem ---- Reuse a server that is already serving THIS project ----
rem  Starting one per double-click stacks servers: vite cannot have a port
rem  that is busy, so it climbs to the next free one rather than failing, and
rem  nothing ever stops the old server. This machine has had sixteen stacked
rem  across 5173-5190 that way, each holding a live volume raymarcher open in
rem  any tab still pointed at it.
rem
rem  The port cannot say whose server it is. Vite climbs past other projects
rem  too, so 5173 is quite possibly a different app entirely - find-server.mjs
rem  asks each port what it is serving and matches only the Storm Diorama.
rem  Reusing an old server is safe rather than a bet on its age: vite
rem  transforms from disk on every request, so it serves the code as it is now
rem  however long it has been up.
set "DIORAMA_URL="
for /f "usebackq delims=" %%u in (`node tools\find-server.mjs 2^>nul`) do set "DIORAMA_URL=%%u"

if defined DIORAMA_URL (
  echo.
  echo   Storm Diorama is already running at %DIORAMA_URL%
  echo   Opening that, instead of starting a second server.
  echo.
  echo   It serves the current code even if it has been up a while.
  echo   Only a vite.config.ts change needs a fresh start - close the
  echo   window running the old server first, then double-click again.
  echo.
  start "" "%DIORAMA_URL%"
  timeout /t 4 >nul 2>nul
  exit /b 0
)

if not exist "node_modules" (
  echo.
  echo   First run - installing dependencies, this may take a minute...
  echo.
  call npm install
  if errorlevel 1 (
    echo.
    echo   npm install failed. See the messages above.
    echo.
    pause
    exit /b 1
  )
)

echo.
echo   Starting the Storm Diorama...
echo   A browser tab will open automatically.
echo   Close this window (or press Ctrl+C) to stop the server.
echo.

call npm run dev -- --open

pause
