# downloader_to_cloud.py
import os
import io
import re
import requests
import pandas as pd
import pandas_ta as ta
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from supabase import create_client
import yfinance as yf

# 讀取環境變數 (支援 Streamlit Secrets 與本地 Env)
try:
    import streamlit as st
    SUPABASE_URL = st.secrets.get("SUPABASE_URL", os.environ.get("SUPABASE_URL"))
    SUPABASE_KEY = st.secrets.get("SUPABASE_KEY", os.environ.get("SUPABASE_KEY"))
except:
    SUPABASE_URL = os.environ.get("SUPABASE_URL")
    SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("❌ 未能讀取到 SUPABASE_URL 或 SUPABASE_KEY 憑證，請確認 secrets 或是環境變數設定。")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

def clean_and_format_ticker(raw_val, market_type):
    raw_str = str(raw_val)
    digits = re.sub(r'\D', '', raw_str)
    if not digits:
        return None
    if market_type == 'HK':
        return f"{digits.zfill(4)}.HK"
    elif market_type == 'CN':
        digits = digits.zfill(6)
        return f"{digits}.SS" if digits.startswith('6') else f"{digits}.SZ"
    return None

def fetch_global_tickers():
    """自動抓取美股 S&P500, Nasdaq100 以供監控"""
    tickers = []
    headers = {"User-Agent": "Mozilla/5.0"}
    
    # S&P 500
    try:
        url = 'https://en.wikipedia.org/wiki/List_of_S%26P_500_companies'
        table = pd.read_html(io.StringIO(requests.get(url, headers=headers).text))[0]
        tickers.extend(table['Symbol'].str.replace('.', '-', regex=False).tolist())
    except Exception as e:
        print(f"抓取 S&P 500 失敗: {e}")

    # Nasdaq 100
    try:
        url = 'https://en.wikipedia.org/wiki/Nasdaq-100'
        tables = pd.read_html(io.StringIO(requests.get(url, headers=headers).text))
        for t in tables:
            if 'Ticker' in t.columns: tickers.extend(t['Ticker'].tolist()); break
            if 'Symbol' in t.columns: tickers.extend(t['Symbol'].tolist()); break
    except Exception as e:
        print(f"抓取 Nasdaq 100 失敗: {e}")

    return list(set(tickers))

def process_and_upload_ticker(ticker):
    """下載單一標的、計算 SCTR Raw、並寫入資料庫"""
    try:
        df = yf.download(ticker, period="1y", interval="1d", progress=False, auto_adjust=True)
        if df.empty or len(df) < 200:
            return ticker, False, "歷史數據不足 200 天"

        # 解析 K 線欄位
        if isinstance(df.columns, pd.MultiIndex):
            close = df['Close'][ticker]
            high  = df['High'][ticker]
            low   = df['Low'][ticker]
            open_p = df['Open'][ticker]
            vol   = df['Volume'][ticker]
        else:
            close = df['Close']
            high  = df['High']
            low   = df['Low']
            open_p = df['Open']
            vol   = df['Volume']

        # ---------- 1. 寫入 K 線數據 (只存 150 天，滿足分析器所有 SMA / 波動率回看) ----------
        kline_data = []
        recent_df = df.tail(150)
        for date_idx, _ in recent_df.iterrows():
            date_str = date_idx.strftime('%Y-%m-%d')
            kline_data.append({
                "ticker": ticker,
                "date": date_str,
                "open": float(open_p.loc[date_idx]),
                "high": float(high.loc[date_idx]),
                "low": float(low.loc[date_idx]),
                "close": float(close.loc[date_idx]),
                "volume": int(vol.loc[date_idx])
            })
        
        if kline_data:
            supabase.table("stock_klines").upsert(kline_data).execute()

        # ---------- 2. 計算 SCTR 原始分數與 20 天前歷史分數 ----------
        def get_sctr_raw(sub_series):
            sma200 = sub_series.rolling(200).mean().iloc[-1]
            sma50 = sub_series.rolling(50).mean().iloc[-1]
            dist_200 = (sub_series.iloc[-1]/sma200-1)*100
            dist_50 = (sub_series.iloc[-1]/sma50-1)*100
            roc125 = (sub_series.iloc[-1]/sub_series.iloc[-125]-1)*100
            roc20 = (sub_series.iloc[-1]/sub_series.iloc[-20]-1)*100
            rsi = ta.rsi(sub_series, length=14).iloc[-1]
            return (dist_200*0.3 + roc125*0.3) + (dist_50*0.15 + roc20*0.15) + (rsi*0.1)

        sctr_curr = get_sctr_raw(close)
        sctr_hist = get_sctr_raw(close.iloc[:-20])

        # ---------- 3. 獲取產業，並上傳 SCTR Snapshot ----------
        try:
            tk = yf.Ticker(ticker)
            sector = tk.info.get('sector', 'Unknown')
        except:
            sector = 'Unknown'

        sctr_payload = {
            "ticker": ticker,
            "price": float(close.iloc[-1]),
            "sctr_current": float(sctr_curr),
            "sctr_historical": float(sctr_hist),
            "sector": sector,
            "last_update": datetime.now().strftime('%Y-%m-%d')
        }
        supabase.table("market_sctr").upsert(sctr_payload).execute()

        return ticker, True, "成功"
    except Exception as e:
        return ticker, False, str(e)

def sync_all_data():
    print("🚀 啟動 Supabase 數據中台同步任務...")
    tickers = fetch_global_tickers()
    
    # A 股與港股讀取本地 text 備份追加
    for filename, market in [("hsi.txt", "HK"), ("csi300.txt", "CN")]:
        file_path = os.path.join("data", filename)
        if os.path.exists(file_path):
            with open(file_path, 'r', encoding='utf-8') as f:
                codes = [line.strip() for line in f if line.strip()]
                tickers.extend(codes)

    tickers = list(set(tickers))
    print(f"📊 預計同步標的數量: {len(tickers)}")

    # 採用 8 線程高效率多路並行寫入
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {executor.submit(process_and_upload_ticker, t): t for t in tickers}
        for idx, future in enumerate(as_completed(futures)):
            ticker, success, msg = future.result()
            if not success:
                print(f"❌ {ticker} 同步失敗: {msg}")
            if (idx + 1) % 50 == 0:
                print(f"⏳ 進度: {idx+1}/{len(tickers)} 筆資料同步中...")

    print("🏁 中台同步完畢！")

if __name__ == "__main__":
    sync_all_data()
