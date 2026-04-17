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
        # --- 修正：只有非港股才將點換成橫線 ---
        if ".HK" in ticker:
            formatted_ticker = ticker  # 港股保持 0700.HK
        else:
            formatted_ticker = ticker.replace('.', '-')
        df = yf.download(formatted_ticker, period="1y", progress=False, auto_adjust=True, threads=False)
        
        if df.empty or len(df) < 100:
            return None
        
        # 處理資料格式
        if isinstance(df.columns, pd.MultiIndex):
            close_prices = df['Close'][formatted_ticker]
        else:
            close_prices = df['Close']

        close_prices = close_prices.astype(float)
        curr_price = float(close_prices.iloc[-1])

        # --- 安全計算指標 (關鍵修正) ---
        sma50_series = ta.sma(close_prices, 50)
        sma150_series = ta.sma(close_prices, 150)
        sma200_series = ta.sma(close_prices, 200)

        # 檢查指標是否存在，且最後一筆不是空值
        if (sma50_series is None or sma150_series is None or sma200_series is None):
            return None
            
        sma50 = sma50_series.iloc[-1]
        sma150 = sma150_series.iloc[-1]
        sma200 = sma200_series.iloc[-1]

        # 如果任何一個均線是 NaN，代表數據不足以支持計算，跳過
        if pd.isna(sma50) or pd.isna(sma150) or pd.isna(sma200):
            return None

        low52 = float(close_prices.min())
        high52 = float(close_prices.max())

        # 6 個條件
        conditions = [
            curr_price > sma150 and curr_price > sma200,
            sma150 > sma200,
            sma50 > sma150 and sma50 > sma200,
            curr_price > sma50,
            curr_price >= (low52 * 1.25),
            curr_price >= (high52 * 0.75)
        ]
        
        score = sum(conditions)
        dist_high = round((1 - curr_price/high52) * 100, 2)
        
        # --- 修改門檻為 6 分滿分 ---
        if score == 6:
            status = "🚀 強勢領頭羊"
            # 回傳 5 個值，確保與你的 DataFrame 欄位對齊
            return [ticker, round(curr_price, 2), dist_high, f"{score}/6", status]
        
        # 低於 6 分的標的全部跳過
        return None

    except Exception as e:
        # 這裡的錯誤訊息會幫你抓出具體哪隻股票、哪個步驟出問題
        st.error(f"解析 {ticker} 時發生錯誤: {e}")
        return None
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
    st.write(f"掃描結束，結果清單長度為: {len(results)}")
    
if results:
        # 1. 建立 DataFrame 並進行數值排序
        df_final = pd.DataFrame(results, columns=["代碼", "現價", "距離高點數值", "評分", "狀態"])
        df_final = df_final.sort_values(by=["評分", "距離高點數值"], ascending=[False, True])
        
        # 2. 格式化顯示：數值轉百分比
        df_final["距離 52 週高點 %"] = df_final["距離高點數值"].apply(lambda x: f"{x}%")
        
if results:
        # 1. 建立 DataFrame 並進行數值排序
        df_final = pd.DataFrame(results, columns=["代碼", "現價", "距離高點數值", "評分", "狀態"])
        df_final = df_final.sort_values(by=["評分", "距離高點數值"], ascending=[False, True])
        
        # 2. 格式化顯示：數值轉百分比
        df_final["距離 52 週高點 %"] = df_final["距離高點數值"].apply(lambda x: f"{x}%")
        
        # 3. 生成 TradingView 連結 (優化港股跳轉邏輯)
        def get_tv_url(ticker):
            if ".HK" in ticker:
                # 港股加上 HKG: 前綴，確保直接定位到港交所標的
                code = ticker.replace('.HK', '')
                return f"https://www.tradingview.com/chart/?symbol=HKG:{code}"
            else:
                # 美股點號轉橫線 (如 BRK.B -> BRK-B)
                return f"https://www.tradingview.com/chart/?symbol={ticker.replace('.', '-')}"

        df_final['查看圖表'] = df_final['代碼'].apply(get_tv_url)
        
        # 4. 定義最終顯示的欄位與順序
        display_cols = ["代碼", "現價", "距離 52 週高點 %", "評分", "狀態", "查看圖表"]
        
        # 5. 渲染表格
        st.dataframe(
            df_final[display_cols], 
            column_config={
                "查看圖表": st.column_config.LinkColumn("點擊打開圖表", display_text="Open Chart")
            },
            use_container_width=True
        )
        
        st.success(f"篩選完畢！找到 {len(results)} 隻符合 6/6 趨勢模板的強勢股。")
        st.balloons()
        
    else:
        st.warning("⚠️ 目前沒有股票完全符合『 6/6 滿分』趨勢模板條件。")

# --- 底部提示 ---
st.divider()
st.caption("註：S&P 500 掃描可能需要 2-3 分鐘，請耐心等候進度條完成。")
