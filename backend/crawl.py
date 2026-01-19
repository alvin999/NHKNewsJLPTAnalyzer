import requests
import pandas as pd
import os
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
#from playwright_stealth import stealth

def fetch_nhk_news():
    api_url = "https://www3.nhk.or.jp/news/json16/new_001.json"
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36'}
    try:
        response = requests.get(api_url, headers=headers, timeout=10)
        data = response.json()
        items = data.get('channel', {}).get('item', [])
        
        articles = []
        for item in items:
            this_id = item.get('id')
            # 從 API 的 link 提取像 k10015029391000 這樣的完整 ID
            # 範例 link: "html/20260118/k10015029511000.html"
            raw_link = item.get('link', '')
            full_id_with_prefix = raw_link.split('/')[-1].replace('.html', '')
            
            # 產生 NA 網址
            na_url = f"https://news.web.nhk/newsweb/na/na-{full_id_with_prefix}"
            
            articles.append({
                'id': this_id,
                'title': item.get('title'),
                'url': na_url
            })
        return pd.DataFrame(articles)
    except Exception as e:
        print(f"❌ 抓取清單失敗: {e}")
        return pd.DataFrame()

    except Exception as e:
        print(f"❌ 抓取失敗: {e}")
        return pd.DataFrame()

def fetch_article_full_text(url):
    paragraphs = [] # 預設空列表，避免失敗時回傳 None
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(viewport={'width': 1280, 'height': 1200})
            page = context.new_page()
            
            # 前往網址
            page.goto(url, wait_until="domcontentloaded")

            # --- 核心：擊穿海外彈窗 ---
            try:
                # 使用你提供的特定按鈕特徵
                confirm_selector = "button:has-text('確認しました')"
                page.wait_for_selector(confirm_selector, timeout=5000)
                page.click(confirm_selector)
                print("✅ 成功點擊『確認しました』按鈕")
                page.wait_for_timeout(1500)
            except Exception as e:
                print(f"ℹ️ 未發現彈窗或按鈕已失效: {e}")

            # --- 模擬捲動觸發 Lazy Loading ---
            #page.mouse.wheel(0, 1500)
            #page.wait_for_timeout(2000)
            # --- 核心簡化：將 HTML 轉交給 BeautifulSoup ---
            html_content = page.content()
            
            browser.close()
            
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # 4. 使用 BeautifulSoup 尋找所有內文標籤
            nodes = soup.find_all(['p', 'h3'], class_=['_1i1d7sh2', '_1i1d7sh9'])
            
            # 提取文字並過濾空值
            paragraphs = [n.get_text().strip() for n in nodes if n.get_text().strip()]

            return paragraphs

    except Exception as e:
        print(f"❌ Playwright 過程出錯: {e}")
        return [f"抓取失敗: {str(e)}"]


# --- 測試與執行區塊 ---
if __name__ == "__main__":
    print("📡 正在嘗試抓取 NHK 最新新聞...")
    
    df = fetch_nhk_news_list()
    
    if not df.empty:
        os.makedirs('data', exist_ok=True)
        # 儲存清單
        df.to_csv('data/latest_articles.csv', index=False, encoding='utf-8-sig')
        print(f"✅ 成功！抓取到 {len(df)} 則新聞清單。")
        
        # 測試抓取第一則的全文
        first_url = df.iloc[0]['url']
        print(f"🔍 測試抓取第一則全文: {first_url}")
        content = fetch_article_full_text(first_url)
        print(f"📝 內文段落數: {len(content)}")
        for i, p in enumerate(content[:3]): # 印出前三段看看
            print(f"  段落 {i+1}: {p[:50]}...")
    else:
        print("❌ 依然無法抓取資料，請檢查 JSON 結構。")