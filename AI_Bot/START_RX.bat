@echo off
chcp 65001 >nul
title RX Local Server
cd /d "%~dp0"

netsh advfirewall firewall show rule name="RX App 5000" >nul 2>&1
if errorlevel 1 echo NOTE: For mobile access, run ALLOW_FIREWALL.bat as Administrator once.

echo Detecting your LAN IP...
set "LAN_IP="
powershell -NoProfile -Command "$ip=(Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '169.254.*' } | Select-Object -First 1).IPAddress; [IO.File]::WriteAllText('%~dp0lan_ip.txt', $ip)"
set /p LAN_IP=<"%~dp0lan_ip.txt"
del "%~dp0lan_ip.txt" >nul 2>&1

if "%LAN_IP%"=="" set "LAN_IP=127.0.0.1"

echo Updating .env for local + mobile access...
powershell -NoProfile -Command "$p='.env'; $t=Get-Content $p -Raw; $t=$t -replace '(?m)^WEB_HOST=.*','WEB_HOST=0.0.0.0'; $t=$t -replace '(?m)^PUBLIC_BASE_URL=.*','PUBLIC_BASE_URL=http://%LAN_IP%:5000'; [IO.File]::WriteAllText((Resolve-Path $p).Path, $t)"

echo.
echo ===================================================
echo  RX is starting
echo.
echo  PC    : http://127.0.0.1:5000/login
echo  Mobile: http://%LAN_IP%:5000/login   (same Wi-Fi)
echo.
echo  Close this window to stop the app.
echo ===================================================
echo.

"%~dp0venv\Scripts\python.exe" run.py

pause
