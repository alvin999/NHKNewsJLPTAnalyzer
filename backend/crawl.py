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

def fetch_article_full_text(url):
    try:
        with sync_playwright() as p:
            # 1. 模擬 Codegen 的啟動環境
            try:
                # 改用 headless=True 並加入反偵測參數
                browser = p.chromium.launch(
                    headless=True,
                    args=[
                        "--headless=new",  # 關鍵：使用新版 Headless 模式，行為更像真實瀏覽器
                        "--disable-blink-features=AutomationControlled", # 關鍵：隱藏 navigator.webdriver 標記
                        "--no-sandbox",
                        "--disable-dev-shm-usage", # 防止記憶體不足崩潰
                        "--disable-extensions",
                        "--disable-gpu",
                        "--disable-infobars"
                    ]
                )
            except Exception as e:
                # 如果遇到瀏覽器未安裝的錯誤，嘗試自動安裝
                if "Executable doesn't exist" in str(e):
                    print("⚠️ 偵測到瀏覽器未安裝，正在自動執行 playwright install chromium...")
                    subprocess.check_call([sys.executable, "-m", "playwright", "install", "chromium"])
                    browser = p.chromium.launch(headless=True, args=["--headless=new", "--disable-blink-features=AutomationControlled"])
                else:
                    raise e

            state_path = "data/playwright_state.json"
            context_kwargs = {
                'viewport': {'width': 1920, 'height': 1080},
                'locale': 'ja-JP',
                'timezone_id': 'Asia/Tokyo',
                'geolocation': {'latitude': 35.6895, 'longitude': 139.6917}, # 📍 設定為日本東京座標
                'permissions': ['geolocation'], # ✅ 允許網站獲取位置資訊 (增加真實感)
                'user_agent': "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
            }
            if os.path.exists(state_path):
                context_kwargs['storage_state'] = state_path

            context = browser.new_context(**context_kwargs)
            
            # 🕵️‍♂️ 注入 Stealth 腳本：徹底隱藏自動化特徵
            context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            """)
            
            page = context.new_page()
            
            
            # 2. 前往網址
            page.goto(url, wait_until="domcontentloaded")


            # --- 關鍵修正：判斷是否已經有 Cookie，如果有則能極速通關 ---
            has_state = os.path.exists(state_path)
            
            # 嘗試擊穿第 1 & 2 層 (如果有的話)
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
                print("ℹ️ 未偵測到前兩層，可能已跳過")
                
            # 3. 擊穿第三層 (Codegen 錄到的那一步)
            try:
                # 定義定位器：文字 與 Class (增加容錯)
                btn_text = page.get_by_role("button", name="確認しました / I understand")
                btn_class = page.locator("button.esl7kn2s")
                
                target_btn = None
                
                if btn_text.is_visible():
                    target_btn = btn_text
                elif btn_class.is_visible():
                    target_btn = btn_class
                elif not has_state:
                    # ✅ 只有在「沒有載入過 Cookie」時，才需要花費 5 秒鐘向下捲動尋找按鈕
                    print("⚠️ 尚未建立 Cookie，需要模擬捲動以尋找確認按鈕...")
                    for _ in range(5):
                        page.mouse.wheel(0, 1000)
                        page.wait_for_timeout(1000)
                        if btn_text.is_visible():
                            target_btn = btn_text
                            break
                        if btn_class.is_visible():
                            target_btn = btn_class
                            break
                    
                    # 如果還沒找到，最後試一次直接到底
                    if not target_btn:
                        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                        page.wait_for_timeout(1000)
                        if btn_text.is_visible(): target_btn = btn_text
                        elif btn_class.is_visible(): target_btn = btn_class

                if target_btn:
                    target_btn.scroll_into_view_if_needed()
                    target_btn.click(force=True)
                    print("✅ 成功執行點擊：確認しました / I understand")

                    # 關鍵修正：點擊後頁面會刷新或導航，必須等待載入完成
                    page.wait_for_load_state("domcontentloaded")
                    page.wait_for_timeout(2000)
                else:
                    print("ℹ️ 無需點擊第三層按鈕 (可能已透過 Cookie 略過)")
            except Exception as e:
                print(f"⚠️ 處理第三層按鈕發生錯誤: {e}")

            # 擷取內文
            html_content = page.content()
            
            # ✅ 儲存狀態 (包含 Cookies 與 LocalStorage)
            # 下次執行 new_context 時會自動載入，遇到 NHK 確認條款就不會再跳出
            context.storage_state(path=state_path)
            
            browser.close()
            
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