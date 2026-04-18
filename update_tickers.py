# update_tickers.py 的正確寫法範例
import os

# 確保 data 資料夾存在
os.makedirs('data', exist_ok=True)

# 假設這是你獲取股票代碼的邏輯
# ... 獲取邏輯 ...

# 只負責將資料寫入 txt 檔案
with open('data/hsi.txt', 'w', encoding='utf-8') as f:
    for ticker in hsi_list:
        f.write(f"{ticker}\n")

with open('data/csi300.txt', 'w', encoding='utf-8') as f:
    for ticker in as_list:
        f.write(f"{ticker}\n")

print("檔案更新完成。")
