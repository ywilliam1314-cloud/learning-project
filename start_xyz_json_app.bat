@echo off
setlocal
cd /d "%~dp0"

set "HOST=127.0.0.1"
set "PORT=2100"
set "URL=http://%HOST%:%PORT%"

set "PY_CMD="
where py >nul 2>&1
if %errorlevel%==0 set "PY_CMD=py"

if not defined PY_CMD (
  where python >nul 2>&1
  if %errorlevel%==0 set "PY_CMD=python"
)

if not defined PY_CMD (
  echo Python launcher not found. Please install Python and Flask first.
  pause
  exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$port=%PORT%; $client = New-Object Net.Sockets.TcpClient; try { $client.Connect('%HOST%', $port); $client.Close(); exit 0 } catch { exit 1 }"
if %errorlevel% neq 0 (
  start "XYZ to JSON Backend" %PY_CMD% xyz_to_json.py --serve --port %PORT%
)

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$deadline=(Get-Date).AddSeconds(12); while((Get-Date) -lt $deadline){ $client = New-Object Net.Sockets.TcpClient; try { $client.Connect('%HOST%', %PORT%); $client.Close(); exit 0 } catch { Start-Sleep -Milliseconds 300 } }; exit 1"
if %errorlevel% neq 0 (
  echo Backend did not start on %URL%.
  echo Make sure Python and Flask are installed. Example: pip install -r requirements.txt
  pause
  exit /b 1
)

start "" "%URL%"
