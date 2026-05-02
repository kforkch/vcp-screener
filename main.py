# main.py - 優化欄位顯示版
import streamlit as st
import pandas as pd
from data_loader import get_stock_list
from analyzer import calculate_sctr_ranks, check_vcp_advanced

st.set_page_config(page_title="VCP Alpha Terminal", layout="wide")
st.title("🏹 VCP Alpha 全球終極交易終端 v2.0")

st.sidebar.header("🎛️ 參數設定")
market_name = st.sidebar.selectbox("選擇市場", ["美股 (Nasdaq 100)", "美股 (S&P 500)", "港股 (恒生指數)", "中國 A 股 (滬深 300 龍頭)"])
min_sctr = st.sidebar.slider("最低 SCTR", 0, 99, 68)
b_days = st.sidebar.selectbox("突破檢測天數", [10, 20, 50], index=1)
only_breakout = st.sidebar.checkbox("僅顯示突破", value=False)
min_quality = st.sidebar.slider("最低品質分數", 50, 95, 55)

def make_link(ticker):
    t_str = str(ticker)
    if ".HK" in t_str:
        code = t_str.replace('.HK', '').lstrip('0')
        return f"https://www.tradingview.com/chart/?symbol=HKEX:{code}"
    elif ".SS" in t_str or ".SZ" in t_str:
        code = t_str.split('.')[0]
        prefix = "SSE" if ".SS" in t_str else "SZSE"
        return f"https://www.tradingview.com/chart/?symbol={prefix}:{code}"
    else:
        return f"https://www.tradingview.com/chart/?symbol={t_str.replace('.', '-')}"


if st.sidebar.button("🚀 開始掃描", type="primary"):
    with st.spinner(f"正在掃描 {market_name} ..."):
        tickers, _ = get_stock_list(market_name)
        if not tickers:
            st.error("無法取得股票清單")
            st.stop()
        
        sctr_map, sctr_hist = calculate_sctr_ranks(tickers)
        results = []
        pb = st.progress(0)
        
        for i, t in enumerate(tickers):
            res = check_vcp_advanced(t, sctr_map, sctr_hist, only_breakout, b_days)
            if res and res[3] >= min_sctr and res[-1] >= min_quality:
                results.append(res)
            pb.progress((i + 1) / len(tickers))
        
        if results:
            df = pd.DataFrame(results, columns=[
                "代碼", "價格", "距離高點%", "SCTR", "收縮狀態", "量比",
                "狀態", "行業", "Pivot", "SL", "Target", "品質分數"
            ])
            
            # === 優化欄位順序（最重要的放前面）===
            desired_order = [
                "代碼", "圖表", "狀態", "SCTR", "品質分數", "價格", 
                "距離高點%", "收縮狀態", "量比", "行業",
                "Pivot", "SL", "Target"
            ]
            
            df['圖表'] = df['代碼'].apply(make_link)
            
            # 重新排列欄位
            df = df[[col for col in desired_order if col in df.columns]]
            
            # 排序
            df = df.sort_values(["品質分數", "SCTR"], ascending=False)
            
            st.success(f"✅ 找到 {len(df)} 檔符合條件的標的")
            
            # 美化顯示
            st.dataframe(
                df,
                column_config={
                    "圖表": st.column_config.LinkColumn("📈 圖表", display_text="開啟 TradingView"),
                    "SCTR": st.column_config.NumberColumn(format="%.1f"),
                    "品質分數": st.column_config.NumberColumn(format="%d"),
                    "價格": st.column_config.NumberColumn(format="%.2f"),
                    "距離高點%": st.column_config.NumberColumn(format="%.1f%%"),
                    "量比": st.column_config.NumberColumn(format="%.2f"),
                    "Pivot": st.column_config.NumberColumn(format="%.2f"),
                    "SL": st.column_config.NumberColumn(format="%.2f"),
                    "Target": st.column_config.NumberColumn(format="%.2f"),
                },
                use_container_width=True,
                hide_index=True
            )
            
            # 額外統計
            st.info(f"最高品質分數：{df['品質分數'].max()} | 平均 SCTR：{df['SCTR'].mean():.1f}")
            
        else:
            st.warning("本次掃描未找到符合條件的標的，請嘗試放寬 SCTR 或品質分數門檻。")
