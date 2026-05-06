# main.py
import streamlit as st
import pandas as pd
import yfinance as yf

# 1. 優先安全導入 data_loader（避免在最外層發生 Circular Import）
import data_loader
from data_loader import get_stock_list

# 從 data_loader 安全地取得已初始化的 supabase 用戶端
supabase = getattr(data_loader, "supabase", None)

# ==================== 核心 yfinance 攔截注入 ====================
def mock_download(tickers, *args, **kwargs):
    """
    [中台代理] 欺騙原 yfinance 套件。當 analyzer.py 呼叫 yf.download 時，
    此函數會攔截請求，並從 Supabase 資料庫抓取對應日 K 回傳，完全不用聯網到 Yahoo Finance。
    """
    if not supabase:
        print("⚠️ 數據中台未連線，Mock Download 降級回原本的 yfinance 下載...")
        # 降級使用原本 yfinance 備份的真實下載函數（防止無限遞迴，我們在下方備份）
        return REAL_YF_DOWNLOAD(tickers, *args, **kwargs)

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
            print(f"⚠️ 中台無 {ticker} K 線資料，降級調用 yfinance...")
            return REAL_YF_DOWNLOAD(tickers, *args, **kwargs)

        df = pd.DataFrame(data)
        df['date'] = pd.to_datetime(df['date'])
        df.set_index('date', inplace=True)
        # yfinance 回傳的 columns 是首字母大寫，保持一致
        df.rename(columns={
            "open": "Open", "high": "High", "low": "Low", "close": "Close", "volume": "Volume"
        }, inplace=True)
        return df
    except Exception as e:
        print(f"Mock Download 發生錯誤: {e}，自動降級調用 yfinance")
        return REAL_YF_DOWNLOAD(tickers, *args, **kwargs)

# 💡 安全防禦：先備份真實的 yfinance download，以便在 Supabase 沒資料時自動無感降級
REAL_YF_DOWNLOAD = yf.download
# 巧妙地用 mock 函數取代 yfinance 模組底層的 download
yf.download = mock_download
# ===============================================================

# 2. 載入原分析器 (此時 analyzer.py 內部的 yf.download 已經被替換為 Supabase 讀取)
# 修正引入路徑：將 calculate_sctr_ranks 從 analyzer 引入 (解決原 ImportError 核心痛點)
from analyzer import check_vcp_advanced, calculate_sctr_ranks

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
                hide_
