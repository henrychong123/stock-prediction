@echo off
echo ============================================
echo  StockSight - ngrok Tunnel Task Setup
echo ============================================
echo.
echo This registers a Windows task (StockPred-NgrokTunnel) that auto-starts
echo the ngrok tunnel whenever you log in.
echo.
echo Prerequisites (do these once before running this script):
echo   1. Install ngrok and put it on PATH: https://ngrok.com/download
echo   2. Sign up + grab your authtoken: https://dashboard.ngrok.com/get-started/your-authtoken
echo   3. Reserve a free static domain: https://dashboard.ngrok.com/domains
echo   4. Edit ngrok.yml: paste your authtoken + reserved domain
echo   5. Add this exact URL as an Authorized redirect URI in Google Cloud
echo      Console (OAuth client) — replace with YOUR domain:
echo        https://YOUR-DOMAIN.ngrok-free.app/login/google/authorized
echo   6. In .env, switch to "behind proxy" mode:
echo        TRUST_PROXY=1
echo        SESSION_COOKIE_SECURE=1
echo      And COMMENT OUT or DELETE this line (it enables insecure transport
echo      regardless of value, even "=0"):
echo        # OAUTHLIB_INSECURE_TRANSPORT=...
echo.
pause
echo.
schtasks /create /TN "StockPred-NgrokTunnel" /TR "wscript.exe \"D:\stock-prediction\run_tunnel_hidden.vbs\"" /SC ONLOGON /F
echo.
echo Done. The tunnel will start at next login. To start it now without
echo logging out, run: start-tunnel.bat
pause
