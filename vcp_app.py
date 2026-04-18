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
    try:
        url = st.secrets["SUPABASE_URL"]
        key = st.secrets["SUPABASE_KEY"]
        return create_client(url, key)
    except Exception as e:
        st.error(f"Supabase 初始化失敗: {e}")
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
        elif market == "港股 (恒生指數)":
            hsi_list = ["0700.HK", "9988.HK", "2318.HK", "3690.HK", "1299.HK", "0941.HK", "0005.HK"]
            return hsi_list, "^HSI"
        return [], None
    except: return [], None

# --- 3. SCTR 排名計算 ---
def calculate_sctr_ranks(tickers):
    try:
        raw_data = yf.download(tickers, period="1y", progress=False, auto_adjust=True)
        data = raw_data['Close'] if 'Close' in raw_data else raw_data
        sctr_data = []
        for ticker in tickers:
            try:
                series = data[ticker].dropna() if isinstance(data, pd.DataFrame) else data.dropna()
                if len(series) < 200: continue
                sma200, sma50 = series.rolling(200).mean().iloc[-1], series.rolling(50).mean().iloc[-1]
                raw = ((series.iloc[-1]/sma200-1)*30) + ((series.iloc[-1]/sma50-1)*15)
                sctr_data.append({'ticker': ticker, 'raw': raw})
            except: continue
        if not sctr_data: return {}
        df_sctr = pd.DataFrame(sctr_data)
        df_sctr['rank'] = df_sctr['raw'].rank(pct=True) * 99.9
        return df_sctr.set_index('ticker')['rank'].to_dict()
    except: return {}

# --- 4. 核心篩選 ---
def check_vcp_advanced(ticker, sctr_map):
    try:
        df = yf.download(ticker, period="1y", progress=False, auto_adjust=True)
        if df.empty or len(df) < 200: return None
        close = df['Close'][ticker] if isinstance(df.columns, pd.MultiIndex) else df['Close']
        curr_p = float(close.iloc[-1])
        sma50, sma150 = ta.sma(close, 50).iloc[-1], ta.sma(close, 150).iloc[-1]
        
        if curr_p > sma50 and curr_p > sma150:
            recent_range = (close.iloc[-5:].max() - close.iloc[-5:].min()) / close.iloc[-5:].min()
            is_tight = "緊湊" if recent_range < 0.05 else "鬆散"
            dist_high = round((1 - curr_p/close.max()) * 100, 2)
            sctr_val = round(sctr_map.get(ticker, 0), 1)
            return [ticker, round(curr_p, 2), dist_high, sctr_val, is_tight, 1.0, "強勢"]
    except: return None
    return None

# --- 5. UI 與同步邏輯 ---
st.sidebar.header("🎛️ 設定")
market_name = st.sidebar.selectbox("市場", ["美股 (Nasdaq 100)", "美股 (S&P 500)", "港股 (恒生指數)"])

if st.button("🚀 開始掃描"):
    tickers, _ = get_stock_list(market_name)
    sctr_ranks = calculate_sctr_ranks(tickers)
    results = []
    for t in tickers[:20]:
        res = check_vcp_advanced(t, sctr_ranks)
        if res: results.append(res)
    
    if results:
        df = pd.DataFrame(results, columns=["代碼", "價格", "距離高點%", "SCTR排名", "收縮狀態", "量比", "狀態"])
        st.session_state['scan_result'] = df
        st.dataframe(df)

# 同步區塊：現在已放置在正確的邏輯位置
if 'scan_result' in st.session_state:
    st.markdown("---")
    if st.button("💾 將本次掃描結果同步至雲端看板"):
        if supabase:
            df = st.session_state['scan_result']
            # 精確的對應關係
            col_mapping = {
                "代碼": "ticker",
                "價格": "price",
                "距離高點%": "dist_high",
                "SCTR排名": "sctr",        # 對應到資料庫欄位 sctr
                "收縮狀態": "vol_state",
                "量比": "vol_ratio",
                "狀態": "status"
            }
            
            df_to_sync = df.rename(columns=col_mapping)
            try:
                # 執行 Upsert
                supabase.table("stock_analysis").upsert(df_to_sync.to_dict(orient='records')).execute()
                st.success("✅ 同步成功！")
            except Exception as e:
                st.error(f"同步錯誤: {e}")
