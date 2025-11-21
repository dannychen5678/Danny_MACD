# 🚀 Render 部署快速指南

## 步驟 1: 建立 PostgreSQL 資料庫

1. 前往 https://dashboard.render.com/
2. 點擊右上角 **"New +"** → 選擇 **"PostgreSQL"**
3. 填寫資料：
   ```
   Name: macd-database
   Database: macd_db
   User: macd_user
   Region: Singapore (或選擇離你最近的)
   PostgreSQL Version: 16 (預設)
   Plan: Free
   ```
4. 點擊 **"Create Database"**
5. 等待 2-3 分鐘建立完成
6. 在資料庫頁面找到 **"Internal Database URL"**，複製它
   - 格式類似: `postgresql://macd_user:xxxxx@dpg-xxxxx/macd_db`

## 步驟 2: 推送程式碼到 GitHub

```bash
git add .
git commit -m "Add PostgreSQL support"
git push origin main
```

## 步驟 3: 部署 Web Service

1. 在 Render Dashboard 點擊 **"New +"** → **"Web Service"**
2. 選擇 **"Connect a repository"**
3. 授權並選擇你的 GitHub repository: `Danny_MACD`
4. 填寫設定：
   ```
   Name: macd-monitor
   Region: Singapore (與資料庫相同)
   Branch: main
   Root Directory: (留空)
   Environment: Python
   Build Command: pip install --upgrade pip && pip install -r requirements.txt
   Start Command: python main.py
   Plan: Free
   ```

5. **重要！** 在 "Environment Variables" 區塊點擊 **"Add Environment Variable"**：
   ```
   Key: DATABASE_URL
   Value: [貼上步驟 1 複製的 Internal Database URL]
   ```

6. 點擊 **"Create Web Service"**

## 步驟 4: 等待部署完成

- 部署需要 5-10 分鐘
- 可以在 "Logs" 頁面查看進度
- 看到 `Running on http://0.0.0.0:10000` 表示成功

## 步驟 5: 測試

訪問以下網址（替換成你的網址）：

1. **健康檢查**: `https://macd-monitor.onrender.com/`
   - 應該顯示: "Service is running (AI Learning Version)"

2. **查看訊號**: `https://macd-monitor.onrender.com/signals`
   - 顯示最近 50 筆訊號記錄

3. **查看統計**: `https://macd-monitor.onrender.com/stats`
   - 顯示勝率和損益統計

## 常見問題

### Q: 部署失敗怎麼辦？
A: 檢查 Logs 頁面的錯誤訊息，常見原因：
- Python 版本問題 → 確認 `runtime.txt` 存在
- 套件安裝失敗 → 檢查 `requirements.txt`
- 資料庫連線失敗 → 確認 `DATABASE_URL` 環境變數正確

### Q: 如何查看資料庫內容？
A: 
1. 在 Render Dashboard 進入你的 PostgreSQL 資料庫
2. 點擊右上角 "Connect" → 選擇 "External Connection"
3. 使用 pgAdmin 或其他工具連線

### Q: 程式會自動休眠嗎？
A: 
- 免費方案會在 15 分鐘無活動後休眠
- 程式內建 `keep_alive` 功能每 10 分鐘自動喚醒
- 資料庫不會休眠，數據永久保存

### Q: 如何更新程式？
A:
```bash
git add .
git commit -m "Update code"
git push origin main
```
Render 會自動偵測並重新部署

## 🎉 完成！

你的 MACD 監控系統現在已經在雲端運行了！
- ✅ 24/7 自動監控
- ✅ 數據永久保存
- ✅ Telegram 即時通知
- ✅ AI 自動學習優化
