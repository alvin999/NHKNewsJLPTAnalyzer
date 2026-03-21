---
description: 如何執行 NHK 新聞同步與自動穿透驗證 (How to sync NHK news with auto-bypass)
---

# NHK 新聞同步工作流 (NHK News Sync Workflow)

本工作流說明了優化後的「共用 Context」爬蟲如何執行增量同步以及自動處理確認遮罩。

## 系統架構流程圖 (System Flowchart)

```mermaid
graph TD
    Start([🚀 開始]) --> Init[1. 初始化主程序 sync_news.py]
    Init --> SetupContext[2. setup_browser_context: 啟動單一瀏覽器實例並載入快取]
    SetupContext --> Loop{3. 遍歷新聞列表}
    
    Loop -- 發現新文章 --> Fetch[4. fetch_article_full_text]
    Loop -- 遍歷結束 --> SaveState[8. 儲存最新 Cookie 狀態檔]
    
    subgraph "單篇抓取邏輯 (backend/crawl.py)"
    Fetch --> Goto[5. page.goto 新聞網址]
    Goto --> Detect{6. 偵測方案 A 遮罩元素?}
    Detect -- 偵測到 --> Bypass[7. bypass_nhk_modals: 執行點擊穿透程序]
    Detect -- 未偵測 --> Scrape[擷取 BeautifulSoup 正文]
    Bypass --> Scrape
    end
    
    Scrape --> Loop
    SaveState --> Commit[9. 寫回資料庫檔案 & 關閉瀏覽器]
    Commit --> End([🏁 同步完成])
```

## 執行步驟 (Execution Steps)

1. **環境檢查**：
   確保 `data/` 目錄存在，且本地或 GitHub Cache 中已有 `playwright_state.json` (如有)。

// turbo
2. **執行同步**：
   ```bash
   python sync_news.py
   ```

3. **觀察輸出**：
   - 如果看到 `⚠️ 偵測到遮罩層`：代表 Cookie 過期或 NHK 強制要求驗證，程式會自動處理。
   - 如果直接看到 `🔍 爬取新新聞`：代表 Cookie 生效，已實現極速跳轉。

4. **結果檢查**：
   確認 `data/news_db.json` 或 `data/news_db_test.json` 已更新最新內容。
