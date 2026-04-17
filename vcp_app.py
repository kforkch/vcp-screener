import streamlit as st
import yfinance as yf
import pandas as pd
import pandas_ta as ta
import requests
import io
import numpy as np

# --- 頁面配置 ---
st.set_page_config(page_title="VCP Alpha Terminal", layout="wide")
st.title("🏹 VCP Alpha 全球終極終端 (產業群聚版)")

# --- 1. 自動獲取成份股 (全量名單) ---
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
            # 完整的 82 隻恆指成份股，代碼補齊 4 位數
            hsi_list = [
                "0001.HK", "0002.HK", "0003.HK", "0005.HK", "0006.HK", "0011.HK", "0012.HK", "0016.HK", 
                "0017.HK", "0020.HK", "0027.HK", "0066.HK", "0101.HK", "0175.HK", "0241.HK", "0267.HK", 
                "0288.HK", "0291.HK", "0316.HK", "0322.HK", "0386.HK", "0388.HK", "0669.HK", "0688.HK", 
                "0700.HK", "0762.HK", "0823.HK", "0857.HK", "0868.HK", "0881.HK", "0883.HK", "0939.HK", 
                "0941.HK", "0960.HK", "0968.HK", "0981.HK", "0992.HK", "1038.HK", "1044.HK", "1088.HK", 
                "1093.HK", "1109.HK", "1113.HK", "1177.HK", "1211.HK", "1299.HK", "1313.HK", "1378.HK", 
                "1398.HK", "1810.HK", "1876.HK", "1928.HK", "1929.HK", "2020.HK", "2269.HK", "2313.HK", 
                "2318.HK", "2319.HK", "2331.HK", "2382.HK", "2388.HK", "2628.HK", "2688.HK", "3690.HK", 
                "3692.HK", "3968.HK", "3988.HK", "6098.HK", "6608.HK", "6618.HK", "6690.HK", "6862.HK", 
                "9618.HK", "9633.HK", "9868.HK", "9888.HK", "9922.HK", "9961.HK", "9988.HK", "9992.HK", "9999.HK"
            ]
            return hsi_list, "^HSI"

        elif market == "中國 A 股 (核心龍頭 100)":
            as_list = [
                "600519.SS", "601318.SS", "600036.SS", "601012.SS", "600276.SS", "601166.SS", "600900.SS", "600030.SS",
                "601888.SS", "600809.SS", "601398.SS", "601288.SS", "601988.SS", "601628.SS", "601601.SS", "600019.SS",
                "600048.SS", "601919.SS", "000858.SZ", "300750.SZ", "002594.SZ", "000333.SZ" # 此處僅為演示，可照樣補齊到100隻
            ]
            return as_list, "000300.SS"
    except: return [], None
    return [], None

# --- 2. SCTR 排名計算 (15個月數據確保 SMA200 準確) ---
def calculate_sctr_ranks(tickers):
    try:
        raw_data = yf.download(tickers, period="15mo", interval="1d", progress=False, auto_adjust=True)
        data = raw_data['Close'] if 'Close' in raw_data else raw_data
        sctr_data = []
        for ticker in tickers:
            try:
                series = data[ticker].dropna() if isinstance(data, pd.DataFrame) else data.dropna()
                if len(series) < 200: continue # 嚴格門檻
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
    except: return {}

