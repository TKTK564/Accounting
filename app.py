import streamlit as st
import gspread
import json
import pandas as pd
import plotly.express as px
from datetime import datetime

# --- 1. 介面設定 ---
st.set_page_config(page_title="個人財務戰情系統", layout="centered")
st.markdown("""
    <style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    .stTabs [data-baseweb="tab-list"] { gap: 10px; }
    .stTabs [data-baseweb="tab"] { 
        height: 50px; 
        background-color: #dee2e6; 
        color: #495057; 
        border-radius: 5px; 
        padding: 10px; 
        border: 1px solid #ced4da;
    }
    .stTabs [aria-selected="true"] { 
        background-color: #007bff !important; 
        color: white !important; 
        font-weight: bold;
    }
    </style>
    """, unsafe_allow_html=True)

# --- 2. 連線 Google Sheets ---
credentials = json.loads(st.secrets["gcp_service_account_json"])
gc = gspread.service_account_from_dict(credentials)
sh = gc.open('專屬財務戰情資料庫')
users_sheet = sh.worksheet('使用者名冊')

# --- 3. 初始化 Session State ---
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.username = ""

if 'budget_cats' not in st.session_state:
    st.session_state.budget_cats = [{"類別": "生活預算", "百分比": 50}, {"類別": "投資帳戶", "百分比": 30}, {"類別": "儲蓄帳戶", "百分比": 20}]

if 'expense_cats' not in st.session_state:
    st.session_state.expense_cats = ["飲食", "交通", "自我提升", "運動裝備", "休閒娛樂"]

# --- 4. 登入閘門 ---
if not st.session_state.logged_in:
    st.title("🔐 戰情中心登入閘門")
    tab1, tab2 = st.tabs(["🔑 登入", "📝 註冊新帳號"])
    with tab1:
        login_user = st.text_input("帳號", key="login_user")
        login_pw = st.text_input("密碼", type="password", key="login_pw")
        if st.button("登入系統"):
            records = users_sheet.get_all_records()
            user_found = False
            for row in records:
                if str(row.get("Username")).strip() == login_user.strip() and str(row.get("Password")).strip() == login_pw.strip():
                    st.session_state.logged_in = True
                    st.session_state.username = login_user
                    user_found = True
                    st.rerun()
            if not user_found:
                st.error("❌ 帳號或密碼錯誤。")
    with tab2:
        reg_user = st.text_input("設定新帳號", key="reg_user")
        reg_pw = st.text_input("設定密碼", type="password", key="reg_pw")
        if st.button("確認註冊"):
            if reg_user and reg_pw:
                users_sheet.append_row([reg_user, reg_pw])
                new_ws = sh.add_worksheet(title=reg_user, rows="1000", cols="10")
                new_ws.append_row(["日期", "類型", "類別", "金額", "帳戶", "備註"])
                st.success("✅ 註冊成功，請登入。")
    st.stop()

# --- 5. 分頁檢查 ---
try:
    worksheet = sh.worksheet(st.session_state.username)
except gspread.WorksheetNotFound:
    worksheet = sh.add_worksheet(title=st.session_state.username, rows="1000", cols="10")
    worksheet.append_row(["日期", "類型", "類別", "金額", "帳戶", "備註"])
    st.rerun()

# ==========================================
# --- 6. 主戰情系統 ---
# ==========================================
colA, colB = st.columns([4, 1])
with colA:
    st.title(f"🛠️ {st.session_state.username} 的戰略儀表板")
with colB:
    if st.button("登出 👋"):
        st.session_state.logged_in = False
        st.rerun()

tab_dash, tab_income, tab_expense, tab_setting = st.tabs(["📊 戰情看板", "📥 收入分配", "💸 日常支出", "⚙️ 類別設定"])

