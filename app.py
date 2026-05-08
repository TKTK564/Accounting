import streamlit as st
import gspread
import json
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime

# --- 1. 介面設定 ---
st.set_page_config(page_title="個人財務戰情系統", layout="wide")
st.markdown("""
    <style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    .stTabs [data-baseweb="tab-list"] { gap: 10px; }
    .stTabs [data-baseweb="tab"] { 
        height: 50px; background-color: #adb5bd; color: #212529; border-radius: 5px; padding: 10px 20px; border: 1px solid #6c757d;
    }
    .stTabs [aria-selected="true"] { 
        background-color: #007bff !important; color: white !important; font-weight: bold;
    }
    </style>
    """, unsafe_allow_html=True)

# --- 2. 雲端連線 ---
try:
    credentials = json.loads(st.secrets["gcp_service_account_json"])
    gc = gspread.service_account_from_dict(credentials)
    sh = gc.open('專屬財務戰情資料庫')
    users_sheet = sh.worksheet('使用者名冊')
except Exception as e:
    st.error(f"❌ 雲端連線失敗：{e}")
    st.stop()

# --- 3. 初始化 Session State ---
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.username = ""

# 初始化「預算池定義」
if 'pool_defs' not in st.session_state:
    st.session_state.pool_defs = [
        {"池名": "生活預算", "預算目標": 10000},
        {"池名": "投資帳戶", "預算目標": 5000},
        {"池名": "儲蓄帳戶", "預算目標": 0}
    ]

if 'expense_cats' not in st.session_state:
    st.session_state.expense_cats = ["飲食", "交通", "自我提升", "運動訓練", "娛樂"]

# --- 4. 登入閘門 ---
if not st.session_state.logged_in:
    st.title("🔐 戰情中心登入")
    lt, rt = st.tabs(["🔑 登入", "📝 註冊"])
    with lt:
        u = st.text_input("帳號", key="u_login")
        p = st.text_input("密碼", type="password", key="p_login")
        if st.button("登入系統"):
            recs = users_sheet.get_all_records()
            for r in recs:
                if str(r.get("Username")).strip() == u.strip() and str(r.get("Password")).strip() == p.strip():
                    st.session_state.logged_in = True
                    st.session_state.username = u
                    st.rerun()
            st.error("帳密錯誤")
    with rt:
        nu = st.text_input("新帳號", key="u_reg")
        np = st.text_input("新密碼", type="password", key="p_reg")
        if st.button("註冊"):
            users_sheet.append_row([nu, np])
            sh.add_worksheet(title=nu, rows="1000", cols="10").append_row(["日期", "類型", "類別", "金額", "帳戶", "備註"])
            st.success("註冊成功")
    st.stop()

# --- 5. 數據加載 ---
worksheet = sh.worksheet(st.session_state.username)
records = worksheet.get_all_records()
df = pd.DataFrame(records)
if not df.empty:
    df['金額'] = pd.to_numeric(df['金額'], errors='coerce').fillna(0)
    df['日期'] = pd.to_datetime(df['日期']).dt.date

# ==========================================
# --- 6. 主戰情系統 ---
# ==========================================
colA, colB = st.columns([5, 1])
with colA: st.title(f"🛠️ {st.session_state.username} 的戰略指揮所")
with colB: 
    if st.button("登出 👋"):
        st.session_state.logged_in = False
        st.rerun()

tabs = st.tabs(["📊 戰情看板", "📥 收入金錢分配", "💸 支出登錄", "📁 數據管理", "⚙️ 設定中心"])

