import streamlit as st
import json
import os
import pandas as pd
from app.translator import translate_text
from app.analyzer import analyze_jlpt_level
import plotly.express as px
from backend.crawl import fetch_article_full_text

# 1. 頁面設定
st.set_page_config(page_title="NHK News JLPT Analyzer", layout="wide")

# CSS 美化樣式：調整側邊欄行距與視覺效果
st.markdown("""
<style>
    /* 優化側邊欄 Radio Button 的選項顯示 */
    .stRadio div[role="radiogroup"] > label {
        padding: 12px 15px;      /* 增加內距，讓選項更寬敞 */
        margin-bottom: 8px;      /* 增加選項之間的行距 */
        border-radius: 8px;      /* 圓角設計 */
        border: 1px solid rgba(128, 128, 128, 0.2); /* 增加輕微邊框 */
        transition: background-color 0.3s;
    }
    /* 滑鼠懸停效果 */
    .stRadio div[role="radiogroup"] > label:hover {
        background-color: rgba(128, 128, 128, 0.1);
    }
    /* 調整側邊欄標題間距 */
    section[data-testid="stSidebar"] .block-container {
        padding-top: 2rem;
    }
</style>
""", unsafe_allow_html=True)

st.title("🇯🇵 NHK News JLPT 學習分析器")

# 2. 載入資料
@st.cache_data
def load_data():
    # 優先讀取正式資料庫 (news_db.json)，如果不存在才讀取測試資料庫
    # 這樣在 Streamlit Cloud (會有 news_db.json) 也能正確讀取
    if os.path.exists("data/news_db.json"):
        file_path = "data/news_db.json"
    else:
        file_path = "data/news_db_test.json"

    if not os.path.exists(file_path):
        return pd.DataFrame()
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            # 將 JSON (Dict) 轉為 DataFrame 以便操作，並處理空資料情況
            return pd.DataFrame.from_dict(data, orient='index') if data else pd.DataFrame()
    except Exception as e:
        print(f"❌ 讀取資料庫失敗: {e}")
        return pd.DataFrame()

@st.cache_data
def load_vocab():
    raw_url = "https://raw.githubusercontent.com/Bluskyo/JLPT_Vocabulary/main/data/results/JLPTWords.csv"
    
    try:
        with st.spinner('📡 正在從線上同步 JLPT 全級別字彙庫...'):
            # 直接讀取線上 CSV
            df = pd.read_csv(raw_url)
            
            # 1. 強制清理欄位名稱：去除首尾空白並轉為小寫
            # 這樣無論 CSV 是 "Word" 還是 "word" 都能對齊
            df.columns = df.columns.str.strip().str.lower()
            
            # 2. 定義對應關係（將我們代碼用的 'word' 對應到 CSV 的 'word'）
            # 根據你提供的結構，我們需要的是 'word' 和 'jlptlevel'
            if 'word' in df.columns and 'jlptlevel' in df.columns:
                # 重新命名以便後續代碼統一使用
                df = df.rename(columns={'jlptlevel': 'level'})
            else:
                # 萬一標題完全對不上，回傳錯誤訊息
                st.error(f"❌ CSV 結構不符。現有欄位: {list(df.columns)}")
                return pd.DataFrame(columns=['word', 'level'])
            
            # 3. 數據清洗
            df['word'] = df['word'].astype(str).str.strip()
            df['level'] = df['level'].astype(str).str.strip()
            
            # 4. 格式標準化：確保 Level 顯示為 N1, N2...
            # 有些資料會存成 "1" 或 "n1"，我們統一轉換
            def format_level(lv):
                lv = lv.upper()
                return lv if lv.startswith('N') else f"N{lv}"
            
            df['level'] = df['level'].apply(format_level)
            
            # 5. 移除重複項，確保每個單字只有一個難度分級
            df = df.drop_duplicates(subset=['word'], keep='first')
            
            return df[['word', 'level']]
            
    except Exception as e:
        st.error(f"❌ 線上詞庫載入失敗: {e}")
        return pd.DataFrame(columns=['word', 'level'])

def plot_jlpt_distribution(text, vocab_df):
    """繪製 JLPT 難度分佈圓餅圖的共用函式"""
    level_stats = analyze_jlpt_level(text, vocab_df)
    fig = px.pie(values=level_stats.values, names=level_stats.index, 
                 title="全文單字難度分佈",
                 color_discrete_sequence=px.colors.sequential.RdBu)
    st.plotly_chart(fig, width='stretch')
    return level_stats

df_news = load_data()
df_vocab = load_vocab()

# 3. 側邊欄：功能選單
st.sidebar.header("功能選單")

