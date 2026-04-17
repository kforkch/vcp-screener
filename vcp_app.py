import streamlit as st
import yfinance as yf
import pandas as pd
import pandas_ta as ta
import requests
import io
import numpy as np

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
                if 'Symbol' in t.columns: return t['Symbol'].tolist(), "^IXIC"
        
        elif market == "中國 A 股 (滬深 300)":
            url = 'https://en.wikipedia.org/wiki/CSI_300_Index'
            tables = pd.read_html(io.StringIO(requests.get(url, headers=headers).text))
            target_table = None
            for t in tables:
                if ('Ticker' in t.columns or 'Symbol' in t.columns) and len(t) > 200:
                    target_table = t
                    break
            
            if target_table is None:
                return ["600519.SS", "000858.SZ", "300750.SZ"], "000300.SS"
            
            tickers = []
            col = 'Ticker' if 'Ticker' in target_table.columns else 'Symbol'
            for _, row in target_table.iterrows():
                raw_val = str(row[col]).split('.')[0].zfill(6)
                exch = str(row['Exchange']) if 'Exchange' in target_table.columns else ""
                suffix = ".SS" if "Shanghai" in exch or raw_val.startswith(('6', '9')) else ".SZ"
                tickers.append(f"{raw_val}{suffix}")
            return tickers, "000300.SS"

        elif market == "港股 (恒生指數)":
            hsi_list = [
                "0001.HK", "0002.HK", "0003.HK", "0005.HK", "0006.HK", "0011.HK", "0012.HK", "0016.HK", 
                "0017.HK", "0027.HK", "0066.HK", "0101.HK", "0175.HK", "0241.HK", "0267.HK", "0288.HK", 
                "0386.HK", "0388.HK", "0669.HK", "0688.HK", "0700.HK", "0762.HK", "0823.HK", "0857.HK", 
                "0883.HK", "0939.HK", "0941.HK", "0960.HK", "0968.HK", "0981.HK", "0992.HK", "1038.HK", 
                "1044.HK", "1088.HK", "1093.HK", "1109.HK", "1113.HK", "1177.HK", "1211.HK", "1299.HK", 
                "1378.HK", "1398.HK", "1810.HK", "1876.HK", "1928.HK", "1929.HK", "2020.HK", "2269.HK", 
                "2313.HK", "2318.HK", "2319.HK", "2331.HK", "2382.HK", "2388.HK", "2628.HK", "2688.HK", 
                "3690.HK", "3968.HK", "3988.HK", "6098.HK", "6618.HK", "6690.HK", "9618.HK", "9633.HK", 
                "9888.HK", "9961.HK", "9988.HK", "9999.HK"
            ]
            return hsi_list, "^HSI"
            
    except Exception as e:
        st.error(f"獲取名單出錯: {e}")
        return [], None

# --- 2. SCTR 排名計算 ---
def calculate_sctr_ranks(tickers):
    try:
        raw_data = yf.download(tickers, period="1y", interval="1d", progress=False, auto_adjust=True)
        data = raw_data['Close'] if 'Close' in raw_data else raw_data
    except:
        return {}

    sctr_data = []
    for ticker in tickers:
        try:
            series = data[ticker].dropna() if isinstance(data, pd.DataFrame) and ticker in data.columns else data.dropna()
            if len(series) < 200: continue
            
            sma200, sma50 = series.rolling(200).mean().iloc[-1], series.rolling(50).mean().iloc[-1]
            dist_200, dist_50 = (series.iloc[-1]/sma200-1)*100, (series.iloc[-1]/sma50-1)*100
            roc125, roc20 = (series.iloc[-1]/series.iloc[-125]-1)*100, (series.iloc[-1]/series.iloc[-20]-1)*100
            rsi = ta.rsi(series, length=14).iloc[-1]
            
            raw_score = (dist_200*0.3 + roc125*0.3) + (dist_50*0.15 + roc20*0.15) + (rsi*0.1)
            sctr_data.append({'ticker': ticker, 'raw': raw_score})
        except: continue
        
    if not sctr_data: return {}
    df_sctr = pd.DataFrame(sctr_data)
    df_sctr['rank'] = df_sctr['raw'].rank(pct=True) * 99.9
    return df_sctr.set_index('ticker')['rank'].to_dict()

