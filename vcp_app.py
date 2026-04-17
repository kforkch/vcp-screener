import streamlit as st
import yfinance as yf
import pandas as pd
import pandas_ta as ta
import requests
import io
import numpy as np

# --- 頁面配置 ---
st.set_page_config(page_title="VCP Alpha Terminal", layout="wide")
st.title("🏹 VCP Alpha 終極交易終端")

# --- 1. 自動獲取成份股 ---
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
                if 'Symbol' in t.columns: return t['Symbol'].tolist(), "^IXIC"
        elif market == "港股 (恒生指數)":
            return ["0700.HK", "9988.HK", "3690.HK", "1211.HK", "1810.HK", "2318.HK", "0005.HK", "0388.HK", "9618.HK", "2269.HK"], "^HSI"
    except: return [], None

# --- 2. SCTR 排名計算 ---
def calculate_sctr_ranks(tickers):
    data = yf.download(tickers, period="1y", interval="1d", progress=False, auto_adjust=True)['Close']
    sctr_data = []
    for ticker in tickers:
        try:
            series = data[ticker].dropna()
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

# --- 3. 核心篩選（補齊所有欄位） ---
def check_vcp_advanced(ticker, sctr_map, b_only, b_days):
    try:
        df = yf.download(ticker, period="1y", progress=False, auto_adjust=True)
        if df.empty or len(df) < 200: return None
        close = df['Close'][ticker] if isinstance(df.columns, pd.MultiIndex) else df['Close']
        vol = df['Volume'][ticker] if isinstance(df.columns, pd.MultiIndex) else df['Volume']
        curr_p = float(close.iloc[-1])
        
        # 你的 6/6 條件
        sma50, sma150, sma200 = ta.sma(close, 50).iloc[-1], ta.sma(close, 150).iloc[-1], ta.sma(close, 200).iloc[-1]
        low52, high52 = float(close.min()), float(close.max())
        cond = [curr_p > sma150 and curr_p > sma200, sma150 > sma200, sma50 > sma150 and sma50 > sma200,
                curr_p > sma50, curr_p >= (low52 * 1.25), curr_p >= (high52 * 0.75)]
        
        if sum(cond) == 6:
            # 波動收縮檢測 (Tightness)
            recent_range = (close.iloc[-5:].max() - close.iloc[-5:].min()) / close.iloc[-5:].min()
            prev_range = (close.iloc[-25:-5].max() - close.iloc[-25:-5].min()) / close.iloc[-25:-5].min()
            is_tight = "✅ 緊湊" if recent_range < (prev_range * 0.7) else "❌ 鬆散"
            
            # 突破與距離高點 (補回)
            recent_max = float(close.iloc[-(b_days+1):-1].max())
            is_breakout = curr_p > recent_max
            if b_only and not is_breakout: return None
            
            dist_high = round((1 - curr_p/high52) * 100, 2)
            vol_ratio = round(float(vol.iloc[-1]) / vol.rolling(20).mean().iloc[-1], 2)
            sctr_val = round(sctr_map.get(ticker, 0), 1)
            
            status = f"🔥 {b_days}D突破" if is_breakout else "🚀 強勢向上"
            
            return [ticker, round(curr_p, 2), dist_high, sctr_val, is_tight, vol_ratio, status]
        return None
    except: return None

# --- 4. 側邊欄與執行 ---
st.sidebar.header("🎛️ 系統參數")
market_name = st.sidebar.selectbox("選擇市場", ["美股 (S&P 500)", "美股 (Nasdaq 100)", "港股 (恒生指數)"])
min_sctr_val = st.sidebar.slider("最低 SCTR 排名", 0.0, 99.9, 70.0)
b_days = st.sidebar.selectbox("突破檢測天數", [10, 20, 50], index=1)
only_b = st.sidebar.checkbox("僅看突破", value=False)

if st.sidebar.button("🚀 執行全方位掃描"):
    tickers, bench_code = get_stock_list(market_name)
    
    # 大盤溫度計
    bench_df = yf.download(bench_code, period="1y", progress=False, auto_adjust=True)
    b_close = bench_df['Close'].iloc[-1]
    b_sma50 = bench_df['Close'].rolling(50).mean().iloc[-1]
    health = "🟢 牛市環境" if b_close > b_sma50 else "🔴 熊市/調整"
    
    c1, c2, c3 = st.columns(3)
    c1.metric("大盤狀態", health)
    c2.metric("大盤收盤", f"{b_close:.2f}")
    c3.metric("50MA 距離", f"{((b_close/b_sma50-1)*100):.2f}%")

    st.write("---")
    st.info("📊 第一階段：SCTR 動能排名...")
    sctr_ranks = calculate_sctr_ranks(tickers)
    
    st.info("🔍 第二階段：VCP 形態與收縮檢測...")
    results = []
    pb = st.progress(0)
    for i, t in enumerate(tickers):
        res = check_vcp_advanced(t, sctr_ranks, only_b, b_days)
        if res and res[3] >= min_sctr_val: results.append(res)
        pb.progress((i + 1) / len(tickers))

    if results:
        df = pd.DataFrame(results, columns=["代碼", "價格", "距離高點%", "SCTR排名", "收縮狀態", "量比", "狀態"])
        
        # 補回 TradingView 連結
        def make_link(t):
            t_str = str(t)
            code = t_str.replace('.HK', '').lstrip('0') if ".HK" in t_str else t_str.replace('.', '-')
            px = "HKEX:" if ".HK" in t_str else ""
            return f"https://www.tradingview.com/chart/?symbol={px}{code}"
        
        df['圖表'] = df['代碼'].apply(make_link)
        df = df.sort_values("SCTR排名", ascending=False)
        
        st.dataframe(df, column_config={"圖表": st.column_config.LinkColumn("查看", display_text="Open")}, use_container_width=True)
        st.success(f"找到 {len(df)} 隻標的。")
    else:
        st.warning("無符合條件標的。")
