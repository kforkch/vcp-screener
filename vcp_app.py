import streamlit as st
import yfinance as yf
import pandas as pd

st.set_page_config(layout="wide")
st.title("🏹 網路連線測試儀")

# 1. 測試列表 (強制寫死，避開抓取失敗)
test_tickers = ["AAPL", "NVDA", "MSFT", "TSLA", "GOOGL"]

if st.button("🚀 開始測試連線"):
    st.write("正在下載資料...")
    results = []
    
    for t in test_tickers:
        # 下載最近一個月的資料
        df = yf.download(t, period="1mo", progress=False)
        
        # 只要不是空的，就記錄下來
        if not df.empty:
            # 處理可能的多層級索引問題
            curr_price = df['Close'].iloc[-1]
            if isinstance(curr_price, pd.Series):
                curr_price = curr_price.iloc[0]
            
            results.append({"代碼": t, "最新價格": round(float(curr_price), 2)})
            st.write(f"✅ {t} 下載成功")
        else:
            st.write(f"❌ {t} 下載失敗")
            
    if results:
        st.success("測試完成！以下是下載到的資料：")
        st.dataframe(pd.DataFrame(results))
    else:
        st.error("掃描失敗，完全沒有抓到任何資料。")
