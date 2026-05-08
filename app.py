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
    st.error(f"❌ 雲端連線失敗：{e}")
    st.stop()

# --- 3. 初始化 Session State ---
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.username = ""

if 'budget_cats' not in st.session_state:
    st.session_state.budget_cats = [
        {"類別": "生活預算", "模式": "百分比", "數值": 50},
        {"類別": "投資帳戶", "模式": "百分比", "數值": 30},
        {"類別": "儲蓄帳戶", "模式": "百分比", "數值": 20}
    ]
if 'expense_cats' not in st.session_state:
    st.session_state.expense_cats = ["飲食", "交通", "自我提升", "運動訓練", "娛樂"]

# --- 4. 登入閘門 ---
if not st.session_state.logged_in:
    st.title("🔐 戰情中心登入")
    lt, rt = st.tabs(["🔑 登入", "📝 註冊"])
    with lt:
        u = st.text_input("帳號", key="u")
        p = st.text_input("密碼", type="password", key="p")
        if st.button("登入"):
            recs = users_sheet.get_all_records()
            for r in recs:
                if str(r.get("Username")).strip() == u.strip() and str(r.get("Password")).strip() == p.strip():
                    st.session_state.logged_in = True
                    st.session_state.username = u
                    st.rerun()
            st.error("帳密錯誤")
    with rt:
        nu = st.text_input("新帳號")
        np = st.text_input("新密碼", type="password")
        if st.button("確認註冊"):
            users_sheet.append_row([nu, np])
            sh.add_worksheet(title=nu, rows="1000", cols="10").append_row(["日期", "類型", "類別", "金額", "帳戶", "備註"])
            st.success("註冊成功")
    st.stop()

# --- 5. 數據處理 ---
worksheet = sh.worksheet(st.session_state.username)
records = worksheet.get_all_records()
df = pd.DataFrame(records)
if not df.empty:
    df['金額'] = pd.to_numeric(df['金額'], errors='coerce').fillna(0)
    df['日期'] = pd.to_datetime(df['日期']).dt.date

# ==========================================
# --- 6. 主系統 ---
# ==========================================
colA, colB = st.columns([5, 1])
with colA: st.title(f"🛠️ {st.session_state.username} 的財務指揮所")
with colB: 
    if st.button("登出 👋"):
        st.session_state.logged_in = False
        st.rerun()

tabs = st.tabs(["📊 戰情看板", "📥 資金分配", "💸 支出登錄", "📁 數據管理", "⚙️ 設定"])

# ------------------------------------------
# 【Tab 1：戰情看板】
# ------------------------------------------
with tabs[0]:
    if df.empty:
        st.info("尚無數據")
    else:
        # 指標
        total_in = df[df['類型'] == '收入']['金額'].sum()
        total_ex = df[df['類型'] == '支出']['金額'].sum()
        c1, c2, c3 = st.columns(3)
        c1.metric("💰 當前總餘額", f"${total_in - total_ex:,.0f}")
        c2.metric("📈 累計總收入", f"${total_in:,.0f}")
        c3.metric("📉 累計總支出", f"${total_ex:,.0f}")
        
        st.markdown("---")
        # 視覺化選單
        viz = st.radio("數據分析模式：", ["🏦 預算池剩餘 (連動)", "📉 每日流水趨勢", "💰 總收入結構", "💸 總支出結構"], horizontal=True)

        if viz == "🏦 預算池剩餘 (連動)":
            # 邏輯：該帳戶轉入 - 該帳戶支出
            in_pool = df[df['類型'] == '轉帳'].groupby('帳戶')['金額'].sum()
            out_pool = df[df['類型'] == '支出'].groupby('帳戶')['金額'].sum()
            pool_data = []
            for p in in_pool.index:
                rem = in_pool[p] - out_pool.get(p, 0)
                if rem != 0: pool_data.append({"預算池": p, "餘額": rem})
            if pool_data:
                fig = px.pie(pd.DataFrame(pool_data), values='餘額', names='預算池', hole=0.4, title="各預算池剩餘資金")
                st.plotly_chart(fig, use_container_width=True)
            else: st.write("無預算分配紀錄")

        elif viz == "📉 每日流水趨勢":
            # 聚合每日收入與支出
            daily_in = df[df['類型'] == '收入'].groupby('日期')['金額'].sum().reset_index(name='收入')
            daily_ex = df[df['類型'] == '支出'].groupby('日期')['金額'].sum().reset_index(name='支出')
            daily_merge = pd.merge(daily_in, daily_ex, on='日期', how='outer').fillna(0)
            daily_merge = daily_merge.sort_values('日期')
            
            fig = go.Figure()
            # 收入柱狀圖
            fig.add_trace(go.Bar(x=daily_merge['日期'], y=daily_merge['收入'], name='每日收入', marker_color='#28a745', 
                                 hovertemplate='日期: %{x}<br>收入: $%{y}<extra></extra>'))
            # 支出柱狀圖 (顯示為負數但 hover 顯示正數)
            fig.add_trace(go.Bar(x=daily_merge['日期'], y=-daily_merge['支出'], name='每日支出', marker_color='#dc3545',
                                 hovertemplate='日期: %{x}<br>支出: $%{customdata}<extra></extra>',
                                 customdata=daily_merge['支出']))
            
            fig.update_layout(barmode='relative', title="每日資金流向 (X軸為日期)", xaxis_tickformat='%Y-%m-%d')
            st.plotly_chart(fig, use_container_width=True)

        elif viz == "💰 總收入結構":
            inc_df = df[df['類型'] == '收入']
            if not inc_df.empty:
                # 這裡依據「備註」來分類收入來源
                fig = px.pie(inc_df, values='金額', names='備註', title="總收入來源分析", color_discrete_sequence=px.colors.sequential.Greens)
                st.plotly_chart(fig, use_container_width=True)

        elif viz == "💸 總支出結構":
            exp_df = df[df['類型'] == '支出']
            if not exp_df.empty:
                fig = px.pie(exp_df, values='金額', names='類別', title="總支出項目佔比", color_discrete_sequence=px.colors.sequential.Reds)
                st.plotly_chart(fig, use_container_width=True)

