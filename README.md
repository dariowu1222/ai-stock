# AI 台股策略顧問系統 MVP

本專案是本機執行的台股策略顧問 MVP，第一階段只提供策略建議、技術指標、股票篩選、固定持有天數回測與 Markdown 報告輸出。

## 第一階段功能

- 啟動時透過 FinMind 更新真實台股日 K，並讀取本地快取 `price_data/*.csv`。
- 計算 MA、RSI、MACD、KD、ATR、量均與突破欄位。
- 提供 5 種策略模板：爆量突破、回檔轉強、超跌反彈、均線多頭、MACD 翻正。
- 依最新一日訊號篩選候選股並匯出 `output/screener_result.csv`。
- 對候選股執行固定持有天數回測並匯出 `output/backtest_result.csv`。
- 產出個股 Markdown 決策輔助報告到 `output/reports/`。

## 不做真實下單聲明

第一階段不實作真實下單、自動交易、Shioaji live mode、盤中 tick 資料、高頻交易、全市場即時掃描或雲端部署。所有交易相關模組都是 stub，任何下單呼叫都會直接丟出錯誤。

本系統只提供決策輔助與研究用途，不構成投資建議；策略分數與回測結果不能保證未來績效。

## 安裝方式

```bash
pip install -r requirements.txt
```

## 執行方式

```bash
streamlit run app.py
```

也可以直接雙擊 `啟動AI台股.lnk` 開啟畫面。啟動時會先執行股價更新，再開啟瀏覽器。若需要看啟動與更新 log，可改用 `啟動AI台股.cmd`。

## 更新真實股價資料

目前支援 FinMind 的 `TaiwanStockPrice` 日成交資訊，更新後存成本地 CSV，畫面端讀 `price_data/*.csv`。

先設定 FinMind token：

```powershell
setx FINMIND_TOKEN "你的_token"
```

若環境變數尚未生效，也可建立本地檔案 `secrets/finmind_token.txt`，只放 token 內容。`secrets/` 已被 `.gitignore` 排除，避免誤提交。

平常雙擊 `啟動AI台股.lnk` 會自動更新。內部會呼叫 `update_prices.py`，這個檔案是系統用的資料更新程式，不需要日常手動執行。

```bash
python update_prices.py
```

更新程式會讀 `watchlist.json`，逐檔下載並覆寫同名 CSV。若 CSV 已存在，會從最後日期往前回補 `price_update_backfill_days` 天再合併，避免漏掉修正資料。

## CSV 格式

每檔股票一個 CSV，例如 `price_data/2330.csv`。

```csv
date,open,high,low,close,volume
2025-01-02,1000,1010,995,1005,30000
2025-01-03,1005,1020,1000,1015,35000
```

必要欄位為 `date/open/high/low/close/volume`。`date` 必須可轉為日期，價格與成交量欄位必須為數字，資料需依日期升冪排序。

## 專案資料夾

- `advisor/`: 規則式策略顧問與 Markdown 報告。
- `strategy/`: 指標、策略模板與訊號引擎。
- `backtest/`: 固定持有天數回測與績效指標。
- `data/`: 本地資料載入、市場情境與籌碼 stub。
- `data/finmind.py`: FinMind 日 K 下載與欄位轉換。
- `screener/`: 候選股篩選與排序。
- `trader/`: 禁用真實交易的 stub。
- `price_data/`: FinMind 更新後的本地股價快取 CSV。
- `output/`: 篩選、回測與報告輸出。
