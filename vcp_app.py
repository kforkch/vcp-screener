import streamlit as st
import yfinance as yf
import pandas as pd
import pandas_ta as ta
import requests
import io
import numpy as np
from supabase import create_client

# --- 頁面配置 ---
st.set_page_config(page_title="VCP Alpha Terminal", layout="wide")
st.title("🏹 VCP Alpha 全球終極交易終端")

# --- 1. Supabase 初始化 ---
@st.cache_resource
def get_supabase_client():
    try:
        return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])
    except: return None

supabase = get_supabase_client()

# --- 2. 行業資訊快取 ---
@st.cache_data(ttl=86400)
def get_sector_cached(ticker):
    try:
        info = yf.Ticker(ticker).info
        return info.get('sector', 'N/A')
    except:
        return 'N/A'

# --- 3. 獲取市場清單 ---
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
            return ["0001.HK", "0005.HK", "0388.HK", "0700.HK", "0939.HK", "0941.HK", "1299.HK", "1810.HK", "2318.HK", "3690.HK", "9988.HK"], "^HSI"
        elif market == "中國 A 股 (滬深 300 龍頭)":
            as_list = [
                "600519.SS", "601318.SS", "600036.SS", "601012.SS", "600276.SS", "601166.SS", "600900.SS", "600030.SS",
                "601888.SS", "600809.SS", "601398.SS", "601288.SS", "601988.SS", "601628.SS", "601601.SS", "600019.SS",
                "600048.SS", "601919.SS", "600104.SS", "601088.SS", "600309.SS", "600585.SS", "603288.SS", "603501.SS",
                "600703.SS", "600406.SS", "601857.SS", "601899.SS", "600111.SS", "600016.SS", "600690.SS", "600887.SS",
                "000858.SZ", "000333.SZ", "002415.SZ", "000651.SZ", "002475.SZ", "300750.SZ", "300059.SZ", "000725.SZ"
            ]
            return as_list, "000300.SS"
        return [], None
    except: return [], None

# --- 4. SCTR 排名計算 ---
def calculate_sctr_ranks(tickers):
    try:
        raw_data = yf.download(tickers, period="1y", interval="1d", progress=False, auto_adjust=True)
        data = raw_data['Close'] if 'Close' in raw_data else raw_data
        sctr_data = []
        for ticker in tickers:
            try:
                series = data[ticker].dropna() if isinstance(data, pd.DataFrame) else data.dropna()
                if len(series) < 200: continue
                sma200, sma50 = series.rolling(200).mean().iloc[-1], series.rolling(50).mean().iloc[-1]
                raw = ((series.iloc[-1]/sma200-1)*30) + ((series.iloc[-1]/sma50-1)*15)
                sctr_data.append({'ticker': ticker, 'raw': raw})
            except: continue
        if not sctr_data: return {}
        df_sctr = pd.DataFrame(sctr_data)
        df_sctr['rank'] = df_sctr['raw'].rank(pct=True) * 99.9
        return df_sctr.set_index('ticker')['rank'].to_dict()
    except: return {}

