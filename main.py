# main.py
import streamlit as st
import pandas as pd
from data_loader import get_stock_list
from analyzer import calculate_sctr_ranks, check_vcp_advanced

st.set_page_config(page_title="VCP Alpha Terminal", layout="wide")
st.title("🏹 VCP Alpha 全球終極交易終端")

st.sidebar.header("🎛️ 系統參數")
market_name = st.sidebar.selectbox("選擇市場", ["美股 (Nasdaq 100)", "美股 (S&P 500)", "港股 (恒生指數)", "中國 A 股 (滬深 300 龍頭)"])
min_sctr_val = st.sidebar.slider("最低 SCTR 排名", 0.0, 99.9, 80.0)
b_days = st.sidebar.selectbox("突破檢測天數", [10, 20, 50], index=1)
only_b = st.sidebar.checkbox("僅看突破", value=False)
use_fund = st.sidebar.checkbox("啟用基本面過濾 (慢)", value=False) # 新增選項

def make_link(t):
    t_str = str(t)
    if ".HK" in t_str:
        code = t_str.replace('.HK', '').lstrip('0')
        return f"https://www.tradingview.com/chart/?symbol=HKEX:{code}"
    elif ".SS" in t_str or ".SZ" in t_str:
        code = t_str.split('.')[0]
        prefix = "SSE" if ".SS" in t_str else "SZSE"
        return f"https://www.tradingview.com/chart/?symbol={prefix}:{code}"
    else:
        return f"https://www.tradingview.com/chart/?symbol={t_str.replace('.', '-')}"

if st.sidebar.button("🚀 執行全球同步掃描"):
    res_tuple = get_stock_list(market_name)
    if res_tuple[0]:
        tickers, bench_code = res_tuple
        st.write(f"正在掃描 {market_name} (基本面: {'開' if use_fund else '關'}) ...")
        sctr_ranks = calculate_sctr_ranks(tickers)
        results = []
        pb = st.progress(0)
        
        for i, t in enumerate(tickers):
            # 傳入 use_fund 參數
            res = check_vcp_advanced(t, sctr_ranks, only_b, b_days, use_fundamentals=use_fund)
            if res and res[3] >= min_sctr_val: 
                results.append(res)
            pb.progress((i + 1) / len(tickers))

        if results:
            df = pd.DataFrame(results, columns=[
                "代碼", "價格", "距離高點%", "SCTR排名", "收縮狀態", "量比", "狀態", "行業",
                "Pivot(樞軸)", "SL(ATR停損)", "Target(目標3R)"
            ])
            decision_order = ["代碼", "行業", "SCTR排名", "價格", "Pivot(樞軸)", "SL(ATR停損)", "Target(目標3R)", "量比", "收縮狀態", "狀態", "距離高點%"]
            df = df[decision_order]
            df['圖表'] = df['代碼'].apply(make_link)
            df_sorted = df.sort_values("SCTR排名", ascending=False)
            
            st.dataframe(
                df_sorted, 
                column_config={"圖表": st.column_config.LinkColumn("查看", display_text="Open")}, 
                use_container_width=True,
                hide_index=True
            )
            st.success(f"掃描完成！找到 {len(df)} 檔符合條件標的。")
        else:
            st.warning("無符合條件標的。")
    else:
        st.error("無法取得市場股票清單。")
