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
    st.error(f"❌ 雲端連線失敗，請檢查 Secrets：{e}")
    st.stop()

# --- 3. 初始化 Session State ---
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.username = ""

# 初始化預算池與分配策略
if 'pool_config' not in st.session_state:
    st.session_state.pool_config = [
        {"池名": "生活預算", "分配模式": "百分比", "分配值": 50, "支出上限": 10000},
        {"池名": "投資帳戶", "分配模式": "百分比", "分配值": 30, "支出上限": 5000},
        {"池名": "儲蓄帳戶", "分配模式": "固定金額", "分配值": 2000, "支出上限": 0}
    ]

if 'expense_cats' not in st.session_state:
    st.session_state.expense_cats = ["飲食", "交通", "自我提升", "運動訓練", "娛樂"]

# --- 4. 登入閘門 ---
if not st.session_state.logged_in:
    st.title("🔐 戰情中心登入")
    tab_l, tab_r = st.tabs(["🔑 登入", "📝 註冊"])
    with tab_l:
        u = st.text_input("帳號", key="l_u")
        p = st.text_input("密碼", type="password", key="l_p")
        if st.button("確認進入"):
            recs = users_sheet.get_all_records()
            for r in recs:
                if str(r.get("Username")).strip() == u.strip() and str(r.get("Password")).strip() == p.strip():
                    st.session_state.logged_in = True
                    st.session_state.username = u
                    st.rerun()
            st.error("帳密錯誤")
    with tab_r:
        nu = st.text_input("設定新帳號")
        np = st.text_input("設定新密碼", type="password")
        if st.button("立即註冊"):
            users_sheet.append_row([nu, np])
            sh.add_worksheet(title=nu, rows="1000", cols="10").append_row(["日期", "類型", "類別", "金額", "帳戶", "備註"])
            st.success("註冊成功")
    st.stop()

# --- 5. 數據獲取 ---
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

tabs = st.tabs(["📊 戰情看板", "📥 收入分配", "💸 支出登錄", "📁 數據修正", "⚙️ 設定中心"])

# ------------------------------------------
# 【Tab 1：戰情看板】
# ------------------------------------------
with tabs[0]:
    if df.empty:
        st.info("尚無數據，請先開始記帳。")
    else:
        inc_s = df[df['類型'] == '收入']['金額'].sum()
        exp_s = df[df['類型'] == '支出']['金額'].sum()
        
        c1, c2, c3 = st.columns(3)
        c1.metric("💰 實質帳戶總餘額", f"${inc_s - exp_s:,.0f}")
        c2.metric("📈 累計總收入", f"${inc_s:,.0f}")
        c3.metric("📉 累計總支出", f"${exp_s:,.0f}")
        
        st.markdown("---")
        mode = st.radio("監控模式：", ["🏦 預算池餘額 (手上現金)", "🎯 預算執行率 (支出 vs 上限)", "📉 每日流水"], horizontal=True)

        if mode == "🏦 預算池餘額 (手上現金)":
            # 邏輯：分配進來的轉帳 - 從該帳戶付出的支出
            in_p = df[df['類型'] == '轉帳'].groupby('帳戶')['金額'].sum()
            out_p = df[df['類型'] == '支出'].groupby('帳戶')['金額'].sum()
            pool_data = []
            for pool in in_p.index:
                rem = in_p[pool] - out_p.get(pool, 0)
                if rem != 0: pool_data.append({"預算池": pool, "當前餘額": rem})
            if pool_data:
                st.plotly_chart(px.pie(pd.DataFrame(pool_data), values='當前餘額', names='預算池', hole=0.4, title="各帳戶現金分佈"), use_container_width=True)
                st.table(pd.DataFrame(pool_data).set_index("預算池"))
            else: st.write("尚無分配資金紀錄。")

        elif mode == "🎯 預算執行率 (支出 vs 上限)":
            # 邏輯：對比設定的「支出上限」與「實際支出」
            config_df = pd.DataFrame(st.session_state.pool_config)
            real_spent = df[df['類型'] == '支出'].groupby('帳戶')['金額'].sum().reset_index()
            real_spent.columns = ['池名', '實際支出']
            comp_df = pd.merge(config_df, real_spent, left_on='池名', right_on='池名', how='left').fillna(0)
            
            fig = go.Figure()
            fig.add_trace(go.Bar(x=comp_df['池名'], y=comp_df['支出上限'], name='設定支出上限', marker_color='#adb5bd'))
            fig.add_trace(go.Bar(x=comp_df['池名'], y=comp_df['實際支出'], name='實際支出金額', marker_color='#dc3545'))
            fig.update_layout(barmode='overlay', title="預算控管：支出上限 vs 實際花費")
            st.plotly_chart(fig, use_container_width=True)

        elif mode == "📉 每日流水":
            daily = df[df['類型'].isin(['收入', '支出'])].copy()
            daily.loc[daily['類型'] == '支出', '金額'] = -daily['金額']
            daily_sum = daily.groupby('日期')['金額'].sum().reset_index()
            fig = px.bar(daily_sum, x='日期', y='金額', color='金額', color_continuous_scale=['#dc3545', '#28a745'])
            fig.add_hline(y=0, line_dash="dash")
            st.plotly_chart(fig, use_container_width=True)

