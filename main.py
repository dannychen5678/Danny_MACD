import requests
import pandas as pd
import numpy as np
import time
import json
import os
import pytz
from datetime import datetime, timedelta
from flask import Flask
import threading
from pathlib import Path
from sqlalchemy import create_engine, Column, Integer, Float, String, DateTime, Text
from sqlalchemy.orm import declarative_base, sessionmaker

# === Telegram 設定 ===
BOT_TOKEN = "8559295076:AAG-FeyHD6vMSWTXsskbuguY3GhRgMQcxAY"
CHAT_ID = "8207833130"
API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

# === 台指期即時行情 URL ===
URL = "https://mis.taifex.com.tw/futures/api/getQuoteList"

# === 台灣時區 ===
TW_TZ = pytz.timezone('Asia/Taipei')

# === 資料庫設定 ===
DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///macd_data.db')
if DATABASE_URL.startswith('postgres://'):
    DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql://', 1)

Base = declarative_base()

# 資料庫模型
class SignalLog(Base):
    __tablename__ = 'signal_logs'
    
    id = Column(Integer, primary_key=True)
    timestamp = Column(DateTime, nullable=False)
    signal_type = Column(String(100), nullable=False)
    entry_price = Column(Float, nullable=False)
    slope = Column(Float)
    hist_avg = Column(Float)
    hist_now = Column(Float)
    price_range = Column(Float)
    slope_threshold = Column(Float)
    lookback = Column(Integer)
    price_10min = Column(Float)
    price_30min = Column(Float)
    price_1hour = Column(Float)
    result = Column(String(20))
    profit_loss = Column(Float)
    threshold_used = Column(Float)

class Parameters(Base):
    __tablename__ = 'parameters'
    
    id = Column(Integer, primary_key=True)
    slope_threshold = Column(Float, nullable=False)
    lookback = Column(Integer, nullable=False)
    hist_confirm_bars = Column(Integer, nullable=False)
    cooldown_minutes = Column(Integer, nullable=False)
    last_update = Column(DateTime, nullable=False)

engine = create_engine(DATABASE_URL)
Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)

DATA_DIR = Path("macd_data")
DATA_DIR.mkdir(exist_ok=True)
PARAMS_FILE = DATA_DIR / "parameters.json"

# === 動態參數 ===
class DynamicParams:
    def __init__(self):
        self.slope_threshold = 3.0
        self.lookback = 10
        self.hist_confirm_bars = 3
        self.cooldown_minutes = 5
        self.min_signals_for_optimization = 20
        self.load_params()
    
    def load_params(self):
        try:
            session = Session()
            param = session.query(Parameters).order_by(Parameters.last_update.desc()).first()
            if param:
                self.slope_threshold = param.slope_threshold
                self.lookback = param.lookback
                self.hist_confirm_bars = param.hist_confirm_bars
                self.cooldown_minutes = param.cooldown_minutes
                print(f"✅ 從資料庫載入參數: slope={self.slope_threshold}, lookback={self.lookback}")
            session.close()
        except Exception as e:
            print(f"⚠️ 資料庫載入失敗: {e}")
    
    def save_params(self):
        try:
            session = Session()
            param = Parameters(
                slope_threshold=self.slope_threshold,
                lookback=self.lookback,
                hist_confirm_bars=self.hist_confirm_bars,
                cooldown_minutes=self.cooldown_minutes,
                last_update=datetime.now(TW_TZ)
            )
            session.add(param)
            session.commit()
            session.close()
            print(f"✅ 參數已儲存到資料庫")
        except Exception as e:
            print(f"⚠️ 資料庫儲存失敗: {e}")

params = DynamicParams()

def get_tw_time():
    """取得台灣時間"""
    return datetime.now(TW_TZ)

