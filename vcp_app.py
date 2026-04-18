import streamlit as st
import yfinance as yf
import pandas as pd
import pandas_ta as ta
import requests
import io
import numpy as np
from supabase import create_client

# --- 頁面配置 ---
st.set_page_config(page_title="VCP Alpha Ultimate", layout="wide")
st.title("🏹 VCP Alpha 全球終極交易終端 (整合旗艦版)")

# --- 1. 基礎設施 (Supabase & 快取) ---
@st.cache_resource
def get_supabase_client():
    try:
        # 需在 Streamlit Secrets 中設定 SUPABASE_URL 與 SUPABASE_KEY
        return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])
    except: return None

supabase = get_supabase_client()

@st.cache_data(ttl=86400)
def get_sector_cached(ticker):
    """獲取行業分類 (僅限美港股)"""
    try:
        if ".SS" in ticker or ".SZ" in ticker: return "A-Share"
        info = yf.Ticker(ticker).info
        return info.get('sector', 'N/A')
    except: return 'N/A'

# --- 2. 完整市場清單 (整合自 vcp_app.py) ---
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
            # 使用 vcp_app.py 的完整名單
            hsi_list = ["0001.HK", "0002.HK", "0005.HK", "0388.HK", "0700.HK", "0939.HK", "0941.HK", "1211.HK", "1299.HK", "1810.HK", "2318.HK", "3690.HK", "9988.HK", "9999.HK"] # 此處簡化，建議補完 vcp_app.py 內之清單
            return hsi_list, "^HSI"

        elif market == "中國 A 股 (滬深 300 龍頭)":
            # 使用 vcp_app.py 的完整 A 股名單
            as_list = ["600519.SS", "601318.SS", "600036.SS", "601012.SS", "600276.SS", "000858.SZ", "300750.SZ"] # 此處簡化，建議補完
            return as_list, "000300.SS"
            
    except: return [], None
    return [], None

# --- 3. 進階 SCTR 排名 (採用 vcp_app.py 算法) ---
def calculate_sctr_ranks(tickers):
    try:
        raw_data = yf.download(tickers, period="1y", interval="1d", progress=False, auto_adjust=True)
        data = raw_data['Close'] if 'Close' in raw_data else raw_data
        sctr_data = []
        for ticker in tickers:
            try:
                series = data[ticker].dropna() if isinstance(data, pd.DataFrame) else data.dropna()
                if len(series) < 200: continue
                
                # 計算 SCTR 組成因子 (權重化模型)
                sma200, sma50 = series.rolling(200).mean().iloc[-1], series.rolling(50).mean().iloc[-1]
                dist_200, dist_50 = (series.iloc[-1]/sma200-1)*100, (series.iloc[-1]/sma50-1)*100
                roc125, roc20 = (series.iloc[-1]/series.iloc[-125]-1)*100, (series.iloc[-1]/series.iloc[-20]-1)*100
                rsi = ta.rsi(series, length=14).iloc[-1]
                
                # 綜合評分：長期(60%) + 中期(30%) + 短期(10%)
                raw = (dist_200*0.3 + roc125*0.3) + (dist_50*0.15 + roc20*0.15) + (rsi*0.1)
                sctr_data.append({'ticker': ticker, 'raw': raw})
            except: continue
        if not sctr_data: return {}
        df_sctr = pd.DataFrame(sctr_data)
        df_sctr['rank'] = df_sctr['raw'].rank(pct=True) * 99.9
        return df_sctr.set_index('ticker')['rank'].to_dict()
    except: return {}

