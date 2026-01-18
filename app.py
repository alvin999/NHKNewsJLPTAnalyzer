import streamlit as st
import pandas as pd
from app.translator import translate_text
from app.analyzer import analyze_jlpt_level
import plotly.express as px
from backend.crawl import fetch_article_full_text

# 1. 頁面設定
st.set_page_config(page_title="NHK News JLPT Analyzer", layout="wide")
st.title("🇯🇵 NHK News JLPT 學習分析器")

# 2. 載入資料 (模擬讀取 GitHub Actions 抓下來的 CSV)
@st.cache_data
def load_data():
    # 這裡讀取你 data/latest_articles.csv
    return pd.read_csv("data/latest_articles.csv")

@st.cache_data
def load_vocab():
    # 這裡讀取你 data/jlpt_vocab.csv
    return pd.read_csv("data/jlpt_vocab.csv")

df_news = load_data()
df_vocab = load_vocab()

# 3. 側邊欄：選擇新聞
st.sidebar.header("新聞選擇")
news_titles = df_news['title'].tolist()
selected_title = st.sidebar.selectbox("請選擇一篇新聞", news_titles)
current_article = df_news[df_news['title'] == selected_title].iloc[0]

# --- 核心邏輯：即時獲取內文 ---
@st.cache_data(show_spinner="正在擷取日本 NHK 完整內文...")
def get_full_content(url):
    return fetch_article_full_text(url)

paragraphs = get_full_content(current_article['url'])
full_text = "".join(paragraphs) # 用於 JLPT 分析

# 4. 主畫面佈局
col1, col2 = st.columns([1, 1])

with col1:
    st.subheader("📰 新聞原文 (完整版)")
    
    if 'translations' not in st.session_state:
        st.session_state.translations = {}

    for i, para in enumerate(paragraphs):
        st.write(para)
        # 每段提供翻譯按鈕
        if st.button(f"翻譯第 {i+1} 段", key=f"btn_{i}"):
            with st.spinner("翻譯中..."):
                translated = translate_text(para)
                st.session_state.translations[i] = translated
        
        if i in st.session_state.translations:
            st.info(st.session_state.translations[i])

with col2:
    st.subheader("📊 JLPT 全文難度分析")
    # 使用完整的內文進行分析
    level_stats = analyze_jlpt_level(full_text, df_vocab)
    
    fig = px.pie(values=level_stats.values, names=level_stats.index, 
                 title="全文單字難度分佈",
                 color_discrete_sequence=px.colors.sequential.RdBu)
    st.plotly_chart(fig, width='stretch')
    
    # 顯示指標
    total_words = level_stats.sum()
    n3_up_ratio = (level_stats[['N1', 'N2', 'N3']].sum() / total_words * 100) if total_words > 0 else 0
    st.metric("N3 以上難度占比", f"{n3_up_ratio:.1f}%")

st.divider()
st.caption("資料來源：NHK News Web. 本系統僅供學習使用。")