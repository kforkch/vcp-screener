import streamlit as st
import pandas as pd
import requests
import io
import yfinance as yf

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
                if 'Symbol' in t.columns: return t['Symbol'].tolist(), "^IXIC"
        
        elif market == "港股 (恒生指數)":
            hsi_list = [
                "0001.HK", "0002.HK", "0003.HK", "0005.HK", "0006.HK", "0011.HK", "0012.HK", "0016.HK", 
                "0017.HK", "0020.HK", "0027.HK", "0066.HK", "0101.HK", "0175.HK", "0241.HK", "0267.HK", 
                "0288.HK", "0291.HK", "0316.HK", "0322.HK", "0386.HK", "0388.HK", "0669.HK", "0688.HK", 
                "0700.HK", "0762.HK", "0823.HK", "0857.HK", "0868.HK", "0881.HK", "0883.HK", "0939.HK", 
                "0941.HK", "0960.HK", "0968.HK", "0981.HK", "0992.HK", "1038.HK", "1044.HK", "1088.HK", 
                "1093.HK", "1109.HK", "1113.HK", "1177.HK", "1211.HK", "1299.HK", "1313.HK", "1378.HK", 
                "1398.HK", "1810.HK", "1876.HK", "1928.HK", "1929.HK", "2020.HK", "2269.HK", "2313.HK", 
                "2318.HK", "2319.HK", "2331.HK", "2382.HK", "2388.HK", "2628.HK", "2688.HK", "3690.HK", 
                "3692.HK", "3968.HK", "3988.HK", "6098.HK", "6608.HK", "6618.HK", "6690.HK", "6862.HK", 
                "9618.HK", "9633.HK", "9868.HK", "9888.HK", "9922.HK", "9961.HK", "9988.HK", "9992.HK", "9999.HK"
            ]
            return hsi_list, "^HSI"

        elif market == "中國 A 股 (滬深 300 龍頭)":
            as_list = [
                "600519.SS", "601318.SS", "600036.SS", "601012.SS", "600276.SS", "601166.SS", "600900.SS", "600030.SS",
                "601888.SS", "600809.SS", "601398.SS", "601288.SS", "601988.SS", "601628.SS", "601601.SS", "600019.SS",
                "600048.SS", "601919.SS", "600104.SS", "601088.SS", "600309.SS", "600585.SS", "603288.SS", "603501.SS",
                "600703.SS", "600406.SS", "601857.SS", "601899.SS", "600111.SS", "600016.SS", "600690.SS", "600887.SS",
                "601668.SS", "601138.SS", "601328.SS", "601006.SS", "601998.SS", "600000.SS", "600009.SS", "600150.SS",
                "600196.SS", "600346.SS", "600547.SS", "600741.SS", "600760.SS", "600837.SS", "601766.SS", "601818.SS",
                "601939.SS", "601985.SS", "000858.SZ", "000333.SZ", "002415.SZ", "000651.SZ", "002475.SZ", "300750.SZ",
                "300059.SZ", "000725.SZ", "002594.SZ", "002142.SZ", "000001.SZ", "002352.SZ", "002304.SZ", "002714.SZ",
                "300015.SZ", "300760.SZ", "002460.SZ", "002466.SZ", "000768.SZ", "002027.SZ", "000661.SZ", "000792.SZ",
                "000895.SZ", "002001.SZ", "002007.SZ", "002241.SZ", "002271.SZ", "002371.SZ", "002410.SZ", "002459.SZ",
                "002493.SZ", "002555.SZ", "002812.SZ", "300122.SZ", "300124.SZ", "300142.SZ", "300274.SZ", "300347.SZ",
                "300408.SZ", "300433.SZ", "300498.SZ", "300529.SZ", "300896.SZ", "000002.SZ", "000063.SZ", "000100.SZ",
                "000425.SZ", "000538.SZ", "000568.SZ", "001979.SZ"
            ]
            return as_list, "000300.SS"
            
    except Exception as e:
        return [], None
    return [], None

@st.cache_data(ttl=86400)
def get_sector_cached(ticker):
    """取得股票行業板塊，並快取 24 小時"""
    try:
        ticker_obj = yf.Ticker(ticker)
        # 獲取 info 資料
        info = ticker_obj.info
        return info.get('sector', 'N/A')
    except:
        return 'N/A'
