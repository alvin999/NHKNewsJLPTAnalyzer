import requests
import pandas as pd
import os
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
import urllib.request
import json
#from playwright_stealth import stealth

def fetch_nhk_news():
    api_url = "https://www3.nhk.or.jp/news/json16/new_001.json"
    
    # 使用最極簡但有效的 Headers
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/121.0.0.0 Safari/537.36',
        'Accept': 'application/json'
    }
    
    try:
        req = urllib.request.Request(api_url, headers=headers)
        # 這裡不使用 HTTP/2，直接走標準 HTTP/1.1 串流
        with urllib.request.urlopen(req, timeout=15) as response:
            if response.status == 200:
                data = json.loads(response.read().decode('utf-8'))
                items = data.get('channel', {}).get('item', [])
                
                articles = []
                for item in items:
                    raw_link = item.get('link', '')
                    full_id = raw_link.split('/')[-1].replace('.html', '')
                    na_url = f"https://news.web.nhk/newsweb/na/na-{full_id}"
                    
                    articles.append({
                        'id': item.get('id'),
                        'title': item.get('title'),
                        'url': na_url
                    })
                return pd.DataFrame(articles)
            else:
                print(f"❌ 伺服器回傳狀態碼: {response.status}")
                return pd.DataFrame()
                
    except Exception as e:
        print(f"❌ urllib 抓取失敗: {e}")
        return pd.DataFrame()

def fetch_article_full_text(url):
    paragraphs = []
    # 建立除錯截圖資料夾
    debug_dir = "debug_steps"
    if not os.path.exists(debug_dir):
        os.makedirs(debug_dir)
    try:
        with sync_playwright() as p:
            # 1. 模擬 Codegen 的啟動環境
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                viewport={'width': 1280, 'height': 800},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
            )
            page = context.new_page()
            
            # 2. 前往網址
            page.goto(url, wait_until="domcontentloaded")

            # --- 關鍵修正：像 Codegen 一樣靈活應對 ---
            # 有些環境會跳出 1/2 層，有些直接跳 3 層。我們用 try-except 包起來。
            
            # 嘗試擊穿第 1 & 2 層 (如果有的話)
            try:
                if page.get_by_text("内容について確認しました").is_visible(timeout=3000):
                    page.get_by_text("内容について確認しました").click()
                    page.get_by_role("button", name="次へ").click()
                    page.wait_for_timeout(1000)
                    
                    # 處理 2/2 區域選擇
                    page.get_by_label("世帯(個人)で").check()
                    page.locator("select").select_option(index=1)
                    page.get_by_role("button", name="サービスの利用を開始する").click()
                    print("✅ 擊穿前兩層導覽")
            except:
                print("ℹ️ 未偵測到前兩層，可能已跳過")

            # 3. 擊穿第三層 (Codegen 錄到的那一步)
            try:
                # 這裡使用 Codegen 產生的精確定位
                target_btn = page.get_by_role("button", name="確認しました / I understand")
                target_btn.wait_for(state="visible", timeout=5000)
                target_btn.click()
                print("✅ 成功執行 Codegen 錄製的點擊：確認しました / I understand")
            except Exception as e:
                print(f"⚠️ 無法點擊第三層按鈕: {e}")

            # 4. 最終確認：如果遮罩還在，暴力移除 (確保萬無一失)
            page.wait_for_timeout(2000)
            page.evaluate("""() => {
                document.querySelectorAll('div').forEach(div => {
                    const style = window.getComputedStyle(div);
                    if (style.position === 'fixed' && parseInt(style.zIndex) > 50) div.remove();
                });
                document.body.style.overflow = 'auto';
            }""")

            # 擷取內文
            html_content = page.content()
            browser.close()
            
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html_content, 'html.parser')
            # 抓取新版內文標籤
            nodes = soup.find_all(['p', 'h3'], class_=['_1i1d7sh2', '_1i1d7sh9'])
            return [n.get_text().strip() for n in nodes if n.get_text().strip()]

    except Exception as e:
        print(f"❌ 執行失敗: {e}")
        return []

# --- 測試與執行區塊 ---
if __name__ == "__main__":
    print("📡 正在嘗試抓取 NHK 最新新聞...")
    
    df = fetch_nhk_news()
    
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