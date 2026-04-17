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
            # 港股核心成份股
            return ["0700.HK", "9988.HK", "3690.HK", "1211.HK", "1810.HK", "2318.HK", "0005.HK", "0388.HK", "9618.HK", "2269.HK", "0941.HK", "0939.HK", "1299.HK"], "^HSI"
    except: 
        return [], None
    return [], None

# --- 2. SCTR 排名計算 (加入防錯機制) ---
def calculate_sctr_ranks(tickers):
    try:
        raw_data = yf.download(tickers, period="1y", interval="1d", progress=False, auto_adjust=True)
        # 處理多重索引
        data = raw_data['Close'] if 'Close' in raw_data else raw_data
        
        sctr_data = []
        for ticker in tickers:
            try:
                # 確保 ticker 在 data 中且資料充足
                series = data[ticker].dropna() if isinstance(data, pd.DataFrame) else data.dropna()
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
    except Exception as e:
        st.warning(f"SCTR 計算遇到部分問題: {e}")
        return {}

# --- 3. 核心篩選 ---
def check_vcp_advanced(ticker, sctr_map, b_only, b_days):
    try:
        df = yf.download(ticker, period="1y", progress=False, auto_adjust=True)
        if df.empty or len(df) < 200: return None
        
        # 兼容 yfinance 下載單一標的與多重標的的格式
        close = df['Close'][ticker] if isinstance(df.columns, pd.MultiIndex) else df['Close']
        vol = df['Volume'][ticker] if isinstance(df.columns, pd.MultiIndex) else df['Volume']
        curr_p = float(close.iloc[-1])
        
        # Minervini 6/6 條件
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
            # 波動收縮檢測 (Tightness)
            recent_range = (close.iloc[-5:].max() - close.iloc[-5:].min()) / close.iloc[-5:].min()
            prev_range = (close.iloc[-25:-5].max() - close.iloc[-25:-5].min()) / close.iloc[-25:-5].min()
            is_tight = "✅ 緊湊" if recent_range < (prev_range * 0.7) else "❌ 鬆散"
            
            # 突破與距離高點
            recent_max = float(close.iloc[-(b_days+1):-1].max())
            is_breakout = curr_p > recent_max
            if b_only and not is_breakout: return None
            
            dist_high = round((1 - curr_p/high52) * 100, 2)
            vol_ratio = round(float(vol.iloc[-1]) / vol.rolling(20).mean().iloc[-1], 2)
            sctr_val = round(sctr_map.get(ticker, 0), 1)
            
            status = f"🔥 {b_days}D突破" if is_breakout else "🚀 強勢向上"
            
            return [ticker, round(curr_p, 2), dist_high, sctr_val, is_tight, vol_ratio, status]
        return None
    except: 
        return None

# --- 4. 側邊欄與執行 ---
st.sidebar.header("🎛️ 系統參數")
market_name = st.sidebar.selectbox("選擇市場", ["美股 (Nasdaq 100)", "美股 (S&P 500)", "港股 (恒生指數)"])
min_sctr_val = st.sidebar.slider("最低 SCTR 排名", 0.0, 99.9, 70.0)
b_days = st.sidebar.selectbox("突破檢測天數", [10, 20, 50], index=1)
only_b = st.sidebar.checkbox("僅看突破", value=False)

if st.sidebar.button("🚀 執行全方位掃描"):
    res_list = get_stock_list(market_name)
    if res_list[0]:
        tickers, bench_code = res_list
        
        # --- 大盤溫度計 ---
        try:
            bench_df = yf.download(bench_code, period="1y", progress=False, auto_adjust=True)
            if not bench_df.empty:
                b_series = bench_df['Close'][bench_code] if isinstance(bench_df.columns, pd.MultiIndex) else bench_df['Close']
                b_series = b_series.dropna()
                b_close = float(b_series.iloc[-1])
                b_sma50 = float(b_series.rolling(50).mean().iloc[-1])
                
                health = "🟢 牛市環境" if b_close > b_sma50 else "🔴 熊市/調整"
                
                c1, c2, c3 = st.columns(3)
                c1.metric("大盤狀態", health)
                c2.metric("大盤收盤", f"{b_close:.2f}")
                c3.metric("50MA 距離", f"{((b_close/b_sma50-1)*100):.2f}%")
        except Exception as e:
            st.error(f"溫度計數據加載失敗: {e}")

        st.write("---")
        st.info("📊 第一階段：SCTR 動能排名...")
        sctr_ranks = calculate_sctr_ranks(tickers)
        
        st.info(f"🔍 第二階段：掃描 {len(tickers)} 隻股票形態...")
        results = []
        pb = st.progress(0)
        for i, t in enumerate(tickers):
            res = check_vcp_advanced(t, sctr_ranks, only_b, b_days)
            if res and res[3] >= min_sctr_val: 
                results.append(res)
            pb.progress((i + 1) / len(tickers))

        if results:
            df = pd.DataFrame(results, columns=["代碼", "價格", "距離高點%", "SCTR排名", "收縮狀態", "量比", "狀態"])
            
            def make_link(t):
                t_str = str(t)
                code = t_str.replace('.HK', '').lstrip('0') if ".HK" in t_str else t_str.replace('.', '-')
                px = "HKEX:" if ".HK" in t_str else ""
                return f"https://www.tradingview.com/chart/?symbol={px}{code}"
            
            df['圖表'] = df['代碼'].apply(make_link)
            df = df.sort_values("SCTR排名", ascending=False)
            
            st.dataframe(df, column_config={"圖表": st.column_config.LinkColumn("查看", display_text="Open")}, use_container_width=True)
            st.success(f"找到 {len(df)} 隻符合條件的標的。")
        else:
            st.warning("當前市場環境下無符合標的。建議嘗試調低 SCTR 排名要求。")
    else:
        st.error("無法獲取成份股名單，請稍後再試。")
