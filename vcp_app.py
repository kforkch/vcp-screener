import streamlit as st
import yfinance as yf
import pandas as pd
import pandas_ta as ta
import requests
import io
import numpy as np
from supabase import create_client

# --- 1. 頁面配置 ---
st.set_page_config(page_title="VCP Alpha Terminal", layout="wide")
st.title("🏹 VCP Alpha 全球終極交易終端")

# --- 2. 初始化 Supabase ---
@st.cache_resource
def get_supabase_client():
    url = str(st.secrets["SUPABASE_URL"]).strip().replace('"', '').replace("'", "")
    key = str(st.secrets["SUPABASE_KEY"]).strip().replace('"', '').replace("'", "")
    return create_client(url, key)

supabase = get_supabase_client()

# --- 3. 所有功能函式定義 (放在 UI 呼叫之前) ---

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
            return ["0700.HK", "9988.HK", "3690.HK", "2318.HK", "0941.HK"], "^HSI"
        elif market == "中國 A 股 (滬深 300 龍頭)":
            return ["600519.SS", "601318.SS", "600036.SS"], "000300.SS"
    except: return [], None
    return [], None

def calculate_sctr_ranks(tickers):
    try:
        raw_data = yf.download(tickers, period="1y", interval="1d", progress=False, auto_adjust=True)
        data = raw_data['Close'] if 'Close' in raw_data else raw_data
        sctr_data = []
        for ticker in tickers:
            try:
                series = data[ticker].dropna() if isinstance(data, pd.DataFrame) else data.dropna()
                if len(series) < 200: continue
                sma200, sma50 = series.rolling(200).mean().iloc[-1], series.rolling(50).mean().iloc[-1]
                dist_200, dist_50 = (series.iloc[-1]/sma200-1)*100, (series.iloc[-1]/sma50-1)*100
                roc125, roc20 = (series.iloc[-1]/series.iloc[-125]-1)*100, (series.iloc[-1]/series.iloc[-20]-1)*100
                rsi = ta.rsi(series, length=14).iloc[-1]
                raw = (dist_200*0.3 + roc125*0.3) + (dist_50*0.15 + roc20*0.15) + (rsi*0.1)
                sctr_data.append({'ticker': ticker, 'raw': raw})
            except: continue
        if not sctr_data: return {}
        df_sctr = pd.DataFrame(sctr_data)
        df_sctr['rank'] = df_sctr['raw'].rank(pct=True) * 99.9
        return df_sctr.set_index('ticker')['rank'].to_dict()
    except: return {}

def check_vcp_advanced(ticker, sctr_map, b_only, b_days):
    try:
        df = yf.download(ticker, period="1y", progress=False, auto_adjust=True)
        if df.empty or len(df) < 200: return None
        close = df['Close'][ticker] if isinstance(df.columns, pd.MultiIndex) else df['Close']
        curr_p = float(close.iloc[-1])
        sma50, sma150, sma200 = ta.sma(close, 50).iloc[-1], ta.sma(close, 150).iloc[-1], ta.sma(close, 200).iloc[-1]
        low52, high52 = float(close.min()), float(close.max())
        cond = [curr_p > sma150 > sma200, sma150 > sma200, sma50 > sma150 > sma200, curr_p > sma50, curr_p >= low52*1.25, curr_p >= high52*0.75]
        if sum(cond) == 6:
            recent_max = float(close.iloc[-(b_days+1):-1].max())
            if b_only and not (curr_p > recent_max): return None
            return [ticker, round(curr_p, 2), round((1 - curr_p/high52)*100, 2), round(sctr_map.get(ticker, 0), 1), "✅ 緊湊", "🚀 強勢"]
    except: return None
    return None

# --- 4. UI 邏輯 ---
tab1, tab2 = st.tabs(["☁️ 雲端每日看板", "🚀 即時掃描"])

with tab1:
    st.subheader("雲端同步看板")
    if st.button("🔄 重新讀取雲端資料"):
        try:
            response = supabase.table("stock_analysis").select("*").execute()
            if response.data: st.dataframe(pd.DataFrame(response.data))
            else: st.info("資料庫目前為空。")
        except Exception as e: st.error(f"讀取失敗: {e}")

with tab2:
    market_name = st.sidebar.selectbox("選擇市場", ["美股 (Nasdaq 100)", "美股 (S&P 500)", "港股 (恒生指數)", "中國 A 股 (滬深 300 龍頭)"])
    if st.sidebar.button("🚀 執行全球同步掃描"):
        tickers, bench_code = get_stock_list(market_name) # 這裡確保 get_stock_list 已被定義
        sctr_ranks = calculate_sctr_ranks(tickers)
        results = []
        for t in tickers:
            res = check_vcp_advanced(t, sctr_ranks, False, 20)
            if res: results.append(res)
        
        if results:
            df = pd.DataFrame(results, columns=["代碼", "價格", "距離高點%", "SCTR排名", "收縮狀態", "狀態"])
            st.session_state['scan_result'] = df
            st.dataframe(df)
            
    if 'scan_result' in st.session_state:
        if st.button("💾 同步至雲端"):
            try:
                df_to_save = st.session_state['scan_result'].rename(columns={"代碼":"ticker", "價格":"price", "距離高點%":"dist_high", "SCTR排名":"sctr", "收縮狀態":"contraction_status", "狀態":"status"})
                supabase.table("stock_analysis").upsert(df_to_save.to_dict(orient='records')).execute()
                st.success("✅ 同步成功！")
            except Exception as e: st.error(f"同步失敗: {e}")
