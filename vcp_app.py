import streamlit as st
import yfinance as yf
import pandas as pd
import pandas_ta as ta
import requests
import io
import numpy as np

# --- 頁面配置 ---
st.set_page_config(page_title="VCP SCTR Pro", layout="wide")
st.title("🏹 VCP + SCTR 終極全功能篩選系統")

# --- 1. 自動獲取成份股 ---
@st.cache_data(ttl=86400)
def get_stock_list(market):
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
                if 'Symbol' in t.columns: return t['Symbol'].tolist()
        elif market == "港股 (恒生指數)":
            return ["0700.HK", "9988.HK", "3690.HK", "1211.HK", "1810.HK", "2318.HK", "0005.HK", "0388.HK", "9618.HK", "2269.HK"]
    except: return []

# --- 2. SCTR 排名計算 ---
def calculate_sctr_ranks(tickers):
    # 為了效能，這裡批量下載一次 Close
    data = yf.download(tickers, period="1y", interval="1d", progress=False, auto_adjust=True)['Close']
    sctr_data = []
    for ticker in tickers:
        try:
            series = data[ticker].dropna()
            if len(series) < 200: continue
            # 長線 (60%)
            sma200 = series.rolling(200).mean().iloc[-1]
            dist_200 = (series.iloc[-1] / sma200 - 1) * 100
            roc125 = (series.iloc[-1] / series.iloc[-125] - 1) * 100
            # 中線 (30%)
            sma50 = series.rolling(50).mean().iloc[-1]
            dist_50 = (series.iloc[-1] / sma50 - 1) * 100
            roc20 = (series.iloc[-1] / series.iloc[-20] - 1) * 100
            # 短線 (10%)
            rsi = ta.rsi(series, length=14).iloc[-1]
            # 總分
            raw = (dist_200*0.3 + roc125*0.3) + (dist_50*0.15 + roc20*0.15) + (rsi*0.1)
            sctr_data.append({'ticker': ticker, 'raw': raw})
        except: continue
    if not sctr_data: return {}
    df_sctr = pd.DataFrame(sctr_data)
    df_sctr['rank'] = df_sctr['raw'].rank(pct=True) * 99.9
    return df_sctr.set_index('ticker')['rank'].to_dict()

# --- 3. 核心篩選 ---
def check_vcp_final(ticker, sctr_map, breakout_only, breakout_days):
    try:
        df = yf.download(ticker, period="1y", progress=False, auto_adjust=True)
        if df.empty or len(df) < 200: return None
        
        close = df['Close'][ticker] if isinstance(df.columns, pd.MultiIndex) else df['Close']
        vol = df['Volume'][ticker] if isinstance(df.columns, pd.MultiIndex) else df['Volume']
        curr_price = float(close.iloc[-1])
        
        # 你的 6/6 條件
        sma50, sma150, sma200 = ta.sma(close, 50).iloc[-1], ta.sma(close, 150).iloc[-1], ta.sma(close, 200).iloc[-1]
        low52, high52 = float(close.min()), float(close.max())
        
        cond = [curr_price > sma150 and curr_price > sma200, sma150 > sma200, sma50 > sma150 and sma50 > sma200,
                curr_price > sma50, curr_price >= (low52 * 1.25), curr_price >= (high52 * 0.75)]
        
        if sum(cond) == 6:
            # 突破與距離高點
            recent_max = float(close.iloc[-(breakout_days+1):-1].max())
            is_breakout = curr_price > recent_max
            if breakout_only and not is_breakout: return None
            
            dist_high = round((1 - curr_price/high52) * 100, 2)
            vol_ratio = round(float(vol.iloc[-1]) / vol.rolling(20).mean().iloc[-1], 2)
            sctr_val = round(sctr_map.get(ticker, 0), 1)
            
            status = f"🔥 {breakout_days}D突破" if is_breakout else "🚀 強勢領頭"
            return [ticker, round(curr_price, 2), dist_high, sctr_val, vol_ratio, status]
        return None
    except: return None

# --- 4. 側邊欄與顯示 ---
st.sidebar.header("參數設定")
market = st.sidebar.selectbox("選擇市場", ["美股 (S&P 500)", "美股 (Nasdaq 100)", "港股 (恒生指數)"])
b_only = st.sidebar.checkbox("只看突破", value=False)
b_days = st.sidebar.selectbox("突破天數", [10, 20, 50], index=1)
min_sctr = st.sidebar.slider("最低 SCTR 排名", 0.0, 99.9, 70.0)

if st.sidebar.button("🚀 開始全能掃描"):
    tickers = get_stock_list(market)
    st.info(f"正在計算全市場 SCTR 排名...")
    sctr_ranking = calculate_sctr_ranks(tickers)
    
    st.info(f"正在分析 VCP 形態...")
    results = []
    pb = st.progress(0)
    for i, t in enumerate(tickers):
        res = check_vcp_final(t, sctr_ranking, b_only, b_days)
        if res and res[3] >= min_sctr: results.append(res)
        pb.progress((i + 1) / len(tickers))
    
    if results:
        df = pd.DataFrame(results, columns=["代碼", "現價", "距離高點%", "SCTR排名", "量比", "狀態"])
        
        # 補回 TradingView 連結
        def make_link(t):
            t_str = str(t)
            code = t_str.replace('.HK', '').lstrip('0') if ".HK" in t_str else t_str.replace('.', '-')
            prefix = "HKEX:" if ".HK" in t_str else ""
            return f"https://www.tradingview.com/chart/?symbol={prefix}{code}"
        
        df['圖表'] = df['代碼'].apply(make_link)
        df = df.sort_values("SCTR排名", ascending=False)
        
        st.dataframe(df, column_config={"圖表": st.column_config.LinkColumn("查看", display_text="Open")}, use_container_width=True)
        st.success(f"找到 {len(df)} 隻標的")
    else: st.warning("未找到符合標的")
