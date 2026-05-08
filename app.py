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

# --- 2. 升級後的動態預算設定區 ---
st.header("2. 戰略分配設定 (自定義)")

# 預設一些分類，但使用者可以隨意修改、新增或刪除
if 'budget_settings' not in st.session_state:
    st.session_state.budget_settings = [
        {"類別": "生活預算", "百分比": 50},
        {"類別": "投資帳戶", "百分比": 30},
        {"類別": "儲蓄帳戶", "百分比": 20}
    ]

# 使用 data_editor 讓使用者直接在介面上修改「類別名稱」和「百分比」
edited_df = st.data_editor(
    st.session_state.budget_settings,
    num_rows="dynamic",  # 允許使用者自行新增或刪除列
    key="budget_editor",
    use_container_width=True
)

# 計算總百分比
total_ratio = sum(item['百分比'] for item in edited_df)

# --- 3. 視覺化預覽與寫入邏輯 (終極整合版) ---
if total_ratio != 100:
    st.error(f"⚠️ 目前總和為 {total_ratio}%，請調整至 100% 以執行分配。")
else:
    st.success("✅ 比例分配完美")

    # 動態預覽計算結果 (根據使用者自訂的類別跑迴圈)
    st.markdown("### 💰 預算分配預覽")
    for item in edited_df:
        calculated_amount = int(income_amount * (item['百分比'] / 100))
        st.write(f"**{item['類別']}：** ${calculated_amount}")

    st.markdown("---")

    # 唯一且強大的寫入按鈕
    if st.button("⚡ 確認寫入戰情資料庫"):
        today = datetime.now().strftime('%Y-%m-%d')
        records_to_add = []

        # 1. 紀錄總收入
        records_to_add.append([today, '收入', source_name, income_amount, '主帳戶', '收入進帳'])

        # 2. 根據使用者自定義的分類，跑迴圈產出紀錄
        for item in edited_df:
            cat_name = item['類別']
            ratio = item['百分比']
            allocated_amount = int(income_amount * (ratio / 100))

            records_to_add.append([
                today,
                '轉帳',
                f'{cat_name}({ratio}%)',
                allocated_amount,
                cat_name,  # 直接以自定義的名稱作為「帳戶」名稱
                '系統自動預算分配'
            ])

        # 3. 執行寫入 (加上錯誤捕捉)
        try:
            worksheet.append_rows(records_to_add)
            st.balloons()
            st.success("✅ 戰術執行成功！資料已同步至您的專屬雲端資料庫。")
        except Exception as e:
            st.error(f"❌ 寫入失敗，請檢查權限或連線：{e}")
