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
    url = str(st.secrets["SUPABASE_URL"]).strip().replace('"', '').replace("'", "")
    key = str(st.secrets["SUPABASE_KEY"]).strip().replace('"', '').replace("'", "")
    return create_client(url, key)

supabase = get_supabase_client()

# --- 2. 核心功能函數 (保持你原本的邏輯) ---
# (此處省略部分重複函數定義，請確認你原本的邏輯已完整保留)
# 確保這些函數: get_stock_list, calculate_sctr_ranks, check_vcp_advanced 都在這裡

# --- 3. UI 與 整合邏輯 ---
tab1, tab2 = st.tabs(["☁️ 雲端每日看板", "🚀 即時掃描"])

with tab1:
    st.subheader("雲端同步看板")
    if st.button("🔄 重新讀取雲端資料"):
        try:
            response = supabase.table("stock_analysis").select("*").execute()
            if response.data:
                st.dataframe(pd.DataFrame(response.data), use_container_width=True)
            else:
                st.info("資料庫目前為空。")
        except Exception as e: st.error(f"讀取失敗: {e}")

with tab2:
    # (此處填入你原本的 side bar 參數設定)
    # ...
    
    if st.sidebar.button("🚀 執行全球同步掃描"):
        # ... (掃描邏輯) ...
        if results:
            df_display = pd.DataFrame(results, columns=["代碼", "價格", "距離高點%", "SCTR排名", "收縮狀態", "狀態"])
            st.session_state['scan_result'] = df_display 
            st.dataframe(df_display, use_container_width=True)
            st.success("掃描完成！")

    # --- 關鍵修正區：同步按鈕 ---
    if 'scan_result' in st.session_state:
        if st.button("💾 將本次掃描結果同步至雲端看板"):
            try:
                df_to_save = st.session_state['scan_result'].copy()
                
                # 【重要】請檢查右側英文名稱是否對應你 Supabase 裡面的欄位名稱
                column_mapping = {
                    "代碼": "ticker",
                    "價格": "price",
                    "距離高點%": "dist_high",
                    "SCTR排名": "sctr",
                    "收縮狀態": "contraction_status",  # 如果你的欄位叫別的，請改這裡
                    "狀態": "status"
                }
                
                # 重新命名欄位
                df_to_save = df_to_save.rename(columns=column_mapping)
                
                # 篩選掉資料庫不支援的額外欄位 (防止錯誤)
                # 這裡保留 column_mapping 對應到的英文欄位
                df_to_save = df_to_save[list(column_mapping.values())]
                
                data_to_sync = df_to_save.to_dict(orient='records')
                
                supabase.table("stock_analysis").upsert(data_to_sync).execute()
                st.success("✅ 同步成功！")
            except Exception as e: 
                st.error(f"同步失敗: {e}")
                st.write("請檢查資料庫欄位名稱是否包含:", column_mapping.values())
