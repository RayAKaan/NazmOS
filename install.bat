@echo off
REM NazmOS KSA – Windows One-Click Installer
REM Requires: Docker Desktop for Windows

echo ==============================
echo   NazmOS KSA v2.1 - Installer
echo   SAR 25,000 License
echo ==============================
echo.

where docker >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
  echo [!] Docker Desktop not found.
  echo Please install Docker Desktop from https://www.docker.com/products/docker-desktop/
  pause
  exit /b 1
)

if not exist backend\.env (
  echo [+] Creating backend\.env
  powershell -Command "$s = -join ((65..90) + (97..122) + (48..57) | Get-Random -Count 64 | ForEach-Object {[char]$_}); @'
ENVIRONMENT=production
SECRET_KEY=
'@ | Set-Content backend\.env.tmp ; (Get-Content backend\.env.tmp) -replace 'SECRET_KEY=',\"SECRET_KEY=$s\" | Set-Content backend\.env ; Remove-Item backend\.env.tmp"
  powershell -Command "Add-Content backend\.env \"`nDATABASE_URL=postgresql+asyncpg://nazmos:nazmos_ksa_2026@postgres:5432/nazmos`nCORS_ORIGINS=http://localhost:3000`nREDIS_URL=redis://redis:6379/0`nCHAT_ENABLED=false`nBILLING_ENABLED=false`nUSE_MOCK_LLM=true`nDEFAULT_CURRENCY=SAR`nDEFAULT_TIMEZONE=Asia/Riyadh\""
  echo   SECRET_KEY generated
)

if not exist frontend\.env.local (
  echo [+] Creating frontend\.env.local
  (
    echo NEXT_PUBLIC_API_URL=http://localhost:8000
    echo NEXT_PUBLIC_CHAT_ENABLED=false
    echo NEXT_PUBLIC_APP_NAME=NazmOS KSA
    echo NEXT_PUBLIC_CURRENCY=SAR
    echo NEXT_PUBLIC_LOCALE=ar-SA
  ) > frontend\.env.local
)

echo.
echo [+] Starting NazmOS KSA (production)...
docker compose -f docker-compose.prod.yml up -d --build

echo.
echo Waiting 20 seconds for services...
timeout /t 20 /nobreak >nul

echo.
echo ==========================================
echo   NazmOS KSA is running!
echo ==========================================
echo   Frontend: http://localhost:3000
echo   API Docs: http://localhost:8000/docs
echo.
echo   First time? Go to http://localhost:3000/register
echo   Create your admin account, then upload your POS CSV
echo.
echo   Support WhatsApp: +966 5X XXX XXXX
echo ==========================================
echo.
pause
