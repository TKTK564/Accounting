import streamlit as st
import gspread
import json
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
import time
import calendar

# --- 1. APP 質感與圖示設定 (核心品牌化區塊) ---
st.set_page_config(page_title="個人財務戰情系統", layout="wide")

# 你的 GitHub 圖片原始連結
ICON_URL = "https://raw.githubusercontent.com/TKTK564/Accounting/refs/heads/main/ChatGPT%20Image%202026%E5%B9%B45%E6%9C%889%E6%97%A5%20%E4%B8%8B%E5%8D%8812_14_52.png"

# 注意：這裡的內容必須全部靠左對齊，不能有縮進
st.markdown(f"""
<head>
<link rel="apple-touch-icon" href="{ICON_URL}">
<link rel="icon" sizes="192x192" href="{ICON_URL}">
<link rel="icon" sizes="512x512" href="{ICON_URL}">
</head>
<style>
header {{visibility: hidden;}}
footer {{visibility: hidden;}}
#MainMenu {{visibility: hidden;}}

.block-container {{
    padding-top: 1.5rem;
    padding-bottom: 0rem;
    padding-left: 1.5rem;
    padding-right: 1.5rem;
}}

.stTabs [data-baseweb="tab-list"] {{ 
    gap: 10px; 
}}

.stTabs [data-baseweb="tab"] {{ 
    height: 45px; 
    background-color: #f1f3f5; 
    color: #495057; 
    border-radius: 10px; 
    padding: 10px 15px; 
    border: none;
}}

.stTabs [aria-selected="true"] {{ 
    background-color: #007bff !important; 
    color: white !important; 
    font-weight: bold; 
    box-shadow: 0 4px 6px rgba(0,0,0,0.1);
}}
</style>
""", unsafe_allow_html=True)

# --- 2. 雲端連線 ---
try:
    credentials = json.loads(st.secrets["gcp_service_account_json"])
    gc = gspread.service_account_from_dict(credentials)
    sh = gc.open('專屬財務戰情資料庫')
    users_sheet = sh.worksheet('使用者名冊')
except Exception as e:
    st.error(f"❌ 雲端連線失敗：{e}");
    st.stop()

# --- 3. 初始化 Session State ---
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.username = ""

if 'pool_configs' not in st.session_state:
    st.session_state.pool_configs = [
        {"池名": "生活預算", "上限模式": "百分比", "上限值": 50},
        {"池名": "投資帳戶", "上限模式": "固定金額", "上限值": 5000}
    ]

if 'expense_cats' not in st.session_state:
    st.session_state.expense_cats = ["飲食", "交通", "自我提升", "娛樂", "生活用品", "未分類"]

# --- 4. 登入閘門 ---
if not st.session_state.logged_in:
    st.title("🔐 戰情中心登入")
    t1, t2 = st.tabs(["🔑 登入", "📝 註冊"])
    with t1:
        u = st.text_input("帳號", key="login_u");
        p = st.text_input("密碼", type="password", key="login_p")
        if st.button("進入指揮所"):
            recs = users_sheet.get_all_records()
            for r in recs:
                if str(r.get("Username")).strip() == u.strip() and str(r.get("Password")).strip() == p.strip():
                    st.session_state.logged_in = True
                    st.session_state.username = u
                    st.rerun()
            st.error("帳密不符")
    with t2:
        nu = st.text_input("新帳號", key="reg_u");
        np = st.text_input("新密碼", type="password", key="reg_p")
        if st.button("確認註冊"):
            users_sheet.append_row([nu, np, "", ""])
            sh.add_worksheet(title=nu, rows="1000", cols="10").append_row(
                ["日期", "類型", "類別", "金額", "帳戶", "備註"])
            st.toast("✅ 註冊成功！", icon="🎉")
    st.stop()

# --- 5. 數據加載 ---
worksheet = sh.worksheet(st.session_state.username)
records = worksheet.get_all_records()
df = pd.DataFrame(records)
if not df.empty:
    df['金額'] = pd.to_numeric(df['金額'], errors='coerce').fillna(0)
    df['日期'] = pd.to_datetime(df['日期'])
    df['年月'] = df['日期'].dt.strftime('%Y-%m')
    df['年'] = df['日期'].dt.year

try:
    rec_ws = sh.worksheet(f"{st.session_state.username}_自動扣款")
except gspread.WorksheetNotFound:
    rec_ws = sh.add_worksheet(title=f"{st.session_state.username}_自動扣款", rows="100", cols="10")
    rec_ws.append_row(["項目名稱", "金額", "預算池", "支出類別", "扣款時間", "週期"])
rec_df = pd.DataFrame(rec_ws.get_all_records())

# ==========================================
# --- 6. 主戰情系統 ---
# ==========================================
colA, colB = st.columns([5, 1])
with colA: st.title(f"🛠️ {st.session_state.username} 的財務戰略中心")
with colB:
    if st.button("登出 👋"): st.session_state.logged_in = False; st.rerun()

tabs = st.tabs(["📥 收入分配", "💸 支出與載具同步", "🔄 自動扣款", "📊 現金流", "📁 數據管理", "⚙️ 設定中心"])

# --- Tab 內容與之前一致，為節省篇幅此處省略，請保留你原本代碼中的 Tab 1 ~ Tab 6 ---
# (請直接將原本代碼中從 with tabs[0]: 開始到最後的部分接在這裡)
