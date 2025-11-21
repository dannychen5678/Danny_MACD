# 🔍 Render 運行監控指南

## 方法 1：心跳頁面（最簡單）⭐

### 訪問心跳監控頁面
```
https://danny-macd.onrender.com/heartbeat
```

### 特點：
- ✅ 每 10 秒自動刷新
- ✅ 顯示當前時間
- ✅ 如果時間停止更新 = 服務關閉了

### 正常狀態：
```
💚 系統心跳監控
⏰ 2024-11-22 14:30:15
✅ 服務正常運行
🔄 每 10 秒自動刷新
```

### 異常狀態：
- 時間不再更新
- 頁面無法載入
- 顯示錯誤訊息

---

## 方法 2：Render Dashboard Logs

### 步驟：
1. 登入 https://dashboard.render.com/
2. 點擊服務 "danny-macd"
3. 點擊 "Logs" 標籤
4. 查看最新日誌

### 正常運行的日誌：
```
💓 心跳 #20 | 2024-11-22 14:31:00 | 監控運行中...
💓 心跳 #40 | 2024-11-22 14:32:00 | 監控運行中...
Pinged self to stay awake
📊 14:35:00 | 價格: 23,180 | K棒: 65 | MACD: +2.35 | 循環: #60
```

### 服務關閉的跡象：
- ❌ 日誌停在某個時間點
- ❌ 沒有新的心跳訊息
- ❌ 看到錯誤訊息（紅色）
- ❌ 顯示 "Service stopped"

---

## 方法 3：健康檢查 API

### 使用瀏覽器或 curl
```bash
curl https://danny-macd.onrender.com/health
```

### 正常回應：
```json
{
  "status": "ok",
  "service": "macd-monitor",
  "timestamp": "2024-11-22T14:30:15.123456"
}
```

### 異常回應：
- 無回應（超時）
- 錯誤訊息
- HTTP 500 錯誤

---

## 方法 4：設定外部監控（推薦）

### 使用 UptimeRobot（免費）

1. 註冊 https://uptimerobot.com/
2. 新增監控：
   - Monitor Type: HTTP(s)
   - URL: `https://danny-macd.onrender.com/health`
   - Monitoring Interval: 5 分鐘
3. 設定通知：
   - Email 或 Telegram
   - 當服務關閉時自動通知你

### 使用 Cron-job.org（免費）

1. 註冊 https://cron-job.org/
2. 新增 Cron Job：
   - URL: `https://danny-macd.onrender.com/health`
   - Schedule: 每 5 分鐘
3. 啟用失敗通知

---

## 方法 5：Telegram 機器人監控

建立一個簡單的監控腳本，定期檢查服務：

```python
import requests
import time

def check_service():
    try:
        response = requests.get("https://danny-macd.onrender.com/health", timeout=10)
        if response.status_code == 200:
            print("✅ 服務正常")
            return True
        else:
            print(f"⚠️ 服務異常: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ 服務無回應: {e}")
        return False

# 每 5 分鐘檢查一次
while True:
    check_service()
    time.sleep(300)
```

---

## 📊 監控檢查清單

### 每天檢查（推薦）
- [ ] 訪問 `/heartbeat` 確認時間在更新
- [ ] 查看 Render Logs 是否有心跳訊息
- [ ] 檢查 Telegram 是否收到訊號

### 每週檢查
- [ ] 查看 `/signals` 頁面的訊號記錄
- [ ] 查看 `/stats` 頁面的勝率統計
- [ ] 確認資料庫有新資料

### 每月檢查
- [ ] 檢查 Render 使用時數（免費 750 小時/月）
- [ ] 檢查資料庫容量（免費 1GB）
- [ ] 查看整體系統表現

---

## 🚨 常見問題

### Q1: 心跳頁面時間停止更新了
**原因：** 服務已關閉或崩潰
**解決：**
1. 查看 Render Logs 找錯誤訊息
2. 手動重啟服務（Manual Deploy）
3. 檢查環境變數設定

### Q2: Logs 顯示 "Service stopped"
**原因：** 程式崩潰或被終止
**解決：**
1. 查看崩潰前的錯誤訊息
2. 檢查是否記憶體不足
3. 重新部署服務

### Q3: 每 15 分鐘就休眠
**原因：** Keep-alive 功能沒運作
**解決：**
1. 確認 Logs 有 "Pinged self to stay awake"
2. 檢查 keep_alive URL 是否正確
3. 使用外部監控服務定期 ping

### Q4: 心跳訊息消失了
**原因：** 監控執行緒崩潰
**解決：**
1. 查看 Logs 的錯誤訊息
2. 檢查資料庫連線
3. 重新部署

---

## ✅ 快速判斷服務狀態

### 正常運行 ✅
- 心跳頁面時間持續更新
- Logs 每分鐘有心跳訊息
- 每 10 分鐘有 "Pinged self to stay awake"
- 可以訪問所有網頁端點

### 休眠中 😴
- 訪問網頁時顯示 "SERVICE WAKING UP"
- 需要 30-60 秒喚醒
- 喚醒後恢復正常

### 已關閉 ❌
- 心跳頁面無法載入或時間停止
- Logs 停在某個時間點
- 所有網頁端點無回應
- Render Dashboard 顯示 "Failed" 或 "Stopped"

---

## 🎯 推薦監控方案

### 方案 A：簡單監控
1. 每天訪問一次 `/heartbeat`
2. 每週查看一次 Render Logs
3. 等待 Telegram 訊號通知

### 方案 B：完整監控（推薦）
1. 設定 UptimeRobot 每 5 分鐘檢查
2. 每天訪問 `/heartbeat` 確認
3. 每週查看 `/stats` 統計報告
4. 關注 Telegram 通知

### 方案 C：專業監控
1. UptimeRobot 自動監控
2. 自建監控腳本
3. 設定多重通知（Email + Telegram）
4. 定期查看 Render Logs 和統計

---

## 📱 設定通知提醒

### 手機提醒
1. 在手機瀏覽器加入書籤：
   - `https://danny-macd.onrender.com/heartbeat`
2. 每天打開一次確認

### Email 通知
使用 UptimeRobot 設定 Email 通知

### Telegram 通知
程式本身會發送訊號通知到 Telegram

---

## 💡 最佳實踐

1. **每天至少檢查一次** `/heartbeat` 頁面
2. **設定外部監控**（UptimeRobot）自動檢查
3. **關注 Telegram 通知**，有訊號表示正常運行
4. **每週查看統計**，確認系統學習進度
5. **定期查看 Logs**，及早發現問題

---

## 🆘 緊急聯絡

如果服務持續無法運行：
1. 檢查 Render Dashboard 的 Events 標籤
2. 查看完整的 Build Logs
3. 確認環境變數設定正確
4. 嘗試 "Clear build cache & deploy"
5. 檢查 GitHub 程式碼是否有錯誤