# --- 5. 核心篩選 ---
def check_vcp_advanced(ticker, sctr_map, b_only, b_days):
    try:
        df = yf.download(ticker, period="1y", progress=False, auto_adjust=True)
        if df.empty or len(df) < 200: return None
        
        close = df['Close'][ticker] if isinstance(df.columns, pd.MultiIndex) else df['Close']
        vol = df['Volume'][ticker] if isinstance(df.columns, pd.MultiIndex) else df['Volume']
        curr_p = float(close.iloc[-1])
        
        sma50, sma150, sma200 = ta.sma(close, 50).iloc[-1], ta.sma(close, 150).iloc[-1], ta.sma(close, 200).iloc[-1]
        low52, high52 = float(close.min()), float(close.max())
        
        # Minervini 6 條件篩選
        cond = [
            curr_p > sma150 and curr_p > sma200, sma150 > sma200, 
            sma50 > sma150 and sma50 > sma200, curr_p > sma50,
            curr_p >= (low52 * 1.25), curr_p >= (high52 * 0.75)
        ]
        
        if sum(cond) == 6:
            recent_range = (close.iloc[-5:].max() - close.iloc[-5:].min()) / close.iloc[-5:].min()
            is_tight = "✅ 緊湊" if recent_range < 0.05 else "❌ 鬆散"
            dist_high = round((1 - curr_p/high52) * 100, 2)
            sctr_val = round(sctr_map.get(ticker, 0), 1)
            vol_ratio = round(float(vol.iloc[-1]) / vol.rolling(20).mean().iloc[-1], 2)
            
            is_breakout = curr_p > close.iloc[-(b_days+1):-1].max()
            if b_only and not is_breakout: return None
            
            sector = get_sector_cached(ticker)
            return [ticker, round(curr_p, 2), dist_high, sctr_val, is_tight, vol_ratio, "強勢", sector]
    except: return None
    return None

# --- 6. UI 與執行 ---
st.sidebar.header("🎛️ 系統參數")
market_name = st.sidebar.selectbox("選擇市場", ["美股 (Nasdaq 100)", "美股 (S&P 500)", "港股 (恒生指數)", "中國 A 股 (滬深 300 龍頭)"])
min_sctr_val = st.sidebar.slider("最低 SCTR 排名", 0.0, 99.9, 70.0)
b_days = st.sidebar.selectbox("突破檢測天數", [10, 20, 50], index=1)
only_b = st.sidebar.checkbox("僅看突破", value=False)

if st.sidebar.button("🚀 開始掃描"):
    tickers, _ = get_stock_list(market_name)
    sctr_ranks = calculate_sctr_ranks(tickers)
    results = []
    
    # 建立進度顯示
    pb = st.progress(0)
    status_text = st.empty()
    
    for i, t in enumerate(tickers):
        status_text.text(f"正在分析 ({i+1}/{len(tickers)}): {t}")
        try:
            res = check_vcp_advanced(t, sctr_ranks, only_b, b_days)
            if res and res[3] >= min_sctr_val:
                results.append(res)
        except: continue
        pb.progress((i + 1) / len(tickers))
    
    status_text.empty()
    
    if results:
        df = pd.DataFrame(results, columns=["代碼", "價格", "距離高點%", "SCTR排名", "收縮狀態", "量比", "狀態", "行業"])
        
        def make_link(t):
            t_str = str(t)
            if ".HK" in t_str: return f"https://www.tradingview.com/chart/?symbol=HKEX:{t_str.replace('.HK', '').lstrip('0')}"
            elif ".SS" in t_str or ".SZ" in t_str:
                prefix = "SSE" if ".SS" in t_str else "SZSE"
                return f"https://www.tradingview.com/chart/?symbol={prefix}:{t_str.split('.')[0]}"
            else: return f"https://www.tradingview.com/chart/?symbol={t_str.replace('.', '-')}"
        
        df['圖表'] = df['代碼'].apply(make_link)
        st.session_state['scan_result'] = df
        st.dataframe(df, column_config={"圖表": st.column_config.LinkColumn("查看", display_text="Open")}, use_container_width=True)

# --- 7. 同步邏輯 ---
if 'scan_result' in st.session_state:
    if st.button("💾 同步至雲端看板"):
        if supabase:
            df = st.session_state['scan_result']
            col_mapping = {
                "代碼": "ticker", "價格": "price", "距離高點%": "dist_high",
                "SCTR排名": "sctr", "收縮狀態": "vol_state", "量比": "vol_ratio",
                "狀態": "status", "行業": "sector"
            }
            try:
                df_to_sync = df.rename(columns=col_mapping)[list(col_mapping.values())]
                supabase.table("stock_analysis").upsert(df_to_sync.to_dict(orient='records')).execute()
                st.success("✅ 同步成功！")
            except Exception as e:
                st.error(f"同步錯誤: {e}")
