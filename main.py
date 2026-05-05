# main.py
import streamlit as st
import pandas as pd
import yfinance as yf
from data_loader import get_stock_list
from analyzer import calculate_sctr_ranks, check_vcp_advanced_preloaded

st.set_page_config(page_title="VCP Alpha Terminal", layout="wide")
st.title("🏹 VCP Alpha 全球終極交易終端")

st.sidebar.header("🎛️ 系統參數")
market_name = st.sidebar.selectbox("選擇市場", ["美股 (Nasdaq 100)", "美股 (S&P 500)", "港股 (恒生指數)", "中國 A 股 (滬深 300 龍頭)"])
min_sctr_val = st.sidebar.slider("最低 SCTR 排名", 0.0, 99.9, 80.0)
b_days = st.sidebar.selectbox("突破檢測天數", [10, 20, 50], index=1)
only_b = st.sidebar.checkbox("僅看突破", value=False)

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

# 實戰精髓：利用 Streamlit Cache 機制在本地記憶體中快取批次下載的數據
# ttl=14400 代表 4 小時之內，同一個市場的數據不需要重疊下載，滑動 Slider 時瞬間反應！
@st.cache_data(show_spinner=False, ttl=14400)
def fetch_market_data_cached(tickers):
    """
    一次性整批下載所有標的數據，對 Yahoo Finance 伺服器只發送一次請求，徹底根治 Rate Limit！
    """
    try:
        # 下載歷史數據
        df_raw = yf.download(tickers, period="1y", group_by="ticker", progress=False, auto_adjust=True)
        return df_raw
    except Exception as e:
        return None

if st.sidebar.button("開始掃描"):
    tickers, bench_code = get_stock_list(market_name)
    if tickers:
        st.info(f"正在載入 {market_name} 數據 (共 {len(tickers)} 檔)... 首次載入約需 10-15 秒，隨後操作將瞬間完成 🛡️")
        
        # 1. 記憶體快取批次下載
        with st.spinner("正在與 Yahoo Finance 同步批次數據..."):
            full_raw = fetch_market_data_cached(tickers)
            
        if full_raw is None or full_raw.empty:
            st.error("數據同步失敗，請稍後再試。")
            st.stop()
            
        # 整理下載後的 Close 數據框（計算 SCTR 使用）
        close_df = pd.DataFrame()
        for t in tickers:
            try:
                # 兼容 Multi-Index 結構
                if isinstance(full_raw.columns, pd.MultiIndex):
                    if t in full_raw.columns.levels[0]:
                        close_df[t] = full_raw[t]['Close']
                else:
                    if t in full_raw.columns:
                        close_df[t] = full_raw[t]
            except:
                continue

        st.write("正在計算全球市場 SCTR 強度排名與 VCP 動態波幅...")
        sctr_ranks, sctr_hist = calculate_sctr_ranks(tickers, lookback=20, pre_downloaded_data=close_df)
        
        results = []
        pb = st.progress(0)
        
        # 2. 本地記憶體極速掃描，無網絡延遲
        for i, t in enumerate(tickers):
            try:
                # 提取個股 DataFrame
                if isinstance(full_raw.columns, pd.MultiIndex):
                    if t in full_raw.columns.levels[0]:
                        ticker_df = full_raw[t]
                        res = check_vcp_advanced_preloaded(t, ticker_df, sctr_ranks, sctr_hist, only_b, b_days)
                        if res and res[3] >= min_sctr_val: 
                            results.append(res)
                else:
                    # 如果只有單個 Ticker 數據
                    ticker_df = full_raw
                    res = check_vcp_advanced_preloaded(t, ticker_df, sctr_ranks, sctr_hist, only_b, b_days)
                    if res and res[3] >= min_sctr_val: 
                        results.append(res)
            except Exception as e:
                pass
            pb.progress((i + 1) / len(tickers))

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
            
            st.dataframe(
                df_sorted, 
                column_config={"圖表": st.column_config.LinkColumn("TradingView 圖表", display_text="🔍 查看圖表")},
                hide_index=True
            )
            st.success(f"掃描完畢！篩選出符合馬克 VCP 標準股票共 {len(df_sorted)} 檔！")
        else:
            st.info("當前篩選條件下，未找到符合 VCP 標準的標的。建議可適度降低最低 SCTR 限制。")
