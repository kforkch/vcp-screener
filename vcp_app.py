import streamlit as st
import yfinance as yf
import pandas as pd
import pandas_ta as ta
import requests
import io

# --- 頁面配置 ---
st.set_page_config(page_title="VCP Pro Screener", layout="wide")
st.title("🏹 VCP 專業量化篩選系統 (成交量 + RS 強度)")

# --- 1. 自動獲取成份股 (新增大盤基準用於 RS 計算) ---
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

# --- 2. 核心篩選邏輯 (加入 Volume 與 RS) ---
def check_vcp_pro(ticker, benchmark_df, breakout_only=False, breakout_days=20):
    try:
        formatted_ticker = ticker if ".HK" in ticker else ticker.replace('.', '-')
        df = yf.download(formatted_ticker, period="1y", progress=False, auto_adjust=True)
        
        if df.empty or len(df) < 150: return None
        
        # 處理資料
        close_prices = df['Close'][formatted_ticker] if isinstance(df.columns, pd.MultiIndex) else df['Close']
        volumes = df['Volume'][formatted_ticker] if isinstance(df.columns, pd.MultiIndex) else df['Volume']
        curr_price = float(close_prices.iloc[-1])

        # A. 趨勢條件 (Minervini 6/6)
        sma50 = ta.sma(close_prices, 50).iloc[-1]
        sma150 = ta.sma(close_prices, 150).iloc[-1]
        sma200 = ta.sma(close_prices, 200).iloc[-1]
        low52, high52 = float(close_prices.min()), float(close_prices.max())
        
        conditions = [
            curr_price > sma150 and curr_price > sma200,
            sma150 > sma200,
            sma50 > sma150 and sma50 > sma200,
            curr_price > sma50,
            curr_price >= (low52 * 1.25),
            curr_price >= (high52 * 0.75)
        ]
        score = sum(conditions)

        # B. 突破檢測
        lookback = breakout_days + 1
        recent_max = float(close_prices.iloc[-lookback:-1].max())
        is_breakout = curr_price > recent_max

        if score == 6:
            if breakout_only and not is_breakout: return None
            
            # C. 加入「成交量倍數」 (Relative Volume)
            avg_vol = volumes.rolling(20).mean().iloc[-1]
            vol_ratio = round(float(volumes.iloc[-1]) / avg_vol, 2)

            # D. 加入「相對強度 (RS)」(對標大盤)
            # 計算該股 3 個月回報 vs 大盤 3 個月回報
            stock_ret = (curr_price / close_prices.iloc[-63]) - 1
            bench_ret = (benchmark_df.iloc[-1] / benchmark_df.iloc[-63]) - 1
            rs_score = round((stock_ret - bench_ret) * 100, 2) # 正數代表贏大盤

            status = f"🔥 {breakout_days}D突破" if is_breakout else "🚀 趨勢向上"
            dist_high = round((1 - curr_price/high52) * 100, 2)
            
            return [ticker, round(curr_price, 2), dist_high, f"{score}/6", vol_ratio, rs_score, status]
        return None
    except: return None

# --- 3. 側邊欄與執行 ---
st.sidebar.header("專業篩選參數")
market_choice = st.sidebar.selectbox("市場", ["美股 (S&P 500)", "美股 (Nasdaq 100)", "港股 (恒生指數)"])
breakout_only = st.sidebar.checkbox("🎯 僅顯示突破", value=False)
breakout_days = st.sidebar.selectbox("突破天數", [10, 20, 50], index=1)
min_vol_ratio = st.sidebar.slider("最低成交量倍數", 0.5, 3.0, 1.0, 0.1)

if st.sidebar.button("🚀 開始專業掃描"):
    tickers, bench_ticker = get_stock_list(market_choice)
    benchmark_data = yf.download(bench_ticker, period="1y", progress=False)['Close']
    
    results = []
    progress_bar = st.progress(0)
    status_text = st.empty()

    for i, t in enumerate(tickers):
        status_text.text(f"分析中: {t}")
        res = check_vcp_pro(t, benchmark_data, breakout_only, breakout_days)
        # 額外過濾成交量
        if res and res[4] >= min_vol_ratio:
            results.append(res)
        progress_bar.progress((i + 1) / len(tickers))

    if results:
        df_final = pd.DataFrame(results, columns=["代碼", "現價", "距離高點%", "評分", "量比(20日)", "相對強度(RS)", "狀態"])
        
        # 專業排序：RS 越高越好，量比越高越好
        df_final = df_final.sort_values(by=["相對強度(RS)", "量比(20日)"], ascending=[False, False])
        
        # TradingView 連結
        def get_tv_url(ticker):
            code = ticker.replace('.HK', '').lstrip('0') if ".HK" in ticker else ticker.replace('.', '-')
            prefix = "HKEX:" if ".HK" in ticker else ""
            return f"https://www.tradingview.com/chart/?symbol={prefix}{code}"
        
        df_final['圖表'] = df_final['代碼'].apply(get_tv_url)

        st.dataframe(
            df_final,
            column_config={"圖表": st.column_config.LinkColumn("查看", display_text="Open")},
            use_container_width=True
        )
        st.success(f"找到 {len(results)} 隻標的。")
    else:
        st.warning("查無符合條件標的。")