MODE_NEWS = "📰 NHK 新聞閱讀"
MODE_CUSTOM = "📝 自訂文章分析"
app_mode = st.sidebar.radio("請選擇模式", [MODE_NEWS, MODE_CUSTOM])

if app_mode == MODE_NEWS:
    if df_news.empty:
        st.warning("目前沒有新聞資料，請先執行 `python sync_news.py` 進行同步。")
        st.stop()

    # 根據 timestamp 排序 (最新的在最上面)
    if 'timestamp' in df_news.columns:
        df_news = df_news.sort_values('timestamp', ascending=False)

    # ✅ 優化：改用 index (文章 ID) 作為 selectbox 的值，並用 format_func 顯示標題
    selected_aid = st.sidebar.selectbox(
        "請選擇一篇新聞", 
        options=df_news.index.tolist(),
        format_func=lambda x: df_news.loc[x, 'title']
    )
    current_article = df_news.loc[selected_aid]

    # --- 核心邏輯：即時獲取內文 ---
    # 優先使用資料庫中的內容，如果沒有才即時抓取 (理論上 sync_news 跑過後都會有)
    if 'content' in current_article and current_article['content']:
        paragraphs = current_article['content']
    else:
        # 嘗試即時抓取，但在 Streamlit Cloud 上可能會失敗，需做錯誤處理
        try:
            paragraphs = fetch_article_full_text(current_article['url'])
        except Exception as e:
            st.error(f"⚠️ 無法讀取內文，請稍後再試。(錯誤: {e})")
            paragraphs = []
            
    full_text = "".join(paragraphs) # 用於 JLPT 分析

    # 4. 主畫面佈局
    col1, col2 = st.columns([1, 1])

    with col1:
        st.subheader("📰 新聞原文 (完整版)")
        
        if 'translations' not in st.session_state:
            st.session_state.translations = {}
        
        # ✅ 使用文章 ID 進行隔離，避免換文章時看到舊翻譯
        if selected_aid not in st.session_state.translations:
            st.session_state.translations[selected_aid] = {}

        for i, para in enumerate(paragraphs):
            st.write(para)
            # 每段提供翻譯按鈕
            # ✅ Button 的 Key 也加上文章 ID，避免 Streamlit 的 Widget ID 衝突
            if st.button(f"翻譯第 {i+1} 段", key=f"btn_{selected_aid}_{i}"):
                with st.spinner("翻譯中..."):
                    translated = translate_text(para)
                    st.session_state.translations[selected_aid][i] = translated
            
            if i in st.session_state.translations[selected_aid]:
                st.info(st.session_state.translations[selected_aid][i])

    with col2:
        st.subheader("📊 JLPT 全文難度分析")
        # 使用完整的內文進行分析
        level_stats = plot_jlpt_distribution(full_text, df_vocab)
        
        # 顯示指標
        total_words = level_stats.sum()
        n3_up_ratio = (level_stats[['N1', 'N2', 'N3']].sum() / total_words * 100) if total_words > 0 else 0
        st.metric("N3 以上難度占比", f"{n3_up_ratio:.1f}%")

elif app_mode == MODE_CUSTOM:
    st.subheader("📝 自訂文章分析")
    user_text = st.text_area("請在此貼上日文文章：", height=300, placeholder="請輸入日文文章...")
    
    # 初始化 Session State 以支援互動 (如翻譯)
    if 'custom_analysis_text' not in st.session_state:
        st.session_state.custom_analysis_text = ""
    if 'custom_translation' not in st.session_state:
        st.session_state.custom_translation = ""

    if st.button("開始分析") and user_text:
        st.session_state.custom_analysis_text = user_text
        st.session_state.custom_translation = "" # 重置翻譯

    if st.session_state.custom_analysis_text:
        target_text = st.session_state.custom_analysis_text
        col1, col2 = st.columns([1, 1])
        
        with col1:
            st.subheader("原文")
            st.write(target_text)
            
            if st.button("翻譯全文", key="btn_custom_trans"):
                with st.spinner("翻譯中..."):
                    st.session_state.custom_translation = translate_text(target_text)
            
            if st.session_state.custom_translation:
                st.info(st.session_state.custom_translation)
            
        with col2:
            st.subheader("📊 JLPT 難度分析")
            level_stats = plot_jlpt_distribution(target_text, df_vocab)
            
            total_words = level_stats.sum()
            n3_up_ratio = (level_stats[['N1', 'N2', 'N3']].sum() / total_words * 100) if total_words > 0 else 0
            st.metric("N3 以上難度占比", f"{n3_up_ratio:.1f}%")

st.divider()
st.caption("資料來源：NHK News Web. 本系統僅供學習使用。")