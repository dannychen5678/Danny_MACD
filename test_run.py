"""
本地測試腳本 - 確認程式是否持續運行
"""
import subprocess
import time
import sys

print("=" * 70)
print("🧪 測試 MACD 監控程式")
print("=" * 70)
print("這個腳本會啟動 main.py 並觀察輸出")
print("按 Ctrl+C 可以停止")
print("=" * 70 + "\n")

try:
    # 啟動 main.py
    process = subprocess.Popen(
        [sys.executable, "main.py"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )
    
    print("✅ 程式已啟動，開始監控輸出...\n")
    
    line_count = 0
    last_output_time = time.time()
    
    # 即時顯示輸出
    for line in process.stdout:
        print(line, end='')
        line_count += 1
        last_output_time = time.time()
        
        # 每 10 行檢查一次
        if line_count % 10 == 0:
            elapsed = time.time() - last_output_time
            print(f"\n[測試] 已輸出 {line_count} 行，最後輸出: {elapsed:.1f} 秒前\n")
    
except KeyboardInterrupt:
    print("\n\n⚠️ 使用者中斷")
    process.terminate()
    print("✅ 程式已停止")

except Exception as e:
    print(f"\n❌ 錯誤: {e}")
    if 'process' in locals():
        process.terminate()
