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

# --- 初始化 Supabase ---
@st.cache_resource
def get_supabase_client():
    url = str(st.secrets["SUPABASE_URL"]).strip().replace('"', '').replace("'", "")
    key = str(st.secrets["SUPABASE_KEY"]).strip().replace('"', '').replace("'", "")
    return create_client(url, key)

supabase = get_supabase_client()

# --- 核心函數：掃描邏輯 ---
# [請確保這裡保留你原本完整的 get_stock_list, calculate_sctr_ranks, check_vcp_advanced 函數]
# (為了縮短版面，這裡略過這些函數的內容，請直接使用你原本檔案中的版本)

# --- UI 介面 ---
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
    # 參數設定
    market_name = st.sidebar.selectbox("選擇市場", ["美股 (Nasdaq 100)", "美股 (S&P 500)", "港股 (恒生指數)", "中國 A 股 (滬深 300 龍頭)"])
    min_sctr_val = st.sidebar.slider("最低 SCTR 排名", 0.0, 99.9, 70.0)
    b_days = st.sidebar.selectbox("突破檢測天數", [10, 20, 50], index=1)
    only_b = st.sidebar.checkbox("僅看突破", value=False)

    # 掃描按鈕 (修正作用域問題：將結果存入 st.session_state)
    if st.sidebar.button("🚀 執行全球同步掃描"):
        tickers, bench_code = get_stock_list(market_name)
        sctr_ranks = calculate_sctr_ranks(tickers)
        results = []
        pb = st.progress(0)
        
        for i, t in enumerate(tickers):
            res = check_vcp_advanced(t, sctr_ranks, only_b, b_days)
            if res and res[3] >= min_sctr_val: results.append(res)
            pb.progress((i + 1) / len(tickers))

        if results:
            df = pd.DataFrame(results, columns=["代碼", "價格", "距離高點%", "SCTR排名", "收縮狀態", "量比", "狀態"])
            st.session_state['scan_result'] = df # 存入 session_state
            st.success("掃描完成！")
        else:
            st.warning("無符合標的。")
            if 'scan_result' in st.session_state: del st.session_state['scan_result']

    # 顯示與同步 (修正作用域問題：讀取 st.session_state)
    if 'scan_result' in st.session_state:
        df_display = st.session_state['scan_result']
        st.dataframe(df_display, use_container_width=True)
        
        if st.button("💾 將本次掃描結果同步至雲端看板"):
            try:
                # 欄位映射
                column_mapping = {
                    "代碼": "ticker",
                    "價格": "price",
                    "距離高點%": "dist_high",
                    "SCTR排名": "sctr",
                    "收縮狀態": "contraction_status",
                    "狀態": "status"
                }
                df_to_save = df_display.rename(columns=column_mapping)
                # 確保只寫入正確的欄位
                df_to_save = df_to_save[list(column_mapping.values())]
                data_to_sync = df_to_save.to_dict(orient='records')
                
                supabase.table("stock_analysis").upsert(data_to_sync).execute()
                st.success("✅ 同步成功！")
            except Exception as e: 
                st.error(f"同步失敗: {e}")
