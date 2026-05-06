# main.py
import streamlit as st
import pandas as pd
from data_loader import get_stock_list, calculate_sctr_ranks, supabase

# ==================== 核心 yfinance 攔截注入 ====================
import yfinance as yf

def mock_download(tickers, *args, **kwargs):
    """
    [中台代理] 欺騙原 yfinance 套件。當 analyzer.py 呼叫 yf.download 時，
    此函數會攔截請求，並從 Supabase 資料庫抓取對應日 K 回傳，完全不用聯網到 Yahoo Finance。
    """
    # 確保 tickers 是單一字串
    ticker = tickers[0] if isinstance(tickers, list) else tickers
    try:
        # 從 Supabase 取出這檔股票所有的 K 線
        response = supabase.table("stock_klines")\
            .select("date, open, high, low, close, volume")\
            .eq("ticker", ticker)\
            .order("date", ascending=True)\
            .execute()
        
        data = response.data
        if not data:
            return pd.DataFrame() # 回傳空 DataFrame 避免 crash

        df = pd.DataFrame(data)
        df['date'] = pd.to_datetime(df['date'])
        df.set_index('date', inplace=True)
        # yfinance 回傳的 columns 是首字母大寫，保持一致
        df.rename(columns={
            "open": "Open", "high": "High", "low": "Low", "close": "Close", "volume": "Volume"
        }, inplace=True)
        return df
    except Exception as e:
        print(f"Mock Download 發生錯誤: {e}")
        return pd.DataFrame()

# 巧妙地用 mock 函數取代 yfinance 模組底層的 download
yf.download = mock_download
# ===============================================================

# 載入原分析器 (此時 analyzer.py 內部的 yf.download 已經被替換為 Supabase 讀取)
from analyzer import check_vcp_advanced

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

if st.sidebar.button("🚀 執行全球同步掃描"):
    res_tuple = get_stock_list(market_name)
    if res_tuple[0]:
        tickers, bench_code = res_tuple
        
        st.write(f"正在掃描 {market_name} ...")
        # 獲取最新與歷史 SCTR
        sctr_ranks, sctr_hist = calculate_sctr_ranks(tickers, lookback=20)
        results = []
        pb = st.progress(0)
        
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
                column_config={"圖表": st.column_config.LinkColumn("查看", display_text="Open")}, 
                use_container_width=True,
                hide_index=True
            )
            st.success(f"掃描完成！共找到 {len(df)} 檔符合 VCP 多段收縮且 SCTR 持續攀升的標的。")
        else:
            st.warning("今日未篩選出符合 VCP 多段收縮與 SCTR 持續成長的標的。")
    else:
        st.error("無法取得市場股票清單，請檢查網路連線。")
