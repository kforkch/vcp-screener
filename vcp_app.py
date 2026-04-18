import streamlit as st
import yfinance as yf
import pandas as pd

st.set_page_config(layout="wide")
st.title("🏹 VCP Alpha 測試模式")

# 簡化版的獲取列表
def get_test_list():
    return ["AAPL", "NVDA", "MSFT", "GOOGL", "TSLA"]

if st.sidebar.button("🚀 開始測試掃描"):
    tickers = get_test_list()
    results = []
    
    with st.spinner("正在下載資料..."):
        for t in tickers:
            df = yf.download(t, period="1mo", progress=False)
            if not df.empty:
                curr_p = float(df['Close'].iloc[-1])
                results.append({"代碼": t, "價格": round(curr_p, 2), "狀態": "資料下載成功"})
                
    if results:
        st.success("成功掃描！")
        st.dataframe(pd.DataFrame(results))
    else:
        st.error("掃描失敗，請檢查網路連線")
