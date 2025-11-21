# MACD 台指期監控系統（AI 自動學習版）

## 功能特色
- 🤖 自動監控台指期 MACD 背離訊號
- 📊 自動收集數據並分析勝率
- 🔧 根據勝率自動優化參數
- 💾 使用 PostgreSQL 永久儲存數據
- 📱 Telegram 即時通知

## Render 部署步驟

### 1. 建立 PostgreSQL 資料庫
1. 登入 [Render Dashboard](https://dashboard.render.com/)
2. 點擊 "New +" → "PostgreSQL"
3. 設定：
   - Name: `macd-database`
   - Database: `macd_db`
   - User: `macd_user`
   - Region: 選擇離你最近的
   - Plan: **Free**
4. 點擊 "Create Database"
5. 等待建立完成後，複製 **Internal Database URL**

### 2. 部署 Web Service
1. 點擊 "New +" → "Web Service"
2. 連接你的 GitHub repository
3. 設定：
   - Name: `macd-monitor`
   - Environment: `Python`
   - Build Command: `pip install --upgrade pip && pip install -r requirements.txt`
   - Start Command: `python main.py`
4. 在 "Environment Variables" 新增：
   - Key: `DATABASE_URL`
   - Value: 貼上剛才複製的 Internal Database URL
5. 點擊 "Create Web Service"

### 3. 驗證部署
訪問以下網址：
- 主頁: `https://your-app.onrender.com/`
- 訊號記錄: `https://your-app.onrender.com/signals`
- 統計報告: `https://your-app.onrender.com/stats`

## 本地開發

### 安裝依賴
```bash
pip install -r requirements.txt
```

### 執行（使用本地 SQLite）
```bash
python main.py
```

### 執行（連接 Render PostgreSQL）
```bash
set DATABASE_URL=postgresql://user:password@host/database
python main.py
```

## 資料庫結構

### signal_logs 表
- 儲存所有訊號記錄
- 包含進場價、結果、損益等資訊

### parameters 表
- 儲存參數調整歷史
- 追蹤 AI 學習過程

## API 端點

- `GET /` - 健康檢查
- `GET /signals` - 查看最近 50 筆訊號
- `GET /stats` - 查看統計報告

## 注意事項

⚠️ **重要**: 
- Render 免費方案會在 15 分鐘無活動後休眠
- 使用 `keep_alive` 功能每 10 分鐘自動喚醒
- PostgreSQL 免費方案有 1GB 儲存限制
- 資料會永久保存，不會因重新部署而遺失