# ------------------------------------------
# 【分頁 1：戰情看板】
# ------------------------------------------
with tab_dash:
    records = worksheet.get_all_records()
    if not records:
        st.info("尚無數據，請先開始記帳。")
    else:
        df = pd.DataFrame(records)
        df['金額'] = pd.to_numeric(df['金額'], errors='coerce').fillna(0)
        df['日期'] = pd.to_datetime(df['日期']).dt.date
        
        income_sum = df[df['類型'] == '收入']['金額'].sum()
        expense_sum = df[df['類型'] == '支出']['金額'].sum()
        balance = income_sum - expense_sum
        
        c1, c2, c3 = st.columns(3)
        c1.metric("💰 當前總資產", f"${balance:,.0f}")
        c2.metric("📈 累計總收入", f"${income_sum:,.0f}")
        c3.metric("📉 累計總支出", f"${expense_sum:,.0f}", delta=f"-{expense_sum:,.0f}", delta_color="inverse")
        
        st.markdown("---")
        
        # 視覺化模式切換器
        viz_mode = st.radio(
            "選擇視覺化分析模式：", 
            ["🔥 支出比例 (圓餅圖)", "🏦 資產分佈 (圓餅圖)", "📈 財務趨勢 (折線圖)"],
            horizontal=True
        )

        if viz_mode == "🔥 支出比例 (圓餅圖)":
            exp_df = df[df['類型'] == '支出']
            if not exp_df.empty:
                summary = exp_df.groupby('類別')['金額'].sum().reset_index()
                fig = px.pie(summary, values='金額', names='類別', hole=0.4, title="各項支出佔比", color_discrete_sequence=px.colors.qualitative.Pastel)
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.write("目前無支出紀錄。")

        elif viz_mode == "🏦 資產分佈 (圓餅圖)":
            # 計算邏輯：(各類別轉帳總額) - (該類別支出總額)
            trans_df = df[df['類型'] == '轉帳'].groupby('帳戶')['金額'].sum()
            exp_sum_df = df[df['類型'] == '支出'].groupby('類別')['金額'].sum()
            
            asset_data = []
            for pool in trans_df.index:
                spent = exp_sum_df.get(pool, 0)
                remaining = trans_df[pool] - spent
                if remaining > 0:
                    asset_data.append({"預算池": pool, "餘額": remaining})
            
            if asset_data:
                asset_df = pd.DataFrame(asset_data)
                fig = px.pie(asset_df, values='餘額', names='預算池', hole=0.4, title="各帳戶資產分佈", color_discrete_sequence=px.colors.sequential.Tealgrn)
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.write("目前尚無分配後的資產。")

        elif viz_mode == "📈 財務趨勢 (折線圖)":
            # 建立時間序列數據
            trend_df = df.sort_values('日期')
            # 每日加總
            daily = trend_df.groupby(['日期', '類型'])['金額'].sum().unstack(fill_value=0).reset_index()
            
            # 如果缺項補 0
            for col in ['收入', '支出']:
                if col not in daily.columns:
                    daily[col] = 0
            
            # 計算累計金額
            daily['累計收入'] = daily['收入'].cumsum()
            daily['累計支出'] = daily['支出'].cumsum()
            daily['淨資產趨勢'] = daily['累計收入'] - daily['累計支出']
            
            fig = px.line(daily, x='日期', y=['累計收入', '累計支出', '淨資產趨勢'], 
                          title="財務成長曲線",
                          labels={'value': '金額', 'variable': '指標'},
                          color_discrete_map={'累計收入': '#28a745', '累計支出': '#dc3545', '淨資產趨勢': '#007bff'})
            st.plotly_chart(fig, use_container_width=True)

# ------------------------------------------
# 其餘分頁 (維持原本代碼邏輯)
# ------------------------------------------
with tab_income:
    st.header("📥 資金匯入與預算自動化")
    inc_amt = st.number_input("本次進帳金額", min_value=0, value=0, step=1000)
    inc_note = st.text_input("資金來源備註", value="本薪/獎學金")
    st.markdown("##### 📍 當前分配比例設定")
    total_p = 0
    temp_budget = []
    for i, item in enumerate(st.session_state.budget_cats):
        col1, col2 = st.columns([3, 2])
        with col1: st.write(f"**{item['類別']}**")
        with col2:
            p = st.number_input(f"比例 %", value=item['百分比'], key=f"p_{i}", min_value=0, max_value=100)
        total_p += p
        temp_budget.append({"類別": item['類別'], "百分比": p})

    if total_p != 100:
        st.warning(f"⚠️ 當前總計：{total_p}% -> 「請重新計算」")
    else:
        st.success("✅ 比例分配完美")
        if st.button("⚡ 執行自動分配寫入"):
            today = datetime.now().strftime('%Y-%m-%d')
            rows = [[today, '收入', inc_note, inc_amt, '主帳戶', '收入進帳']]
            for b in temp_budget:
                rows.append([today, '轉帳', f"{b['類別']}({b['百分比']}%)", int(inc_amt * (b['百分比']/100)), b['類別'], '系統分配'])
            worksheet.append_rows(rows)
            st.balloons()
            st.success("資料已寫入！")

with tab_expense:
    st.header("💸 支出登錄")
    with st.container(border=True):
        exp_item = st.text_input("支出項目名稱")
        exp_amt = st.number_input("支出金額", min_value=0, value=0)
        exp_cat = st.selectbox("選擇支出類別", st.session_state.expense_cats)
        if st.button("🔴 確認支出"):
            if exp_amt > 0:
                today = datetime.now().strftime('%Y-%m-%d')
                worksheet.append_row([today, '支出', exp_cat, exp_amt, '主帳戶', exp_item])
                st.success(f"已記錄：{exp_item} ${exp_amt}")
            else:
                st.warning("請輸入正確金額")

with tab_setting:
    st.header("⚙️ 系統類別設定")
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("🛠️ 預算分配類別")
        new_budget_cats = []
        for i, b in enumerate(st.session_state.budget_cats):
            c1, c2 = st.columns([3, 1])
            with c1:
                n = st.text_input(f"預算-{i}", value=b['類別'], label_visibility="collapsed")
            with c2:
                if st.button("🗑️", key=f"del_b_{i}"):
                    st.session_state.budget_cats.pop(i)
                    st.rerun()
            new_budget_cats.append({"類別": n, "百分比": b['百分比']})
        st.session_state.budget_cats = new_budget_cats
        new_b = st.text_input("新增預算類別...")
        if st.button("➕ 新增預算"):
            st.session_state.budget_cats.append({"類別": new_b, "百分比": 0})
            st.rerun()
    with col2:
        st.subheader("🛠️ 支出項目類別")
        for i, e in enumerate(st.session_state.expense_cats):
            c1, c2 = st.columns([3, 1])
            with c1: st.write(e)
            with c2:
                if st.button("🗑️", key=f"del_e_{i}"):
                    st.session_state.expense_cats.pop(i)
                    st.rerun()
        new_e = st.text_input("新增支出類別...")
        if st.button("➕ 新增項目"):
            st.session_state.expense_cats.append(new_e)
            st.rerun()
