import streamlit as st
import pandas as pd
import requests
import io
import yfinance as yf
import os

# 輔助函數：從 data/ 資料夾讀取 txt 檔案
def load_tickers_from_file(filename):
    file_path = os.path.join("data", filename)
    try:
        if os.path.exists(file_path):
            with open(file_path, 'r', encoding='utf-8') as f:
                # 讀取每一行並去除空白字元，忽略空行
                return [line.strip() for line in f if line.strip()]
        else:
            st.error(f"檔案不存在: {file_path}")
            return []
    except Exception as e:
        st.error(f"讀取 {filename} 時發生錯誤: {e}")
        return []

@st.cache_data(ttl=86400)
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
        st.error(f"獲取市場清單失敗: {e}")
        return [], None
    
    return [], None

@st.cache_data(ttl=86400)
def get_sector_cached(ticker):
    """取得股票行業板塊，並快取 24 小時"""
    try:
        ticker_obj = yf.Ticker(ticker)
        info = ticker_obj.info
        return info.get('sector', 'N/A')
    except:
        return 'N/A'
