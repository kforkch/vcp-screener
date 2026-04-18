import streamlit as st
import yfinance as yf
import pandas as pd
import pandas_ta as ta
import requests
import io
import numpy as np
from supabase import create_client

# --- 頁面配置 ---
st.set_page_config(page_title="VCP Alpha Terminal", layout="wide")
st.title("🏹 VCP Alpha 全球終極交易終端")

# --- 1. 初始化 ---
@st.cache_resource
def get_supabase_client():
    try:
        return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])
    except: return None

supabase = get_supabase_client()

# --- 2. 獲取市場清單 ---
@st.cache_data(ttl=86400)
def get_stock_list(market):
    headers = {"User-Agent": "Mozilla/5.0"}
    # ... (保留您原有的市場獲取邏輯) ...
    if market == "美股 (Nasdaq 100)":
        url = 'https://en.wikipedia.org/wiki/Nasdaq-100'
        tables = pd.read_html(io.StringIO(requests.get(url, headers=headers).text))
        for t in tables:
            if 'Ticker' in t.columns: return t['Ticker'].tolist(), "^IXIC"
    return [], None

# --- 3. 核心邏輯 (含行業抓取) ---
def check_vcp_advanced(ticker):
    try:
        df = yf.download(ticker, period="1y", progress=False, auto_adjust=True)
        if df.empty or len(df) < 200: return None
        
        # 抓取行業 (加入 try 避免因為單一股票錯誤中斷)
        try:
            info = yf.Ticker(ticker).info
            sector = info.get('sector', 'N/A')
        except: sector = "N/A"
        
        close = df['Close'][ticker] if isinstance(df.columns, pd.MultiIndex) else df['Close']
        vol = df['Volume'][ticker] if isinstance(df.columns, pd.MultiIndex) else df['Volume']
        curr_p = float(close.iloc[-1])
        sma50, sma150 = ta.sma(close, 50).iloc[-1], ta.sma(close, 150).iloc[-1]
        
        # VCP 篩選 (簡化版)
        if curr_p > sma50 and curr_p > sma150:
            recent_range = (close.iloc[-5:].max() - close.iloc[-5:].min()) / close.iloc[-5:].min()
            is_tight = "緊湊" if recent_range < 0.05 else "鬆散"
            dist_high = round((1 - curr_p/close.max()) * 100, 2)
            vol_ratio = round(float(vol.iloc[-1]) / vol.rolling(20).mean().iloc[-1], 2)
            return [ticker, round(curr_p, 2), dist_high, is_tight, vol_ratio, "強勢", sector]
    except: return None
    return None

# --- 4. 側邊欄 ---
st.sidebar.header("🎛️ 系統參數")
market_name = st.sidebar.selectbox("選擇市場", ["美股 (Nasdaq 100)", "美股 (S&P 500)", "港股 (恒生指數)"])
start_scan = st.sidebar.button("🚀 開始掃描")

# --- 5. 主程式執行 ---
if start_scan:
    tickers, _ = get_stock_list(market_name)
    results = []
    pb = st.progress(0)
    for i, t in enumerate(tickers[:20]):
        res = check_vcp_advanced(t)
        if res: results.append(res)
        pb.progress((i + 1) / 20)
    
    if results:
        df = pd.DataFrame(results, columns=["代碼", "價格", "距離高點%", "收縮狀態", "量比", "狀態", "行業"])
        st.session_state['scan_result'] = df
        st.dataframe(df, use_container_width=True)

# --- 6. 同步邏輯 ---
if 'scan_result' in st.session_state:
    st.markdown("---")
    if st.button("💾 同步至雲端 (含行業板塊)"):
        if supabase:
            df = st.session_state['scan_result']
            col_mapping = {
                "代碼": "ticker",
                "價格": "price",
                "距離高點%": "dist_high",
                "收縮狀態": "vol_state",
                "量比": "vol_ratio",
                "狀態": "status",
                "行業": "sector"
            }
            df_to_sync = df.rename(columns=col_mapping)
            try:
                supabase.table("stock_analysis").upsert(df_to_sync.to_dict(orient='records')).execute()
                st.success("✅ 同步成功！行業資訊已寫入。")
            except Exception as e:
                st.error(f"同步錯誤: {e}")