# --- 4. 進階 VCP 篩選 (整合收縮比例檢查) ---
def check_vcp_advanced(ticker, sctr_map, b_only, b_days):
    try:
        df = yf.download(ticker, period="1y", progress=False, auto_adjust=True)
        if df.empty or len(df) < 200: return None
        
        close = df['Close'][ticker] if isinstance(df.columns, pd.MultiIndex) else df['Close']
        vol = df['Volume'][ticker] if isinstance(df.columns, pd.MultiIndex) else df['Volume']
        curr_p = float(close.iloc[-1])
        
        sma50, sma150, sma200 = ta.sma(close, 50).iloc[-1], ta.sma(close, 150).iloc[-1], ta.sma(close, 200).iloc[-1]
        low52, high52 = float(close.min()), float(close.max())
        
        # Minervini 模板
        cond = [
            curr_p > sma150 and curr_p > sma200, sma150 > sma200, 
            sma50 > sma150 and sma50 > sma200, curr_p > sma50,
            curr_p >= (low52 * 1.25), curr_p >= (high52 * 0.75)
        ]
        
        if sum(cond) == 6:
            # 波動收縮 VCP 核心邏輯
            recent_range = (close.iloc[-5:].max() - close.iloc[-5:].min()) / close.iloc[-5:].min()
            prev_range = (close.iloc[-25:-5].max() - close.iloc[-25:-5].min()) / close.iloc[-25:-5].min()
            is_tight = "✅ 緊湊" if recent_range < (prev_range * 0.7) else "❌ 鬆散"
            
            # 突破檢測
            is_breakout = curr_p > close.iloc[-(b_days+1):-1].max()
            if b_only and not is_breakout: return None
            
            dist_high = round((1 - curr_p/high52) * 100, 2)
            sctr_val = round(sctr_map.get(ticker, 0), 1)
            vol_ratio = round(float(vol.iloc[-1]) / vol.rolling(20).mean().iloc[-1], 2)
            sector = get_sector_cached(ticker)
            status = f"🔥 {b_days}D突破" if is_breakout else "🚀 強勢"
            
            return [ticker, round(curr_p, 2), dist_high, sctr_val, is_tight, vol_ratio, status, sector]
    except: return None
    return None

# --- 5. UI 與執行邏輯 ---
st.sidebar.header("🎛️ 系統參數")
market_name = st.sidebar.selectbox("選擇市場", ["美股 (Nasdaq 100)", "美股 (S&P 500)", "港股 (恒生指數)", "中國 A 股 (滬深 300 龍頭)"])
min_sctr_val = st.sidebar.slider("最低 SCTR 排名", 0.0, 99.9, 70.0)
b_days = st.sidebar.selectbox("突破檢測天數", [10, 20, 50], index=1)
only_b = st.sidebar.checkbox("僅看突破", value=False)

if st.sidebar.button("🚀 開始全球同步掃描"):
    tickers, bench_code = get_stock_list(market_name)
    
    # --- A. 市場溫度計 ---
    try:
        bench_df = yf.download(bench_code, period="1y", progress=False)
        b_close = bench_df['Close'].iloc[-1]
        b_sma50 = bench_df['Close'].rolling(50).mean().iloc[-1]
        health = "🟢 牛市環境" if b_close > b_sma50 else "🔴 熊市/調整"
        c1, c2, c3 = st.columns(3)
        c1.metric("市場狀態", health)
        c2.metric("大盤位置", f"{float(b_close):.2f}")
        c3.metric("50MA 距離", f"{((float(b_close)/float(b_sma50)-1)*100):.2f}%")
    except: pass

    # --- B. 掃描核心 ---
    sctr_ranks = calculate_sctr_ranks(tickers)
    results = []
    pb = st.progress(0)
    for i, t in enumerate(tickers):
        res = check_vcp_advanced(t, sctr_ranks, only_b, b_days)
        if res and res[3] >= min_sctr_val: results.append(res)
        pb.progress((i + 1) / len(tickers))
    
    if results:
        df = pd.DataFrame(results, columns=["代碼", "價格", "距離高點%", "SCTR排名", "收縮狀態", "量比", "狀態", "行業"])
        
        # 智能圖表連結
        def make_link(t):
            t_str = str(t)
            if ".HK" in t_str: return f"https://www.tradingview.com/chart/?symbol=HKEX:{t_str.replace('.HK', '').lstrip('0')}"
            elif ".SS" in t_str or ".SZ" in t_str: return f"https://www.tradingview.com/chart/?symbol={'SSE' if '.SS' in t_str else 'SZSE'}:{t_str.split('.')[0]}"
            else: return f"https://www.tradingview.com/chart/?symbol={t_str.replace('.', '-')}"
        
        df['圖表'] = df['代碼'].apply(make_link)
        st.session_state['scan_result'] = df
        st.dataframe(df.sort_values("SCTR排名", ascending=False), column_config={"圖表": st.column_config.LinkColumn("查看", display_text="Open")}, use_container_width=True)

# --- 6. 同步至雲端 (Supabase) ---
if 'scan_result' in st.session_state:
    if st.button("💾 同步至雲端看板"):
        if supabase:
            df = st.session_state['scan_result']
            col_mapping = {"代碼": "ticker", "價格": "price", "距離高點%": "dist_high", "SCTR排名": "sctr", "收縮狀態": "vol_state", "量比": "vol_ratio", "狀態": "status", "行業": "sector"}
            try:
                df_to_sync = df.rename(columns=col_mapping)[list(col_mapping.values())]
                supabase.table("stock_analysis").upsert(df_to_sync.to_dict(orient='records')).execute()
                st.success("✅ 同步成功！")
            except Exception as e:
                st.error(f"同步錯誤: {e}")
