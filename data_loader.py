# data_loader.py
import streamlit as st
import pandas as pd
import requests
import io
import yfinance as yf
import os

# Helper: Load tickers from local text files
def load_tickers_from_file(filename):
    file_path = os.path.join("data", filename)
    try:
        if os.path.exists(file_path):
            with open(file_path, 'r', encoding='utf-8') as f:
                return [line.strip() for line in f if line.strip()]
        else:
            st.error(f"File not found: {file_path}")
            return []
    except Exception as e:
        st.error(f"Error reading {filename}: {e}")
        return []

@st.cache_data(ttl=86400)
def get_stock_list(market):
    """
    Fetch list of tickers based on the selected market.
    Integration with Wikipedia for US markets and local files for Asia markets.
    """
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        # US Markets
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
        
        # Asia Markets (Loading from /data directory)
        elif market == "港股 (恒生指數)":
            return load_tickers_from_file("hsi.txt"), "^HSI"
        
        elif market == "中國 A 股 (滬深 300 龍頭)":
            return load_tickers_from_file("csi300.txt"), "000300.SS"
            
    except Exception as e:
        st.error(f"Failed to fetch market list: {e}")
        return [], None
    
    return [], None

@st.cache_data(ttl=86400)
def get_sector_cached(ticker):
    """
    Fetch stock sector using yfinance and cache for 24 hours.
    Crucial for O'Neil's 'Industry Group' analysis.
    """
    try:
        ticker_obj = yf.Ticker(ticker)
        info = ticker_obj.info
        return info.get('sector', 'N/A')
    except:
        return 'N/A'
