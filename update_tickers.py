import pandas as pd
import requests
import io
import os

def get_hsi_tickers():
    """從 Wikipedia 抓取恒生指數成分股"""
    url = "https://en.wikipedia.org/wiki/Hang_Seng_Index"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        response = requests.get(url, headers=headers)
        tables = pd.read_html(io.StringIO(response.text))
        # 尋找包含成分股的表格 (通常是包含 'Ticker' 或 'Code' 的表格)
        for table in tables:
            if 'Ticker' in table.columns:
                # 確保格式為 0001.HK
                tickers = table['Ticker'].astype(str).str.zfill(4) + ".HK"
                return tickers.tolist()
    except Exception as e:
        print(f"Error fetching HSI: {e}")
    return []

def get_csi300_tickers():
    """從 Wikipedia 抓取滬深 300 成分股"""
    url = "https://en.wikipedia.org/wiki/CSI_300_Index"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        response = requests.get(url, headers=headers)
        tables = pd.read_html(io.StringIO(response.text))
        for table in tables:
            if 'Ticker' in table.columns:
                # 滬深 300 代碼格式處理 (6開頭為 SS, 0/3開頭為 SZ)
                def format_ticker(t):
                    t = str(t).zfill(6)
                    return f"{t}.SS" if t.startswith('6') else f"{t}.SZ"
                return table['Ticker'].apply(format_ticker).tolist()
    except Exception as e:
        print(f"Error fetching CSI300: {e}")
    return []

def main():
    # 確保 data 目錄存在
    os.makedirs('data', exist_ok=True)
    
    # 執行抓取
    hsi = get_hsi_tickers()
    csi300 = get_csi300_tickers()
    
    # 寫入檔案 (如果抓到資料才更新)
    if hsi:
        with open('data/hsi.txt', 'w', encoding='utf-8') as f:
            f.write("\n".join(hsi))
        print(f"成功寫入 {len(hsi)} 個 HSI 股票代碼")
        
    if csi300:
        with open('data/csi300.txt', 'w', encoding='utf-8') as f:
            f.write("\n".join(csi300))
        print(f"成功寫入 {len(csi300)} 個 CSI300 股票代碼")

if __name__ == "__main__":
    main()
