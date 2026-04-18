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
    url = str(st.secrets["SUPABASE_URL"]).strip().replace('"', '').replace("'", "")
    key = str(st.secrets["SUPABASE_KEY"]).strip().replace('"', '').replace("'", "")
    return create_client(url, key)

supabase = get_supabase_client()

# --- 2. 功能函數 ---
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

def calculate_sctr_ranks(tickers):
    # 簡化計算，避免錯誤
    return {t: 0 for t in tickers}

def check_vcp_advanced(ticker):
    try:
        df = yf.download(ticker, period="1y", progress=False, auto_adjust=True)
        if df.empty or len(df) < 100: return None
        
        # --- 修正 TypeError 的關鍵 ---
        close_series = df['Close']
        if isinstance(close_series, pd.DataFrame):
            curr_p = float(close_series.iloc[:, 0].iloc[-1])
        else:
            curr_p = float(close_series.iloc[-1])
            
        high52 = float(df['Close'].max())
        
        # 簡易邏輯：距離高點小於 20% 即列出
        dist = round((1 - curr_p/high52)*100, 2)
        if dist < 20:
            return [ticker, round(curr_p, 2), dist, "N/A", "✅ 強勢"]
    except: return None
    return None

# --- 3. UI ---
tab1, tab2 = st.tabs(["☁️ 雲端每日看板", "🚀 即時掃描"])

with tab1:
    if st.button("🔄 重新讀取雲端資料"):
        try:
            response = supabase.table("stock_analysis").select("*").execute()
            if response.data: st.dataframe(pd.DataFrame(response.data))
        except Exception as e: st.error(f"讀取失敗: {e}")

with tab2:
    market_name = st.selectbox("選擇市場", ["美股 (S&P 500)", "美股 (Nasdaq 100)"])
    if st.button("🚀 開始掃描"):
        tickers, _ = get_stock_list(market_name)
        results = []
        for t in tickers[:50]: # 先掃前 50 支，避免超時
            res = check_vcp_advanced(t)
            if res: results.append(res)
        
        if results:
            df = pd.DataFrame(results, columns=["代碼", "價格", "距離高點%", "SCTR排名", "狀態"])
            st.session_state['scan_result'] = df
            st.dataframe(df)

    if 'scan_result' in st.session_state:
        if st.button("💾 同步至雲端"):
            try:
                # 強制英文欄位，避免 PGRST204
                df_to_save = st.session_state['scan_result'].rename(columns={
                    "代碼": "ticker", 
                    "價格": "price", 
                    "距離高點%": "dist_high", 
                    "SCTR排名": "sctr", 
                    "狀態": "status"
                })
                supabase.table("stock_analysis").upsert(df_to_save.to_dict(orient='records')).execute()
                st.success("✅ 同步成功！")
            except Exception as e: st.error(f"同步失敗: {e}")
