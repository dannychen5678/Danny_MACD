import requests
import pandas as pd
import numpy as np
import time
import json
from datetime import datetime, timedelta
from flask import Flask
import threading
from pathlib import Path

# === Telegram 設定 ===
BOT_TOKEN = "8559295076:AAG-FeyHD6vMSWTXsskbuguY3GhRgMQcxAY"
CHAT_ID = "8207833130"
API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

# === 台指期即時行情 URL ===
URL = "https://mis.taifex.com.tw/futures/api/getQuoteList"

# === 數據儲存路徑 ===
DATA_DIR = Path("macd_data")
DATA_DIR.mkdir(exist_ok=True)
SIGNAL_LOG_FILE = DATA_DIR / "signal_log.csv"
PARAMS_FILE = DATA_DIR / "parameters.json"
STATS_FILE = DATA_DIR / "statistics.json"

# === 動態參數（會自動調整） ===
class DynamicParams:
    def __init__(self):
        self.slope_threshold = 3.0
        self.lookback = 10
        self.hist_confirm_bars = 3
        self.cooldown_minutes = 5
        self.min_signals_for_optimization = 20
        self.load_params()
    
    def load_params(self):
        """載入已儲存的參數"""
        if PARAMS_FILE.exists():
            with open(PARAMS_FILE, 'r') as f:
                params = json.load(f)
                self.slope_threshold = params.get('slope_threshold', 3.0)
                self.lookback = params.get('lookback', 10)
                self.hist_confirm_bars = params.get('hist_confirm_bars', 3)
                self.cooldown_minutes = params.get('cooldown_minutes', 5)
                print(f"✅ 載入已儲存的參數: slope={self.slope_threshold}, lookback={self.lookback}")
    
    def save_params(self):
        """儲存參數"""
        params = {
            'slope_threshold': self.slope_threshold,
            'lookback': self.lookback,
            'hist_confirm_bars': self.hist_confirm_bars,
            'cooldown_minutes': self.cooldown_minutes,
            'last_update': datetime.now().isoformat()
        }
        with open(PARAMS_FILE, 'w') as f:
            json.dump(params, f, indent=2)

params = DynamicParams()

def get_market_type():
    """切換交易時段"""
    now = datetime.now().time()
    if datetime.strptime("08:45", "%H:%M").time() <= now <= datetime.strptime("13:45", "%H:%M").time():
        return "0"
    if now >= datetime.strptime("15:00", "%H:%M").time() or now <= datetime.strptime("05:00", "%H:%M").time():
        return "1"
    return "0"

def get_payload():  
    return {
        "MarketType": get_market_type(),
        "SymbolType": "F",
        "KindID": "1",
        "CID": "TXF",
        "ExpireMonth": "",      
        "RowSize": "全部",
        "PageNo": "",
        "SortColumn": "",
        "AscDesc": "A"
    }

def keep_alive(url):
    """自我保持運作"""
    while True:
        try:
            requests.get(url)
            print("Pinged self to stay awake")
        except:
            pass
        time.sleep(600)

def send_alert(msg):
    """發送通知給 Telegram"""
    requests.post(API_URL, data={"chat_id": CHAT_ID, "text": msg})

def fetch_latest_price():
    """抓取最新成交價"""
    try:
        r = requests.post(URL, json=get_payload(), headers={"Content-Type": "application/json"})
        
        if r.status_code != 200:
            return None, None, None
        
        data = r.json()
        quotes = data.get("RtData", {}).get("QuoteList", [])
        
        if not quotes:
            return None, None, None

        txf_list = [q for q in quotes if q["SymbolID"].startswith("TXF") and q["CLastPrice"]]
        
        if not txf_list:
            return None, None, None

        q = txf_list[0]
        price = float(q["CLastPrice"])
        ref_price = float(q["CRefPrice"]) if q["CRefPrice"] else price
        timestamp = datetime.now()
        
        return timestamp, price, ref_price

    except Exception as e:
        print(f"❌ 抓取價格失敗: {e}")
        return None, None, None

