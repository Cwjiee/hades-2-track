@echo off
REM Install (or refresh) the Hades II journal watcher so it starts with Windows.
setlocal
set PROJECT=%~dp0..
set STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup

if not exist "%PROJECT%\.venv\Scripts\pythonw.exe" (
  echo Could not find %PROJECT%\.venv\Scripts\pythonw.exe
  echo Run: uv venv .venv ^&^& uv pip install --python .venv\Scripts\python.exe -e .
  exit /b 1
)

copy /Y "%PROJECT%\scripts\watch_hidden.vbs" "%STARTUP%\hades-track.vbs" >nul
echo Installed "%STARTUP%\hades-track.vbs"

REM Start it now too, so new runs are picked up without a reboot.
wscript "%STARTUP%\hades-track.vbs"
echo Watcher started. Run "hades-track status" to check it.
endlocal
