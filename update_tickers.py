def save_list_to_file(data_list, filepath):
    """確保只寫入有效的代碼，並過濾掉空行或無效字串"""
    # 過濾空字串並去除前後空白
    cleaned_data = [str(item).strip() for item in data_list if str(item).strip()]
    
    if cleaned_data:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write("\n".join(cleaned_data))
        print(f"成功更新 {filepath}: {len(cleaned_data)} 個代碼")
    else:
        print(f"警告: 未抓取到有效資料，不更新 {filepath}")

def main():
    os.makedirs('data', exist_ok=True)
    
    # 執行抓取
    hsi = get_hsi_tickers()
    csi300 = get_csi300_tickers()
    
    # 使用封裝好的函數寫入
    save_list_to_file(hsi, 'data/hsi.txt')
    save_list_to_file(csi300, 'data/csi300.txt')

if __name__ == "__main__":
    main()
