# .github/workflows/sync_data.yml
name: Daily Supabase Data Sync

on:
  schedule:
    # 每天 UTC 時間 09:30 運行 (約台北時間 17:30，港、中、美股市皆已收盤)
    - cron: '30 9 * * *'
  workflow_dispatch: # 允許手動點擊執行測試

jobs:
  sync:
    runs-on: ubuntu-latest

    steps:
    - name: Checkout Code
      uses: actions/checkout@v4

    - name: Set up Python
      uses: actions/setup-python@v5
      with:
        python-version: '3.10'
        cache: 'pip'

    - name: Install Dependencies
      run: |
        python -m pip install --upgrade pip
        # 強制安裝所有可能缺少的依賴庫，避免執行時 ImportError 導致 Exit Code 1
        pip install supabase lxml pandas_ta openpyxl yfinance pandas requests

    - name: Ensure Data Directory and Tickers Exist
      run: |
        # 防禦性措施：建立 data 資料夾，並執行代碼更新腳本，確保 txt 檔案百分之百存在
        mkdir -p data
        python update_tickers.py

    - name: Run Downloader to Cloud
      env:
        SUPABASE_URL: ${{ secrets.SUPABASE_URL }}
        SUPABASE_KEY: ${{ secrets.SUPABASE_KEY }}
      run: |
        python downloader_to_cloud.py
