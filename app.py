import streamlit as st
import gspread
import json
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime

# --- 1. 介面設定 (視覺強化) ---
st.set_page_config(page_title="個人財務戰情系統", layout="wide") # 改為寬版，方便編輯資料
st.markdown("""
    <style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    .stTabs [data-baseweb="tab-list"] { gap: 10px; }
    .stTabs [data-baseweb="tab"] { 
        height: 50px; 
        background-color: #ced4da; /* 較深的灰色 */
        color: #495057; 
        border-radius: 5px; 
        padding: 10px 20px;
        border: 1px solid #adb5bd;
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

# 預設類別設定 (如果使用者沒設定過)
if 'budget_cats' not in st.session_state:
    st.session_state.budget_cats = [{"類別": "生活預算", "百分比": 50}, {"類別": "投資帳戶", "百分比": 30}, {"類別": "儲蓄帳戶", "百分比": 20}]
if 'expense_cats' not in st.session_state:
    st.session_state.expense_cats = ["飲食", "交通", "自我提升", "運動裝備", "休閒娛樂"]

# --- 4. 登入閘門 ---
if not st.session_state.logged_in:
    st.title("🔐 戰情中心登入閘門")
    t1, t2 = st.tabs(["🔑 登入", "📝 註冊"])
    with t1:
        u = st.text_input("帳號")
        p = st.text_input("密碼", type="password")
        if st.button("進入系統"):
            recs = users_sheet.get_all_records()
            for r in recs:
                if str(r.get("Username")).strip() == u.strip() and str(r.get("Password")).strip() == p.strip():
                    st.session_state.logged_in = True
                    st.session_state.username = u
                    st.rerun()
            st.error("❌ 帳密不符")
    with t2:
        nu = st.text_input("新帳號")
        np = st.text_input("新密碼", type="password")
        if st.button("註冊"):
            if nu and np:
                users_sheet.append_row([nu, np])
                new_ws = sh.add_worksheet(title=nu, rows="1000", cols="10")
                new_ws.append_row(["日期", "類型", "類別", "金額", "帳戶", "備註"])
                st.success("✅ 註冊成功")
    st.stop()

# --- 5. 分頁自動建檔檢查 ---
try:
    worksheet = sh.worksheet(st.session_state.username)
except gspread.WorksheetNotFound:
    worksheet = sh.add_worksheet(title=st.session_state.username, rows="1000", cols="10")
    worksheet.append_row(["日期", "類型", "類別", "金額", "帳戶", "備註"])
    st.rerun()

# ==========================================
# --- 6. 主戰情系統 ---
# ==========================================
colA, colB = st.columns([5, 1])
with colA:
    st.title(f"🛠️ {st.session_state.username} 的戰略指揮所")
with colB:
    if st.button("登出 👋"):
        st.session_state.logged_in = False
        st.rerun()

tabs = st.tabs(["📊 戰情看板", "📥 收入分配", "💸 支出登錄", "📁 數據管理", "⚙️ 類別設定"])

# 讀取資料庫
records = worksheet.get_all_records()
df = pd.DataFrame(records)
if not df.empty:
    df['金額'] = pd.to_numeric(df['金額'], errors='coerce').fillna(0)
    df['日期'] = pd.to_datetime(df['日期'])
    df['月份'] = df['日期'].dt.strftime('%Y-%m')

# ------------------------------------------
# 【Tab 1：戰情看板】
# ------------------------------------------
with tabs[0]:
    if df.empty:
        st.info("尚無數據")
    else:
        # 三大看板
        inc_sum = df[df['類型'] == '收入']['金額'].sum()
        exp_sum_total = df[df['類型'] == '支出']['金額'].sum()
        bal = inc_sum - exp_sum_total
        
        c1, c2, c3 = st.columns(3)
        c1.metric("💰 當前總資產", f"${bal:,.0f}")
        c2.metric("📈 累計收入", f"${inc_sum:,.0f}")
        c3.metric("📉 累計支出", f"${exp_sum_total:,.0f}", delta=f"-{exp_sum_total:,.0f}", delta_color="inverse")
        
        st.markdown("---")
        mode = st.radio("視覺化模式：", ["🔥 支出佔比", "🏦 預算池餘額 (已連線)", "📅 月度消費分析", "📈 每日流水"], horizontal=True)

        if mode == "🔥 支出佔比":
            exp_df = df[df['類型'] == '支出']
            if not exp_df.empty:
                fig = px.pie(exp_df, values='金額', names='類別', hole=0.4, title="支出類別分佈", color_discrete_sequence=px.colors.qualitative.Pastel)
                st.plotly_chart(fig, use_container_width=True)

        elif mode == "🏦 預算池餘額 (已連線)":
            # 精準邏輯：該帳戶的轉入 - 該帳戶的支出
            trans = df[df['類型'] == '轉帳'].groupby('帳戶')['金額'].sum()
            exps = df[df['類型'] == '支出'].groupby('帳戶')['金額'].sum()
            pool_data = []
            for p in trans.index:
                rem = trans[p] - exps.get(p, 0)
                if rem > 0: pool_data.append({"預算池": p, "餘額": rem})
            if pool_data:
                fig = px.pie(pd.DataFrame(pool_data), values='餘額', names='預算池', hole=0.4, title="各預算池剩餘彈藥")
                st.plotly_chart(fig, use_container_width=True)
            else: st.write("預算池目前為空")

        elif mode == "📅 月度消費分析":
            # 呈現每個月的支出總額圓餅圖
            monthly_exp = df[df['類型'] == '支出'].groupby('月份')['金額'].sum().reset_index()
            if not monthly_exp.empty:
                fig = px.pie(monthly_exp, values='金額', names='月份', title="每個月支出總額佔比", color_discrete_sequence=px.colors.sequential.RdBu)
                st.plotly_chart(fig, use_container_width=True)
                st.dataframe(monthly_exp.set_index('月份'))
            else: st.write("尚無月度支出數據")

        elif mode == "📈 每日流水":
            daily = df[df['類型'].isin(['收入', '支出'])].copy()
            daily.loc[daily['類型'] == '支出', '金額'] = -daily['金額']
            daily_sum = daily.groupby(daily['日期'].dt.date)['金額'].sum().reset_index()
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=daily_sum['日期'], y=daily_sum['金額'], mode='lines+markers', name='每日淨流'))
            fig.add_hline(y=0, line_dash="dash", line_color="red")
            st.plotly_chart(fig, use_container_width=True)

# ------------------------------------------
# 【Tab 2：收入分配】
# ------------------------------------------
with tabs[1]:
    st.header("📥 資金匯入分配")
    inc_val = st.number_input("進帳金額", min_value=0, step=1000)
    inc_note = st.text_input("來源說明", value="本薪")
    total_p = sum(c['百分比'] for c in st.session_state.budget_cats)
    
    if total_p != 100:
        st.warning(f"⚠️ 分配比例總計：{total_p}% -> 「請重新計算」")
    else:
        st.success("✅ 比例分配完美")
        if st.button("🚀 執行自動分配"):
            today = datetime.now().strftime('%Y-%m-%d')
            rows = [[today, '收入', inc_note, inc_val, '主帳戶', '收入進帳']]
            for b in st.session_state.budget_cats:
                rows.append([today, '轉帳', f"{b['類別']}({b['百分比']}%)", int(inc_val * (b['百分比']/100)), b['類別'], '系統分配'])
            worksheet.append_rows(rows)
            st.balloons()
            st.rerun()

# ------------------------------------------
# 【Tab 3：支出登錄 (連線扣款機制)】
# ------------------------------------------
with tabs[2]:
    st.header("💸 日常支出紀錄")
    with st.container(border=True):
        e_item = st.text_input("支出什麼？ (備註)")
        e_amt = st.number_input("花了多少？", min_value=0)
        # 關鍵：選擇從哪個預算池扣款
        pool_opts = [c['類別'] for c in st.session_state.budget_cats]
        e_pool = st.selectbox("從哪個預算池扣款？", pool_opts)
        e_cat = st.selectbox("支出類別", st.session_state.expense_cats)
        
        if st.button("🔴 確認支出"):
            if e_amt > 0:
                today = datetime.now().strftime('%Y-%m-%d')
                # 這裡的「帳戶」欄位存的是預算池名稱，這就是連動的關鍵！
                worksheet.append_row([today, '支出', e_cat, e_amt, e_pool, e_item])
                st.success(f"已從 {e_pool} 扣除 ${e_amt}")
                st.rerun()

# ------------------------------------------
# 【Tab 4：數據管理 (更改紀錄功能)】
# ------------------------------------------
with tabs[3]:
    st.header("📁 數據修正中心")
    st.write("可在下方表格直接修改內容，或勾選左側進行刪除。修改完請點擊下方的「💾 同步修正至雲端」。")
    
    if not df.empty:
        # 使用 data_editor 讓使用者直接編輯
        # 注意：我們需要保留原本的順序以便寫回
        edited_df = st.data_editor(df, num_rows="dynamic", use_container_width=True)
        
        if st.button("💾 同步修正至雲端"):
            try:
                # 1. 清空原本的工作表內容 (保留標題)
                worksheet.clear()
                worksheet.append_row(["日期", "類型", "類別", "金額", "帳戶", "備註"])
                
                # 2. 處理資料格式並寫回
                # 轉換日期回字串格式，避免 Google Sheets 報錯
                output_df = edited_df.copy()
                if '月份' in output_df.columns: output_df = output_df.drop(columns=['月份'])
                output_df['日期'] = output_df['日期'].dt.strftime('%Y-%m-%d')
                
                # 將資料轉換為列表格式寫入
                worksheet.append_rows(output_df.values.tolist())
                st.success("✅ 雲端資料已完美同步修正！")
                st.rerun()
            except Exception as e:
                st.error(f"同步失敗：{e}")
    else:
        st.write("目前沒有紀錄可管理")

# ------------------------------------------
# 【Tab 5：類別設定】
# ------------------------------------------
with tabs[4]:
    # (此處維持之前的類別管理邏輯)
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("🛠️ 預算池管理")
        new_b_cats = []
        for i, b in enumerate(st.session_state.budget_cats):
            ca1, ca2 = st.columns([3, 1])
            with ca1: n = st.text_input(f"池-{i}", value=b['類別'], label_visibility="collapsed")
            with ca2:
                if st.button("🗑️", key=f"db_{i}"):
                    st.session_state.budget_cats.pop(i)
                    st.rerun()
            p = st.number_input(f"比例-{i}", value=b['百分比'], key=f"bp_{i}", min_value=0, max_value=100)
            new_b_cats.append({"類別": n, "百分比": p})
        st.session_state.budget_cats = new_budget_cats
        if st.button("➕ 新增預算池"):
            st.session_state.budget_cats.append({"類別": "新類別", "百分比": 0})
            st.rerun()
    with c2:
        st.subheader("🛠️ 支出類別管理")
        for i, e in enumerate(st.session_state.expense_cats):
            ca1, ca2 = st.columns([3, 1])
            with ca1: st.write(e)
            with ca2:
                if st.button("🗑️", key=f"de_{i}"):
                    st.session_state.expense_cats.pop(i)
                    st.rerun()
        new_e = st.text_input("新增支出項目...")
        if st.button("➕ 新增項目"):
            st.session_state.expense_cats.append(new_e)
            st.rerun()
