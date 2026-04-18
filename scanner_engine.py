import yfinance as yf
import pandas as pd
import streamlit as st

@st.cache_data(ttl=3600)
def run_scanner(tickers):
    """
    接收代碼列表，回傳包含技術指標的 DataFrame
    """
    data = yf.download(tickers, period="250d", group_by='ticker', progress=False)
    
    results = []
    for ticker in tickers:
        try:
            # 取得單一股票數據
            df = data[ticker]
            if df.empty: continue
            
            # 計算簡單指標 (例如: MA200)
            ma200 = df['Close'].rolling(window=200).mean().iloc[-1]
            current_price = df['Close'].iloc[-1]
            
            # 判斷是否站在 MA200 之上 (這是非常常見的風險管理指標)
            is_bullish = current_price > ma200
            
            results.append({
                "Ticker": ticker,
                "Price": round(current_price, 2),
                "MA200": round(ma200, 2),
                "Status": "Bullish" if is_bullish else "Bearish"
            })
        except:
            continue
            
    return pd.DataFrame(results)
