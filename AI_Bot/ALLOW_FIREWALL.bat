@echo off
title Allow RX on port 5000
echo Adding Windows Firewall rule for RX (port 5000)...
echo.
netsh advfirewall firewall add rule name="RX App 5000" dir=in action=allow protocol=TCP localport=5000
echo.
echo Done. You can close this window.
pause
