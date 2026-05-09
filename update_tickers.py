# update_tickers.py
import pandas as pd
import requests
import io
import os
import re
import sys

def clean_and_format_ticker(raw_val, market_type):
    """
    清洗並格式化代碼：
    1. 使用 Regex 去除所有非數字字元 (例如 'SSE: 600519' -> '600519')
    2. 根據市場類型補足位數並加上正確後綴
    """
    raw_str = str(raw_val).strip()
    # 只保留數字
    digits = re.sub(r'\D', '', raw_str)
    
    if not digits:
        return None

    if market_type == 'HK':
        # 港股：補齊 4 位數，加 .HK
        return f"{digits.zfill(4)}.HK"
    
    elif market_type == 'CN':
        # A股：補齊 6 位數，根據開頭決定 .SS 或 .SZ
        digits = digits.zfill(6)
        if digits.startswith('6') or digits.startswith('688') or digits.startswith('601'):
            return f"{digits}.SS"
        else:
            return f"{digits}.SZ"
    
    return None

def find_ticker_column(df):
    """模糊匹配最像股票代碼的欄位名稱 (不區分大小寫)"""
    cols = [str(c).lower() for c in df.columns]
    targets = ['ticker', 'code', 'symbol', 'ric', 'id', 'constituent']
    
    # 1. 尋找完全或部分匹配
    for target in targets:
        for idx, col in enumerate(cols):
            if target in col:
                return df.columns[idx]
    return None

def get_hsi_tickers():
    url = "https://en.wikipedia.org/wiki/Hang_Seng_Index"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    try:
        response = requests.get(url, headers=headers, timeout=15)
        tables = pd.read_html(io.StringIO(response.text))
        for table in tables:
            col = find_ticker_column(table)
            if col:
                results = [clean_and_format_ticker(t, 'HK') for t in table[col]]
                valid_results = [r for r in results if r]
                if valid_results:
                    return valid_results
    except Exception as e:
        print(f"⚠️ 抓取 HSI 失敗: {e}")
    
    # 降級備用名單 (恆生核心權重股)
    print("💡 啟用港股備用核心名單...")
    return ["0700.HK", "9988.HK", "3690.HK", "1299.HK", "0005.HK", "0939.HK", "1398.HK", "2318.HK"]

def get_csi300_tickers():
    url = "https://en.wikipedia.org/wiki/CSI_300_Index"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    try:
        response = requests.get(url, headers=headers, timeout=15)
        tables = pd.read_html(io.StringIO(response.text))
        for table in tables:
            col = find_ticker_column(table)
            if col:
                results = [clean_and_format_ticker(t, 'CN') for t in table[col]]
                valid_results = [r for r in results if r]
                if valid_results:
                    return valid_results
    except Exception as e:
        print(f"⚠️ 抓取 CSI300 失敗: {e}")
    
    # 降級備用名單 (滬深300核心龍頭股)
    print("💡 啟用 A 股備用核心名單...")
    return ["600519.SS", "601318.SS", "600036.SS", "000858.SZ", "000333.SZ", "300750.SZ", "601888.SS"]

def save_list_to_file(data_list, filepath):
    # 去重並排序
    cleaned_data = sorted(list(set([d for d in data_list if d])))
    if cleaned_data:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write("\n".join(cleaned_data))
        print(f"✅ 成功寫入 {filepath}: {len(cleaned_data)} 個代碼")
    else:
        # 防禦性保底：絕不允許寫入空檔案
        print(f"🚨 警告: 試圖寫入空的 {filepath}。寫入預設保底代碼。")
        default_codes = ["0700.HK"] if "hsi" in filepath else ["600519.SS"]
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write("\n".join(default_codes))

def main():
    try:
        os.makedirs('data', exist_ok=True)
        hsi = get_hsi_tickers()
        csi300 = get_csi300_tickers()
        
        save_list_to_file(hsi, 'data/hsi.txt')
        save_list_to_file(csi300, 'data/csi300.txt')
    except Exception as e:
        print(f"🚨 執行主程序時發生未預期錯誤: {e}")
        sys.exit(0)  # 即使出錯，也安全退出，避免阻斷 Actions 工作流

if __name__ == "__main__":
    main()