# ------------------------------------------
# 【Tab 2：收入分配】
# ------------------------------------------
with tabs[1]:
    st.header("📥 收入金錢分配")
    i_v = st.number_input("本次進帳總額", min_value=0, step=1000)
    i_n = st.text_input("來源說明", value="本薪")
    
    fixed_v = sum(c['數值'] for c in st.session_state.budget_cats if c['模式'] == "固定金額")
    rem_v = i_v - fixed_v
    
    alloc = []
    for c in st.session_state.budget_cats:
        if c['模式'] == "固定金額":
            amt = c['數值']
        else:
            amt = int(rem_v * (c['數值']/100)) if rem_v > 0 else 0
        st.write(f"🔹 {c['類別']}: 分配 **${amt}**")
        alloc.append([c['類別'], amt])
    
    if i_v > 0 and st.button("🚀 確認分配寫入"):
        today = datetime.now().strftime('%Y-%m-%d')
        rows = [[today, '收入', i_n, i_v, '主帳戶', i_n]]
        for a in alloc:
            rows.append([today, '轉帳', '系統分配', a[1], a[0], '自動撥款'])
        worksheet.append_rows(rows)
        st.balloons()
        st.rerun()

# ------------------------------------------
# 【Tab 3：支出登錄】
# ------------------------------------------
with tabs[2]:
    st.header("💸 支出登錄")
    with st.container(border=True):
        e_n = st.text_input("支出項目")
        e_v = st.number_input("金額 ", min_value=0)
        e_p = st.selectbox("扣款預算池", [c['類別'] for c in st.session_state.budget_cats])
        e_t = st.selectbox("支出細項類別", st.session_state.expense_cats)
        if st.button("🔴 寫入支出"):
            if e_v > 0:
                worksheet.append_row([datetime.now().strftime('%Y-%m-%d'), '支出', e_t, e_v, e_p, e_n])
                st.success("寫入成功")
                st.rerun()

# ------------------------------------------
# 【Tab 4：數據管理】
# ------------------------------------------
with tabs[3]:
    st.header("📁 數據修正中心")
    if not df.empty:
        new_df = st.data_editor(df, num_rows="dynamic", use_container_width=True)
        if st.button("💾 同步到雲端"):
            worksheet.clear()
            worksheet.append_row(["日期", "類型", "類別", "金額", "帳戶", "備註"])
            save_df = new_df.copy()
            save_df['日期'] = save_df['日期'].astype(str)
            worksheet.append_rows(save_df.values.tolist())
            st.success("同步成功")
            st.rerun()

# ------------------------------------------
# 【Tab 5：設定】
# ------------------------------------------
with tabs[4]:
    st.header("⚙️ 類別設定")
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("預算池定義")
        new_bc = []
        for i, b in enumerate(st.session_state.budget_cats):
            with st.container(border=True):
                ca1, ca2, ca3 = st.columns([2, 2, 1])
                n = ca1.text_input("名稱", b['類別'], key=f"bn{i}")
                m = ca2.selectbox("模式", ["百分比", "固定金額"], index=0 if b['模式']=="百分比" else 1, key=f"bm{i}")
                v = ca3.number_input("值", b['數值'], key=f"bv{i}")
                if st.button("🗑️", key=f"bd{i}"):
                    st.session_state.budget_cats.pop(i)
                    st.rerun()
                new_bc.append({"類別": n, "模式": m, "數值": v})
        st.session_state.budget_cats = new_bc
        if st.button("➕ 新增池"):
            st.session_state.budget_cats.append({"類別": "新池", "模式": "百分比", "數值": 0})
            st.rerun()
    with c2:
        st.subheader("支出類別定義")
        # (此處維持之前的支出類別增減邏輯)
        for i, ex in enumerate(st.session_state.expense_cats):
            col1, col2 = st.columns([3, 1])
            col1.write(f"🔹 {ex}")
            if col2.button("刪除", key=f"exd{i}"):
                st.session_state.expense_cats.pop(i)
                st.rerun()
        add_ex = st.text_input("新增支出項目名稱...")
        if st.button("確認新增項目"):
            st.session_state.expense_cats.append(add_ex)
            st.rerun()
