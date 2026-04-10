@echo off
echo ============================================
echo  StockSight — Scheduled Tasks Setup
echo ============================================
echo.

echo [1/3] Setting up Daily Collector (6:00 PM daily)...
schtasks /create /TN "StockPred-DailyCollector" /TR "wscript.exe \"D:\stock-prediction\run_hidden.vbs\" src\data\daily_collector.py" /SC DAILY /ST 18:00 /F
echo.

echo [2/3] Setting up Batch Predictor (6:30 PM daily)...
schtasks /create /TN "StockPred-BatchPredict" /TR "wscript.exe \"D:\stock-prediction\run_hidden.vbs\" src\data\batch_predict.py --quick" /SC DAILY /ST 18:30 /F
echo.

echo [3/3] Setting up Catalyst Scanner (every 30 min)...
schtasks /create /TN "StockPred-CatalystScan" /TR "wscript.exe \"D:\stock-prediction\run_hidden.vbs\" catalyst_scanner.py --hours 6" /SC MINUTE /MO 30 /F
echo.

echo ============================================
echo  All tasks scheduled!
echo ============================================
echo.
echo  Daily Collector:   6:00 PM    — collects sentiment, GDELT, Fear/Greed
echo  Batch Predict:     6:30 PM    — runs predictions for all 80 Bursa stocks
echo  Catalyst Scanner:  every 30m  — scans news, predicts next rising stocks
echo.
echo  To run manually:
echo    python src/data/daily_collector.py
echo    python src/data/batch_predict.py
echo    python catalyst_scanner.py
echo.
echo  To check status:
echo    schtasks /query /TN "StockPred-DailyCollector"
echo    schtasks /query /TN "StockPred-BatchPredict"
echo    schtasks /query /TN "StockPred-CatalystScan"
echo.
echo  To delete:
echo    schtasks /delete /TN "StockPred-DailyCollector" /F
echo    schtasks /delete /TN "StockPred-BatchPredict" /F
echo    schtasks /delete /TN "StockPred-CatalystScan" /F
echo.
pause
