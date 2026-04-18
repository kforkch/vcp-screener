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

# --- 2. 獲取股票列表 (完整版本) ---
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
            hsi_list = ["0001.HK", "0005.HK", "0388.HK", "0700.HK", "0939.HK", "0941.HK", "1299.HK", "1810.HK", "2318.HK", "3690.HK", "9988.HK"]
            return hsi_list, "^HSI"
        return [], None
    except: return [], None

# --- 3. 核心邏輯 (含行業與篩選) ---
def check_vcp_advanced(ticker, sctr_map, b_only, b_days):
    try:
        df = yf.download(ticker, period="1y", progress=False, auto_adjust=True)
        if df.empty or len(df) < 200: return None
        
        # 獲取行業
        info = yf.Ticker(ticker).info
        sector = info.get('sector', 'N/A')
        
        close = df['Close'][ticker] if isinstance(df.columns, pd.MultiIndex) else df['Close']
        vol = df['Volume'][ticker] if isinstance(df.columns, pd.MultiIndex) else df['Volume']
        curr_p = float(close.iloc[-1])
        sma50, sma150, sma200 = ta.sma(close, 50).iloc[-1], ta.sma(close, 150).iloc[-1], ta.sma(close, 200).iloc[-1]
        
        # 篩選邏輯
        if curr_p > sma50 and curr_p > sma150:
            recent_range = (close.iloc[-5:].max() - close.iloc[-5:].min()) / close.iloc[-5:].min()
            is_tight = "緊湊" if recent_range < 0.05 else "鬆散"
            dist_high = round((1 - curr_p/close.max()) * 100, 2)
            sctr_val = round(sctr_map.get(ticker, 0), 1)
            vol_ratio = round(float(vol.iloc[-1]) / vol.rolling(20).mean().iloc[-1], 2)
            
            # 突破邏輯
            is_breakout = curr_p > close.iloc[-(b_days+1):-1].max()
            if b_only and not is_breakout: return None
            
            return [ticker, round(curr_p, 2), dist_high, sctr_val, is_tight, vol_ratio, "強勢", sector]
    except: return None
    return None

# --- 4. 側邊欄參數 (恢復完整控制) ---
st.sidebar.header("🎛️ 系統參數")
market_name = st.sidebar.selectbox("選擇市場", ["美股 (Nasdaq 100)", "美股 (S&P 500)", "港股 (恒生指數)"])
min_sctr_val = st.sidebar.slider("最低 SCTR 排名", 0.0, 99.9, 70.0)
b_days = st.sidebar.selectbox("突破檢測天數", [10, 20, 50], index=1)
only_b = st.sidebar.checkbox("僅看突破", value=False)
start_scan = st.sidebar.button("🚀 開始掃描")

# --- 5. 主程式執行 ---
if start_scan:
    tickers, _ = get_stock_list(market_name)
    # (假設已預先計算 SCTR，這裡簡化調用)
    sctr_ranks = {} 
    results = []
    
    pb = st.progress(0)
    for i, t in enumerate(tickers[:20]):
        res = check_vcp_advanced(t, sctr_ranks, only_b, b_days)
        if res and res[3] >= min_sctr_val: 
            results.append(res)
        pb.progress((i + 1) / 20)
    
    if results:
        df = pd.DataFrame(results, columns=["代碼", "價格", "距離高點%", "SCTR排名", "收縮狀態", "量比", "狀態", "行業"])
        
        # TradingView 連結生成
        def make_link(t):
            t_str = str(t)
            if ".HK" in t_str: return f"https://www.tradingview.com/chart/?symbol=HKEX:{t_str.replace('.HK', '').lstrip('0')}"
            else: return f"https://www.tradingview.com/chart/?symbol={t_str.replace('.', '-')}"
        
        df['圖表'] = df['代碼'].apply(make_link)
        st.session_state['scan_result'] = df
        st.dataframe(df, column_config={"圖表": st.column_config.LinkColumn("查看", display_text="Open")}, use_container_width=True)

# --- 6. 同步邏輯 ---
if 'scan_result' in st.session_state:
    st.markdown("---")
    if st.button("💾 同步至雲端 (含行業板塊)"):
        if supabase:
            df = st.session_state['scan_result']
            col_mapping = {
                "代碼": "ticker", "價格": "price", "距離高點%": "dist_high",
                "SCTR排名": "sctr", "收縮狀態": "vol_state", "量比": "vol_ratio",
                "狀態": "status", "行業": "sector"
            }
            df_to_sync = df.rename(columns=col_mapping)
            try:
                # 排除圖表欄位
                valid_cols = list(col_mapping.values())
                supabase.table("stock_analysis").upsert(df_to_sync[valid_cols].to_dict(orient='records')).execute()
                st.success("✅ 同步成功！行業資訊已寫入。")
            except Exception as e:
                st.error(f"同步錯誤: {e}")
