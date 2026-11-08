@echo off
chcp 65001 >nul
title Bot aislador - 『⛓️』ɴᴏ-ʜᴀʙʟᴀʀ (modo mantenido)
cd /d "%~dp0"
echo ============================================
echo  Iniciando el bot aislador...
echo  Cada mensaje en el canal vigilado:
echo    - borra lo que tenga mas de 30 minutos
echo    - aisla a quien lo escribio 1 hora
echo  Modo mantenido: si el bot falla o se cierra,
echo  se reinicia solo. Cierra esta ventana para
echo  detenerlo del todo.
echo ============================================
set "PY=python"
py -3.12 -c "import discord" >nul 2>&1
if not errorlevel 1 set "PY=py -3.12"
%PY% mantener_vivo.py
echo.
echo El mantenimiento se ha detenido.
pause