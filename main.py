# main.py
import streamlit as st
import pandas as pd

# 1. 導入數據載入模組
from data_loader import get_stock_list

# 2. 導入分析器與 SCTR 計算核心
from analyzer import check_vcp_advanced, calculate_sctr_ranks

# ==================== 頁面基本配置 ====================
st.set_page_config(page_title="VCP Alpha Terminal", layout="wide")
st.title("🏹 VCP Alpha 全球終極交易終端")

# ==================== 側邊欄控制面版 ====================
st.sidebar.header("🎛️ 系統參數")
market_name = st.sidebar.selectbox(
    "選擇市場", 
    ["美股 (Nasdaq 100)", "美股 (S&P 500)", "港股 (恒生指數)", "中國 A 股 (滬深 300 龍頭)"]
)
min_sctr_val = st.sidebar.slider("最低 SCTR 排名", 0.0, 99.9, 80.0)
b_days = st.sidebar.selectbox("突破檢測天數", [10, 20, 50], index=1)
only_b = st.sidebar.checkbox("僅看突破", value=False)

def make_link(t):
    """為股票代碼生成 TradingView 連結"""
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

# ==================== 主掃描邏輯 ====================
if st.sidebar.button("🚀 執行全球同步掃描"):
    res_tuple = get_stock_list(market_name)
    if res_tuple and res_tuple[0]:
        tickers, bench_code = res_tuple
        
        st.write(f"正在掃描 {market_name} ...")
        
        # 獲取最新與歷史 SCTR 排名 (內部會自動安全調用 Supabase)
        sctr_ranks, sctr_hist = calculate_sctr_ranks(tickers, lookback=20)
        results = []
        
        # 建立進度條
        pb = st.progress(0)
        
        for i, t in enumerate(tickers):
            try:
                # 執行 VCP 篩選 (analyzer.py 內部會自動優先從 Supabase 讀取日 K)
                res = check_vcp_advanced(t, sctr_ranks, sctr_hist, only_b, b_days)
                if res and res[3] >= min_sctr_val: 
                    results.append(res)
            except Exception as e:
                # 單檔股票出錯不中斷整體掃描
                print(f"⚠️ 掃描 {t} 時發生非致命錯誤: {e}")
            
            pb.progress((i + 1) / len(tickers))

        if results:
            # 建立 DataFrame 
            df = pd.DataFrame(results, columns=[
                "代碼", "價格", "距離高點%", "SCTR排名", "收縮狀態", "量比", "狀態", "行業",
                "Pivot(樞軸)", "SL(ATR停損)", "Target(目標3R)"
            ])
            
            # 重新排列欄位順序，提升可讀性
            decision_order = [
                "代碼", "行業", "SCTR排名", "價格", 
                "Pivot(樞軸)", "SL(ATR停損)", "Target(目標3R)", 
                "量比", "收縮狀態", "狀態", "距離高點%"
            ]
            df = df[decision_order]
            
            # 新增 TradingView 圖表觀看連結
            df['圖表'] = df['代碼'].apply(make_link)
            
            # 依 SCTR 排名降序排序
            df_sorted = df.sort_values("SCTR排名", ascending=False)
            
            # 渲染數據表格
            st.dataframe(
                df_sorted, 
                column_config={"圖表": st.column_config.LinkColumn("查看", display_text="Open")}, 
                use_container_width=True,
                hide_index=True
            )
            st.success(f"🎉 掃描完成！共找到 {len(df)} 檔符合 VCP 多段收縮且 SCTR 持續攀升的標的。")
        else:
            st.warning("今日未篩選出符合 VCP 多段收縮與 SCTR 持續成長的標的。")
    else:
        st.error("無法取得市場股票清單，請檢查網路連線或 data/ 資料夾下的代碼檔案。")