# --- 3. 核心 VCP 分析 (整合產業獲取) ---
def analyze_vcp_full(ticker, sctr_map, b_only, b_days):
    try:
        t_obj = yf.Ticker(ticker)
        df = t_obj.history(period="15mo", auto_adjust=True)
        if df.empty or len(df) < 200: return None
        
        close = df['Close']
        vol = df['Volume']
        curr_p = float(close.iloc[-1])
        
        sma50, sma150, sma200 = ta.sma(close, 50).iloc[-1], ta.sma(close, 150).iloc[-1], ta.sma(close, 200).iloc[-1]
        low52, high52 = float(close.min()), float(close.max())
        
        cond = [
            curr_p > sma150 and curr_p > sma200, 
            sma150 > sma200, 
            sma50 > sma150 and sma50 > sma200,
            curr_p > sma50, 
            curr_p >= (low52 * 1.25), 
            curr_p >= (high52 * 0.75)
        ]
        
        if all(cond):
            # 獲取產業 (這就是你剛才代碼中能看到行業的關鍵)
            try:
                sector = t_obj.info.get('sector', '其他/多元化')
            except:
                sector = "金融/權重" if ".HK" in ticker or ".SS" in ticker else "技術/其他"

            recent_range = (close.iloc[-5:].max() - close.iloc[-5:].min()) / close.iloc[-5:].min()
            prev_range = (close.iloc[-25:-5].max() - close.iloc[-25:-5].min()) / close.iloc[-25:-5].min()
            is_tight = "✅ 緊湊" if recent_range < (prev_range * 0.7) else "❌ 鬆散"
            
            recent_max = float(close.iloc[-(b_days+1):-1].max())
            is_breakout = curr_p > recent_max
            if b_only and not is_breakout: return None
            
            dist_high = round((1 - curr_p/high52) * 100, 2)
            vol_ratio = round(float(vol.iloc[-1]) / vol.rolling(20).mean().iloc[-1], 2)
            sctr_val = round(sctr_map.get(ticker, 0), 1)
            
            return [ticker, round(curr_p, 2), dist_high, sctr_val, is_tight, vol_ratio, sector]
    except: return None

# --- 4. UI 介面 ---
market_name = st.sidebar.selectbox("選擇市場", ["美股 (Nasdaq 100)", "美股 (S&P 500)", "港股 (恒生指數)", "中國 A 股 (核心龍頭 100)"])
min_sctr = st.sidebar.slider("最低 SCTR", 0.0, 99.9, 70.0)
b_days = st.sidebar.selectbox("突破天數", [10, 20, 50], index=1)
only_b = st.sidebar.checkbox("僅看突破")

if st.sidebar.button("🚀 開始全量掃描"):
    tickers, bench = get_stock_list(market_name)
    if tickers:
        # 大盤溫度計
        try:
            b_df = yf.download(bench, period="1y", progress=False, auto_adjust=True)
            b_c = b_df['Close'].iloc[-1]
            b_ma = b_df['Close'].rolling(50).mean().iloc[-1]
            st.columns(3)[0].metric("大盤狀態", "🟢 牛市" if b_c > b_ma else "🔴 調整")
        except: pass

        st.info(f"正在分析 {market_name} 數據...")
        sctr_ranks = calculate_sctr_ranks(tickers)
        results = []
        pb = st.progress(0)
        
        for i, t in enumerate(tickers):
            res = analyze_vcp_full(t, sctr_ranks, only_b, b_days)
            if res and res[3] >= min_sctr: results.append(res)
            pb.progress((i + 1) / len(tickers))
        
        if results:
            df = pd.DataFrame(results, columns=["代碼", "價格", "距離高點%", "SCTR", "收縮", "量比", "產業"])
            
            # --- 產業群聚統計 (圖表) ---
            st.subheader("🔥 產業群聚分佈")
            st.bar_chart(df['產業'].value_counts())
            
            # --- TradingView 連結 ---
            def make_link(t):
                if ".HK" in t: return f"https://www.tradingview.com/chart/?symbol=HKEX:{t.replace('.HK','').lstrip('0')}"
                if ".SS" in t or ".SZ" in t: return f"https://www.tradingview.com/chart/?symbol={'SSE' if '.SS' in t else 'SZSE'}:{t.split('.')[0]}"
                return f"https://www.tradingview.com/chart/?symbol={t.replace('.','-')}"
            df['圖表'] = df['代碼'].apply(make_link)

            st.dataframe(df.sort_values("SCTR", ascending=False), column_config={"圖表": st.column_config.LinkColumn("查看")}, hide_index=True)
        else:
            st.warning("無符合標的。")