# === 標準 MACD 計算 ===
def calc_macd(df):
    """計算標準 MACD (12, 26, 9)"""
    ema12 = df['close'].ewm(span=12, adjust=False).mean()
    ema26 = df['close'].ewm(span=26, adjust=False).mean()
    df['MACD'] = ema12 - ema26
    df['Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()
    df['Histogram'] = df['MACD'] - df['Signal']
    return df

def check_divergence(df):
    """背離判斷（使用動態參數）"""
    lookback = params.lookback
    
    if len(df) < lookback + 5:
        return None, None
    
    if 'Histogram' not in df.columns:
        return None, None
    
    recent = df.tail(lookback)
    prices = recent['close'].values
    x = np.arange(len(prices))
    
    if len(prices) > 1:
        slope = np.polyfit(x, prices, 1)[0]
    else:
        return None, None
    
    hist_recent = recent['Histogram'].iloc[-params.hist_confirm_bars:]
    
    if hist_recent.isna().any():
        return None, None
    
    hist_avg = hist_recent.mean()
    hist_now = recent['Histogram'].iloc[-1]
    hist_prev = recent['Histogram'].iloc[-2]
    
    # 記錄判斷依據
    signal_data = {
        'slope': slope,
        'hist_avg': hist_avg,
        'hist_now': hist_now,
        'hist_prev': hist_prev,
        'price_range': prices.max() - prices.min()
    }
    
    # 背離判斷
    if abs(slope) >= params.slope_threshold:
        if slope < 0 and hist_avg > 0 and hist_now > 0:
            return "底部背離（看多）", signal_data
        
        if slope > 0 and hist_avg < 0 and hist_now < 0:
            return "頂部背離（看空）", signal_data
    
    # 動能轉換判斷
    current_price = prices[-1]
    price_max = prices.max()
    price_min = prices.min()
    price_range = price_max - price_min
    
    if price_range > 0:
        is_high = (current_price - price_min) / price_range > 0.7
        is_low = (price_max - current_price) / price_range > 0.7
        
        if is_high and hist_prev < 0 and hist_now > 0:
            return "高檔轉多（注意反轉）", signal_data
        
        if is_low and hist_prev > 0 and hist_now < 0:
            return "低檔轉空（注意反轉）", signal_data
    
    if abs(slope) < params.slope_threshold:
        if hist_prev < 0 and hist_now > 0:
            return "盤整轉多", signal_data
        
        if hist_prev > 0 and hist_now < 0:
            return "盤整轉空", signal_data
    
    return None, None

# === 階段 1：數據收集 ===
def record_signal(signal_type, price, signal_data, df_5min):
    """記錄訊號到 CSV"""
    try:
        # 準備記錄資料
        record = {
            'timestamp': datetime.now().isoformat(),
            'signal_type': signal_type,
            'entry_price': price,
            'slope': signal_data['slope'],
            'hist_avg': signal_data['hist_avg'],
            'hist_now': signal_data['hist_now'],
            'price_range': signal_data['price_range'],
            'slope_threshold': params.slope_threshold,
            'lookback': params.lookback,
            # 結果欄位（稍後更新）
            'price_10min': None,
            'price_30min': None,
            'price_1hour': None,
            'result': None,
            'profit_loss': None,
            'threshold_used': None  # 記錄使用的動態門檻
        }
        
        # 寫入 CSV
        df_log = pd.DataFrame([record])
        
        if SIGNAL_LOG_FILE.exists():
            df_log.to_csv(SIGNAL_LOG_FILE, mode='a', header=False, index=False)
        else:
            df_log.to_csv(SIGNAL_LOG_FILE, mode='w', header=True, index=False)
        
        print(f"✅ 訊號已記錄到: {SIGNAL_LOG_FILE}")
        
    except Exception as e:
        print(f"❌ 記錄訊號失敗: {e}")

def update_signal_results(df_5min):
    """更新訊號結果（追蹤價格變化）"""
    try:
        if not SIGNAL_LOG_FILE.exists():
            return
        
        df_log = pd.read_csv(SIGNAL_LOG_FILE)
        df_log['timestamp'] = pd.to_datetime(df_log['timestamp'])
        
        current_time = datetime.now()
        current_price = df_5min['close'].iloc[-1]
        
        updated = False
        
        for idx, row in df_log.iterrows():
            if pd.notna(row['result']):
                continue  # 已經有結果了
            
            signal_time = row['timestamp']
            time_diff = (current_time - signal_time).total_seconds() / 60
            
            # 更新 10 分鐘後價格
            if pd.isna(row['price_10min']) and time_diff >= 10:
                df_log.at[idx, 'price_10min'] = current_price
                updated = True
            
            # 更新 30 分鐘後價格
            if pd.isna(row['price_30min']) and time_diff >= 30:
                df_log.at[idx, 'price_30min'] = current_price
                updated = True
            
            # 更新 1 小時後價格並判斷結果
            if pd.isna(row['price_1hour']) and time_diff >= 60:
                df_log.at[idx, 'price_1hour'] = current_price
                
                # 判斷訊號結果
                entry_price = row['entry_price']
                signal_type = row['signal_type']
                
                if '看多' in signal_type or '轉多' in signal_type:
                    profit_loss = current_price - entry_price
                else:  # 看空
                    profit_loss = entry_price - current_price
                
                df_log.at[idx, 'profit_loss'] = profit_loss
                
                # === 動態門檻：根據價格波動調整 ===
                price_range = row['price_range']
                
                # 計算動態門檻（波動的 25-35%）
                # 最小 20 點，最大 50 點
                dynamic_threshold = max(20, min(50, price_range * 0.3))
                
                # 判斷成功或失敗
                if profit_loss > dynamic_threshold:
                    df_log.at[idx, 'result'] = 'success'
                elif profit_loss < -dynamic_threshold:
                    df_log.at[idx, 'result'] = 'fail'
                else:
                    df_log.at[idx, 'result'] = 'neutral'
                
                # 記錄使用的門檻（用於分析）
                df_log.at[idx, 'threshold_used'] = dynamic_threshold
                
                updated = True
        
        if updated:
            df_log.to_csv(SIGNAL_LOG_FILE, index=False)
            print(f"✅ 訊號結果已更新")
        
    except Exception as e:
        print(f"❌ 更新訊號結果失敗: {e}")

# === 階段 2：結果分析 ===
def analyze_signals():
    """分析訊號勝率"""
    try:
        if not SIGNAL_LOG_FILE.exists():
            return None
        
        df_log = pd.read_csv(SIGNAL_LOG_FILE)
        
        # 只分析有結果的訊號
        df_completed = df_log[df_log['result'].notna()]
        
        if len(df_completed) == 0:
            return None
        
        stats = {
            'total_signals': len(df_completed),
            'success_count': len(df_completed[df_completed['result'] == 'success']),
            'fail_count': len(df_completed[df_completed['result'] == 'fail']),
            'neutral_count': len(df_completed[df_completed['result'] == 'neutral']),
            'success_rate': 0,
            'avg_profit': df_completed['profit_loss'].mean(),
            'by_signal_type': {}
        }
        
        stats['success_rate'] = stats['success_count'] / len(df_completed) * 100
        
        # 分析各種訊號類型
        for signal_type in df_completed['signal_type'].unique():
            df_type = df_completed[df_completed['signal_type'] == signal_type]
            success = len(df_type[df_type['result'] == 'success'])
            total = len(df_type)
            
            stats['by_signal_type'][signal_type] = {
                'total': total,
                'success': success,
                'success_rate': success / total * 100 if total > 0 else 0,
                'avg_profit': df_type['profit_loss'].mean()
            }
        
        # 儲存統計資料
        with open(STATS_FILE, 'w') as f:
            json.dump(stats, f, indent=2)
        
        return stats
        
    except Exception as e:
        print(f"❌ 分析訊號失敗: {e}")
        return None

def print_statistics(stats):
    """打印統計報告"""
    if not stats:
        return
    
    print("\n" + "=" * 80)
    print("📊 訊號統計報告")
    print("=" * 80)
    print(f"總訊號數: {stats['total_signals']}")
    print(f"成功: {stats['success_count']} | 失敗: {stats['fail_count']} | 中性: {stats['neutral_count']}")
    print(f"整體勝率: {stats['success_rate']:.1f}%")
    print(f"平均損益: {stats['avg_profit']:+.1f} 點")
    
    print("\n各類訊號表現:")
    for signal_type, data in stats['by_signal_type'].items():
        print(f"  {signal_type}:")
        print(f"    數量: {data['total']} | 勝率: {data['success_rate']:.1f}% | 平均損益: {data['avg_profit']:+.1f} 點")
    
    print("=" * 80 + "\n")

# === 階段 3：自動調整參數 ===
def optimize_parameters(stats):
    """根據勝率自動調整參數"""
    if not stats or stats['total_signals'] < params.min_signals_for_optimization:
        print(f"⏳ 訊號數量不足，需要至少 {params.min_signals_for_optimization} 個訊號才能優化")
        return False
    
    success_rate = stats['success_rate']
    old_slope = params.slope_threshold
    old_lookback = params.lookback
    
    print("\n" + "=" * 80)
    print("🤖 開始自動優化參數")
    print("=" * 80)
    print(f"當前勝率: {success_rate:.1f}%")
    print(f"當前參數: slope_threshold={old_slope}, lookback={old_lookback}")
    
    # 優化邏輯
    if success_rate < 55:
        # 勝率太低，提高門檻減少假訊號
        params.slope_threshold = min(old_slope + 0.5, 6.0)
        params.lookback = min(old_lookback + 2, 15)
        print("📉 勝率偏低，提高門檻以減少假訊號")
        
    elif success_rate > 75:
        # 勝率很高，降低門檻增加訊號數量
        params.slope_threshold = max(old_slope - 0.5, 2.0)
        params.lookback = max(old_lookback - 1, 8)
        print("📈 勝率良好，降低門檻以增加訊號")
        
    elif 60 <= success_rate <= 70:
        # 勝率適中，微調參數
        avg_profit = stats['avg_profit']
        if avg_profit < 20:
            params.slope_threshold = old_slope + 0.2
            print("💰 平均獲利偏低，微調門檻")
    
    # 儲存新參數
    params.save_params()
    
    print(f"新參數: slope_threshold={params.slope_threshold}, lookback={params.lookback}")
    print("=" * 80 + "\n")
    
    # 發送通知
    msg = (f"🤖 參數已自動優化\n"
           f"勝率: {success_rate:.1f}%\n"
           f"slope: {old_slope} → {params.slope_threshold}\n"
           f"lookback: {old_lookback} → {params.lookback}")
    send_alert(msg)
    
    return True

# === 主程式 ===
def main():
    print("=" * 60)
    print("🤖 開始監控台指期 MACD 背離訊號（AI 自動學習版）")
    print("=" * 60)
    print("📌 指標系統：標準 MACD (12, 26, 9)")
    print("📌 學習功能：自動收集數據、分析勝率、優化參數")
    print(f"📌 當前參數：slope={params.slope_threshold}, lookback={params.lookback}")
    print("=" * 60 + "\n")
    
    df_tick = pd.DataFrame(columns=['Close'])
    last_alert = None
    last_alert_time = datetime.min
    last_price = None
    last_record_time = None
    data_ready = False
    last_analysis_time = datetime.now()
    
    while True:
        timestamp, price, current_ref = fetch_latest_price()
        
        if price:
            should_record = False
            
            if last_price is None or price != last_price:
                should_record = True
            elif last_record_time is None or (timestamp - last_record_time).total_seconds() >= 30:
                should_record = True
            
            if should_record:
                df_tick.index = pd.to_datetime(df_tick.index, errors='coerce')
                cutoff_time = datetime.now() - timedelta(hours=48)
                df_tick = df_tick.loc[df_tick.index >= cutoff_time]
                df_tick.loc[timestamp] = price
                last_price = price
                last_record_time = timestamp
            
            df_5min = df_tick['Close'].resample('5min').ohlc()
            df_5min['volume'] = df_tick['Close'].resample('5min').count()
            df_5min.dropna(inplace=True)
            
            if len(df_5min) < 60:
                continue
            
            if not data_ready:
                data_ready = True
                print("✅ 資料量已足夠，開始監控！\n")
            
            df_5min = calc_macd(df_5min)
            
            # 更新訊號結果
            update_signal_results(df_5min)
            
            # 每 30 分鐘分析一次並優化參數
            if (datetime.now() - last_analysis_time).total_seconds() >= 1800:
                stats = analyze_signals()
                if stats:
                    print_statistics(stats)
                    optimize_parameters(stats)
                last_analysis_time = datetime.now()
            
            # 檢查背離訊號
            alert, signal_data = check_divergence(df_5min)
            
            now = datetime.now()
            cooldown = timedelta(minutes=params.cooldown_minutes)
            
            if alert and alert != last_alert and now - last_alert_time > cooldown:
                # 記錄訊號
                record_signal(alert, price, signal_data, df_5min)
                
                # 發送通知
                msg = (f"⚠️ {alert}\n"
                       f"⏰ {timestamp.strftime('%Y-%m-%d %H:%M:%S')}\n"
                       f"💰 價格: {price:,.0f}\n"
                       f"📊 斜率: {signal_data['slope']:+.2f}\n"
                       f"📊 MACD: {signal_data['hist_now']:+.2f}\n"
                       f"🤖 參數: slope={params.slope_threshold}, lookback={params.lookback}")
                send_alert(msg)
                
                last_alert = alert
                last_alert_time = now
                print(f"\n🔔 發送警報: {alert}\n")
        
        time.sleep(3)


app = Flask(__name__)

@app.route("/")
def home():
    return "Service is running (AI Learning Version)", 200

def run_bot():
    main()

if __name__ == "__main__":
    t = threading.Thread(target=run_bot)
    t.daemon = True
    t.start()
    
    t2 = threading.Thread(target=keep_alive, args=("https://macd-rx43.onrender.com",))
    t2.daemon = True
    t2.start()

    app.run(host="0.0.0.0", port=10000)
