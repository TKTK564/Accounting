import pandas as pd
import plotly.express as px
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
                # 抓取資料庫的值，強制轉成文字並消除隱形空白
                db_user = str(row.get("Username", "")).strip()
                db_pw = str(row.get("Password", "")).strip()
                
                # 你輸入的值也消除隱形空白
                input_user = login_user.strip()
                input_pw = login_pw.strip()
                
                if db_user == input_user and db_pw == input_pw:
                    st.session_state.logged_in = True
                    st.session_state.username = input_user
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

# 抓取該登入者的專屬分頁 (加上自動重建防護罩)
try:
    worksheet = sh.worksheet(st.session_state.username)
except gspread.WorksheetNotFound:
    # 如果系統找不到這個人的分頁，就當場幫他蓋一個！
    st.warning("🔧 系統偵測到您的專屬資料庫未建立或遺失，正在自動為您重建...")
    worksheet = sh.add_worksheet(title=st.session_state.username, rows="100", cols="10")
    worksheet.append_row(["日期", "類型", "類別", "金額", "帳戶", "備註"])
    st.rerun() # 建好之後立刻重新整理畫面

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

# --- 建立兩大核心分頁 ---
tab_entry, tab_dashboard = st.tabs(["💰 資金調度 (記帳)", "📈 戰情儀表板 (數據)"])

# ------------------------------------------
# 【分頁 1：資金調度與記帳】
# ------------------------------------------
with tab_entry:
    # --- 新增：日常支出紀錄區 ---
    st.header("💸 1. 日常支出登錄")
    with st.container(border=True):
        expense_name = st.text_input("支出項目", placeholder="例如：拳擊手套、講義費...")
        expense_amount = st.number_input("支出金額", min_value=0, value=0, step=100)
        expense_category = st.selectbox("歸屬預算池", ["生活預算", "自我提升", "運動裝備", "休閒娛樂", "交通", "其他"])
        
        if st.button("🔴 寫入支出"):
            if expense_amount > 0 and expense_name:
                today = datetime.now().strftime('%Y-%m-%d')
                try:
                    worksheet.append_row([today, '支出', expense_category, expense_amount, '主帳戶', expense_name])
                    st.success(f"已記錄支出：{expense_name} ${expense_amount}")
                except Exception as e:
                    st.error(f"寫入失敗：{e}")
            else:
                st.warning("請填寫項目與金額")

    st.markdown("---")

    # --- 原本的：資金匯入與自動分配區 ---
    st.header("📥 2. 資金進帳與戰略分配")
    income_amount = st.number_input("本次進帳金額", min_value=0, value=10000, step=1000)
    source_name = st.text_input("資金來源", value="本薪/獎學金")

    if 'temp_budget' not in st.session_state:
        st.session_state.temp_budget = [
            {"類別": "生活預算", "百分比": 50},
            {"類別": "投資帳戶", "百分比": 30},
            {"類別": "儲蓄帳戶", "百分比": 20}
        ]

    with st.expander("➕ 新增分配類別"):
        new_cat_name = st.text_input("輸入新類別名稱", placeholder="例如：國考基金")
        if st.button("確認新增"):
            if new_cat_name:
                st.session_state.temp_budget.append({"類別": new_cat_name, "百分比": 0})
                st.rerun()

    updated_budget = []
    for i, item in enumerate(st.session_state.temp_budget):
        col_name, col_pct, col_del = st.columns([3, 2, 1])
        with col_name:
            new_name = st.text_input(f"類別-{i}", value=item["類別"], label_visibility="collapsed")
        with col_pct:
            new_pct = st.number_input(f"百分比-{i}", value=item["百分比"], min_value=0, max_value=100, step=1, label_visibility="collapsed")
        with col_del:
            if st.button("🗑️", key=f"del_{i}"):
                st.session_state.temp_budget.pop(i)
                st.rerun()
        updated_budget.append({"類別": new_name, "百分比": new_pct})

    st.session_state.temp_budget = updated_budget
    total_ratio = sum(item['百分比'] for item in st.session_state.temp_budget)

    if total_ratio != 100:
        st.warning(f"⚠️ 目前總和：{total_ratio}% -> 「請重新計算」")
    else:
        st.success("✅ 比例分配完美")
        if st.button("🟢 確認分配並寫入"):
            today = datetime.now().strftime('%Y-%m-%d')
            records_to_add = []
            records_to_add.append([today, '收入', source_name, income_amount, '主帳戶', '收入進帳'])
            for item in st.session_state.temp_budget:
                records_to_add.append([
                    today, '轉帳', f"{item['類別']}({item['百分比']}%)", 
                    int(income_amount * (item['百分比']/100)), item['類別'], '系統自動預算分配'
                ])
            try:
                worksheet.append_rows(records_to_add)
                st.balloons()
                st.success("✅ 資金已完美調度！")
            except Exception as e:
                st.error(f"❌ 寫入失敗：{e}")

# ------------------------------------------
# 【分頁 2：戰情儀表板 (視覺化數據)】
# ------------------------------------------
with tab_dashboard:
    st.header("📈 財務戰情總覽")
    
    # 讀取你的專屬資料庫
    records = worksheet.get_all_records()
    
    if not records:
        st.info("目前資料庫尚無紀錄，請先至「資金調度」分頁新增資料。")
    else:
        # 將資料轉換為 Pandas 數據表以便高速計算
        df = pd.DataFrame(records)
        df['金額'] = pd.to_numeric(df['金額'], errors='coerce').fillna(0) # 確保金額是數字
        
        # 核心計算邏輯
        total_income = df[df['類型'] == '收入']['金額'].sum()
        total_expense = df[df['類型'] == '支出']['金額'].sum()
        current_balance = total_income - total_expense
        
        # 1. 頂部核心指標 (三大看板)
        col1, col2, col3 = st.columns(3)
        col1.metric("💰 總持有餘額", f"${current_balance:,.0f}")
        col2.metric("📥 累計總收入", f"${total_income:,.0f}")
        col3.metric("🔥 累計總支出", f"${total_expense:,.0f}")
        
        st.markdown("---")
        
        # 2. 支出佔比分析 (你要求的百分比圖)
        st.subheader("📊 支出火力分佈 (百分比圖)")
        expense_df = df[df['類型'] == '支出']
        
        if not expense_df.empty:
            # 將相同類別的支出加總
            expense_summary = expense_df.groupby('類別')['金額'].sum().reset_index()
            
            # 使用 Plotly 畫出高質感的甜甜圈圖
            fig = px.pie(
                expense_summary, 
                values='金額', 
                names='類別', 
                hole=0.4, # 調整為甜甜圈造型，更具現代感
                color_discrete_sequence=px.colors.sequential.Agsunset # 戰情室專屬的高級配色
            )
            # 隱藏圖表背景，融入系統
            fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)") 
            
            # 顯示圖表
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.write("目前尚無任何支出紀錄。")
