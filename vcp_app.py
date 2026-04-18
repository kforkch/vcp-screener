import streamlit as st
import yfinance as yf
import pandas as pd
import pandas_ta as ta
import requests
import io
import numpy as np
from supabase import create_client
from concurrent.futures import ThreadPoolExecutor

# --- 頁面配置 ---
st.set_page_config(page_title="VCP Alpha Terminal", layout="wide")
st.title("🏹 VCP Alpha 高效能交易終端")

# --- 1. Supabase 初始化 ---
@st.cache_resource
def get_supabase_client():
    try: return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])
    except: return None

supabase = get_supabase_client()

# --- 2. 工具函式 ---
@st.cache_data(ttl=86400)
def get_sector_cached(ticker):
    try:
        info = yf.Ticker(ticker).info
        return info.get('sector', 'N/A')
    except: return 'N/A'

@st.cache_data(ttl=86400)
def get_stock_list(market):
    # 此處保留你的列表邏輯
    if market == "港股 (恒生指數)":
        return ["0001.HK", "0005.HK", "0388.HK", "0700.HK", "0939.HK", "0941.HK", "1299.HK", "1810.HK", "2318.HK", "3690.HK", "9988.HK"], "^HSI"
    elif market == "中國 A 股 (滬深 300 龍頭)":
        return ["600519.SS", "601318.SS", "600036.SS", "601012.SS", "600276.SS", "601166.SS", "000858.SZ", "000333.SZ", "300750.SZ"], "000300.SS"
    return [], None

# --- 3. 核心邏輯 ---
def check_vcp_advanced(ticker, sctr_map, b_only, b_days):
    try:
        df = yf.download(ticker, period="1y", progress=False, auto_adjust=True)
        if df.empty or len(df) < 200: return None
        
        close = df['Close'][ticker] if isinstance(df.columns, pd.MultiIndex) else df['Close']
        vol = df['Volume'][ticker] if isinstance(df.columns, pd.MultiIndex) else df['Volume']
        curr_p = float(close.iloc[-1])
        
        sma50, sma150, sma200 = ta.sma(close, 50).iloc[-1], ta.sma(close, 150).iloc[-1], ta.sma(close, 200).iloc[-1]
        high52 = float(close.max())
        
        # Minervini 篩選
        cond = [curr_p > sma150 and curr_p > sma200, sma150 > sma200, sma50 > sma150 and sma50 > sma200, curr_p > sma50]
        if sum(cond) == 4:
            dist_high = round((1 - curr_p/high52) * 100, 2)
            sctr_val = round(sctr_map.get(ticker, 0), 1)
            is_breakout = curr_p > close.iloc[-(b_days+1):-1].max()
            if b_only and not is_breakout: return None
            return [ticker, round(curr_p, 2), dist_high, sctr_val, "強勢", get_sector_cached(ticker)]
    except: return None
    return None

# --- 4. 介面與並行執行 ---
st.sidebar.header("🎛️ 系統參數")
market_name = st.sidebar.selectbox("選擇市場", ["港股 (恒生指數)", "中國 A 股 (滬深 300 龍頭)"])
only_b = st.sidebar.checkbox("僅看突破", value=False)

if st.sidebar.button("🚀 開始高速掃描"):
    tickers, _ = get_stock_list(market_name)
    
    # 簡易 SCTR 模擬
    sctr_ranks = {t: 50.0 for t in tickers} 
    
    results = []
    pb = st.progress(0)
    
    # 【關鍵升級：使用 ThreadPoolExecutor 同時處理 10 檔股票】
    with ThreadPoolExecutor(max_workers=10) as executor:
        # 將任務提交給線程池
        future_to_ticker = {executor.submit(check_vcp_advanced, t, sctr_ranks, only_b, 20): t for t in tickers}
        
        for i, future in enumerate(future_to_ticker):
            res = future.result() # 獲取結果
            if res: results.append(res)
            pb.progress((i + 1) / len(tickers))

    if results:
        df = pd.DataFrame(results, columns=["代碼", "價格", "距離高點%", "SCTR排名", "狀態", "行業"])
        st.dataframe(df, use_container_width=True)
        st.session_state['scan_result'] = df
        st.success(f"✅ 掃描完成，共找到 {len(results)} 檔標的")
