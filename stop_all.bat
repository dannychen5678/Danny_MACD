@echo off
echo ========================================
echo 停止所有 MACD 監控程式
echo ========================================

REM 停止所有 Python 程式
taskkill /F /IM python.exe 2>nul
if %errorlevel% equ 0 (
    echo ✅ 已停止 Python 程式
) else (
    echo ℹ️ 沒有找到運行中的 Python 程式
)

REM 刪除鎖定檔案
if exist macd_monitor.lock (
    del macd_monitor.lock
    echo ✅ 已刪除鎖定檔案
)

echo ========================================
echo 清理完成！現在可以重新啟動程式
echo ========================================
pause
