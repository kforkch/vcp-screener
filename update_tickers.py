import os

# 1. 定義你的股票列表 (或者是從 API 獲取邏輯)
hsi_list = ["0001.HK", "0002.HK", ...] # 填入你的完整清單
csi300_list = ["600519.SS", "601318.SS", ...] # 填入你的完整清單

# 2. 確保資料夾存在
os.makedirs('data', exist_ok=True)

# 3. 將資料寫入檔案 (Python 負責寫檔)
with open('data/hsi.txt', 'w', encoding='utf-8') as f:
    for ticker in hsi_list:
        f.write(f"{ticker}\n")

with open('data/csi300.txt', 'w', encoding='utf-8') as f:
    for ticker in csi300_list:
        f.write(f"{ticker}\n")

print("資料更新完成！")
