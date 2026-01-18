import pandas as pd
from sudachipy import dictionary
import os
import subprocess
import sys

def ensure_sudachi_dictionary():
    """確保 Sudachi 字典已正確連結，支援 Streamlit Cloud 部署"""
    try:
        # 嘗試初始化，看 'full' 字典是否可用
        dictionary.Dictionary(dict="full").create()
    except (Exception, SystemExit):
        # 如果失敗，執行系統指令進行連結
        try:
            # 1. 執行 link 指令
            subprocess.check_call(["sudachipy", "link", "-t", "full"])
            print("Successfully linked sudachidict_full")
        except Exception as e:
            # 如果還是失敗，可能是權限問題，嘗試安裝並連結
            print(f"Linking failed, attempting re-install: {e}")
            subprocess.check_call([sys.executable, "-m", "pip", "install", "sudachidict_full"])
            subprocess.check_call(["sudachipy", "link", "-t", "full"])

# 在模組載入時執行一次
ensure_sudachi_dictionary()

# 初始化 tokenizer
tokenizer_obj = dictionary.Dictionary(dict="full").create()
mode = tokenizer_obj.SplitMode.C

def analyze_jlpt_level(text, vocab_df):
    if not text or vocab_df.empty:
        return pd.Series([0,0,0,0,0], index=['N1','N2','N3','N4','N5'])

    # 取得斷詞原型
    tokens = [m.dictionary_form() for m in tokenizer_obj.tokenize(text, mode)]
    
    # 強制轉換詞庫中的單字為字串，避免比對出錯
    vocab_df['word'] = vocab_df['word'].astype(str)
    
    # 進行過濾
    match_df = vocab_df[vocab_df['word'].isin(tokens)]
    
    level_order = ['N1', 'N2', 'N3', 'N4', 'N5']
    counts = match_df['level'].value_counts().reindex(level_order, fill_value=0)
    return counts