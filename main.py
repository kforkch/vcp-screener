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

# ==================== UI 樣式增強函數 ====================
def highlight_status(val):
    """高亮交易狀態"""
    if val == "🔥 剛突破":
        return 'color: #ff4b4b; font-weight: bold'
    # 💡【邏輯優化】：改用包含字串判斷，以相容「⚡蓄勢待發」與「⚡蓄勢待發 (VUD極度萎縮)」
    elif isinstance(val, str) and "蓄勢待發" in val:
        return 'color: #ffa500; font-weight: bold'
    elif val == "🚀 強勢續航":
        return 'color: #00fa9a; font-weight: bold'
    return ''

def highlight_contraction(val):
    """高亮收縮緊湊度"""
    if val == "🎯 極度緊湊":
        return 'color: #00fa9a; font-weight: bold'
    elif val == "✅ 緊湊":
        return 'color: #7df9ff'
    return ''

# ==================== 主掃描邏輯 ====================
if st.sidebar.button("🚀 執行全球同步掃描"):
    res_tuple = get_stock_list(market_name)
    if res_tuple and res_tuple[0]:
        tickers, bench_code = res_tuple
        
        with st.status(f"正在掃描 {market_name} (共 {len(tickers)} 檔)...", expanded=True) as status:
            st.write("獲取最新與歷史 SCTR 排名...")
            sctr_ranks, sctr_hist = calculate_sctr_ranks(tickers, lookback=20)
            results = []
            
            st.write("執行 VCP 波動收縮辨識與量價分析...")
            pb = st.progress(0)
            
            for i, t in enumerate(tickers):
                try:
                    res = check_vcp_advanced(t, sctr_ranks, sctr_hist, only_b, b_days)
                    if res and res[3] >= min_sctr_val: 
                        results.append(res)
                except Exception as e:
                    pass
                
                pb.progress((i + 1) / len(tickers))
            
            status.update(label="✅ 掃描與計算完成！", state="complete", expanded=False)

        if results:
            df = pd.DataFrame(results, columns=[
                "代碼", "價格", "距離高點%", "SCTR排名", "收縮狀態", "量比", "狀態", "行業",
                "Pivot(樞軸)", "SL(ATR停損)", "Target(目標3R)"
            ])
            
            decision_order = [
                "代碼", "行業", "SCTR排名", "價格", 
                "Pivot(樞軸)", "SL(ATR停損)", "Target(目標3R)", 
                "量比", "收縮狀態", "狀態", "距離高點%"
            ]
            df = df[decision_order]
            df['圖表'] = df['代碼'].apply(make_link)
            df_sorted = df.sort_values("SCTR排名", ascending=False)
            
            st.markdown("### 📊 市場總結儀表板")
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("總掃描標的", len(tickers))
            col2.metric("符合 VCP 數量", len(df_sorted))
            col3.metric("突破點位 (剛突破)", len(df_sorted[df_sorted['狀態'] == '🔥 剛突破']))
            col4.metric("極度緊湊數量", len(df_sorted[df_sorted['收縮狀態'] == '🎯 極度緊湊']))
            st.divider()
            
            st.markdown("### 🎯 潛力標的清單")
            
            format_dict = {
                "SCTR排名": "{:.1f}", 
                "價格": "{:.2f}", 
                "Pivot(樞軸)": "{:.2f}",
                "SL(ATR停損)": "{:.2f}",
                "Target(目標3R)": "{:.2f}",
                "量比": "{:.2f}x",
                "距離高點%": "{:.2f}%"
            }
            
            styled_df = df_sorted.style.map(highlight_status, subset=['狀態'])\
                                       .map(highlight_contraction, subset=['收縮狀態'])\
                                       .format(format_dict)
            
            st.dataframe(
                styled_df, 
                column_config={"圖表": st.column_config.LinkColumn("查看", display_text="Open")}, 
                use_container_width=True,
                hide_index=True,
                height=500
            )
            
            csv = df_sorted.drop(columns=['圖表']).to_csv(index=False, encoding='utf-8-sig')
            st.download_button(
                label="📥 匯出當日掃描結果 (CSV)",
                data=csv,
                file_name=f'vcp_scan_{market_name}.csv',
                mime='text/csv',
            )
            
            st.success(f"🎉 掃描完成！共找到 {len(df)} 檔符合條件的標的。")
        else:
            st.warning("今日未篩選出符合 VCP 多段收縮與 SCTR 持續成長的標的。")
    else:
        st.error("無法取得市場股票清單，請檢查網路連線或 data/ 資料夾下的代碼檔案。")
