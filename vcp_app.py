import streamlit as st
import yfinance as yf
import pandas as pd
import pandas_ta as ta
import requests
import io
from supabase import create_client

# --- 頁面配置 ---
st.set_page_config(page_title="VCP Alpha Terminal", layout="wide")
st.title("🏹 VCP Alpha 全球終極交易終端")

# --- 1. Supabase 初始化 ---
@st.cache_resource
def get_supabase_client():
    try:
        url = st.secrets["SUPABASE_URL"]
        key = st.secrets["SUPABASE_KEY"]
        return create_client(url, key)
    except: return None

supabase = get_supabase_client()

# --- 2. 核心計算與抓取 (包含行業板塊) ---
def check_vcp_advanced(ticker, sctr_map, b_only, b_days):
    try:
        # 下載數據
        df = yf.download(ticker, period="1y", progress=False, auto_adjust=True)
        if df.empty or len(df) < 200: return None
        
        # 抓取行業資訊
        info = yf.Ticker(ticker).info
        sector = info.get('sector', 'N/A')
        
        close = df['Close'][ticker] if isinstance(df.columns, pd.MultiIndex) else df['Close']
        vol = df['Volume'][ticker] if isinstance(df.columns, pd.MultiIndex) else df['Volume']
        curr_p = float(close.iloc[-1])
        sma50, sma150, sma200 = ta.sma(close, 50).iloc[-1], ta.sma(close, 150).iloc[-1], ta.sma(close, 200).iloc[-1]
        high52 = float(close.max())
        
        # 篩選邏輯
        if curr_p > sma50 and curr_p > sma150:
            recent_range = (close.iloc[-5:].max() - close.iloc[-5:].min()) / close.iloc[-5:].min()
            is_tight = "緊湊" if recent_range < 0.05 else "鬆散"
            dist_high = round((1 - curr_p/high52) * 100, 2)
            sctr_val = round(sctr_map.get(ticker, 0), 1)
            vol_ratio = round(float(vol.iloc[-1]) / vol.rolling(20).mean().iloc[-1], 2)
            
            # 回傳數據 (注意這裡增加了 sector)
            return [ticker, round(curr_p, 2), dist_high, sctr_val, is_tight, vol_ratio, "強勢", sector]
    except: return None
    return None

# --- 3. 掃描執行 (顯示行業欄位) ---
# (省略 get_stock_list 與 calculate_sctr_ranks，沿用原本的即可)
# ... 請保留您原本的這兩個函數 ...

if st.sidebar.button("🚀 開始掃描"):
    # ... (您的掃描迴圈) ...
    # 掃描完成後建立 DataFrame
    if results:
        df = pd.DataFrame(results, columns=["代碼", "價格", "距離高點%", "SCTR排名", "收縮狀態", "量比", "狀態", "行業"])
        
        # 顯示在 UI 上
        st.dataframe(df, use_container_width=True)
        st.session_state['scan_result'] = df

# --- 4. 同步邏輯 (包含行業欄位) ---
if 'scan_result' in st.session_state:
    if st.button("💾 同步至雲端 (含行業板塊)"):
        if supabase:
            df = st.session_state['scan_result']
            col_mapping = {
                "代碼": "ticker",
                "價格": "price",
                "距離高點%": "dist_high",
                "SCTR排名": "sctr",
                "收縮狀態": "vol_state",
                "量比": "vol_ratio",
                "狀態": "status",
                "行業": "sector"  # 對應資料庫欄位
            }
            df_to_sync = df.rename(columns=col_mapping)
            try:
                supabase.table("stock_analysis").upsert(df_to_sync.to_dict(orient='records')).execute()
                st.success("✅ 同步成功！行業板塊數據已存入資料庫。")
            except Exception as e:
                st.error(f"同步錯誤: {e}")
