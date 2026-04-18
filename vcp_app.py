import streamlit as st
import yfinance as yf
import pandas as pd
import pandas_ta as ta
import requests
import io
from supabase import create_client

# --- 設定頁面 ---
st.set_page_config(page_title="VCP Alpha", layout="wide")
st.title("🏹 VCP Alpha 交易終端")

# --- 1. 連線資料庫 ---
@st.cache_resource
def get_supabase_client():
    url = str(st.secrets["SUPABASE_URL"]).strip()
    key = str(st.secrets["SUPABASE_KEY"]).strip()
    return create_client(url, key)

supabase = get_supabase_client()

# --- 2. 核心功能函式 ---
@st.cache_data(ttl=86400)
def get_stock_list(market):
    # (保持您原本的市場選股邏輯)
    if market == "美股 (S&P 500)":
        url = 'https://en.wikipedia.org/wiki/List_of_S%26P_500_companies'
        table = pd.read_html(io.StringIO(requests.get(url, headers={"User-Agent": "Mozilla/5.0"}).text))[0]
        return table['Symbol'].str.replace('.', '-', regex=False).tolist()
    return ["AAPL", "NVDA", "TSLA"] # 預設測試用

def check_stock(ticker):
    try:
        df = yf.download(ticker, period="6mo", progress=False)
        if df.empty: return None
        curr_p = float(df['Close'].iloc[-1])
        sma50 = ta.sma(df['Close'], 50).iloc[-1]
        
        # 寬鬆篩選：只要股價大於 50 日線即可
        if curr_p > sma50:
            return {
                "ticker": ticker,
                "price": round(curr_p, 2),
                "status": "強勢"
            }
    except: return None
    return None

# --- 3. UI 介面 ---
if 'results' not in st.session_state: st.session_state['results'] = pd.DataFrame()

market = st.selectbox("選擇市場", ["美股 (S&P 500)"])
if st.button("🚀 開始掃描"):
    tickers = get_stock_list(market)[:20] # 先測前 20 支
    data = []
    for t in tickers:
        res = check_stock(t)
        if res: data.append(res)
    st.session_state['results'] = pd.DataFrame(data)

# 顯示與同步
if not st.session_state['results'].empty:
    st.dataframe(st.session_state['results'])
    
    if st.button("💾 同步至 Supabase"):
        try:
            # 這是最終修復 PGRST204 的關鍵：確保送到資料庫的名稱是英文的
            df_to_save = st.session_state['results']
            records = df_to_save.to_dict(orient='records')
            
            # 寫入資料庫
            supabase.table("stock_analysis").upsert(records).execute()
            st.success("✅ 同步成功！")
        except Exception as e:
            st.error(f"同步失敗: {e}")
            st.write("請確認您的 Supabase 表格中，擁有以下欄位：ticker, price, status")
