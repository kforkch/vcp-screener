import streamlit as st
import pandas as pd
from supabase import create_client

# --- 1. 頁面與連線初始化 ---
st.set_page_config(page_title="VCP Alpha Terminal", layout="wide")

@st.cache_resource
def get_supabase_client():
    # 確保讀取出來的設定乾淨，去除所有引號與空白，避免連線錯誤
    url = str(st.secrets["SUPABASE_URL"]).strip().replace('"', '').replace("'", "")
    key = str(st.secrets["SUPABASE_KEY"]).strip().replace('"', '').replace("'", "")
    return create_client(url, key)

supabase = get_supabase_client()

st.title("🏹 VCP Alpha 全球終極交易終端")

# --- 2. 你的掃描演算法 ---
def run_vcp_scan():
    """
    請將你原本的掃描演算法填寫在這裡。
    這支函式必須回傳一個 DataFrame，且欄位名稱對應 Supabase 表格：
    ticker, price, sctr, sector, status
    """
    # 範例模擬資料 (請替換為你的真實掃描邏輯)
    data = {
        "ticker": ["AAPL", "NVDA", "TSLA"],
        "price": [175.0, 850.0, 170.0],
        "sctr": [88.5, 95.2, 72.1],
        "sector": ["Tech", "Tech", "Auto"],
        "status": ["VCP-Stage2", "VCP-Stage2", "VCP-Stage1"]
    }
    return pd.DataFrame(data)

# --- 3. UI 介面架構 ---
tab1, tab2 = st.tabs(["☁️ 雲端每日看板", "🚀 即時掃描"])

with tab1:
    st.subheader("雲端同步看板")
    if st.button("🔄 重新讀取雲端資料"):
        try:
            # 從 Supabase 抓取資料
            response = supabase.table("stock_analysis").select("*").execute()
            if response.data:
                df = pd.DataFrame(response.data)
                # 顯示資料表
                st.dataframe(df, use_container_width=True)
            else:
                st.info("資料庫目前為空。")
        except Exception as e:
            st.error(f"讀取失敗: {e}")

with tab2:
    st.subheader("🚀 即時掃描器")
    
    # 掃描邏輯
    if st.button("開始掃描"):
        with st.spinner("正在執行 VCP 篩選演算法..."):
            df_result = run_vcp_scan()
            # 將掃描結果存入 session_state 以便後續同步
            st.session_state['last_scan'] = df_result
            st.success("掃描完成！")
            st.dataframe(df_result)

    # 同步邏輯 (檢查是否有掃描結果)
    if 'last_scan' in st.session_state:
        if st.button("💾 將掃描結果同步至雲端看板"):
            try:
                # 將 DataFrame 轉為字典清單格式
                data_to_sync = st.session_state['last_scan'].to_dict(orient='records')
                
                # 使用 upsert，如果 Ticker 已存在則更新，不存在則新增
                supabase.table("stock_analysis").upsert(data_to_sync).execute()
                
                st.success("✅ 同步成功！請切換至「雲端每日看板」查看最新狀態。")
            except Exception as e:
                st.error(f"同步失敗: {e}")