# ------------------------------------------
# 【Tab 2：收入分配 (混合混合分配模式)】
# ------------------------------------------
with tabs[1]:
    st.header("📥 收入金錢分配")
    inc_v = st.number_input("本次總進帳金額", min_value=0, step=1000)
    inc_n = st.text_input("來源說明", value="本薪")
    
    st.markdown("---")
    st.write("👉 **根據您的設定進行自動分配：**")
    
    # 邏輯計算
    fixed_total = sum(c['分配值'] for c in st.session_state.pool_config if c['分配模式'] == "固定金額")
    remaining_after_fixed = inc_v - fixed_total
    
    allocation_plan = []
    total_planned = 0
    
    for c in st.session_state.pool_config:
        if c['分配模式'] == "固定金額":
            amt = c['分配值']
        else:
            amt = int(remaining_after_fixed * (c['分配值']/100)) if remaining_after_fixed > 0 else 0
        
        st.write(f"🔹 **{c['池名']}** ({c['分配模式']} {c['分配值']}) -> 預計分配：**${amt}**")
        allocation_plan.append({"池名": c['池名'], "金額": amt, "比例": (amt/inc_v*100) if inc_v > 0 else 0})
        total_planned += amt

    st.markdown("---")
    if inc_v > 0:
        if fixed_total > inc_v:
            st.error(f"❌ 固定分配額 (${fixed_total}) 已超過總收入！請重新設定。")
        else:
            if st.button("🚀 執行戰略分配寫入"):
                today = datetime.now().strftime('%Y-%m-%d')
                rows = [[today, '收入', inc_n, inc_v, '主帳戶', '收入總額進帳']]
                for a in allocation_plan:
                    if a['金額'] > 0:
                        rows.append([today, '轉帳', f"分配入帳({a['比例']:.1f}%)", a['金額'], a['池名'], f"分配來源: {inc_n}"])
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
        e_pool = st.selectbox("從哪個預算池扣款？", [c['池名'] for c in st.session_state.pool_config])
        e_type = st.selectbox("支出細項分類", st.session_state.expense_cats)
        
        if st.button("🔴 確定扣款並寫入"):
            if e_v > 0 and e_n:
                worksheet.append_row([datetime.now().strftime('%Y-%m-%d'), '支出', e_type, e_v, e_pool, e_n])
                st.success(f"已從 {e_pool} 扣除 ${e_v}")
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
            st.success("同步成功！")
            st.rerun()

# ------------------------------------------
# 【Tab 5：設定中心】
# ------------------------------------------
with tabs[4]:
    st.header("⚙️ 系統核心設定")
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("🛠️ 預算池與收入分配策略")
        new_configs = []
        for i, config in enumerate(st.session_state.pool_config):
            with st.container(border=True):
                ca1, ca2 = st.columns(2)
                name = ca1.text_input("池子名稱", config['池名'], key=f"cn_{i}")
                mode = ca2.selectbox("分配模式", ["百分比", "固定金額"], index=0 if config['分配模式']=="百分比" else 1, key=f"cm_{i}")
                
                cb1, cb2 = st.columns(2)
                val = cb1.number_input("分配數值 (% 或 $)", config['分配值'], key=f"cv_{i}")
                limit = cb2.number_input("每月支出上限 (預算目標) $", config['支出上限'], key=f"cl_{i}")
                
                if st.button(f"🗑️ 刪除 {config['池名']}", key=f"cd_{i}"):
                    st.session_state.pool_config.pop(i)
                    st.rerun()
                new_configs.append({"池名": name, "分配模式": mode, "分配值": val, "支出上限": limit})
        st.session_state.pool_config = new_configs
        if st.button("➕ 新增預算池定義"):
            st.session_state.pool_config.append({"池名": "新池子", "分配模式": "百分比", "分配值": 0, "支出上限": 0})
            st.rerun()
            
    with c2:
        st.subheader("🛠️ 支出細項類別管理")
        for i, ex in enumerate(st.session_state.expense_cats):
            st.write(f"🔹 {ex}")
            if st.button("刪除項目", key=f"ed_{i}"):
                st.session_state.expense_cats.pop(i)
                st.rerun()
        add_e = st.text_input("新增細項類別名稱...")
        if st.button("➕ 確認新增"):
            st.session_state.expense_cats.append(add_e)
            st.rerun()
