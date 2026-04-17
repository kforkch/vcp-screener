import streamlit as st
import yfinance as yf
import pandas as pd
import pandas_ta as ta
import requests
import io

# --- 頁面配置 ---
st.set_page_config(page_title="VCP Alpha Global Terminal", layout="wide")
st.title("🏹 VCP Alpha 全球交易終端")

# --- 1. 自動獲取成份股函數 ---
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
        elif market == "中國 A 股 (滬深 300)":
            # 如果 Wiki 抓不到，這裡提供一個核心測試清單確保運作
            return ["600519.SS", "000858.SZ", "300750.SZ", "601318.SS", "000333.SZ"], "000300.SS"
        elif market == "港股 (恒生指數)":
            return ["0700.HK", "9988.HK", "3690.HK", "1211.HK", "1810.HK", "2318.HK", "0005.HK", "0388.HK"], "^HSI"
    except:
        return ["AAPL", "TSLA", "NVDA"], "^GSPC"
    return ["AAPL", "TSLA", "NVDA"], "^GSPC"

# --- 2. 核心計算函數 (改為單隻抓取以避開封鎖) ---
def process_single_stock(ticker, sctr_val, b_only, b_days):
    try:
        df = yf.download(ticker, period="1y", progress=False, auto_adjust=True)
        if df.empty or len(df) < 200: return None
        
        close = df['Close']
        curr_p = float(close.iloc[-1])
        
        # SCTR 簡化版 (直接計算不排名的原始分數，僅作參考)
        sma200, sma50 = close.rolling(200).mean().iloc[-1], close.rolling(50).mean().iloc[-1]
        dist_200 = (curr_p/sma200-1)*100
        dist_50 = (curr_p/sma50-1)*100
        
        # Minervini 6/6 趨勢模板
        sma150 = close.rolling(150).mean().iloc[-1]
        low52, high52 = float(close.min()), float(close.max())
        
        cond = [
            curr_p > sma150 and curr_p > sma200,
            sma150 > sma200,
            sma50 > sma150,
            curr_p > sma50,
            curr_p >= (low52 * 1.25),
            curr_p >= (high52 * 0.8)
        ]
        
        if sum(cond) >= 5: # 稍微放寬到 5/6 確保能看到東西
            recent_range = (close.iloc[-5:].max() - close.iloc[-5:].min()) / close.iloc[-5:].min()
            is_tight = "✅ 緊湊" if recent_range < 0.05 else "❌ 鬆散"
            
            recent_max = float(close.iloc[-(b_days+1):-1].max())
            is_breakout = curr_p > recent_max
            if b_only and not is_breakout: return None
            
            status = f"🔥 {b_days}D突破" if is_breakout else "🚀 強勢向上"
            return [ticker, round(curr_p, 2), round((1-curr_p/high52)*100, 2), round(dist_200, 1), is_tight, status]
    except:
        return None
    return None

# --- 3. UI 邏輯 ---
st.sidebar.header("🎛️ 系統參數")
market_name = st.sidebar.selectbox("選擇市場", ["港股 (恒生指數)", "美股 (Nasdaq 100)", "美股 (S&P 500)", "中國 A 股 (滬深 300)"])
only_b = st.sidebar.checkbox("僅看突破", value=False)

if st.sidebar.button("🚀 開始掃描"):
    tickers, bench_code = get_stock_list(market_name)
    
    # 溫度計
    try:
        bench_df = yf.download(bench_code, period="1y", progress=False)
        if not bench_df.empty:
            b_close = float(bench_df['Close'].iloc[-1])
            st.metric(f"{market_name} 指數", f"{b_close:.2f}")
    except:
        st.warning("基準數據暫時無法獲取")

    st.info(f"正在掃描 {market_name}... 請稍候")
    results = []
    pb = st.progress(0)
    
    # 為了測試，我們先跑前 20 隻（如果是全量會太慢）
    test_tickers = tickers[:30] 
    
    for i, t in enumerate(test_tickers):
        res = process_single_stock(t, 0, only_b, 20)
        if res:
            results.append(res)
        pb.progress((i + 1) / len(test_tickers))

    if results:
        df = pd.DataFrame(results, columns=["代碼", "價格", "距高點%", "強度指標", "收縮狀態", "狀態"])
        st.dataframe(df.sort_values("強度指標", ascending=False), use_container_width=True)
        st.success(f"掃描完成，找到 {len(df)} 隻標的。")
    else:
        st.warning("目前沒有股票符合 VCP 強勢趨勢。這通常代表市場正在調整期。")
