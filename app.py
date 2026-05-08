import streamlit as st
import gspread
import json
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime

# --- 1. 介面與分頁顏色強化 ---
st.set_page_config(page_title="個人財務戰情系統", layout="wide")
st.markdown("""
    <style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    .stTabs [data-baseweb="tab-list"] { gap: 10px; }
    .stTabs [data-baseweb="tab"] { 
        height: 50px; background-color: #ced4da; color: #343a40; border-radius: 5px; padding: 10px 20px; border: 1px solid #adb5bd;
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
    st.error(f"❌ 雲端連線失敗，請檢查 Secrets 設定：{e}")
    st.stop()

# --- 3. 初始化 Session State (防崩潰裝甲) ---
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.username = ""

# 確保預算與支出類別存在
if 'budget_cats' not in st.session_state:
    st.session_state.budget_cats = [
        {"類別": "生活預算", "模式": "百分比", "數值": 50},
        {"類別": "投資帳戶", "模式": "百分比", "數值": 30},
        {"類別": "儲蓄帳戶", "模式": "百分比", "數值": 20}
    ]
else:
    # 修復舊版資料缺失「模式」標籤的問題
    for cat in st.session_state.budget_cats:
        if '模式' not in cat: cat['模式'] = "百分比"
        if '數值' not in cat: cat['數值'] = cat.get('百分比', 0)

if 'expense_cats' not in st.session_state:
    st.session_state.expense_cats = ["飲食", "交通", "自我提升", "運動訓練", "娛樂"]

# --- 4. 登入閘門 (修復黑屏) ---
if not st.session_state.logged_in:
    st.title("🔐 戰情中心登入")
    login_tab, reg_tab = st.tabs(["🔑 帳號登入", "📝 快速註冊"])
    
    with login_tab:
        u = st.text_input("帳號", key="l_u")
        p = st.text_input("密碼", type="password", key="l_p")
        if st.button("確認進入"):
            recs = users_sheet.get_all_records()
            for r in recs:
                if str(r.get("Username")).strip() == u.strip() and str(r.get("Password")).strip() == p.strip():
                    st.session_state.logged_in = True
                    st.session_state.username = u
                    st.rerun()
            st.error("❌ 帳號或密碼不正確")
            
    with reg_tab:
        nu = st.text_input("設定帳號", key="r_u")
        np = st.text_input("設定密碼", type="password", key="r_p")
        if st.button("註冊帳號"):
            if nu and np:
                users_sheet.append_row([nu, np])
                sh.add_worksheet(title=nu, rows="1000", cols="10").append_row(["日期", "類型", "類別", "金額", "帳戶", "備註"])
                st.success("✅ 註冊成功，請切換至登入標籤。")
    st.stop()

# --- 5. 進入主系統 ---
try:
    worksheet = sh.worksheet(st.session_state.username)
except gspread.WorksheetNotFound:
    worksheet = sh.add_worksheet(title=st.session_state.username, rows="1000", cols="10")
    worksheet.append_row(["日期", "類型", "類別", "金額", "帳戶", "備註"])
    st.rerun()

colA, colB = st.columns([5, 1])
with colA: st.title(f"🛠️ {st.session_state.username} 的戰略指揮所")
with colB: 
    if st.button("登出 👋"):
        st.session_state.logged_in = False
        st.rerun()

tabs = st.tabs(["📊 戰情看板", "📥 收入分配", "💸 支出登錄", "📁 數據修正", "⚙️ 類別設定"])

# 讀取雲端數據並預處理
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
        st.info("尚無數據，請先開始記帳。")
    else:
        inc_s = df[df['類型'] == '收入']['金額'].sum()
        exp_s = df[df['類型'] == '支出']['金額'].sum()
        bal = inc_s - exp_s
        
        c1, c2, c3 = st.columns(3)
        c1.metric("💰 當前總資產", f"${bal:,.0f}")
        c2.metric("📈 累計總收入", f"${inc_s:,.0f}")
        c3.metric("📉 累計總支出", f"${exp_s:,.0f}", delta=f"-{exp_s:,.0f}", delta_color="inverse")
        
        st.markdown("---")
        m = st.radio("數據分析：", ["🏦 預算池剩餘", "📅 月度消費佔比", "📉 每日流水趨勢"], horizontal=True)

        if m == "🏦 預算池剩餘":
            # 根據預算池定義抓取帳戶餘額
            trans = df[df['類型'] == '轉帳'].groupby('帳戶')['金額'].sum()
            exps = df[df['類型'] == '支出'].groupby('帳戶')['金額'].sum()
            pool_data = []
            for p in trans.index:
                rem = trans[p] - exps.get(p, 0)
                if rem > 0: pool_data.append({"預算池": p, "餘額": rem})
            if pool_data:
                st.plotly_chart(px.pie(pd.DataFrame(pool_data), values='餘額', names='預算池', hole=0.4, title="各預算池剩餘彈藥"), use_container_width=True)
            else: st.write("預算池目前為空")

        elif m == "📅 月度消費佔比":
            monthly = df[df['類型'] == '支出'].groupby('月份')['金額'].sum().reset_index()
            if not monthly.empty:
                st.plotly_chart(px.pie(monthly, values='金額', names='月份', title="每月消費總額分析"), use_container_width=True)

        elif m == "📉 每日流水趨勢":
            daily = df[df['類型'].isin(['收入', '支出'])].copy()
            daily.loc[daily['類型'] == '支出', '金額'] = -daily['金額']
            daily_sum = daily.groupby(daily['日期'].dt.date)['金額'].sum().reset_index()
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=daily_sum['日期'], y=daily_sum['金額'], mode='lines+markers', name='每日淨額'))
            fig.add_hline(y=0, line_dash="dash", line_color="red")
            st.plotly_chart(fig, use_container_width=True)

# ------------------------------------------
# 【Tab 2：收入分配 (混合模式)】
# ------------------------------------------
with tabs[1]:
    st.header("📥 收入金錢分配")
    inc_v = st.number_input("本次總進帳金額", min_value=0, step=1000)
    inc_n = st.text_input("來源說明", value="本薪")
    
    fixed_sum = sum(c['數值'] for c in st.session_state.budget_cats if c.get('模式') == "固定金額")
    rem_v = inc_v - fixed_sum
    pct_sum = sum(c['數值'] for c in st.session_state.budget_cats if c.get('模式') == "百分比")
    
    alloc_list = []
    st.write(f"已扣除固定金額：${fixed_sum}，剩餘可分配：${rem_v}")
    
    for c in st.session_state.budget_cats:
        mode = c.get('模式', '百分比')
        val = c.get('數值', 0)
        if mode == "固定金額":
            final_a = val
        else:
            final_a = int(rem_v * (val/100)) if rem_v > 0 else 0
        
        st.write(f"📍 **{c['類別']}** ({mode} {val}) -> 預計分配：${final_a}")
        alloc_list.append([c['類別'], final_a, (final_a/inc_v*100) if inc_v > 0 else 0])

    if inc_v > 0 and (fixed_sum > inc_v or (pct_sum != 100 and rem_v > 0)):
        st.warning("⚠️ 分配比例不符或金額溢出 -> 「請重新計算」")
    elif inc_v > 0:
        if st.button("🚀 執行戰略分配"):
            today = datetime.now().strftime('%Y-%m-%d')
            rows = [[today, '收入', inc_n, inc_v, '主帳戶', '收入進帳']]
            for a in alloc_list:
                rows.append([today, '轉帳', f"{a[0]}({a[2]:.1f}%)", a[1], a[0], '自動分配'])
            worksheet.append_rows(rows)
            st.balloons()
            st.rerun()

# ------------------------------------------
# 【Tab 3：支出登錄】
# ------------------------------------------
with tabs[2]:
    st.header("💸 支出登錄")
    with st.container(border=True):
        e_n = st.text_input("支出項目 (如：午餐、拳擊裝備)")
        e_v = st.number_input("支出金額 ", min_value=0)
        e_pool = st.selectbox("從哪個預算池扣款？", [c['類別'] for c in st.session_state.budget_cats])
        e_type = st.selectbox("支出細項類別", st.session_state.expense_cats)
        
        if st.button("🔴 確認支出"):
            if e_v > 0 and e_n:
                worksheet.append_row([datetime.now().strftime('%Y-%m-%d'), '支出', e_type, e_v, e_pool, e_n])
                st.success(f"已從 {e_pool} 扣除 ${e_v}")
                st.rerun()

# ------------------------------------------
# 【Tab 4：數據修正】
# ------------------------------------------
with tabs[3]:
    st.header("📁 數據管理中心")
    if not df.empty:
        # 修正：轉換日期格式以便編輯器正確顯示
        edit_df = df.copy()
        edit_df['日期'] = edit_df['日期'].dt.date
        new_df = st.data_editor(edit_df, num_rows="dynamic", use_container_width=True)
        
        if st.button("💾 同步更新至雲端"):
            worksheet.clear()
            worksheet.append_row(["日期", "類型", "類別", "金額", "帳戶", "備註"])
            save_df = new_df.copy()
            if '月份' in save_df.columns: save_df = save_df.drop(columns=['月份'])
            save_df['日期'] = save_df['日期'].astype(str)
            worksheet.append_rows(save_df.values.tolist())
            st.success("✅ 資料庫同步成功！")
            st.rerun()

# ------------------------------------------
# 【Tab 5：類別設定】
# ------------------------------------------
with tabs[4]:
    st.header("⚙️ 類別與分配模式設定")
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("🛠️ 預算池定義")
        new_b = []
        for i, b in enumerate(st.session_state.budget_cats):
            with st.container(border=True):
                ca1, ca2, ca3 = st.columns([2, 2, 1])
                n = ca1.text_input("名稱", b['類別'], key=f"n_{i}")
                m = ca2.selectbox("模式", ["百分比", "固定金額"], index=0 if b.get('模式')=="百分比" else 1, key=f"m_{i}")
                v = ca3.number_input("值", b.get('數值', 0), key=f"v_{i}")
                if st.button("🗑️", key=f"d_{i}"):
                    st.session_state.budget_cats.pop(i)
                    st.rerun()
                new_b.append({"類別": n, "模式": m, "數值": v})
        st.session_state.budget_cats = new_b
        if st.button("➕ 新增預算池"):
            st.session_state.budget_cats.append({"類別": "新池子", "模式": "百分比", "數值": 0})
            st.rerun()
            
    with c2:
        st.subheader("🛠️ 支出細項定義")
        for i, ex in enumerate(st.session_state.expense_cats):
            st.write(f"🔹 {ex}")
            if st.button("刪除", key=f"ed_{i}"):
                st.session_state.expense_cats.pop(i)
                st.rerun()
        ne = st.text_input("新增支出類別...")
        if st.button("確認新增"):
            st.session_state.expense_cats.append(ne)
            st.rerun()
