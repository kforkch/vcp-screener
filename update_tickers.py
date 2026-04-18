import pandas as pd
import requests
import os
import io

def fetch_hsi():
    # 這是恒生指數成分股的 Wikipedia 網址
    url = "https://en.wikipedia.org/wiki/Hang_Seng_Index"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        tables = pd.read_html(io.StringIO(requests.get(url, headers=headers).text))
        # 通常表格在第二個或特定索引，需視網頁結構而定，這裡假設為第一個包含 'Ticker' 的表格
        for table in tables:
            if 'Ticker' in table.columns:
                # 假設表格內的 Ticker 是數字 (如 0001)，需補上 .HK
                return (table['Ticker'].astype(str).str.zfill(4) + ".HK").tolist()
    except Exception as e:
        print(f"抓取恒生指數失敗: {e}")
    return []

def fetch_csi300():
    # 這是滬深 300 的 Wikipedia 網址
    url = "https://en.wikipedia.org/wiki/CSI_300_Index"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        tables = pd.read_html(io.StringIO(requests.get(url, headers=headers).text))
        for table in tables:
            # 滬深 300 表格通常有 'Ticker' 欄位
            if 'Ticker' in table.columns:
                return table['Ticker'].astype(str).apply(lambda x: f"{x.zfill(6)}.SS" if x.startswith('6') else f"{x.zfill(6)}.SZ").tolist()
    except Exception as e:
        print(f"抓取滬深 300 失敗: {e}")
    return []

# 執行抓取
hsi_tickers = fetch_hsi()
csi_tickers = fetch_csi300()

# 確保資料夾存在
os.makedirs('data', exist_ok=True)

# 寫入檔案
if hsi_tickers:
    with open('data/hsi.txt', 'w', encoding='utf-8') as f:
        f.write("\n".join(hsi_tickers))
    print(f"已更新 HSI: {len(hsi_tickers)} 檔")

if csi_tickers:
    with open('data/csi300.txt', 'w', encoding='utf-8') as f:
        f.write("\n".join(csi_tickers))
    print(f"已更新 CSI300: {len(csi_tickers)} 檔")
