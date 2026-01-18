from googletrans import Translator
import streamlit as st

# 使用 st.cache_resource 避免重複初始化
@st.cache_resource
def get_translator():
    return Translator()

def translate_text(text, dest='zh-tw'):
    translator = get_translator()
    try:
        result = translator.translate(text, dest=dest)
        return result.text
    except Exception as e:
        return f"翻譯出錯: {e}"