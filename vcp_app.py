import streamlit as st
import yfinance as yf
import pandas as pd
import pandas_ta as ta
import requests
import io
import numpy as np

# --- 頁面配置 ---
st.set_page_config(page_title="VCP Alpha Terminal", layout="wide")
st.title("🏹 VCP Alpha 全球交易終端 (產業群聚增強版)")

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
            hsi_list = ["0001.HK", "0002.HK", "0005.HK", "0388.HK", "0700.HK", "0941.HK", "1211.HK", "1299.HK", "1810.HK", "2318.HK", "3690.HK", "9988.HK", "9618.HK"] # 簡化測試版
            return hsi_list, "^HSI"
        elif market == "中國 A 股 (滬深 300 龍頭)":
            as_list = ["600519.SS", "601318.SS", "000858.SZ", "300750.SZ", "600036.SS", "002594.SZ"] # 簡化測試版
            return as_list, "000300.SS"
    except: return [], None
    return [], None

# --- 2. SCTR 排名計算 ---
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

# --- 3. 核心篩選 (加入產業獲取) ---
def check_vcp_advanced(ticker, sctr_map, b_only, b_days):
    try:
        # 獲取個股基本資料 (包含產業)
        t_obj = yf.Ticker(ticker)
        info = t_obj.info
        sector = info.get('sector', '其他產業')
        
        df = t_obj.history(period="1y", auto_adjust=True)
        if df.empty or len(df) < 200: return None
        
        close = df['Close']
        vol = df['Volume']
        curr_p = float(close.iloc[-1])
        
        # 趨勢模板
        sma50, sma150, sma200 = ta.sma(close, 50).iloc[-1], ta.sma(close, 150).iloc[-1], ta.sma(close, 200).iloc[-1]
        low52, high52 = float(close.min()), float(close.max())
        
        cond = [curr_p > sma150, curr_p > sma200, sma150 > sma200, sma50 > sma150, curr_p > sma50, curr_p >= low52*1.25, curr_p >= high52*0.75]
        
        if all(cond):
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

# --- 4. 側邊欄 ---
st.sidebar.header("🎛️ 系統參數")
market_name = st.sidebar.selectbox("選擇市場", ["美股 (Nasdaq 100)", "美股 (S&P 500)", "港股 (恒生指數)", "中國 A 股 (滬深 300 龍頭)"])
min_sctr_val = st.sidebar.slider("最低 SCTR 排名", 0.0, 99.9, 70.0)
b_days = st.sidebar.selectbox("突破檢測天數", [10, 20, 50], index=1)
only_b = st.sidebar.checkbox("僅看突破", value=False)

if st.sidebar.button("🚀 執行群聚掃描"):
    res_tuple = get_stock_list(market_name)
    if res_tuple[0]:
        tickers, bench_code = res_tuple
        st.info(f"正在分析 {market_name} 的產業群聚效應...")
        
        sctr_ranks = calculate_sctr_ranks(tickers)
        results = []
        pb = st.progress(0)
        
        for i, t in enumerate(tickers):
            res = check_vcp_advanced(t, sctr_ranks, only_b, b_days)
            if res and res[3] >= min_sctr_val:
                results.append(res)
            pb.progress((i + 1) / len(tickers))

        if results:
            df = pd.DataFrame(results, columns=["代碼", "價格", "距離高點%", "SCTR排名", "收縮狀態", "量比", "產業"])
            
            # --- 產業群聚可視化 ---
            st.subheader("🔥 當前最強產業群聚 (Industry Group Power)")
            col1, col2 = st.columns([1, 2])
            
            with col1:
                # 統計各產業出現符合 VCP 的股票數量
                group_stats = df['產業'].value_counts()
                st.write("符合 VCP 條件的股票分佈：")
                st.dataframe(group_stats, use_container_width=True)
            
            with col2:
                # 使用橫向柱狀圖展示熱度
                st.bar_chart(group_stats)
            
            st.write("---")
            st.subheader("🎯 精選標的清單")
            st.dataframe(df.sort_values(["產業", "SCTR排名"], ascending=[True, False]), use_container_width=True)
            
        else:
            st.warning("目前市場無明顯群聚效應。")