def is_market_open():
    """判斷是否在交易時間"""
    now = get_tw_time()
    current_time = now.time()
    weekday = now.weekday()
    
    # 週末不交易
    if weekday >= 5:
        return False
    
    # 日盤：08:45-13:45
    if datetime.strptime("08:45", "%H:%M").time() <= current_time <= datetime.strptime("13:45", "%H:%M").time():
        return True
    
    # 夜盤：15:00-05:00（隔天）
    if current_time >= datetime.strptime("15:00", "%H:%M").time():
        return True
    if current_time <= datetime.strptime("05:00", "%H:%M").time():
        return True
    
    return False

def get_market_type():
    """切換交易時段"""
    now = get_tw_time().time()
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
def parse_exchange_datetime(date_str, time_str):
    """解析交易所時間"""
    try:
        year = int(date_str[0:4])
        month = int(date_str[4:6])
        day = int(date_str[6:8])
        hour = int(time_str[0:2])
        minute = int(time_str[2:4])
        second = int(time_str[4:6]) if len(time_str) >= 6 else 0
        
        dt = datetime(year, month, day, hour, minute, second)
        return TW_TZ.localize(dt)
    except:
        return get_tw_time()

def align_to_5min(dt):
    """對齊到 5 分鐘邊界"""
    minute = (dt.minute // 5) * 5
    return dt.replace(minute=minute, second=0, microsecond=0)

def keep_alive(url):
    """自我保持運作"""
    while True:
        try:
            requests.get(url)
            print("Pinged self to stay awake", flush=True)
        except:
            pass
        time.sleep(600)

def send_alert(msg):
    """發送通知給 Telegram"""
    try:
        requests.post(API_URL, data={"chat_id": CHAT_ID, "text": msg})
    except Exception as e:
        print(f"❌ Telegram 發送失敗: {e}")

def fetch_latest_price():
    """抓取最新成交價（修正版）"""
    try:
        r = requests.post(URL, json=get_payload(), headers={"Content-Type": "application/json"})
        
        if r.status_code != 200:
            print(f"⚠️ API 回應錯誤: HTTP {r.status_code}", flush=True)
            return None
        
        data = r.json()
        quotes = data.get("RtData", {}).get("QuoteList", [])
        
        if not quotes:
            print(f"⚠️ API 無資料: QuoteList 是空的", flush=True)
            return None

        # 只抓期貨合約（排除現貨指數 TXF-P）
        txf_futures = [q for q in quotes 
                       if q["SymbolID"].startswith("TXF") 
                       and not q["SymbolID"].endswith("-P")  # 排除現貨指數
                       and q.get("CLastPrice")]
        
        if not txf_futures:
            # 顯示有哪些合約但沒有成交價
            all_txf = [q["SymbolID"] for q in quotes if q["SymbolID"].startswith("TXF")]
            print(f"⚠️ 沒有符合條件的期貨合約", flush=True)
            print(f"   找到的合約: {all_txf[:5]}", flush=True)
            print(f"   可能原因: 還沒有成交價或盤前準備中", flush=True)
            return None

        # 找成交量最大的合約（近月）
        txf_futures.sort(key=lambda x: int(x.get("CTotalVolume", 0) or 0), reverse=True)
        q = txf_futures[0]
        
        # 使用交易所時間
        timestamp = parse_exchange_datetime(
            q.get("CDate", ""),
            q.get("CTime", "")
        )
        
        price = float(q["CLastPrice"])
        ref_price = float(q.get("CRefPrice", 0)) if q.get("CRefPrice") else price
        volume = int(q.get("CTotalVolume", 0) or 0)  # 總成交量
        
        return timestamp, price, ref_price, volume

    except Exception as e:
        print(f"❌ 抓取價格失敗: {e}", flush=True)
        import traceback
        traceback.print_exc()
        return None

def calc_macd(df):
    """計算標準 MACD (12, 26, 9)"""
    ema12 = df['close'].ewm(span=12, adjust=False).mean()
    ema26 = df['close'].ewm(span=26, adjust=False).mean()
    df['MACD'] = ema12 - ema26
    df['Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()
    df['Histogram'] = df['MACD'] - df['Signal']
    return df

def check_divergence(df):
    """背離判斷"""
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

def record_signal(signal_type, price, signal_data, df_5min):
    """記錄訊號到資料庫"""
    try:
        session = Session()
        signal = SignalLog(
            timestamp=get_tw_time(),
            signal_type=signal_type,
            entry_price=price,
            slope=float(signal_data['slope']),
            hist_avg=float(signal_data['hist_avg']),
            hist_now=float(signal_data['hist_now']),
            price_range=float(signal_data['price_range']),
            slope_threshold=params.slope_threshold,
            lookback=params.lookback
        )
        session.add(signal)
        session.commit()
        session.close()
        print(f"✅ 訊號已記錄到資料庫: {signal_type}", flush=True)
    except Exception as e:
        print(f"❌ 記錄訊號失敗: {e}")

def update_signal_results(df_5min):
    """更新訊號結果"""
    try:
        session = Session()
        current_time = get_tw_time()
        current_price = float(df_5min['close'].iloc[-1])
        
        pending_signals = session.query(SignalLog).filter(SignalLog.result == None).all()
        
        for signal in pending_signals:
            time_diff = (current_time - signal.timestamp).total_seconds() / 60
            
            if signal.price_10min is None and time_diff >= 10:
                signal.price_10min = current_price
            
            if signal.price_30min is None and time_diff >= 30:
                signal.price_30min = current_price
            
            if signal.price_1hour is None and time_diff >= 60:
                signal.price_1hour = current_price
                
                if '看多' in signal.signal_type or '轉多' in signal.signal_type:
                    profit_loss = current_price - signal.entry_price
                else:
                    profit_loss = signal.entry_price - current_price
                
                signal.profit_loss = profit_loss
                dynamic_threshold = max(20, min(50, signal.price_range * 0.3))
                
                if profit_loss > dynamic_threshold:
                    signal.result = 'success'
                elif profit_loss < -dynamic_threshold:
                    signal.result = 'fail'
                else:
                    signal.result = 'neutral'
                
                signal.threshold_used = dynamic_threshold
                print(f"✅ 訊號結果已更新: {signal.signal_type} -> {signal.result}", flush=True)
        
        session.commit()
        session.close()
    except Exception as e:
        print(f"❌ 更新訊號結果失敗: {e}")

def analyze_signals():
    """分析訊號勝率"""
    try:
        session = Session()
        completed_signals = session.query(SignalLog).filter(SignalLog.result != None).all()
        
        if len(completed_signals) == 0:
            session.close()
            return None
        
        data = [{
            'signal_type': s.signal_type,
            'result': s.result,
            'profit_loss': s.profit_loss
        } for s in completed_signals]
        df_completed = pd.DataFrame(data)
        
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
        
        session.close()
        return stats
    except Exception as e:
        print(f"❌ 分析訊號失敗: {e}")
        return None

def print_statistics(stats):
    """打印統計報告"""
    if not stats:
        return
    
    print("\n" + "=" * 80, flush=True)
    print("📊 訊號統計報告", flush=True)
    print("=" * 80, flush=True)
    print(f"總訊號數: {stats['total_signals']}", flush=True)
    print(f"成功: {stats['success_count']} | 失敗: {stats['fail_count']} | 中性: {stats['neutral_count']}", flush=True)
    print(f"整體勝率: {stats['success_rate']:.1f}%", flush=True)
    print(f"平均損益: {stats['avg_profit']:+.1f} 點", flush=True)
    
    print("\n各類訊號表現:", flush=True)
    for signal_type, data in stats['by_signal_type'].items():
        print(f"  {signal_type}:", flush=True)
        print(f"    數量: {data['total']} | 勝率: {data['success_rate']:.1f}% | 平均損益: {data['avg_profit']:+.1f} 點", flush=True)
    
    print("=" * 80 + "\n", flush=True)

def optimize_parameters(stats):
    """根據勝率自動調整參數"""
    if not stats or stats['total_signals'] < params.min_signals_for_optimization:
        print(f"⏳ 訊號數量不足，需要至少 {params.min_signals_for_optimization} 個訊號才能優化", flush=True)
        return False
    
    success_rate = stats['success_rate']
    old_slope = params.slope_threshold
    old_lookback = params.lookback
    
    print("\n" + "=" * 80, flush=True)
    print("🤖 開始自動優化參數", flush=True)
    print("=" * 80, flush=True)
    print(f"當前勝率: {success_rate:.1f}%", flush=True)
    print(f"當前參數: slope_threshold={old_slope}, lookback={old_lookback}", flush=True)
    
    if success_rate < 55:
        params.slope_threshold = min(old_slope + 0.5, 6.0)
        params.lookback = min(old_lookback + 2, 15)
        print("📉 勝率偏低，提高門檻以減少假訊號", flush=True)
    elif success_rate > 75:
        params.slope_threshold = max(old_slope - 0.5, 2.0)
        params.lookback = max(old_lookback - 1, 8)
        print("📈 勝率良好，降低門檻以增加訊號", flush=True)
    elif 60 <= success_rate <= 70:
        avg_profit = stats['avg_profit']
        if avg_profit < 20:
            params.slope_threshold = old_slope + 0.2
            print("💰 平均獲利偏低，微調門檻", flush=True)
    
    params.save_params()
    
    print(f"新參數: slope_threshold={params.slope_threshold}, lookback={params.lookback}", flush=True)
    print("=" * 80 + "\n", flush=True)
    
    msg = (f"🤖 參數已自動優化\n"
           f"勝率: {success_rate:.1f}%\n"
           f"slope: {old_slope} → {params.slope_threshold}\n"
           f"lookback: {old_lookback} → {params.lookback}")
    send_alert(msg)
    
    return True

# === 主程式（修正版）===
def main():
    import sys
    print("=" * 60, flush=True)
    print("🤖 開始監控台指期 MACD 背離訊號（完全修正版）", flush=True)
    print("=" * 60, flush=True)
    print("📌 指標系統：標準 MACD (12, 26, 9)", flush=True)
    print("📌 使用交易所時間，K 棒完成後才計算", flush=True)
    print(f"📌 當前參數：slope={params.slope_threshold}, lookback={params.lookback}", flush=True)
    print("=" * 60 + "\n", flush=True)
    sys.stdout.flush()
    
    # K 棒相關變數
    current_bar_ticks = []  # 當前 K 棒的所有 tick
    df_5min = pd.DataFrame(columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    last_bar_time = None
    first_bar_incomplete = False  # 標記第一根 K 棒是否不完整
    
    # 訊號相關變數
    last_alert = None
    last_alert_time = get_tw_time() - timedelta(days=1)
    data_ready = False
    last_analysis_time = get_tw_time()
    last_heartbeat = get_tw_time()
    loop_count = 0
    
    while True:
        loop_count += 1
        
        # 心跳訊息
        if (get_tw_time() - last_heartbeat).total_seconds() >= 60:
            print(f"💓 心跳 #{loop_count} | {get_tw_time().strftime('%Y-%m-%d %H:%M:%S')} | 監控運行中...", flush=True)
            sys.stdout.flush()
            last_heartbeat = get_tw_time()
        
        # 檢查是否在交易時間
        if not is_market_open():
            if loop_count % 20 == 1:  # 每分鐘提示一次
                print(f"😴 非交易時間，暫停監控 | {get_tw_time().strftime('%H:%M:%S')}", flush=True)
            time.sleep(3)
            continue
        
        # 抓取價格
        result = fetch_latest_price()
        
        if not result:
            if loop_count <= 5:
                print(f"⚠️ [{loop_count}] 無法取得價格 | {get_tw_time().strftime('%H:%M:%S')}", flush=True)
            time.sleep(3)
            continue
        
        timestamp, price, ref_price, volume = result
        
        # 顯示前 10 次抓取
        if loop_count <= 10:
            print(f"📊 [{loop_count}] 抓取價格: {price:,.0f} | {timestamp.strftime('%H:%M:%S')}", flush=True)
            sys.stdout.flush()
        
        # 對齊到 5 分鐘邊界
        bar_time = align_to_5min(timestamp)
        
        # 將 tick 加入當前 K 棒（只記錄價格變動的 tick）
        if len(current_bar_ticks) == 0 or current_bar_ticks[-1]['price'] != price:
            current_bar_ticks.append({
                'time': timestamp,
                'price': price,
                'volume': volume
            })
        else:
            # 價格沒變，只更新最後一筆的時間和成交量
            current_bar_ticks[-1]['time'] = timestamp
            current_bar_ticks[-1]['volume'] = volume
        
        # 檢查是否到新的 K 棒
        if last_bar_time is None:
            last_bar_time = bar_time
            # 計算距離 K 棒開始已經過了多久
            bar_start = bar_time
            time_elapsed = (timestamp - bar_start).total_seconds()
            
            if time_elapsed > 60:  # 如果已經過了 1 分鐘
                first_bar_incomplete = True
                print(f"⚠️ 注意：程式啟動時，當前 K 棒 {bar_time.strftime('%H:%M')} 已進行 {time_elapsed/60:.1f} 分鐘", flush=True)
                print(f"⚠️ 這根 K 棒的資料不完整，將標記為不完整並從下一根開始正常收集", flush=True)
            
            print(f"🎯 開始收集 K 棒: {bar_time.strftime('%H:%M')}", flush=True)
        
        if bar_time > last_bar_time:
            # K 棒完成！
            if len(current_bar_ticks) > 0:
                prices = [t['price'] for t in current_bar_ticks]
                
                # 計算這根 K 棒的成交量（最後的總量 - 第一筆的總量）
                bar_volume = current_bar_ticks[-1]['volume'] - current_bar_ticks[0]['volume']
                if bar_volume < 0:  # 跨日或換月時可能出現負數
                    bar_volume = current_bar_ticks[-1]['volume']
                
                new_bar = {
                    'timestamp': last_bar_time,
                    'open': prices[0],
                    'high': max(prices),
                    'low': min(prices),
                    'close': prices[-1],  # 最後一筆才是收盤價
                    'volume': bar_volume,
                    'tick_count': len(prices)  # 記錄實際有幾筆價格變動
                }
                
                # 加入完成的 K 棒
                if len(df_5min) == 0:
                    df_5min = pd.DataFrame([new_bar])
                else:
                    df_5min = pd.concat([df_5min, pd.DataFrame([new_bar])], ignore_index=True)
                df_5min = df_5min.tail(100)  # 只保留最近 100 根
                
                # 顯示 K 棒完成訊息
                incomplete_mark = " ⚠️ [不完整]" if first_bar_incomplete and len(df_5min) == 1 else ""
                print(f"✅ K 棒完成: {last_bar_time.strftime('%H:%M')} | O:{prices[0]:.0f} H:{max(prices):.0f} L:{min(prices):.0f} C:{prices[-1]:.0f} | Vol:{bar_volume} Ticks:{len(prices)}{incomplete_mark}", flush=True)
                
                # 重置不完整標記
                if first_bar_incomplete and len(df_5min) == 1:
                    first_bar_incomplete = False
                
                # 檢查資料是否足夠
                if len(df_5min) >= 60 and not data_ready:
                    data_ready = True
                    print("\n" + "=" * 60, flush=True)
                    print("✅ 資料量已足夠，開始監控！", flush=True)
                    print("=" * 60, flush=True)
                    print(f"📊 當前有 {len(df_5min)} 根 5 分鐘 K 棒", flush=True)
                    print(f"📈 最新價格: {price:,.0f}", flush=True)
                    print(f"⚙️ 監控參數: slope={params.slope_threshold}, lookback={params.lookback}", flush=True)
                    print("=" * 60 + "\n", flush=True)
                
                # 只在 K 棒完成後才計算 MACD
                if len(df_5min) >= 60:
                    df_5min_copy = df_5min.copy()
                    df_5min_copy = calc_macd(df_5min_copy)
                    
                    # 更新訊號結果
                    update_signal_results(df_5min_copy)
                    
                    # 檢查背離訊號
                    alert, signal_data = check_divergence(df_5min_copy)
                    
                    now = get_tw_time()
                    cooldown = timedelta(minutes=params.cooldown_minutes)
                    
                    if alert and alert != last_alert and now - last_alert_time > cooldown:
                        # 記錄訊號
                        record_signal(alert, price, signal_data, df_5min_copy)
                        
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
                        print(f"\n🔔 發送警報: {alert}\n", flush=True)
                
                # 清空當前 K 棒的 tick
                current_bar_ticks = []
            
            # 更新上一根 K 棒時間
            last_bar_time = bar_time
        
        # 每 30 分鐘分析一次
        if data_ready and (get_tw_time() - last_analysis_time).total_seconds() >= 1800:
            stats = analyze_signals()
            if stats:
                print_statistics(stats)
                optimize_parameters(stats)
            last_analysis_time = get_tw_time()
        
        time.sleep(3)


app = Flask(__name__)

@app.route("/")
def home():
    return "Service is running (AI Learning Version - Fixed)", 200

@app.route("/health")
def health():
    return {"status": "ok", "service": "macd-monitor", "timestamp": get_tw_time().isoformat()}, 200

@app.route("/heartbeat")
def heartbeat():
    current_time = get_tw_time()
    return f"""
    <html>
    <head>
        <meta charset="UTF-8">
        <title>心跳監控</title>
        <meta http-equiv="refresh" content="10">
        <style>
            body {{ font-family: monospace; background: #1e1e1e; color: #00ff00; padding: 20px; }}
            .pulse {{ animation: pulse 1s infinite; }}
            @keyframes pulse {{ 0%, 100% {{ opacity: 1; }} 50% {{ opacity: 0.3; }} }}
            .time {{ font-size: 2em; margin: 20px 0; }}
        </style>
    </head>
    <body>
        <h1><span class="pulse">💚</span> 系統心跳監控（修正版）</h1>
        <div class="time">⏰ {current_time.strftime('%Y-%m-%d %H:%M:%S')}</div>
        <p>✅ 服務正常運行</p>
        <p>🔄 每 10 秒自動刷新</p>
        <p>🌏 使用台灣時區</p>
        <p>📊 K 棒完成後才計算 MACD</p>
        <hr>
        <p><a href="/" style="color: #00ff00;">返回首頁</a></p>
    </body>
    </html>
    """, 200

@app.route("/signals")
def view_signals():
    try:
        session = Session()
        signals = session.query(SignalLog).order_by(SignalLog.timestamp.desc()).limit(50).all()
        
        html = "<h1>MACD 訊號記錄（最近 50 筆）</h1>"
        html += "<table border='1' style='border-collapse: collapse; width: 100%;'>"
        html += "<tr><th>時間</th><th>訊號類型</th><th>進場價</th><th>結果</th><th>損益</th></tr>"
        
        for s in signals:
            result_color = {
                'success': 'green',
                'fail': 'red',
                'neutral': 'orange',
                None: 'gray'
            }.get(s.result, 'gray')
            
            html += f"<tr>"
            html += f"<td>{s.timestamp.strftime('%Y-%m-%d %H:%M')}</td>"
            html += f"<td>{s.signal_type}</td>"
            html += f"<td>{s.entry_price:,.0f}</td>"
            html += f"<td style='color: {result_color}'>{s.result or '進行中'}</td>"
            html += f"<td>{s.profit_loss:+.1f if s.profit_loss else '-'}</td>"
            html += f"</tr>"
        
        html += "</table>"
        session.close()
        return html
    except Exception as e:
        return f"Error: {e}", 500

@app.route("/stats")
def view_stats():
    try:
        stats = analyze_signals()
        if not stats:
            return "<h1>尚無統計資料</h1>", 200
        
        html = "<h1>📊 訊號統計報告</h1>"
        html += f"<p>總訊號數: {stats['total_signals']}</p>"
        html += f"<p>成功: {stats['success_count']} | 失敗: {stats['fail_count']} | 中性: {stats['neutral_count']}</p>"
        html += f"<p>整體勝率: {stats['success_rate']:.1f}%</p>"
        html += f"<p>平均損益: {stats['avg_profit']:+.1f} 點</p>"
        
        html += "<h2>各類訊號表現:</h2><ul>"
        for signal_type, data in stats['by_signal_type'].items():
            html += f"<li><b>{signal_type}</b>: "
            html += f"數量 {data['total']} | 勝率 {data['success_rate']:.1f}% | "
            html += f"平均損益 {data['avg_profit']:+.1f} 點</li>"
        html += "</ul>"
        
        return html
    except Exception as e:
        return f"Error: {e}", 500

if __name__ == "__main__":
    import sys
    
    # 檢查是否已有實例在運行
    lock_file = Path("macd_monitor.lock")
    if lock_file.exists():
        print("⚠️ 警告：偵測到另一個監控程式正在運行！", flush=True)
        print("⚠️ 如果確定沒有其他程式在運行，請刪除 macd_monitor.lock 檔案", flush=True)
        sys.exit(1)
    
    # 建立鎖定檔案
    lock_file.write_text(str(os.getpid()))
    
    try:
        current_time = get_tw_time()
        print("\n" + "=" * 70, flush=True)
        print("🚀 MACD 監控系統啟動中（完全修正版）...", flush=True)
        print("=" * 70, flush=True)
        print(f"⏰ 啟動時間: {current_time.strftime('%Y-%m-%d %H:%M:%S')}", flush=True)
        print(f"📅 星期: {['一', '二', '三', '四', '五', '六', '日'][current_time.weekday()]}", flush=True)
        print(f"🌏 時區: 台灣時區 (Asia/Taipei)", flush=True)
        
        current_hour = current_time.hour
        if 8 <= current_hour < 14:
            print("🕐 當前時段: 日盤交易時間 (08:45-13:45)", flush=True)
        elif 15 <= current_hour or current_hour < 5:
            print("🌙 當前時段: 夜盤交易時間 (15:00-05:00)", flush=True)
        else:
            print("😴 當前時段: 休市時間", flush=True)
        
        print("🌐 Flask 服務準備中...", flush=True)
        print("=" * 70 + "\n", flush=True)
        sys.stdout.flush()
        
        def delayed_start():
            import time
            import sys
            time.sleep(5)
            print("\n" + "=" * 70, flush=True)
            print("🤖 監控執行緒啟動中...", flush=True)
            print("=" * 70 + "\n", flush=True)
            sys.stdout.flush()
            try:
                main()
            except Exception as e:
                print(f"❌ 監控執行緒錯誤: {e}", flush=True)
                import traceback
                traceback.print_exc()
        
        t = threading.Thread(target=delayed_start, name="MonitorThread")
        t.daemon = True
        t.start()
        print(f"✅ 監控執行緒已建立 (Thread ID: {t.ident})", flush=True)
        
        def delayed_keepalive():
            import time
            import sys
            time.sleep(10)
            print("🔄 Keep-alive 功能啟動（每 10 分鐘自動喚醒）", flush=True)
            sys.stdout.flush()
            try:
                keep_alive("https://danny-macd.onrender.com")
            except Exception as e:
                print(f"❌ Keep-alive 錯誤: {e}", flush=True)
        
        t2 = threading.Thread(target=delayed_keepalive, name="KeepAliveThread")
        t2.daemon = True
        t2.start()
        print(f"✅ Keep-alive 執行緒已建立 (Thread ID: {t2.ident})", flush=True)

        print("✅ Flask 服務準備就緒，開始監聽 port 10000...", flush=True)
        print("=" * 70 + "\n", flush=True)
        app.run(host="0.0.0.0", port=10000)
    finally:
        # 清理鎖定檔案
        if lock_file.exists():
            lock_file.unlink()
            print("\n🔒 已釋放程式鎖定", flush=True)
