import pandas as pd
import requests
import io
import os
import re

def clean_and_format_ticker(raw_val, market_type):
    """
    清洗並格式化代碼：
    1. 使用 Regex 去除所有非數字字元 (例如 'SSE: 600519' -> '600519')
    2. 根據市場類型補足位數並加上正確後綴
    """
    raw_str = str(raw_val)
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
        if digits.startswith('6'):
            return f"{digits}.SS"
        else:
            return f"{digits}.SZ"
    
    return None

def get_hsi_tickers():
    url = "https://en.wikipedia.org/wiki/Hang_Seng_Index"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        response = requests.get(url, headers=headers)
        tables = pd.read_html(io.StringIO(response.text))
        for table in tables:
            # 嘗試找 'Ticker' 或 'Code' 欄位
            target_col = 'Ticker' if 'Ticker' in table.columns else 'Code'
            if target_col in table.columns:
                results = [clean_and_format_ticker(t, 'HK') for t in table[target_col]]
                return [r for r in results if r]
    except Exception as e:
        print(f"Error fetching HSI: {e}")
    return []

def get_csi300_tickers():
    url = "https://en.wikipedia.org/wiki/CSI_300_Index"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        response = requests.get(url, headers=headers)
        tables = pd.read_html(io.StringIO(response.text))
        for table in tables:
            target_col = 'Ticker' if 'Ticker' in table.columns else 'Code'
            if target_col in table.columns:
                results = [clean_and_format_ticker(t, 'CN') for t in table[target_col]]
                return [r for r in results if r]
    except Exception as e:
        print(f"Error fetching CSI300: {e}")
    return []

def save_list_to_file(data_list, filepath):
    # 去除重複值並排序
    cleaned_data = sorted(list(set([d for d in data_list if d])))
    if cleaned_data:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write("\n".join(cleaned_data))
        print(f"成功更新 {filepath}: {len(cleaned_data)} 個代碼")

def main():
    os.makedirs('data', exist_ok=True)
    hsi = get_hsi_tickers()
    csi300 = get_csi300_tickers()
    
    save_list_to_file(hsi, 'data/hsi.txt')
    save_list_to_file(csi300, 'data/csi300.txt')

if __name__ == "__main__":
    main()
