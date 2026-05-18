# main.py
import streamlit as st
import pandas as pd
from data_loader import get_stock_list
from analyzer import calculate_sctr_ranks, check_vcp_advanced

st.set_page_config(page_title="VCP Alpha Terminal", layout="wide")

# --- Custom CSS for Professional Look ---
st.markdown("""
    <style>
    .main {
        background-color: #0e1117;
    }
    .stDataFrame {
        border: 1px solid #30363d;
        border-radius: 5px;
    }
    </style>
    """, unsafe_allow_html=True)

st.title("🏹 VCP Alpha 全球終極交易終端")
st.markdown("### 實踐 Livermore $\\rightarrow$ O'Neil $\rightarrow$ Minervini 動能交易體系")

# --- Sidebar Configuration ---
st.sidebar.header("🎛️ 系統參數")

# 1. Market Selection
market_name = st.sidebar.selectbox(
    "選擇市場", 
    ["美股 (Nasdaq 100)", "美股 (S&P 500)", "港股 (恒生指數)", "中國 A 股 (滬深 300 龍頭)"]
)

# 2. Strategy Filters
st.sidebar.subheader("🔍 篩選強度")
min_sctr_val = st.sidebar.slider("最低 SCTR 排名 (相對強度)", 0.0, 99.9, 80.0, 
                                help="SCTR 越高代表股票相對市場越強，Minervini 建議關注 70-90 以上的標的")

b_days = st.sidebar.selectbox("突破檢測天數", [10, 20, 50], index=1, 
                                help="檢測過去 N 天內的最高點作為 Pivot 樞軸點")

only_b = st.sidebar.checkbox("僅看突破 (Exclude Pre-breakout)", value=False, 
                             help="勾選後僅顯示已突破 Pivot 的股票，取消勾選則包含『蓄勢待發』的標的")

# 3. Education/Tips in Sidebar
st.sidebar.info("""
**💡 VCP 掃描指南：**
1. **趨勢模板：** 程式已自動過濾非上升趨勢股票。
2. **收縮判定：** 尋找『極緊』且『量能乾涸』的標的。
3. **買入信號：** 當狀態轉為 `🔥 剛突破` 且成交量放大時。
""")

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
        
        # User Feedback: Better status messages
        st.info(f"🚀 正在掃描 {market_name} ... \n\n- 步驟 1: 計算 SCTR 動能排名\n- 步驟 2: 驗證趨勢模板 (Trend Template)\n- 步驟 3: 識別 VCP 波動收縮與量能乾涸")
        
        # Step 1: SCTR Calculation
        sctr_ranks, sctr_hist = calculate_sctr_ranks(tickers, lookback=20)
        
        results = []
        pb = st.progress(0)
        
        # Step 2 & 3: Deep Analysis
        for i, t in enumerate(tickers):
            res = check_vcp_advanced(t, sctr_ranks, sctr_hist, only_b, b_days)
            if res and res[3] >= min_sctr_val: 
                results.append(res)
            pb.progress((i + 1) / len(tickers))
        
        if results:
            df = pd.DataFrame(results, columns=[
                "代碼", "價格", "距離高點%", "SCTR排名", "收縮狀態", "量比", "狀態", "行業",
                "Pivot(樞軸)", "SL(ATR停損)", "Target(目標3R)"
            ])
            
            # Professional column ordering
            decision_order = [
                "代碼", "行業", "SCTR排名", "價格", 
                "Pivot(樞軸)", "SL(ATR停損)", "Target(目標3R)", 
                "量比", "收縮狀態", "狀態", "距離高點%"
            ]
            df = df[decision_order]
            df['圖表'] = df['代碼'].apply(make_link)
            df_sorted = df.sort_values("SCTR排名", ascending=False)
            
            st.success(f"🎉 掃描完成！共找到 {len(df)} 檔符合 VCP 頂級收縮且 SCTR 強勢的標的。")
            
            st.dataframe(
                df_sorted, 
                column_config={"圖表": st.column_config.LinkColumn("查看", display_text="Open Chart")}, 
                use_container_width=True,
                hide_index=True
            )
            
            # Bottom Guidance
            st.warning("⚠️ **風險提示：** 掃描結果僅供參考，請務必結合 K 線圖確認『量能爆發』才進行操作。止損位 (SL) 應嚴格執行。")
        else:
            st.warning("今日未篩選出符合 VCP 頂級收縮與 SCTR 強勢的標的。請耐心等待市場機會。")
    else:
        st.error("無法取得市場股票清單，請檢查網路連線。")
