import streamlit as st
import yfinance as yf
import pandas as pd
import pandas_ta as ta
import requests
import io
import numpy as np

# --- 頁面配置 ---
st.set_page_config(page_title="VCP Alpha Terminal", layout="wide")
st.title("🏹 VCP Alpha 全球終極交易終端")

# --- 1. 全量獲取成份股 (不減少任何標的) ---
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
            # 完整的 82 隻恆指成份股
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
                "600048.SS", "601919.SS", "600104.SS", "601088.SS", "600309.SS", "600585.SS", "603288.SS", "603501.SS",
                "600703.SS", "600406.SS", "601857.SS", "601899.SS", "600111.SS", "600016.SS", "600690.SS", "600887.SS",
                "601668.SS", "601138.SS", "601328.SS", "601006.SS", "601998.SS", "600000.SS", "600009.SS", "600150.SS",
                "600196.SS", "600346.SS", "600547.SS", "600741.SS", "600760.SS", "600837.SS", "601766.SS", "601818.SS",
                "601939.SS", "601985.SS", "000858.SZ", "000333.SZ", "002415.SZ", "000651.SZ", "002475.SZ", "300750.SZ",
                "300059.SZ", "000725.SZ", "002594.SZ", "002142.SZ", "000001.SZ", "002352.SZ", "002304.SZ", "002714.SZ",
                "300015.SZ", "300760.SZ", "002460.SZ", "002466.SZ", "000768.SZ", "002027.SZ", "000661.SZ", "000792.SZ",
                "000895.SZ", "002001.SZ", "002007.SZ", "002241.SZ", "002271.SZ", "002371.SZ", "002410.SZ", "002459.SZ",
                "002493.SZ", "002555.SZ", "002812.SZ", "300122.SZ", "300124.SZ", "300142.SZ", "300274.SZ", "300347.SZ",
                "300408.SZ", "300433.SZ", "300498.SZ", "300529.SZ", "300896.SZ", "000002.SZ", "000063.SZ", "000100.SZ",
                "000425.SZ", "000538.SZ", "000568.SZ", "001979.SZ"
            ]
            return as_list, "000300.SS"
            
    except Exception as e:
        st.error(f"獲取名單失敗: {e}")
        return [], None
    return [], None

# --- 2. SCTR 排名計算 (全量下載) ---
def calculate_sctr_ranks(tickers):
    try:
        raw_data = yf.download(tickers, period="15mo", interval="1d", progress=False, auto_adjust=True)
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

# --- 3. 核心 VCP 篩選 (不妥協的門檻) ---
def check_vcp_advanced(ticker, sctr_map, b_only, b_days):
    try:
        t_obj = yf.Ticker(ticker)
        df = t_obj.history(period="15mo", auto_adjust=True)
        if df.empty or len(df) < 200: return None
        
        close = df['Close']
        vol = df['Volume']
        curr_p = float(close.iloc[-1])
        
        # Minervini 趨勢模板
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
            # 獲取產業 (增加容錯)
            try: sector = t_obj.info.get('sector', '未知板塊')
            except: sector = "未知板塊"

            # 收縮特徵
            recent_range = (close.iloc[-5:].max() - close.iloc[-5:].min()) / close.iloc[-5:].min()
            prev_range = (close.iloc[-25:-5].max() - close.iloc[-25:-5].min()) / close.iloc[-25:-5].min()
            is_tight = "✅ 緊湊" if recent_range < (prev_range * 0.7) else "❌ 鬆散"
            
            recent_max = float(close.iloc[-(b_days+1):-1].max())
            is_breakout = curr_p > recent_max
            if b_only and not is_breakout: return None
            
            sctr_val = round(sctr_map.get(ticker, 0), 1)
            vol_ratio = round(float(vol.iloc[-1]) / vol.rolling(20).mean().iloc[-1], 2)
            dist_high = round((1 - curr_p/high52) * 100, 2)
            
            return [ticker, round(curr_p, 2), dist_high, sctr_val, is_tight, vol_ratio, sector]
    except: return None

# --- 4. 側邊欄與分析執行 ---
st.sidebar.header("🎛️ 全球掃描參數")
market_name = st.sidebar.selectbox("選擇市場", ["美股 (Nasdaq 100)", "美股 (S&P 500)", "港股 (恒生指數)", "中國 A 股 (核心龍頭 100)"])
min_sctr = st.sidebar.slider("最低 SCTR 排名", 0, 99, 70)
b_days = st.sidebar.selectbox("突破檢測天數", [10, 20, 50], index=1)
only_b = st.sidebar.checkbox("僅顯示突破個股", value=False)

if st.sidebar.button("🚀 啟動全量 VCP 掃描"):
    tickers, bench_code = get_stock_list(market_name)
    if tickers:
        st.info(f"🔍 正在掃描 {market_name} 共 {len(tickers)} 隻成份股...")
        sctr_ranks = calculate_sctr_ranks(tickers)
        
        results = []
        pb = st.progress(0)
        for i, t in enumerate(tickers):
            res = check_vcp_advanced(t, sctr_ranks, only_b, b_days)
            if res and res[3] >= min_sctr: results.append(res)
            pb.progress((i + 1) / len(tickers))

        if results:
            df = pd.DataFrame(results, columns=["代碼", "價格", "距離高點%", "SCTR", "收縮", "量比", "產業"])
            
            # --- 產業群聚分析區 ---
            st.subheader("🔥 產業群聚效應 (Industry Clusters)")
            c1, c2 = st.columns([1, 2])
            group_stats = df['產業'].value_counts()
            c1.write("各產業符合條件數量：")
            c1.dataframe(group_stats)
            c2.bar_chart(group_stats)
            
            st.write("---")
            st.subheader(f"🎯 掃描結果 (符合門檻: {len(df)} 隻)")
            st.dataframe(df.sort_values("SCTR", ascending=False), use_container_width=True, hide_index=True)
            st.success(f"全量掃描完成！")
        else:
            st.warning("⚠️ 掃描完成，但在嚴格 200 天門檻下無符合標的。")
