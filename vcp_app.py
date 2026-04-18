import streamlit as st
import pandas as pd
import yfinance as yf
from supabase import create_client

# --- 頁面配置 ---
st.set_page_config(page_title="VCP Alpha Terminal", layout="wide")

# --- 核心：唯一初始化 Supabase (確保變數讀取乾淨) ---
@st.cache_resource
def get_supabase_client():
    # 強制移除引號與前後空白，解決編碼錯誤
    url = str(st.secrets["SUPABASE_URL"]).strip().replace('"', '').replace("'", "")
    key = str(st.secrets["SUPABASE_KEY"]).strip().replace('"', '').replace("'", "")
    return create_client(url, key)

supabase = get_supabase_client()

st.title("🏹 VCP Alpha 全球終極交易終端")

# --- 核心函數：模擬掃描邏輯 ---
def run_vcp_scan():
    # 這裡放你原本的股票掃描篩選邏輯
    # 產出的結果必須是一個 DataFrame，包含: ticker, price, sctr, sector, status
    data = {
        "ticker": ["AAPL", "NVDA", "TSLA"],
        "price": [175.0, 850.0, 170.0],
        "sctr": [88.5, 95.2, 72.1],
        "sector": ["Tech", "Tech", "Auto"],
        "status": ["VCP-Stage2", "VCP-Stage2", "VCP-Stage1"]
    }
    return pd.DataFrame(data)

# --- UI 介面 ---
tab1, tab2 = st.tabs(["☁️ 雲端每日看板", "🚀 即時掃描"])

with tab1:
    st.subheader("雲端同步看板")
    if st.button("🔄 重新讀取雲端資料"):
        try:
            # 從 Supabase 讀取數據
            response = supabase.table("stock_analysis").select("*").execute()
            if response.data:
                df = pd.DataFrame(response.data)
                st.dataframe(df, use_container_width=True)
            else:
                st.info("資料庫目前為空。")
        except Exception as e:
            st.error(f"讀取失敗: {e}")

with tab2:
    st.subheader("🚀 即時掃描器")
    
    # 掃描按鈕
    if st.button("開始掃描"):
        with st.spinner("正在進行 VCP 篩選..."):
            df_result = run_vcp_scan()
            st.session_state['scan_result'] = df_result # 暫存結果
            st.success("掃描完成！")
            st.dataframe(df_result)

    # 如果有掃描結果，顯示同步按鈕
    if 'scan_result' in st.session_state:
        if st.button("💾 將結果同步至雲端看板"):
            try:
                # 將 DataFrame 轉為 Supabase 可讀的格式
                data_to_insert = st.session_state['scan_result'].to_dict(orient='records')
                # 寫入資料庫
                supabase.table("stock_analysis").insert(data_to_insert).execute()
                st.success("✅ 資料已同步，請切換至「雲端每日看板」頁面查看。")
            except Exception as e:
                st.error(f"同步失敗: {e}")
