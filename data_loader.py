import streamlit as st
import yfinance as yf
import os

# 1. 美股保持原先的「靜態定義」
US_STOCKS_UNIVERSE = {
    "美股 (S&P 500)": ["AAPL", "MSFT", "AMZN", "GOOGL", "NVDA", "META", "TSLA", "V", "JPM", "PG"]
}

# 輔助函數：讀取 data 資料夾內的 txt
def load_tickers_from_file(filename):
    file_path = os.path.join("data", filename)
    if not os.path.exists(file_path):
        st.error(f"找不到檔案: {file_path}，請確保 data 資料夾內有此檔案")
        return []
    with open(file_path, "r", encoding="utf-8") as f:
        # 去除每行的空白與換行符號
        return [line.strip() for line in f if line.strip()]

@st.cache_data(ttl=86400)
def get_stock_list(market):
    # --- 情況 A: 美股 (直接從上面的字典讀取) ---
    if market in US_STOCKS_UNIVERSE:
        return US_STOCKS_UNIVERSE[market], "^GSPC"
    
    # --- 情況 B: 港股與 A 股 (從 data/ 資料夾讀取) ---
    file_map = {
        "港股 (恒生指數)": ("hsi.txt", "^HSI"),
        "中國 A 股 (滬深 300 龍頭)": ("csi300.txt", "000300.SS")
    }
    
    if market in file_map:
        filename, index_ticker = file_map[market]
        return load_tickers_from_file(filename), index_ticker
        
    return [], None

@st.cache_data(ttl=86400)
def get_sector_cached(ticker):
    try:
        ticker_obj = yf.Ticker(ticker)
        # 這裡增加一個小優化，減少對 API 的無效請求
        info = ticker_obj.info
        return info.get('sector', 'N/A')
    except:
        return 'N/A'
