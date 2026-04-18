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
        elif market == "港股 (恒生指數)":
            hsi_list = ["0001.HK", "0005.HK", "0388.HK", "0700.HK", "0939.HK", "0941.HK", "1299.HK", "1810.HK", "2318.HK", "3690.HK", "9988.HK"]
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

# --- 4. 核心篩選 (含行業抓取) ---
def check_vcp_advanced(ticker, sctr_map, b_only, b_days):
    try:
        df = yf.download(ticker, period="1y", progress=False, auto_adjust=True)
        if df.empty or len(df) < 200: return None
        
        # 抓取基本面資訊
        info = yf.Ticker(ticker).info
        sector = info.get('sector', 'N/A')
        
        close = df['Close'][ticker] if isinstance(df.columns, pd.MultiIndex) else df['Close']
        vol = df['Volume'][ticker] if isinstance(df.columns, pd.MultiIndex) else df['Volume']
        curr_p = float(close.iloc[-1])
        sma50, sma150, sma200 = ta.sma(close, 50).iloc[-1], ta.sma(close, 150).iloc[-1], ta.sma(close, 200).iloc[-1]
        
        if curr_p > sma50 and curr_p > sma150:
            recent_range = (close.iloc[-5:].max() - close.iloc[-5:].min()) / close.iloc[-5:].min()
            is_tight = "緊湊" if recent_range < 0.05 else "鬆散"
            dist_high = round((1 - curr_p/close.max()) * 100, 2)
            sctr_val = round(sctr_map.get(ticker, 0), 1)
            vol_ratio = round(float(vol.iloc[-1]) / vol.rolling(20).mean().iloc[-1], 2)
            return [ticker, round(curr_p, 2), dist_high, sctr_val, is_tight, vol_ratio, "強勢", sector]
    except: return None
    return None

# --- 5. UI 與執行 ---
st.sidebar.header("🎛️ 設定")
market_name = st.sidebar.selectbox("市場", ["美股 (Nasdaq 100)", "美股 (S&P 500)", "港股 (恒生指數)"])
if st.button("🚀 開始掃描"):
    tickers, _ = get_stock_list(market_name)
    sctr_ranks = calculate_sctr_ranks(tickers)
    results = []
    pb = st.progress(0)
    for i, t in enumerate(tickers[:20]): # 為了演示速度，限制前20支
        res = check_vcp_advanced(t, sctr_ranks, False, 20)
        if res: results.append(res)
        pb.progress((i + 1) / 20)
    
    if results:
        # 欄位增加「行業」
        df = pd.DataFrame(results, columns=["代碼", "價格", "距離高點%", "SCTR排名", "收縮狀態", "量比", "狀態", "行業"])
        st.session_state['scan_result'] = df
        st.dataframe(df)

# --- 6. 同步邏輯 ---
if 'scan_result' in st.session_state:
    if st.button("💾 將本次掃描結果同步至雲端看板"):
        if supabase:
            df = st.session_state['scan_result']
            col_mapping = {
                "代碼": "ticker",
                "價格": "price",
                "距離高點%": "dist_high",
                "SCTR排名": "sctr",
                "收縮狀態": "vol_state",
                "量比": "vol_ratio",
                "狀態": "status",
                "行業": "sector" # 新增對應
            }
            df_to_sync = df.rename(columns=col_mapping)
            try:
                # 確保只寫入資料庫定義的欄位
                valid_cols = list(col_mapping.values())
                supabase.table("stock_analysis").upsert(df_to_sync[valid_cols].to_dict(orient='records')).execute()
                st.success("✅ 同步成功！行業資訊已寫入。")
            except Exception as e:
                st.error(f"同步錯誤: {e}")
