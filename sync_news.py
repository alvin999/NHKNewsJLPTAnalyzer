import json
import os
import time
from backend.crawl import fetch_nhk_news, fetch_article_full_text

# 根據環境決定資料庫路徑
if os.getenv("GITHUB_ACTIONS"):
    DB_PATH = "data/news_db.json"
else:
    DB_PATH = "data/news_db_test.json"

def run_sync():
    print(f"📡 [{time.strftime('%H:%M:%S')}] 開始同步 NHK 新聞...")
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

    # 1. 抓取最新清單
    df_list = fetch_nhk_news()
    if df_list.empty:
        print("❌ 無法取得新聞清單。")
        return

    # 2. 讀取現有資料
    db = {}
    if os.path.exists(DB_PATH):
        try:
            with open(DB_PATH, 'r', encoding='utf-8') as f:
                db = json.load(f)
        except:
            db = {}

    # 3. 增量爬取新文章
    new_count = 0
    for _, row in df_list.iterrows():
        aid = str(row['id'])
        if aid not in db:
            print(f"🔍 爬取新新聞: {row['title']}")
            content = fetch_article_full_text(row['url'])
            if content:
                db[aid] = {
                    "title": row['title'],
                    "url": row['url'],
                    "content": content,
                    "timestamp": time.time()
                }
                new_count += 1
                time.sleep(1) # 友善爬蟲延遲

    # 4. 自動覆蓋：按時間排序並保留最新 15 則
    sorted_items = sorted(db.items(), key=lambda x: x[1]['timestamp'], reverse=True)[:15]
    final_db = dict(sorted_items)

    # 5. 寫回資料庫
    with open(DB_PATH, 'w', encoding='utf-8') as f:
        json.dump(final_db, f, ensure_ascii=False, indent=4)

    print(f"✅ 同步完成！新增 {new_count} 則，目前共 {len(final_db)} 則儲存於資料庫。")

if __name__ == "__main__":
    run_sync()