@echo off
echo ========================================
echo 啟動 MACD 監控系統
echo ========================================

REM 檢查是否已有程式在運行
if exist macd_monitor.lock (
    echo ⚠️ 警告：偵測到鎖定檔案！
    echo ⚠️ 可能有另一個程式正在運行
    echo.
    choice /C YN /M "是否強制啟動 (Y=是, N=否)"
    if errorlevel 2 goto :end
    del macd_monitor.lock
    echo ✅ 已刪除舊的鎖定檔案
)

echo.
echo 🚀 正在啟動監控程式...
echo.
python main.py

:end
pause
