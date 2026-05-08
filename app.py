import streamlit as st
import gspread
import json
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime

# --- 1. 介面與主題設定 ---
st.set_page_config(page_title="個人財務戰情系統", layout="wide")
st.markdown("""
    <style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    .stTabs [data-baseweb="tab-list"] { gap: 10px; }
    .stTabs [data-baseweb="tab"] { 
        height: 50px; background-color: #ced4da; color: #495057; border-radius: 5px; padding: 10px 20px; border: 1px solid #adb5bd;
    }
    .stTabs [aria-selected="true"] { 
        background-color: #007bff !important; color: white !important; font-weight: bold;
    }
    </style>
    """, unsafe_allow_html=True)

# --- 2. 雲端連線與登入 (簡化邏輯，保留你原本的) ---
credentials = json.loads(st.secrets["gcp_service_account_json"])
gc = gspread.service_account_from_dict(credentials)
sh = gc.open('專屬財務戰情資料庫')
users_sheet = sh.worksheet('使用者名冊')

if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.username = ""

# 初始化預設類別
if 'budget_cats' not in st.session_state:
    st.session_state.budget_cats = [{"類別": "生活預算", "百分比": 50}, {"類別": "投資帳戶", "百分比": 30}, {"類別": "儲蓄帳戶", "百分比": 20}]
if 'expense_cats' not in st.session_state:
    st.session_state.expense_cats = ["飲食", "交通", "自我提升", "運動裝備", "休閒娛樂"]

# (登入閘門邏輯請保持你原本的代碼，此處省略以聚焦功能更新)
# ... [保留原本登入邏輯] ...
if not st.session_state.logged_in:
    # 這裡請貼入你之前的登入 tab 程式碼
    st.title("🔐 戰情中心登入")
    # ...
    st.stop()

# --- 5. 分頁自動檢查 ---
try:
    worksheet = sh.worksheet(st.session_state.username)
except gspread.WorksheetNotFound:
    worksheet = sh.add_worksheet(title=st.session_state.username, rows="1000", cols="10")
    worksheet.append_row(["日期", "類型", "類別", "金額", "帳戶", "備註"])
    st.rerun()

# ==========================================
# --- 6. 戰情主系統 ---
# ==========================================
colA, colB = st.columns([5, 1])
with colA: st.title(f"🛠️ {st.session_state.username} 的戰略指揮所")
with colB: 
    if st.button("登出 👋"):
        st.session_state.logged_in = False
        st.rerun()

tabs = st.tabs(["📊 戰情看板", "📥 收入分配", "💸 支出登錄", "📁 數據管理", "⚙️ 類別設定"])

# 讀取雲端數據
records = worksheet.get_all_records()
df = pd.DataFrame(records)
if not df.empty:
    df['金額'] = pd.to_numeric(df['金額'], errors='coerce').fillna(0)
    df['日期'] = pd.to_datetime(df['日期'])

# ------------------------------------------
# 【Tab 1：戰情看板】
# ------------------------------------------
with tabs[0]:
    if df.empty:
        st.info("尚無數據")
    else:
        # 計算總數據
        inc_sum = df[df['類型'] == '收入']['金額'].sum()
        exp_sum = df[df['類型'] == '支出']['金額'].sum()
        bal = inc_sum - exp_sum
        
        c1, c2, c3 = st.columns(3)
        c1.metric("💰 當前總資產", f"${bal:,.0f}")
        c2.metric("📈 累計總收入", f"${inc_sum:,.0f}")
        c3.metric("📉 累計總支出", f"${exp_sum:,.0f}", delta=f"-{exp_sum:,.0f}", delta_color="inverse")
        
        st.markdown("---")
        mode = st.radio("看板視角：", ["🔥 支出項目比例", "🏦 預算池剩餘彈藥", "📉 每日流水"], horizontal=True)

        if mode == "🔥 支出項目比例":
            exp_df = df[df['類型'] == '支出']
            if not exp_df.empty:
                fig = px.pie(exp_df, values='金額', names='類別', hole=0.4, title="支出類別佔比", color_discrete_sequence=px.colors.qualitative.Pastel)
                st.plotly_chart(fig, use_container_width=True)

        elif mode == "🏦 預算池剩餘彈藥":
            # 關鍵：計算各預算池剩餘金額
            # 轉帳進去該池的總和 - 從該池支出出去的總和
            trans = df[df['類型'] == '轉帳'].groupby('帳戶')['金額'].sum()
            exps_by_pool = df[df['類型'] == '支出'].groupby('帳戶')['金額'].sum()
            
            pool_status = []
            for pool in trans.index:
                remain = trans[pool] - exps_by_pool.get(pool, 0)
                if remain > 0: pool_status.append({"預算池": pool, "剩餘金額": remain})
            
            if pool_status:
                pdf = pd.DataFrame(pool_status)
                fig = px.pie(pdf, values='剩餘金額', names='預算池', hole=0.4, title="目前各池子剩下多少錢", color_discrete_sequence=px.colors.sequential.Tealgrn)
                st.plotly_chart(fig, use_container_width=True)
                st.table(pdf.set_index("預算池"))
            else: st.warning("目前預算池都是空的，請先去「收入分配」。")

        elif mode == "📉 每日流水":
            daily = df[df['類型'].isin(['收入', '支出'])].copy()
            daily.loc[daily['類型'] == '支出', '金額'] = -daily['金額']
            daily_sum = daily.groupby(daily['日期'].dt.date)['金額'].sum().reset_index()
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=daily_sum['日期'], y=daily_sum['金額'], mode='lines+markers', name='每日淨流量'))
            fig.add_hline(y=0, line_dash="dash", line_color="red")
            st.plotly_chart(fig, use_container_width=True)

