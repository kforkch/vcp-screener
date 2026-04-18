def save_tickers_to_file(tickers, filename):
    """確保每個代碼獨立佔一行，且過濾掉無效字串"""
    file_path = os.path.join('data', filename)
    with open(file_path, 'w', encoding='utf-8') as f:
        for t in tickers:
            cleaned_ticker = str(t).strip()
            if cleaned_ticker and len(cleaned_ticker) > 2: # 過濾空值與異常簡短字串
                f.write(f"{cleaned_ticker}\n")

def main():
    # 確保 data 目錄存在
    os.makedirs('data', exist_ok=True)
    
    # 執行抓取
    hsi = get_hsi_tickers()
    csi300 = get_csi300_tickers()
    
    # 分別寫入兩個獨立的檔案，絕對不混在一起
    if hsi:
        save_tickers_to_file(hsi, 'hsi.txt')
        print(f"成功更新 HSI: {len(hsi)} 個代碼至 hsi.txt")
        
    if csi300:
        save_tickers_to_file(csi300, 'csi300.txt')
        print(f"成功更新 CSI300: {len(csi300)} 個代碼至 csi300.txt")
