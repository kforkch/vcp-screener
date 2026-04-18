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
    # 確保不會因為格式問題報錯
    url = str(st.secrets.get("SUPABASE_URL", "")).strip().replace('"', '').replace("'", "")
    key = str(st.secrets.get("SUPABASE_KEY", "")).strip().replace('"', '').replace("'", "")
    return create_client(url, key)

try:
    supabase = get_supabase_client()
except:
    st.error("Supabase 連線失敗，請檢查 secrets 設定。")
    supabase = None

# --- 核心功能函式 ---
@st.cache_data(ttl=86400)
def get_stock_list(market):
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        if market == "美股 (S&P 500)":
            url = 'https://en.wikipedia.org/wiki/List_of_S%26P_500_companies'
            table = pd.read_html(io.StringIO(requests.get(url, headers=headers).text))[0]
            return table['Symbol'].str.replace('.', '-', regex=False).tolist()
        return ["AAPL", "NVDA", "MSFT"]
    except: return []

def check_vcp_advanced(ticker):
    try:
        # 下載資料
        df = yf.download(ticker, period="1y", progress=False, auto_adjust=True)
        if df.empty or len(df) < 100: return None
        
        # --- 修正 TypeError 的關鍵 ---
        close_series = df['Close']
        curr_p = float(close_series.iloc[:, 0].iloc[-1]) if isinstance(close_series, pd.DataFrame) else float(close_series.iloc[-1])
        
        # 指標計算
        sma50 = ta.sma(df['Close'].iloc[:, 0] if isinstance(df['Close'], pd.DataFrame) else df['Close'], 50).iloc[-1]
        high52 = float(df['Close'].max())
        dist_high = round((1 - curr_p/high52)*100, 2)
        
        # --- 篩選條件 (這裡設定為寬鬆模式) ---
        # 只要股價 > 50日線 且 距離高點 < 25% 就顯示
                # --- 修改成這樣：放寬篩選，同時顯示失敗原因 ---
        if curr_p > sma50:
            return [ticker, round(curr_p, 2), dist_high, "✅ 符合：股價站上50日線"]
        else:
            # 如果還是空的，我們回傳一個「不合格」的狀態，看看是什麼情況
            return [ticker, round(curr_p, 2), dist_high, "❌ 不符：股價在50日線下"]

    except: return None
    return None

# --- UI 介面 ---
tab1, tab2 = st.tabs(["☁️ 雲端每日看板", "🚀 即時掃描"])

with tab1:
    if st.button("🔄 重新讀取雲端資料"):
        if supabase:
            res = supabase.table("stock_analysis").select("*").execute()
            if res.data: st.dataframe(pd.DataFrame(res.data))

with tab2:
    market_name = st.selectbox("選擇市場", ["美股 (S&P 500)"])
    
    if st.button("🚀 開始掃描"):
        tickers = get_stock_list(market_name)[:20] # 測試前 20 支
        results = []
        bar = st.progress(0)
        
        for i, t in enumerate(tickers):
            res = check_vcp_advanced(t)
            if res: results.append(res)
            bar.progress((i + 1) / len(tickers))
        
        if results:
            df = pd.DataFrame(results, columns=["代碼", "價格", "距離高點%", "狀態"])
            
            # --- 智能圖表連結 ---
            def make_link(t):
                return f"https://www.tradingview.com/chart/?symbol={t.replace('.', '-')}"
            
            df['圖表'] = df['代碼'].apply(make_link)
            st.session_state['scan_result'] = df
            st.success(f"掃描完成，找到 {len(df)} 支標的！")
        else:
            st.warning("沒有符合篩選條件的標的。")

    # 顯示結果與同步
    if 'scan_result' in st.session_state:
        st.dataframe(
            st.session_state['scan_result'],
            column_config={"圖表": st.column_config.LinkColumn("查看圖表")}
        )
        
        if st.button("💾 同步至 Supabase"):
            if supabase:
                data = st.session_state['scan_result'].rename(columns={"代碼": "ticker", "價格": "price", "距離高點%": "dist_high", "狀態": "status"})
                supabase.table("stock_analysis").upsert(data.to_dict(orient='records')).execute()
                st.success("✅ 同步成功！")