# ------------------------------------------
# 【Tab 2：收入分配 (雙模式切換)】
# ------------------------------------------
with tabs[1]:
    st.header("📥 資金匯入分配")
    inc_val = st.number_input("本次進帳金額", min_value=0, step=1000, key="inc_val_input")
    inc_note = st.text_input("來源說明", value="本薪")
    
    st.markdown("---")
    # 雙模式切換開關
    assign_mode = st.toggle("切換為：具體數字分配 ($)", value=False) # 預設為百分比
    
    st.markdown(f"##### 📍 使用「{'具體數字' if assign_mode else '百分比'}」進行分配")
    
    current_assigned_data = []
    total_val = 0
    total_pct = 0
    
    for i, cat in enumerate(st.session_state.budget_cats):
        c1, c2 = st.columns([3, 2])
        with c1: st.write(f"**{cat['類別']}**")
        with c2:
            if assign_mode:
                # 具體數字模式
                val = st.number_input(f"分配金額 $", min_value=0, step=100, key=f"v_{i}")
                total_val += val
                current_assigned_data.append({"類別": cat['類別'], "金額": val, "百分比": (val/inc_val*100) if inc_val > 0 else 0})
            else:
                # 百分比模式
                pct = st.number_input(f"分配比例 %", value=cat['百分比'], min_value=0, max_value=100, key=f"p_{i}")
                total_pct += pct
                current_assigned_data.append({"類別": cat['類別'], "金額": int(inc_val * (pct/100)), "百分比": pct})

    # 檢查邏輯
    is_ready = False
    if assign_mode:
        if total_val != inc_val:
            st.warning(f"⚠️ 分配總額 ${total_val} 不等於進帳 ${inc_val} -> 「請重新計算」")
        else:
            st.success("✅ 金額分配對齊")
            is_ready = True
    else:
        if total_pct != 100:
            st.warning(f"⚠️ 比例總計 {total_pct}% 不等於 100% -> 「請重新計算」")
        else:
            st.success("✅ 比例分配完美")
            is_ready = True

    if is_ready:
        if st.button("🚀 執行自動分配"):
            today = datetime.now().strftime('%Y-%m-%d')
            rows = [[today, '收入', inc_note, inc_val, '主帳戶', '收入進帳']]
            for item in current_assigned_data:
                rows.append([today, '轉帳', f"{item['類別']}({item['百分比']:.1f}%)", item['金額'], item['類別'], '系統分配'])
            worksheet.append_rows(rows)
            st.balloons()
            st.rerun()

# ------------------------------------------
# 【Tab 3：支出登錄 (連動機制)】
# ------------------------------------------
with tabs[2]:
    st.header("💸 日常支出紀錄")
    with st.container(border=True):
        e_item = st.text_input("支出項目名稱")
        e_amt = st.number_input("支出金額", min_value=0)
        # 這裡會動態抓取你設定的預算池
        pool_list = [c['類別'] for c in st.session_state.budget_cats]
        e_pool = st.selectbox("從哪個預算池扣款？ (會影響該池餘額)", pool_list)
        e_cat = st.selectbox("支出細分類", st.session_state.expense_cats)
        
        if st.button("🔴 確認支出"):
            if e_amt > 0 and e_item:
                today = datetime.now().strftime('%Y-%m-%d')
                # 關鍵：帳戶欄位存入「預算池名稱」，這樣看板才能連動扣款
                worksheet.append_row([today, '支出', e_cat, e_amt, e_pool, e_item])
                st.success(f"已從 {e_pool} 扣除 ${e_amt}！")
                st.rerun()

# ------------------------------------------
# 【Tab 4：數據管理 (修正中心)】
# ------------------------------------------
with tabs[3]:
    st.header("📁 數據修正中心")
    if not df.empty:
        # 去掉輔助用的月份列，讓使用者直接編輯原始數據
        edit_df = df.copy()
        edited_df = st.data_editor(edit_df, num_rows="dynamic", use_container_width=True)
        if st.button("💾 同步修正至雲端"):
            worksheet.clear()
            worksheet.append_row(["日期", "類型", "類別", "金額", "帳戶", "備註"])
            # 轉換日期回字串
            edited_df['日期'] = pd.to_datetime(edited_df['日期']).dt.strftime('%Y-%m-%d')
            worksheet.append_rows(edited_df.values.tolist())
            st.success("✅ 雲端資料已同步更新！")
            st.rerun()

# ------------------------------------------
# 【Tab 5：類別設定】
# ------------------------------------------
with tabs[4]:
    # (此處維持修正後的預算與支出類別管理，確保 key 值唯一)
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("🛠️ 預算池定義")
        new_b = []
        for i, b in enumerate(st.session_state.budget_cats):
            ca1, ca2 = st.columns([3, 1])
            with ca1: n = st.text_input(f"名稱-{i}", value=b['類別'], key=f"bn_{i}", label_visibility="collapsed")
            with ca2: 
                if st.button("🗑️", key=f"bd_{i}"):
                    st.session_state.budget_cats.pop(i)
                    st.rerun()
            p = st.number_input(f"預設 %-{i}", value=b['百分比'], key=f"bp_def_{i}", min_value=0, max_value=100, label_visibility="collapsed")
            new_b.append({"類別": n, "百分比": p})
        st.session_state.budget_cats = new_b
        add_b = st.text_input("新增預算池...", key="add_b_new")
        if st.button("➕ 新增池"):
            st.session_state.budget_cats.append({"類別": add_b, "百分比": 0})
            st.rerun()
    with c2:
        st.subheader("🛠️ 支出類別管理")
        # ... (支出類別管理邏輯)
