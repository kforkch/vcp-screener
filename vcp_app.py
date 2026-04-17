import streamlit as st
import yfinance as yf
import pandas as pd
import pandas_ta as ta
import requests
import io

# --- 頁面配置 ---
st.set_page_config(page_title="J Law VCP Ultimate Screener", layout="wide")
st.title("🏹 跨市場自動篩選系統 (美股/港股)")

# --- 1. 自動獲取成份股函數 (加入 S&P 500) ---
@st.cache_data(ttl=86400)
def get_stock_list(market):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    try:
        if market == "美股 (S&P 500)":
            url = 'https://en.wikipedia.org/wiki/List_of_S%26P_500_companies'
            response = requests.get(url, headers=headers)
            # 使用 io.StringIO 包裹 response.text，明確告知這是字串流
            table = pd.read_html(io.StringIO(response.text))[0]
            return table['Symbol'].str.replace('.', '-', regex=False).tolist()
            
        elif market == "美股 (Nasdaq 100)":
            url = 'https://en.wikipedia.org/wiki/Nasdaq-100'
            response = requests.get(url, headers=headers)
            # 讀取該頁面所有表格
            tables = pd.read_html(io.StringIO(response.text))
            
            # 尋找含有 'Ticker' 或 'Symbol' 字眼的表格
            df_nasdaq = None
            for t in tables:
                if 'Ticker' in t.columns:
                    df_nasdaq = t
                    ticker_col = 'Ticker'
                    break
                elif 'Symbol' in t.columns:
                    df_nasdaq = t
                    ticker_col = 'Symbol'
                    break
            
            if df_nasdaq is not None:
                return df_nasdaq[ticker_col].tolist()
            else:
                # 備案：如果 Wikipedia 格式大改，回傳幾個核心股確保程式不死掉
                return ["AAPL", "MSFT", "GOOGL", "AMZN", "META", "TSLA", "NVDA"]
            
        elif market == "港股 (恒生指數)":
            return ["0700.HK", "9988.HK", "3690.HK", "1211.HK", "1810.HK", "2318.HK", "0005.HK", "0388.HK", "9618.HK", "2269.HK"]
            
    except Exception as e:
        st.error(f"獲取名單失敗: {e}")
        return []
    return []

# --- 2. 核心篩選邏輯 (VCP Trend Template) ---
def check_vcp_trend(ticker):
    try:
        formatted_ticker = ticker.replace('.', '-')
        # 加上 auto_adjust=True 確保除權息後的價格精確
        df = yf.download(formatted_ticker, period="1y", progress=False, auto_adjust=True)
        
        if df.empty or len(df) < 200: return None
        
        # 提取收盤價
        close_prices = df['Close']
        curr_price = float(close_prices.iloc[-1])
        
        # 計算均線與指標
        sma50 = ta.sma(close_prices, 50).iloc[-1]
        sma150 = ta.sma(close_prices, 150).iloc[-1]
        sma200 = ta.sma(close_prices, 200).iloc[-1]
        low52 = float(close_prices.min())
        high52 = float(close_prices.max())

        # Minervini 的 6 個關鍵條件
        conditions = [
            curr_price > sma150 and curr_price > sma200,  # 1. 股價在長均線上
            sma150 > sma200,                             # 2. 均線多頭排列
            sma50 > sma150 and sma50 > sma200,           # 3. 中期均線在長期均線上
            curr_price > sma50,                          # 4. 股價在短均線上 (短期強勢)
            curr_price >= (low52 * 1.25),                # 5. 距離底部已反彈 25%
            curr_price >= (high52 * 0.75)                # 6. 距離高點在 25% 以內 (高點整理)
        ]
        
        score = sum(conditions) # 計算符合總數
        dist_high = (1 - curr_price/high52) * 100
        
        # --- 分類邏輯 ---
        if score == 6:
            status = "🚀 強勢領頭羊"
        elif score >= 3:
            status = "👀 觀察名單"
        else:
            return None # 評分低於 3 分的不顯示，保持清單乾淨

        return [ticker, round(curr_price, 2), f"{round(dist_high, 2)}%", f"{score}/6", status]

    except Exception:
        return None

# --- 3. 側邊欄控制與執行 ---
st.sidebar.header("篩選參數")
market_choice = st.sidebar.selectbox("選擇市場範疇", ["美股 (S&P 500)", "美股 (Nasdaq 100)", "港股 (恒生指數)", "手動輸入"])

if market_choice == "手動輸入":
    tickers = st.sidebar.text_input("輸入代碼 (逗號隔開)", "NVDA,PLTR").split(",")
else:
    tickers = get_stock_list(market_choice)

if st.sidebar.button("🚀 開始全自動掃描"):
    st.subheader(f"📊 {market_choice} 篩選結果 (共計 {len(tickers)} 隻股票)")
    results = []
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    for i, t in enumerate(tickers):
        status_text.text(f"正在分析第 {i+1}/{len(tickers)} 隻: {t}")
        res = check_vcp_trend(t)
        if res:
            results.append(res)
        progress_bar.progress((i + 1) / len(tickers))
    
    status_text.text("掃描完成！")
    
    if results:
        # 修改這裡的 columns 以對應 check_vcp_trend 的回傳值
        df_final = pd.DataFrame(results, columns=["代碼", "現價", "距離 52 週高點 %", "評分", "狀態"])
        
        # 關鍵：按評分由高到低排序，同分則按距離高點由近到遠排序
        df_final = df_final.sort_values(by=["評分", "距離 52 週高點 %"], ascending=[False, True])
        
        df_final['查看圖表'] = df_final['代碼'].apply(lambda x: f"https://www.tradingview.com/chart/?symbol={x.replace('.HK', '').replace('.', '-')}")
        
        st.dataframe(
            df_final, 
            column_config={"查看圖表": st.column_config.Link_Column("點擊打開 TradingView")},
            use_container_width=True
        )
        st.balloons()
    else:
        st.warning("目前沒有股票符合趨勢條件（甚至未達觀察門檻 3/6）。")

# --- 底部提示 ---
st.divider()
st.caption("註：S&P 500 掃描可能需要 2-3 分鐘，請耐心等候進度條完成。")
