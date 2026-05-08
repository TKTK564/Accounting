import streamlit as st
import gspread
import json
from datetime import datetime

# --- 1. 隱藏網頁預設選單 ---
st.set_page_config(page_title="個人財務戰情系統", layout="centered")
st.markdown("""
    <style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    </style>
    """, unsafe_allow_html=True)

# --- 2. 連線 Google Sheets ---
credentials = json.loads(st.secrets["gcp_service_account_json"])
gc = gspread.service_account_from_dict(credentials)
sh = gc.open('專屬財務戰情資料庫')
users_sheet = sh.worksheet('使用者名冊')

# --- 3. 初始化 Session State (記憶登入狀態) ---
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.username = ""

# --- 4. 登入與註冊閘門 ---
if not st.session_state.logged_in:
    st.title("🔐 戰情中心登入閘門")
    tab1, tab2 = st.tabs(["🔑 登入", "📝 註冊新帳號"])

    # 【登入區塊】
    with tab1:
        login_user = st.text_input("帳號", key="login_user")
        login_pw = st.text_input("密碼", type="password", key="login_pw")

        if st.button("登入系統"):
            records = users_sheet.get_all_records()
            user_found = False
            for row in records:
                if str(row.get("Username")) == login_user and str(row.get("Password")) == login_pw:
                    st.session_state.logged_in = True
                    st.session_state.username = login_user
                    user_found = True
                    st.rerun()  # 重新整理網頁，進入主系統

            if not user_found:
                st.error("❌ 帳號或密碼錯誤，請重新確認。")

    # 【註冊區塊】
    with tab2:
        reg_user = st.text_input("設定新帳號", key="reg_user")
        reg_pw = st.text_input("設定密碼", type="password", key="reg_pw")

        if st.button("確認註冊"):
            if not reg_user or not reg_pw:
                st.warning("請填寫完整的帳號與密碼！")
            else:
                existing_users = [str(row.get("Username")) for row in users_sheet.get_all_records()]
                if reg_user in existing_users:
                    st.error("⚠️ 此帳號已被註冊過，請換一個。")
                else:
                    # 1. 將新帳號密碼寫入名冊
                    users_sheet.append_row([reg_user, reg_pw])

                    # 2. 在 Google Sheet 自動為他開闢專屬資料分頁，並寫好表頭
                    new_ws = sh.add_worksheet(title=reg_user, rows="100", cols="10")
                    new_ws.append_row(["日期", "類型", "類別", "金額", "帳戶", "備註"])

                    st.success("✅ 註冊成功！系統已為您建立專屬資料庫，請切換至「登入」分頁進入戰情室。")

    st.stop()  # 阻擋未登入者看到下方的程式碼

# ==========================================
# --- 5. 進入主系統 (已登入狀態) ---
# ==========================================

# 抓取該登入者的專屬分頁
worksheet = sh.worksheet(st.session_state.username)

# 頂部控制列 (顯示身分與登出)
colA, colB = st.columns([3, 1])
with colA:
    st.title(f"📊 {st.session_state.username} 的戰情中心")
with colB:
    if st.button("登出 👋"):
        st.session_state.logged_in = False
        st.session_state.username = ""
        st.rerun()

st.markdown("---")

# 1. 收入輸入區
st.header("1. 資金匯入")
income_amount = st.number_input("請輸入本次進帳金額", min_value=0, value=10000, step=1000)
source_name = st.text_input("資金來源備註", value="本薪/獎學金")

# --- 2. 戰略分配設定 (進階自定義版) ---
st.header("2. 戰略分配設定")

# 初始化 session_state
if 'temp_budget' not in st.session_state:
    st.session_state.temp_budget = [
        {"類別": "生活預算", "百分比": 50},
        {"類別": "投資帳戶", "百分比": 30},
        {"類別": "儲蓄帳戶", "百分比": 20}
    ]

# --- 新增類別的區塊 ---
with st.expander("➕ 新增預算類別"):
    new_cat_name = st.text_input("輸入新類別名稱", placeholder="例如：機車改裝")
    if st.button("確認新增"):
        if new_cat_name:
            st.session_state.temp_budget.append({"類別": new_cat_name, "百分比": 0})
            st.rerun()

# --- 動態顯示類別與刪除按鈕 ---
updated_budget = []
for i, item in enumerate(st.session_state.temp_budget):
    col_name, col_pct, col_del = st.columns([3, 2, 1])

    with col_name:
        new_name = st.text_input(f"類別-{i}", value=item["類別"], label_visibility="collapsed")
    with col_pct:
        new_pct = st.number_input(f"百分比-{i}", value=item["百分比"], min_value=0, max_value=100, step=1,
                                  label_visibility="collapsed")
    with col_del:
        if st.button("🗑️", key=f"del_{i}"):
            st.session_state.temp_budget.pop(i)
            st.rerun()

    updated_budget.append({"類別": new_name, "百分比": new_pct})

# 更新數據
st.session_state.temp_budget = updated_budget

# --- 3. 狀態偵測與寫入邏輯 ---
total_ratio = sum(item['百分比'] for item in st.session_state.temp_budget)

if total_ratio != 100:
    # 改為警告色調，並顯示你要求的文字
    st.warning(f"⚠️ 目前總和：{total_ratio}% -> 「請重新計算」")
else:
    st.success("✅ 比例分配完美")

    st.markdown("### 💰 預算分配預覽")
    for item in st.session_state.temp_budget:
        amt = int(income_amount * (item['百分比'] / 100))
        st.write(f"**{item['類別']}：** ${amt}")

    if st.button("⚡ 確認寫入戰情資料庫"):
        today = datetime.now().strftime('%Y-%m-%d')
        records_to_add = []
        records_to_add.append([today, '收入', source_name, income_amount, '主帳戶', '收入進帳'])

        for item in st.session_state.temp_budget:
            records_to_add.append([
                today, '轉帳', f"{item['類別']}({item['百分比']}%)",
                int(income_amount * (item['百分比'] / 100)),
                item['類別'], '系統自動預算分配'
            ])

        try:
            worksheet.append_rows(records_to_add)
            st.balloons()
            st.success("✅ 戰術執行成功！資料已同步。")
        except Exception as e:
            st.error(f"❌ 寫入失敗：{e}")