# ------------------------------------------
# 【Tab 1：戰情看板】
# ------------------------------------------
with tabs[0]:
    if df.empty:
        st.info("尚無數據，請先開始記帳。")
    else:
        t_in = df[df['類型'] == '收入']['金額'].sum()
        t_ex = df[df['類型'] == '支出']['金額'].sum()
        
        c1, c2, c3 = st.columns(3)
        c1.metric("💰 實質總餘額 (手上現金)", f"${t_in - t_ex:,.0f}")
        c2.metric("📈 累計總收入", f"${t_in:,.0f}")
        c3.metric("📉 累計總支出", f"${t_ex:,.0f}")
        
        st.markdown("---")
        view = st.radio("監控模式：", ["🏦 預算池餘額 (實時扣除)", "🎯 預算執行進度 (目標 vs 實際)", "📉 每日流水趨勢"], horizontal=True)

        if view == "🏦 預算池餘額 (實時扣除)":
            # 邏輯：該帳戶所有轉帳進來的 - 該帳戶付出的支出
            in_pool = df[df['類型'] == '轉帳'].groupby('帳戶')['金額'].sum()
            out_pool = df[df['類型'] == '支出'].groupby('帳戶')['金額'].sum()
            pool_rem = []
            for p_name in in_pool.index:
                rem = in_pool[p_name] - out_pool.get(p_name, 0)
                if rem != 0: pool_rem.append({"預算池": p_name, "現金餘額": rem})
            if pool_rem:
                st.plotly_chart(px.pie(pd.DataFrame(pool_rem), values='現金餘額', names='預算池', hole=0.4, title="各帳戶現金分佈"), use_container_width=True)
                st.dataframe(pd.DataFrame(pool_rem).set_index("預算池"))
            else: st.write("尚無分配資金。")

        elif view == "🎯 預算執行進度 (目標 vs 實際)":
            # 邏輯：對比「設定中心」填寫的預算具體金額 vs 該池子的實際支出
            budget_goals = pd.DataFrame(st.session_state.pool_defs)
            actual_spent = df[df['類型'] == '支出'].groupby('帳戶')['金額'].sum().reset_index()
            actual_spent.columns = ['池名', '實際支出']
            
            comp_df = pd.merge(budget_goals, actual_spent, on='池名', how='left').fillna(0)
            
            fig = go.Figure()
            fig.add_trace(go.Bar(x=comp_df['池名'], y=comp_df['預算目標'], name='設定目標', marker_color='#adb5bd'))
            fig.add_trace(go.Bar(x=comp_df['池名'], y=comp_df['實際支出'], name='實際支出', marker_color='#007bff'))
            fig.update_layout(barmode='overlay', title="預算目標 vs 實際支出 (重疊圖)")
            st.plotly_chart(fig, use_container_width=True)

        elif view == "📉 每日流水趨勢":
            daily = df[df['類型'].isin(['收入', '支出'])].copy()
            daily.loc[daily['類型'] == '支出', '金額'] = -daily['金額']
            daily_sum = daily.groupby('日期')['金額'].sum().reset_index()
            fig = px.bar(daily_sum, x='日期', y='金額', color='金額', 
                         color_continuous_scale=['#dc3545', '#28a745'], title="每日淨流向")
            fig.add_hline(y=0, line_dash="dash")
            st.plotly_chart(fig, use_container_width=True)

# ------------------------------------------
# 【Tab 2：收入金錢分配 (單次動態分配)】
# ------------------------------------------
with tabs[1]:
    st.header("📥 收入金錢分配")
    st.write("每次收入登記後，請手動分配資金進入相對應的帳戶。")
    i_amt = st.number_input("本次進帳金額", min_value=0, step=1000, key="inc_val")
    i_note = st.text_input("來源備註", value="本薪")
    
    st.markdown("---")
    st.write("👉 **請分配以下金額：**")
    
    # 建立動態分配清單
    allocation_results = []
    total_allocated = 0
    
    # 使用表格或列來輸入分配
    for p in st.session_state.pool_defs:
        c1, c2 = st.columns([3, 2])
        with c1: st.write(f"**{p['池名']}**")
        with c2:
            amt = st.number_input(f"分配進入 ${p['池名']}", min_value=0, key=f"alloc_{p['池名']}")
            total_allocated += amt
            allocation_results.append({"池名": p['池名'], "金額": amt})
            
    # 計算剩餘未分配
    rem = i_amt - total_allocated
    if rem > 0:
        st.info(f"尚未分配金額：${rem}")
    elif rem < 0:
        st.error(f"⚠️ 分配金額超過總收入 ${abs(rem)}！「請重新計算」")
    
    if i_amt > 0 and total_allocated == i_amt:
        st.success("✅ 分配完全對齊")
        if st.button("⚡ 確認執行分配寫入"):
            today = datetime.now().strftime('%Y-%m-%d')
            rows = [[today, '收入', '收入進帳', i_amt, '主帳戶', i_note]]
            for r in allocation_results:
                if r['金額'] > 0:
                    rows.append([today, '轉帳', '分配入帳', r['金額'], r['池名'], f"分配自: {i_note}"])
            worksheet.append_rows(rows)
            st.balloons()
            st.rerun()

