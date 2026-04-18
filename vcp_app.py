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
def init_supabase():
    try:
        url = st.secrets["SUPABASE_URL"]
        key = st.secrets["SUPABASE_KEY"]
        return create_client(url, key)
    except Exception as e:
        st.error(f"Supabase 初始化失敗，請檢查 secrets 設定: {e}")
        return None

supabase = init_supabase()

# --- 2. 工具函數 ---
def make_link(t):
    t_str = str(t)
    if ".HK" in t_str:
        code = t_str.replace('.HK', '').lstrip('0')
        return f"https://www.tradingview.com/chart/?symbol=HKEX:{code}"
    elif ".SS" in t_str or ".SZ" in t_str:
        code = t_str.split('.')[0]
        prefix = "SSE" if ".SS" in t_str else "SZSE"
        return f"https://www.tradingview.com/chart/?symbol={prefix}:{code}"
    else:
        return f"https://www.tradingview.com/chart/?symbol={t_str.replace('.', '-')}"

# --- 原有的市場掃描函數 (保留) ---
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
                if 'Symbol' in t.columns: return t['Symbol'].tolist(), "^IXIC"
        elif market == "港股 (恒生指數)":
            hsi_list = ["0001.HK", "0005.HK", "0700.HK", "9988.HK", "9888.HK", "3690.HK", "2318.HK"] # 簡化列表，實際請填完整
            return hsi_list, "^HSI"
    except: return [], None
    return [], None

def calculate_sctr_ranks(tickers):
    # ... 原有的 SCTR 計算邏輯 ...
    return {}

def check_vcp_advanced(ticker, sctr_map, b_only, b_days):
    # ... 原有的 VCP 判斷邏輯 ...
    return None

# --- UI 介面 ---
tab1, tab2 = st.tabs(["☁️ 雲端每日看板", "🚀 即時掃描"])

with tab1:
    st.subheader("每日自動掃描結果")
    if st.button("刷新數據"):
        if supabase:
            response = supabase.table("stock_analysis").select("*").execute()
            df = pd.DataFrame(response.data)
            if not df.empty:
                df['圖表'] = df['ticker'].apply(make_link)
                st.dataframe(df, column_config={"圖表": st.column_config.LinkColumn("查看", display_text="Open")})
            else:
                st.info("資料庫目前為空，請確認 GitHub Actions 是否已運行。")
        else:
            st.error("無法連接資料庫")

with tab2:
    market_name = st.selectbox("選擇市場", ["美股 (Nasdaq 100)", "美股 (S&P 500)"])
    if st.button("執行即時掃描"):
        st.warning("即時掃描將消耗大量運算資源，請耐心等待...")
        # ... 原有的掃描執行邏輯 ...
        st.write("掃描中...")
