# main.py
import streamlit as st
import pandas as pd
from data_loader import get_stock_list
from analyzer import calculate_sctr_ranks, check_vcp_advanced

st.set_page_config(page_title="VCP Alpha Terminal", layout="wide")
st.title("🏹 VCP Alpha 全球終極交易終端 v2.0")

st.sidebar.header("🎛️ 系統參數")
market_name = st.sidebar.selectbox("選擇市場", ["美股 (Nasdaq 100)", "美股 (S&P 500)", "港股 (恒生指數)", "中國 A 股 (滬深 300 龍頭)"])
min_sctr = st.sidebar.slider("最低 SCTR", 0.0, 99.9, 78.0)
b_days = st.sidebar.selectbox("突破檢測天數", [10, 20, 50], index=1)
only_breakout = st.sidebar.checkbox("僅顯示突破", value=False)
min_quality = st.sidebar.slider("最低品質分數", 60, 95, 75)

if st.sidebar.button("🚀 執行全球同步掃描", type="primary"):
    with st.spinner(f"正在掃描 {market_name}..."):
        tickers, _ = get_stock_list(market_name)
        if not tickers:
            st.error("無法取得股票清單")
            st.stop()
        
        sctr_map, sctr_hist = calculate_sctr_ranks(tickers)
        results = []
        progress_bar = st.progress(0)
        
        for i, t in enumerate(tickers):
            res = check_vcp_advanced(t, sctr_map, sctr_hist, only_breakout, b_days)
            if res and res[3] >= min_sctr and res[-1] >= min_quality:
                results.append(res)
            progress_bar.progress((i + 1) / len(tickers))
        
        if results:
            df = pd.DataFrame(results, columns=[
                "代碼", "價格", "距離高點%", "SCTR", "收縮狀態", "量比", 
                "狀態", "行業", "Pivot", "SL", "Target", "品質分數"
            ])
            df = df.sort_values(by=["品質分數", "SCTR"], ascending=False)
            
            st.success(f"找到 {len(df)} 檔優質 VCP 標的！")
            st.dataframe(df, use_container_width=True, hide_index=True)
        else:
            st.warning("今日無符合條件的標的")