# --- 3. 核心過濾函數 ---
def check_vcp_advanced(ticker, sctr_map, b_only, b_days):
    try:
        df = yf.download(ticker, period="1y", progress=False, auto_adjust=True)
        if df.empty or len(df) < 200: return None
        
        close = df['Close']
        vol = df['Volume']
        curr_p = float(close.iloc[-1])
        
        sma50 = ta.sma(close, 50).iloc[-1]
        sma150 = ta.sma(close, 150).iloc[-1]
        sma200 = ta.sma(close, 200).iloc[-1]
        low52, high52 = float(close.min()), float(close.max())
        
        cond = [
            curr_p > sma150 and curr_p > sma200,
            sma150 > sma200,
            sma50 > sma150 and sma50 > sma200,
            curr_p > sma50,
            curr_p >= (low52 * 1.25),
            curr_p >= (high52 * 0.75)
        ]
        
        if sum(cond) == 6:
            recent_range = (close.iloc[-5:].max() - close.iloc[-5:].min()) / close.iloc[-5:].min()
            prev_range = (close.iloc[-25:-5].max() - close.iloc[-25:-5].min()) / close.iloc[-25:-5].min()
            is_tight = "✅ 緊湊" if recent_range < (prev_range * 0.7) else "❌ 鬆散"
            
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
market_name = st.sidebar.selectbox("選擇市場", ["美股 (Nasdaq 100)", "美股 (S&P 500)", "中國 A 股 (滬深 300)", "港股 (恒生指數)"])
min_sctr_val = st.sidebar.slider("最低 SCTR 排名", 0.0, 99.9, 80.0)
b_days = st.sidebar.selectbox("突破檢測天數", [10, 20, 50], index=1)
only_b = st.sidebar.checkbox("僅看突破", value=False)

if st.sidebar.button("🚀 執行全球同步掃描"):
    tickers, bench_code = get_stock_list(market_name)
    
    # --- 大盤溫度計 (修正後縮進) ---
    try:
        bench_df = yf.download(bench_code, period="1y", progress=False, auto_adjust=True)
        if bench_df.empty:
            st.error(f"⚠️ 無法獲取基準指數 ({bench_code}) 的數據。")
            b_close = 0.0
        else:
            b_series = bench_df['Close'][bench_code].dropna() if isinstance(bench_df.columns, pd.MultiIndex) else bench_df['Close'].dropna()
            
            if len(b_series) > 0:
                b_close = float(b_series.iloc[-1])
                b_sma50 = float(b_series.rolling(50).mean().iloc[-1])
                health = "🟢 牛市環境" if b_close > b_sma50 else "🔴 熊市/調整"
                
                c1, c2, c3 = st.columns(3)
                c1.metric(f"{market_name} 狀態", health)
                c2.metric("基準指數位置", f"{b_close:.2f}")
                c3.metric("偏離 50MA", f"{((b_close/b_sma50-1)*100):.2f}%")
            else:
                b_close = 0.0
                st.warning("基準指數數據長度不足。")
    except Exception as e:
        st.error(f"🌡️ 大盤溫度計運行出錯: {e}")
        b_close = 0.0

    if b_close > 0:
        st.write("---")
        st.info(f"📊 正在計算 {market_name} 的 SCTR 排名...")
        sctr_ranks = calculate_sctr_ranks(tickers)
        
        st.info("🔍 正在檢測個股 VCP 形態...")
        results = []
        pb = st.progress(0)
        for i, t in enumerate(tickers):
            res = check_vcp_advanced(t, sctr_ranks, only_b, b_days)
            if res and res[3] >= min_sctr_val: results.append(res)
            pb.progress((i + 1) / len(tickers))

        if results:
            df = pd.DataFrame(results, columns=["代碼", "價格", "距離高點%", "SCTR排名", "收縮狀態", "量比", "狀態"])
            def make_link(t):
                t_str = str(t)
                if ".HK" in t_str: return f"https://www.tradingview.com/chart/?symbol=HKEX:{t_str.replace('.HK','').lstrip('0')}"
                elif ".SS" in t_str or ".SZ" in t_str: return f"https://www.tradingview.com/chart/?symbol={'SSE' if '.SS' in t_str else 'SZSE'}:{t_str.split('.')[0]}"
                else: return f"https://www.tradingview.com/chart/?symbol={t_str.replace('.', '-')}"
            
            df['圖表'] = df['代碼'].apply(make_link)
            df = df.sort_values("SCTR排名", ascending=False)
            st.dataframe(df, column_config={"圖表": st.column_config.LinkColumn("查看", display_text="Open")}, use_container_width=True)
            st.success(f"找到 {len(df)} 隻標的。")
        else:
            st.warning("當前市場環境下無符合標的。")
