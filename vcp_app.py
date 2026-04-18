import streamlit as st
import yfinance as yf
import pandas as pd
import pandas_ta as ta
import requests
import io
import time
from supabase import create_client

# --- 設定 ---
st.set_page_config(page_title="VCP Alpha Terminal", layout="wide")
st.title("🏹 VCP Alpha 極速版")

# --- 初始化 Supabase ---
@st.cache_resource
def get_supabase_client():
    try:
        return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])
    except: return None

supabase = get_supabase_client()

# --- 核心邏輯 (去掉了 info 抓取，速度飛快) ---
def check_vcp_advanced(ticker, sctr_map, b_days):
    try:
        df = yf.download(ticker, period="1y", progress=False, auto_adjust=True)
        if df.empty or len(df) < 200: return None
        
        close = df['Close'][ticker] if isinstance(df.columns, pd.MultiIndex) else df['Close']
        vol = df['Volume'][ticker] if isinstance(df.columns, pd.MultiIndex) else df['Volume']
        curr_p = float(close.iloc[-1])
        sma50, sma150, sma200 = ta.sma(close, 50).iloc[-1], ta.sma(close, 150).iloc[-1], ta.sma(close, 200).iloc[-1]
        
        if curr_p > sma50 and curr_p > sma150:
            recent_range = (close.iloc[-5:].max() - close.iloc[-5:].min()) / close.iloc[-5:].min()
            is_tight = "緊湊" if recent_range < 0.05 else "鬆散"
            dist_high = round((1 - curr_p/close.max()) * 100, 2)
            sctr_val = round(sctr_map.get(ticker, 0), 1)
            vol_ratio = round(float(vol.iloc[-1]) / vol.rolling(20).mean().iloc[-1], 2)
            
            return [ticker, round(curr_p, 2), dist_high, sctr_val, is_tight, vol_ratio, "強勢"]
    except: return None
    return None

# --- UI 與執行 ---
st.sidebar.header("🎛️ 系統參數")
market_name = st.sidebar.selectbox("選擇市場", ["美股 (Nasdaq 100)", "美股 (S&P 500)"])
start_scan = st.sidebar.button("🚀 開始掃描")

if start_scan:
    # (此處呼叫您的 get_stock_list)
    tickers, _ = get_stock_list(market_name) # 假設這已定義
    sctr_ranks = {} # 假設已定義
    
    results = []
    pb = st.progress(0)
    
    # 1. 快速篩選
    for i, t in enumerate(tickers[:30]):
        res = check_vcp_advanced(t, sctr_ranks, 20)
        if res: results.append(res)
        pb.progress((i + 1) / 30)
    
    # 2. 只有篩選出的股票才抓行業資訊
    if results:
        final_data = []
        for row in results:
            ticker = row[0]
            try:
                # 只有這幾檔才去查，速度不會卡
                info = yf.Ticker(ticker).info
                sector = info.get('sector', 'N/A')
            except: sector = "N/A"
            row.append(sector) # 加入行業欄位
            final_data.append(row)
        
        df = pd.DataFrame(final_data, columns=["代碼", "價格", "距離高點%", "SCTR排名", "收縮狀態", "量比", "狀態", "行業"])
        st.session_state['scan_result'] = df
        st.dataframe(df)
        st.success("掃描完成！")
