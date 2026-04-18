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

# --- 1. Supabase 初始化 ---
@st.cache_resource
def get_supabase_client():
    # 請確保你有設定 secrets (SUPABASE_URL, SUPABASE_KEY)
    try:
        url = st.secrets["SUPABASE_URL"]
        key = st.secrets["SUPABASE_KEY"]
        return create_client(url, key)
    except:
        return None

supabase = get_supabase_client()

# --- 2. 獲取股票列表 ---
@st.cache_data(ttl=86400)
def get_stock_list(market):
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        if market == "美股 (S&P 500)":
            url = 'https://en.wikipedia.org/wiki/List_of_S%26P_500_companies'
            table = pd.read_html(io.StringIO(requests.get(url, headers=headers).text))[0]
            return table['Symbol'].str.replace('.', '-', regex=False).tolist(), "^GSPC"
        elif market == "美股 (Nasdaq 100)":
            url = 'https://en.wikipedia.org/wiki/Nasdaq-100'
            tables = pd.read_html(io.StringIO(requests.get(url, headers=headers).text))
            for t in tables:
                if 'Ticker' in t.columns: return t['Ticker'].tolist(), "^IXIC"
        return [], None
    except: return [], None

# --- 3. 核心邏輯 ---
def check_vcp_advanced(ticker, b_days, relax_filter):
    try:
        df = yf.download(ticker, period="1y", progress=False, auto_adjust=True)
        if df.empty or len(df) < 150: return None
        
        # 處理資料格式
        close = df['Close'][ticker] if isinstance(df.columns, pd.MultiIndex) else df['Close']
        vol = df['Volume'][ticker] if isinstance(df.columns, pd.MultiIndex) else df['Volume']
        curr_p = float(close.iloc[-1])
        
        sma50 = ta.sma(close, 50).iloc[-1]
        sma150 = ta.sma(close, 150).iloc[-1]
        sma200 = ta.sma(close, 200).iloc[-1]
        
        # 篩選條件
        cond = [
            curr_p > sma150 and curr_p > sma200, 
            sma150 > sma200, 
            sma50 > sma150 and sma50 > sma200,
            curr_p > sma50
        ]
        
        # 鬆綁模式：只需滿足 2 個條件；嚴格模式：需滿足所有 4 個條件
        threshold = 2 if relax_filter else 4
        
        if sum(cond) >= threshold:
            dist_high = round((1 - curr_p/close.max()) * 100, 2)
            is_tight = "✅ 緊湊" if (close.iloc[-5:].max() - close.iloc[-5:].min()) / close.iloc[-5:].min() < 0.05 else "❌ 鬆散"
            
            return [ticker, round(curr_p, 2), dist_high, is_tight, "🚀 符合"]
    except: return None
    return None

# --- 4. UI 介面 ---
st.sidebar.header("🎛️ 設定")
market_name = st.sidebar.selectbox("市場", ["美股 (S&P 500)", "美股 (Nasdaq 100)"])
relax_filter = st.sidebar.checkbox("啟用鬆綁模式 (搜尋不到結果時開啟)", value=False)

if st.button("🚀 開始掃描"):
    tickers, _ = get_stock_list(market_name)
    results = []
    pb = st.progress(0)
    
    for i, t in enumerate(tickers[:30]): # 測試前 30 支
        res = check_vcp_advanced(t, 20, relax_filter)
        if res: results.append(res)
        pb.progress((i + 1) / 30)
    
    if results:
        df = pd.DataFrame(results, columns=["代碼", "價格", "距離高點%", "收縮狀態", "狀態"])
        st.session_state['scan_result'] = df
        st.dataframe(df)
    else:
        st.warning("沒有找到標的，請嘗試開啟側邊欄的「鬆綁模式」。")

# 同步區塊 (修正 PGRST204)
if 'scan_result' in st.session_state:
    if st.button("💾 同步至雲端"):
        if supabase:
            df = st.session_state['scan_result']
            # --- 關鍵修正：將中文欄位映射為英文，以匹配資料庫 ---
            col_mapping = {
                "代碼": "ticker",
                "價格": "price",
                "距離高點%": "dist_high",
                "收縮狀態": "vol_state",
                "狀態": "status"
            }
            df_to_save = df.rename(columns=col_mapping)
            
            try:
                supabase.table("stock_analysis").upsert(df_to_save.to_dict(orient='records')).execute()
                st.success("✅ 同步成功！")
            except Exception as e:
                st.error(f"同步失敗: {e}")
