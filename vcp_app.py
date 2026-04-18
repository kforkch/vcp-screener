import streamlit as st
import yfinance as yf
import pandas as pd
import pandas_ta as ta
import numpy as np
import time
import random
from concurrent.futures import ThreadPoolExecutor, as_completed
from supabase import create_client

# --- 頁面配置 ---
st.set_page_config(page_title="VCP Alpha Terminal", layout="wide")
st.title("🏹 VCP Alpha 終極量化掃描終端")

# --- 1. Supabase 初始化 ---
@st.cache_resource
def get_supabase_client():
    try:
        return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])
    except: return None

supabase = get_supabase_client()

# --- 2. 核心邏輯區 ---

@st.cache_data(ttl=86400)
def get_stock_list(market):
    """獲取選定市場的代碼列表"""
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        if market == "美股 (S&P 500)":
            url = 'https://en.wikipedia.org/wiki/List_of_S%26P_500_companies'
            table = pd.read_html(io.StringIO(requests.get(url, headers=headers).text))[0]
            return table['Symbol'].str.replace('.', '-', regex=False).tolist()
        elif market == "美股 (Nasdaq 100)":
            url = 'https://en.wikipedia.org/wiki/Nasdaq-100'
            tables = pd.read_html(io.StringIO(requests.get(url, headers=headers).text))
            for t in tables:
                if 'Ticker' in t.columns: return t['Ticker'].tolist()
        elif market == "港股 (恒生指數)":
            return ["0001.HK", "0005.HK", "0388.HK", "0700.HK", "0939.HK", "0941.HK", "1299.HK", "1810.HK", "2318.HK", "3690.HK", "9988.HK"]
        elif market == "中國 A 股 (滬深 300 龍頭)":
            return ["600519.SS", "601318.SS", "600036.SS", "601012.SS", "600276.SS", "601166.SS", "000858.SZ", "002415.SZ", "002475.SZ", "300750.SZ"]
        return []
    except: return []

@st.cache_data(ttl=86400)
def get_sector_cached(ticker):
    try: return yf.Ticker(ticker).info.get('sector', 'N/A')
    except: return 'N/A'

def calculate_sctr_ranks(tickers):
    """批量計算 SCTR"""
    try:
        raw_data = yf.download(tickers, period="1y", interval="1d", progress=False, auto_adjust=True)
        data = raw_data['Close']
        sctr_data = []
        for ticker in tickers:
            series = data[ticker].dropna() if isinstance(data, pd.DataFrame) else data.dropna()
            if len(series) < 200: continue
            sma200, sma50 = series.rolling(200).mean().iloc[-1], series.rolling(50).mean().iloc[-1]
            raw = ((series.iloc[-1]/sma200-1)*30) + ((series.iloc[-1]/sma50-1)*15)
            sctr_data.append({'ticker': ticker, 'raw': raw})
        df_sctr = pd.DataFrame(sctr_data)
        df_sctr['rank'] = df_sctr['raw'].rank(pct=True) * 99.9
        return df_sctr.set_index('ticker')['rank'].to_dict()
    except: return {}

def check_vcp_advanced(ticker, sctr_map, b_only, b_days):
    """單一標的篩選邏輯"""
    try:
        time.sleep(random.uniform(0.1, 0.3)) # 防止頻率過高被擋
        df = yf.download(ticker, period="1y", progress=False, auto_adjust=True)
        if df.empty or len(df) < 200: return None
        
        close = df['Close'][ticker] if isinstance(df.columns, pd.MultiIndex) else df['Close']
        vol = df['Volume'][ticker] if isinstance(df.columns, pd.MultiIndex) else df['Volume']
        curr_p = float(close.iloc[-1])
        
        sma50, sma150, sma200 = ta.sma(close, 50).iloc[-1], ta.sma(close, 150).iloc[-1], ta.sma(close, 200).iloc[-1]
        high52 = float(close.max())
        
        # Minervini 模板
        cond = [curr_p > sma150 and curr_p > sma200, sma150 > sma200, sma50 > sma150 and sma50 > sma200, curr_p > sma50]
        
        if sum(cond) == 4:
            recent_range = (close.iloc[-5:].max() - close.iloc[-5:].min()) / close.iloc[-5:].min()
            dist_high = round((1 - curr_p/high52) * 100, 2)
            vol_ratio = round(float(vol.iloc[-1]) / vol.rolling(20).mean().iloc[-1], 2)
            
            is_breakout = curr_p > close.iloc[-(b_days+1):-1].max()
            if b_only and not is_breakout: return None
            
            return [ticker, round(curr_p, 2), dist_high, round(sctr_map.get(ticker, 0), 1), "緊湊" if recent_range < 0.05 else "鬆散", vol_ratio, "強勢", get_sector_cached(ticker)]
    except: return None
    return None

# --- 3. 執行介面 ---
st.sidebar.header("🎛️ 系統參數")
market_name = st.sidebar.selectbox("選擇市場", ["美股 (Nasdaq 100)", "美股 (S&P 500)", "港股 (恒生指數)", "中國 A 股 (滬深 300 龍頭)"])
min_sctr = st.sidebar.slider("最低 SCTR", 0.0, 99.9, 70.0)
b_days = st.sidebar.selectbox("突破天數", [10, 20, 50], index=1)
only_b = st.sidebar.checkbox("僅看突破", value=False)

if st.sidebar.button("🚀 開始並行掃描"):
    tickers = get_stock_list(market_name)
    sctr_ranks = calculate_sctr_ranks(tickers)
    results = []
    
    pb = st.progress(0)
    status_text = st.empty()
    
    # 使用多執行緒 (ThreadPoolExecutor) 同時處理 5 檔股票
    with ThreadPoolExecutor(max_workers=5) as executor:
        future_to_ticker = {executor.submit(check_vcp_advanced, t, sctr_ranks, only_b, b_days): t for t in tickers}
        
        for i, future in enumerate(as_completed(future_to_ticker)):
            res = future.result()
            if res and res[3] >= min_sctr:
                results.append(res)
            
            status_text.text(f"正在掃描 ({i+1}/{len(tickers)})")
            pb.progress((i + 1) / len(tickers))
    
    status_text.empty()
    
    if results:
        df = pd.DataFrame(results, columns=["代碼", "價格", "距離高點%", "SCTR排名", "收縮狀態", "量比", "狀態", "行業"])
        
        def make_link(t):
            t_str = str(t)
            if ".HK" in t_str: return f"https://www.tradingview.com/chart/?symbol=HKEX:{t_str.replace('.HK', '').lstrip('0')}"
            elif ".SS" in t_str or ".SZ" in t_str:
                prefix = "SSE" if ".SS" in t_str else "SZSE"
                return f"https://www.tradingview.com/chart/?symbol={prefix}:{t_str.split('.')[0]}"
            return f"https://www.tradingview.com/chart/?symbol={t_str.replace('.', '-')}"
        
        df['圖表'] = df['代碼'].apply(make_link)
        st.session_state['scan_result'] = df
        st.dataframe(df, column_config={"圖表": st.column_config.LinkColumn("查看", display_text="Open")}, use_container_width=True)

# --- 4. 同步邏輯 ---
if 'scan_result' in st.session_state:
    if st.button("💾 同步至雲端看板"):
        if supabase:
            df = st.session_state['scan_result']
            try:
                data_to_upload = df.rename(columns={"代碼": "ticker", "價格": "price", "行業": "sector"}).to_dict(orient='records')
                supabase.table("stock_analysis").upsert(data_to_upload).execute()
                st.success("✅ 同步成功！")
            except Exception as e: st.error(f"同步錯誤: {e}")