# ------------------------------------------
# 【Tab 3：支出登錄】
# ------------------------------------------
with tabs[2]:
    st.header("💸 日常支出登錄")
    with st.container(border=True):
        e_n = st.text_input("支出項目")
        e_v = st.number_input("支出金額", min_value=0)
        # 扣款池子必須在「預算池定義」中
        e_p = st.selectbox("從哪個預算池扣款？", [p['池名'] for p in st.session_state.pool_defs])
        e_t = st.selectbox("支出細項類別", st.session_state.expense_cats)
        
        if st.button("🔴 確認支出"):
            if e_v > 0 and e_n:
                worksheet.append_row([datetime.now().strftime('%Y-%m-%d'), '支出', e_t, e_v, e_p, e_n])
                st.success(f"已從 {e_p} 扣除 ${e_v}")
                st.rerun()

# ------------------------------------------
# 【Tab 4：數據管理】
# ------------------------------------------
with tabs[3]:
    st.header("📁 數據修正中心")
    if not df.empty:
        new_df = st.data_editor(df, num_rows="dynamic", use_container_width=True)
        if st.button("💾 同步修正"):
            worksheet.clear()
            worksheet.append_row(["日期", "類型", "類別", "金額", "帳戶", "備註"])
            save_df = new_df.copy()
            save_df['日期'] = save_df['日期'].astype(str)
            worksheet.append_rows(save_df.values.tolist())
            st.success("同步成功")
            st.rerun()

# ------------------------------------------
# 【Tab 5：設定中心 (獨立預算設定)】
# ------------------------------------------
with tabs[4]:
    st.header("⚙️ 設定中心")
    c1, c2 = st.columns(2)
    
    with c1:
        st.subheader("🛠️ 預算池名稱與「預算目標」")
        st.write("預算目標是指你「預計」支出的具體金額。")
        new_defs = []
        for i, p in enumerate(st.session_state.pool_defs):
            with st.container(border=True):
                ca1, ca2 = st.columns([3, 2])
                name = ca1.text_input("池名", p['池名'], key=f"pn_{i}")
                goal = ca2.number_input("每月預算目標 $", value=p['預算目標'], key=f"pg_{i}")
                if st.button(f"🗑️ 刪除 {p['池名']}", key=f"pd_{i}"):
                    st.session_state.pool_defs.pop(i)
                    st.rerun()
                new_defs.append({"池名": name, "預算目標": goal})
        st.session_state.pool_defs = new_defs
        
        add_p = st.text_input("新增池子名稱...")
        if st.button("➕ 新增"):
            st.session_state.pool_defs.append({"池名": add_p, "預算目標": 0})
            st.rerun()

    with c2:
        st.subheader("🛠️ 支出類別 (標籤用)")
        for i, ex in enumerate(st.session_state.expense_cats):
            ca1, ca2 = st.columns([3, 1])
            ca1.write(f"🔹 {ex}")
            if ca2.button("刪除", key=f"ed_{i}"):
                st.session_state.expense_cats.pop(i)
                st.rerun()
        ne = st.text_input("新增支出類別標籤...")
        if st.button("➕ 新增類別"):
            st.session_state.expense_cats.append(ne)
            st.rerun()
