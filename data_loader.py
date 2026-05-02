# data_loader.py - 升級版
import streamlit as st
import pandas as pd
import requests
import io
import os
import yfinance as yf

@st.cache_data(ttl=86400)
def get_stock_list(market):
    try:
        if market == "美股 (S&P 500)":
            url = 'https://en.wikipedia.org/wiki/List_of_S%26P_500_companies'
            table = pd.read_html(io.StringIO(requests.get(url, headers={"User-Agent": "Mozilla/5.0"}).text))[0]
            return table['Symbol'].str.replace('.', '-', regex=False).tolist(), "^GSPC"
        
        elif market == "美股 (Nasdaq 100)":
            url = 'https://en.wikipedia.org/wiki/Nasdaq-100'
            tables = pd.read_html(io.StringIO(requests.get(url, headers={"User-Agent": "Mozilla/5.0"}).text))
            for t in tables:
                if 'Ticker' in t.columns:
                    return t['Ticker'].tolist(), "^IXIC"
        
        elif market == "港股 (恒生指數)":
            return load_tickers_from_file("hsi.txt"), "^HSI"
        
        elif market == "中國 A 股 (滬深 300 龍頭)":
            return load_tickers_from_file("csi300.txt"), "000300.SS"
            
    except Exception as e:
        st.error(f"獲取清單失敗: {e}")
        return [], None
    
    return [], None


def load_tickers_from_file(filename):
    file_path = os.path.join("data", filename)
    try:
        if os.path.exists(file_path):
            with open(file_path, 'r', encoding='utf-8') as f:
                return [line.strip() for line in f if line.strip()]
        else:
            st.warning(f"檔案不存在: {file_path}")
            return []
    except Exception as e:
        st.error(f"讀取檔案錯誤: {e}")
        return []


@st.cache_data(ttl=86400)
def get_sector_cached(ticker):
    try:
        info = yf.Ticker(ticker).info
        return info.get('sector', info.get('industry', 'N/A'))
    except:
        return 'N/A'
