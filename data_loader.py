# data_loader.py
import pandas as pd
import requests
import io
import yfinance as yf
import os

# 核心安全機制：檢測當前是不是在 Streamlit 網頁端環境下執行
try:
    import streamlit as st
    # 測試 Streamlit 執行上下文是否可用
    is_streamlit_env = hasattr(st, "runtime") and st.runtime.exists()
except ImportError:
    is_streamlit_env = False

# 自訂環境安全快取裝飾器
def safe_cache(ttl=86400):
    def decorator(func):
        if is_streamlit_env:
            try:
                return st.cache_data(ttl=ttl)(func)
            except Exception:
                return func
        return func
    return decorator

# 輔助函數：從 data/ 資料夾讀取 txt 檔案
def load_tickers_from_file(filename):
    file_path = os.path.join("data", filename)
    try:
        if os.path.exists(file_path):
            with open(file_path, 'r', encoding='utf-8') as f:
                return [line.strip() for line in f if line.strip()]
        else:
            msg = f"檔案不存在: {file_path}"
            if is_streamlit_env:
                st.error(msg)
            else:
                print(f"⚠️ {msg}")
            return []
    except Exception as e:
        msg = f"讀取 {filename} 時發生錯誤: {e}"
        if is_streamlit_env:
            st.error(msg)
        else:
            print(f"❌ {msg}")
        return []

@safe_cache(ttl=86400)
def get_stock_list(market):
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        # 美股邏輯保持不變 (從網頁抓取)
        if market == "美股 (S&P 500)":
            url = 'https://en.wikipedia.org/wiki/List_of_S%26P_500_companies'
            table = pd.read_html(io.StringIO(requests.get(url, headers=headers).text))[0]
            return table['Symbol'].str.replace('.', '-', regex=False).tolist(), "^GSPC"
        
        elif market == "美股 (Nasdaq 100)":
            url = 'https://en.wikipedia.org/wiki/Nasdaq-100'
            tables = pd.read_html(io.StringIO(requests.get(url, headers=headers).text))
            for t in tables:
                if 'Ticker' in t.columns: return t['Ticker'].tolist(), "^IXIC"
                if 'Symbol' in t.columns: return t['Symbol'].tolist(), "^IXIC"
        
        # 港股邏輯：從 data/hsi.txt 讀取
        elif market == "港股 (恒生指數)":
            return load_tickers_from_file("hsi.txt"), "^HSI"

        # 中國 A 股邏輯：從 data/csi300.txt 讀取
        elif market == "中國 A 股 (滬深 300 龍頭)":
            return load_tickers_from_file("csi300.txt"), "000300.SS"
            
    except Exception as e:
        msg = f"獲取市場清單失敗: {e}"
        if is_streamlit_env:
            st.error(msg)
        else:
            print(f"❌ {msg}")
        return [], None
    
    return [], None

@safe_cache(ttl=86400)
def get_sector_cached(ticker):
    """取得股票行業板塊，並快取 24 小時"""
    try:
        ticker_obj = yf.Ticker(ticker)
        info = ticker_obj.info
        return info.get('sector', 'N/A')
    except:
        return 'N/A'
