import pandas as pd
import os
import subprocess
import sys
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
import urllib.request
import json

def fetch_nhk_news():
    api_url = "https://www3.nhk.or.jp/news/json16/new_001.json"
    
    # 使用最極簡但有效的 Headers
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/121.0.0.0 Safari/537.36',
        'Accept': 'application/json',
        'Accept-Language': 'ja-JP,ja;q=0.9'
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

def setup_browser_context(p):
    """
    初始化瀏覽器與 Context，並載入儲存的狀態 (Cookies/LocalStorage)。
    """
    # 改用 headless=True 並加入反偵測參數
    browser = p.chromium.launch(
        headless=True,
        args=[
            "--headless=new",
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-extensions",
            "--disable-gpu",
            "--disable-infobars"
        ]
    )
    
    state_path = "data/playwright_state.json"
    context_kwargs = {
        'viewport': {'width': 1920, 'height': 1080},
        'locale': 'ja-JP',
        'timezone_id': 'Asia/Tokyo',
        'geolocation': {'latitude': 35.6895, 'longitude': 139.6917},
        'permissions': ['geolocation'],
        'user_agent': "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
    }
    if os.path.exists(state_path):
        context_kwargs['storage_state'] = state_path

    context = browser.new_context(**context_kwargs)
    
    # 🕵️‍♂️ 注入 Stealth 腳本：徹底隱藏自動化特徵
    context.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
    """)
    return browser, context

def bypass_nhk_modals(page):
    """
    執行點擊穿透流程 (Level 1, 2, 3)。
    """
    # 1. 嘗試擊穿第 1 & 2 層
    try:
        if page.get_by_text("内容について確認しました").is_visible():
            page.get_by_text("内容について確認しました").click()
            page.get_by_role("button", name="次へ").click()
            page.wait_for_timeout(1000)
            
            # 處理 2/2 區域選擇
            page.get_by_label("世帯(個人)で").check()
            page.locator("select").select_option(index=1)
            page.get_by_role("button", name="サービスの利用を開始する").click()
            print("✅ 擊穿前兩層導覽")
    except:
        pass
        
    # 2. 擊穿第三層
    try:
        btn_text = page.get_by_role("button", name="確認しました / I understand")
        btn_class = page.locator("button.esl7kn2s")
        target_btn = None
        
        if btn_text.is_visible(): target_btn = btn_text
        elif btn_class.is_visible(): target_btn = btn_class
        else:
            # 如果還是沒看到，嘗試捲動一次
            page.mouse.wheel(0, 1000)
            page.wait_for_timeout(1000)
            if btn_text.is_visible(): target_btn = btn_text
            elif btn_class.is_visible(): target_btn = btn_class

        if target_btn:
            target_btn.scroll_into_view_if_needed()
            target_btn.click(force=True)
            print("✅ 成功執行點擊：確認しました / I understand")
            page.wait_for_load_state("domcontentloaded")
            page.wait_for_timeout(2000)
    except Exception as e:
        print(f"⚠️ 處理第三層按鈕發生錯誤: {e}")

def fetch_article_full_text(url, page=None):
    """
    抓取文章全文。支援傳入既有的 page 以共用 Context。
    """
    try:
        if page:
            # --- 使用現有的 Page (共用 Context 模式) ---
            page.goto(url, wait_until="domcontentloaded")
            
            # 【方案 A】直接偵測遮罩元素
            if page.locator("button.esl7kn2s").is_visible() or page.get_by_role("button", name="確認しました / I understand").is_visible():
                print(f"⚠️ 偵測到遮罩層，嘗試進行穿透...")
                bypass_nhk_modals(page)
            
            html_content = page.content()
        else:
            # --- 建立臨時 Page (相容舊模式/測試用) ---
            with sync_playwright() as p:
                browser, context = setup_browser_context(p)
                temp_page = context.new_page()
                temp_page.goto(url, wait_until="domcontentloaded")
                
                if temp_page.locator("button.esl7kn2s").is_visible():
                    bypass_nhk_modals(temp_page)
                
                html_content = temp_page.content()
                browser.close()
            
        soup = BeautifulSoup(html_content, 'html.parser')
        # 抓取新版內文標籤
        nodes = soup.find_all(['p', 'h3'], class_=['_1i1d7sh2', '_1i1d7sh9'])
        return [n.get_text().strip() for n in nodes if n.get_text().strip()]

    except Exception as e:
        print(f"❌ 抓取全文失敗: {e}")
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