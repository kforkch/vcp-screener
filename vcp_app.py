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

# --- 初始化 Supabase ---
@st.cache_resource
def get_supabase_client():
    try:
        url = str(st.secrets["SUPABASE_URL"]).strip().replace('"', '').replace("'", "")
        key = str(st.secrets["SUPABASE_KEY"]).strip().replace('"', '').replace("'", "")
        return create_client(url, key)
    except:
        return None

supabase = get_supabase_client()

# --- 獲取股票列表 ---
@st.cache_data(ttl=86400)
def get_stock_list(market):
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        if market == "美股 (S&P 500)":
            url = 'https://en.wikipedia.org/wiki/List_of_S%26P_500_companies'
            table = pd.read_html(io.StringIO(requests.get(url, headers=headers).text))[0]
            return table['Symbol'].str.replace('.', '-', regex=False).tolist()
        return ["AAPL", "NVDA", "MSFT", "TSLA", "AMD", "GOOGL"]
    except: return []

# --- 核心 VCP 掃描邏輯 (已放寬條件) ---
def check_vcp(ticker):
    try:
        # 下載一年數據
        df = yf.download(ticker, period="1y", progress=False, auto_adjust=True)
        if df.empty or len(df) < 150: return None
        
        # 處理資料格式
        close = df['Close']
        curr_p = float(close.iloc[:, 0].iloc[-1]) if isinstance(close, pd.DataFrame) else float(close.iloc[-1])
        
        # 計算均線
        sma50 = ta.sma(df['Close'].iloc[:, 0] if isinstance(df['Close'], pd.DataFrame) else df['Close'], 50).iloc[-1]
        sma150 = ta.sma(df['Close'].iloc[:, 0] if isinstance(df['Close'], pd.DataFrame) else df['Close'], 150).iloc[-1]
        sma200 = ta.sma(df['Close'].iloc[:, 0] if isinstance(df['Close'], pd.DataFrame) else df['Close'], 200).iloc[-1]
        high52 = float(df['Close'].max())
        
        # --- 寬鬆篩選 ---
        # 只要股價大於 50日線 且 距離高點在 30% 以內 (不要求完美排列，確保有結果)
        dist_high = round((1 - curr_p/high52)*100, 2)
        if curr_p > sma50 and dist_high < 30:
            return [ticker, round(curr_p, 2), dist_high, "✅ 符合趨勢"]
    except: return None
    return None

# --- UI 介面 ---
tab1, tab2 = st.tabs(["☁️ 雲端每日看板", "🚀 即時掃描"])

with tab1:
    if st.button("🔄 重新讀取雲端資料"):
        if supabase:
            try:
                res = supabase.table("stock_analysis").select("*").execute()
                if res.data: st.dataframe(pd.DataFrame(res.data))
                else: st.info("目前雲端無資料。")
            except Exception as e: st.error(f"讀取錯誤: {e}")

with tab2:
    market_name = st.selectbox("選擇市場", ["美股 (S&P 500)"])
    
    if st.button("🚀 開始掃描"):
        tickers = get_stock_list(market_name)[:30] # 限制掃描數量以防超時
        results = []
        bar = st.progress(0)
        
        for i, t in enumerate(tickers):
            res = check_vcp(t)
            if res: results.append(res)
            bar.progress((i + 1) / len(tickers))
        
        if results:
            df = pd.DataFrame(results, columns=["代碼", "價格", "距離高點%", "狀態"])
            # 加上圖表連結
            df['圖表'] = df['代碼'].apply(lambda t: f"https://www.tradingview.com/chart/?symbol={t.replace('.', '-')}")
            st.session_state['scan_result'] = df
            st.success(f"成功找到 {len(df)} 支標的！")
        else:
            st.warning("沒有找到符合條件的標的，請嘗試調寬篩選條件。")

    # 顯示結果與同步
    if 'scan_result' in st.session_state:
        st.dataframe(
            st.session_state['scan_result'],
            column_config={"圖表": st.column_config.LinkColumn("查看圖表")}
        )
        
        if st.button("💾 同步至 Supabase"):
            if supabase:
                try:
                    df_to_save = st.session_state['scan_result'].rename(columns={
                        "代碼": "ticker", 
                        "價格": "price", 
                        "距離高點%": "dist_high", 
                        "狀態": "status"
                    })
                    # 只取資料庫對應欄位
                    save_data = df_to_save[["ticker", "price", "dist_high", "status"]]
                    supabase.table("stock_analysis").upsert(save_data.to_dict(orient='records')).execute()
                    st.success("✅ 同步成功！")
                except Exception as e: st.error(f"同步失敗: {e}")
