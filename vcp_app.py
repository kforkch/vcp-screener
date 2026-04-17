import streamlit as st
import yfinance as yf
import pandas as pd
import pandas_ta as ta
import requests
import io
import numpy as np

# --- 頁面配置 ---
st.set_page_config(page_title="VCP Alpha Terminal", layout="wide")
st.title("🏹 VCP Alpha 全球終極交易終端")

# --- 1. 自動獲取成份股 (修正港/A 股適配) ---
@st.cache_data(ttl=86400)
def get_stock_list(market):
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        if market == "美股 (S&P 500)":
            url = 'https://en.wikipedia.org/wiki/List_of_S%26P_500_companies'
            table = pd.read_html(io.StringIO(requests.get(url, headers=headers).text))[0]
            return table['Symbol'].str.replace('.', '-', regex=False).tolist(), "^GSPC"
        
        elif market == "美股 (Nasdaq 100)":
            url = 'https://en.wikipedia.org/wiki/Nasdaq-100'
            tables = pd.read_html(io.StringIO(requests.get(url, headers=headers).text))
            for t in tables:
                if 'Ticker' in t.columns: return t['Ticker'].tolist(), "^IXIC"
        
        elif market == "港股 (恒生指數)":
            # 修正格式：確保是 0005.HK 這種 4 位數格式
            hsi_list = [
                "0001.HK", "0002.HK", "0003.HK", "0005.HK", "0011.HK", "0016.HK", "0388.HK", 
                "0700.HK", "0939.HK", "0941.HK", "1211.HK", "1299.HK", "1398.HK", "1810.HK", 
                "2318.HK", "3690.HK", "9618.HK", "9888.HK", "9988.HK", "9999.HK"
            ]
            return hsi_list, "^HSI"

        elif market == "中國 A 股 (龍頭)":
            as_list = [
                "600519.SS", "601318.SS", "600036.SS", "601012.SS", "000858.SZ", "300750.SZ", 
                "002594.SZ", "000333.SZ", "601888.SS", "002415.SZ", "600900.SS", "600030.SS"
            ]
            return as_list, "000300.SS"
            
    except Exception as e:
        st.error(f"名單獲取失敗: {e}")
        return [], None
    return [], None

# --- 2. SCTR 排名計算 (恢復你的核心算法) ---
def calculate_sctr_ranks(tickers):
    try:
        # 批量下載數據以提高效率
        raw_data = yf.download(tickers, period="1y", interval="1d", progress=False, auto_adjust=True)
        data = raw_data['Close'] if 'Close' in raw_data else raw_data
        
        sctr_data = []
        for ticker in tickers:
            try:
                series = data[ticker].dropna() if isinstance(data, pd.DataFrame) else data.dropna()
                if len(series) < 150: continue # 港/A股門檻微調
                
                sma200, sma50 = series.rolling(200).mean().iloc[-1], series.rolling(50).mean().iloc[-1]
                dist_200, dist_50 = (series.iloc[-1]/sma200-1)*100, (series.iloc[-1]/sma50-1)*100
                roc125, roc20 = (series.iloc[-1]/series.iloc[-125]-1)*100, (series.iloc[-1]/series.iloc[-20]-1)*100
                rsi = ta.rsi(series, length=14).iloc[-1]
                
                # 恢復你的權重算法
                raw = (dist_200*0.3 + roc125*0.3) + (dist_50*0.15 + roc20*0.15) + (rsi*0.1)
                sctr_data.append({'ticker': ticker, 'raw': raw})
            except: continue
            
        if not sctr_data: return {}
        df_sctr = pd.DataFrame(sctr_data)
        df_sctr['rank'] = df_sctr['raw'].rank(pct=True) * 99
