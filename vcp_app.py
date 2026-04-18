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

# --- Supabase 初始化 ---
@st.cache_resource
def get_supabase():
    try:
        url = st.secrets["SUPABASE_URL"]
        key = st.secrets["SUPABASE_KEY"]
        return create_client(url, key)
    except Exception as e:
        return None

supabase = get_supabase()

# --- 工具函數：圖表連結 ---
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

# --- 原有核心函數 (保留你的邏輯) ---
@st.cache_data(ttl=86400)
def get_stock_list(market):
    # ... (你的原 get_stock_list 程式碼) ...
    pass 

def calculate_sctr_ranks(tickers):
    # ... (你的原 calculate_sctr_ranks 程式碼) ...
    pass

def check_vcp_advanced(ticker, sctr_map, b_only, b_days):
    # ... (你的原 check_vcp_advanced 程式碼) ...
    pass

# --- UI 介面 ---
tab1, tab2 = st.tabs(["☁️ 雲端每日看板", "🚀 即時掃描"])

with tab1:
    st.subheader("每日自動掃描結果")
    if st.button("🔄 重新讀取雲端數據"):
        if supabase:
            try:
                # 從 stock_analysis 表讀取
                response = supabase.table("stock_analysis").select("*").execute()
                df = pd.DataFrame(response.data)
                if not df.empty:
                    df['圖表'] = df['ticker'].apply(make_link)
                    st.dataframe(df, column_config={"圖表": st.column_config.LinkColumn("查看", display_text="Open")})
                else:
                    st.info("資料庫目前為空，請確認 GitHub Actions 是否已運行。")
            except Exception as e:
                st.error(f"讀取資料庫失敗: {e}")
        else:
            st.error("Supabase 未連接，請檢查 Streamlit Secrets 設定。")

with tab2:
    # --- 原有的掃描區 ---
    market_name = st.selectbox("選擇市場", ["美股 (Nasdaq 100)", "美股 (S&P 500)", "港股 (恒生指數)", "中國 A 股 (滬深 300 龍頭)"])
    min_sctr_val = st.slider("最低 SCTR 排名", 0.0, 99.9, 70.0, key="sctr_slider")
    b_days = st.selectbox("突破檢測天數", [10, 20, 50], index=1)
    only_b = st.checkbox("僅看突破", value=False)
    
    if st.button("🚀 執行即時掃描"):
        # ... (將你原本的掃描執行邏輯放在這裡) ...
        st.warning("即時掃描進行中...")
