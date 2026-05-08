import streamlit as st
import gspread
import json
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime

# --- 1. 介面與 CSS 強化 ---
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
    st.error(f"❌ 雲端連線失敗：{e}"); st.stop()

# --- 3. 初始化 Session State ---
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.username = ""

# 初始化「預算池定義」與「上限模式」
if 'pool_configs' not in st.session_state:
    st.session_state.pool_configs = [
        {"池名": "生活預算", "上限模式": "百分比", "上限值": 50},
        {"池名": "投資帳戶", "上限模式": "固定金額", "上限值": 5000}
    ]

if 'expense_cats' not in st.session_state:
    st.session_state.expense_cats = ["飲食", "交通", "自我提升", "娛樂"]

# --- 4. 登入閘門 ---
if not st.session_state.logged_in:
    st.title("🔐 戰情中心登入")
    t1, t2 = st.tabs(["🔑 登入", "📝 註冊"])
    with t1:
        u = st.text_input("帳號", key="u"); p = st.text_input("密碼", type="password", key="p")
        if st.button("進入指揮所"):
            recs = users_sheet.get_all_records()
            for r in recs:
                if str(r.get("Username")).strip() == u.strip() and str(r.get("Password")).strip() == p.strip():
                    st.session_state.logged_in = True
                    st.session_state.username = u; st.rerun()
            st.error("帳密不符")
    with t2:
        nu = st.text_input("新帳號"); np = st.text_input("新密碼", type="password")
        if st.button("確認註冊"):
            users_sheet.append_row([nu, np])
            sh.add_worksheet(title=nu, rows="1000", cols="10").append_row(["日期", "類型", "類別", "金額", "帳戶", "備註"])
            st.success("註冊成功")
    st.stop()

# --- 5. 數據預處理 ---
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
with colA: st.title(f"🛠️ {st.session_state.username} 的財務戰略中心")
with colB: 
    if st.button("登出 👋"): st.session_state.logged_in = False; st.rerun()

tabs = st.tabs(["📊 數據看板", "📥 收入金錢分配", "💸 支出登錄", "📁 數據管理", "⚙️ 類別設定"])

# ------------------------------------------
# 【Tab 1：數據看板】
# ------------------------------------------
with tabs[0]:
    if df.empty: st.info("尚無數據")
    else:
        total_in = df[df['類型'] == '收入']['金額'].sum()
        total_ex = df[df['類型'] == '支出']['金額'].sum()
        
        c1, c2, c3 = st.columns(3)
        c1.metric("💰 實質總資產", f"${total_in - total_ex:,.0f}")
        c2.metric("📈 累計總收入", f"${total_in:,.0f}")
        c3.metric("📉 累計總支出", f"${total_ex:,.0f}")
        
        st.markdown("---")
        view = st.radio("監控模式：", ["🏦 帳戶餘額 (現金)", "🎯 預算上限達成率", "📉 每日流水趨勢"], horizontal=True)

        if view == "🏦 帳戶餘額 (現金)":
            in_p = df[df['類型'] == '轉帳'].groupby('帳戶')['金額'].sum()
            out_p = df[df['類型'] == '支出'].groupby('帳戶')['金額'].sum()
            pool_rem = []
            for name in in_p.index:
                rem = in_p[name] - out_p.get(name, 0)
                if rem != 0: pool_rem.append({"帳戶": name, "現金": rem})
            if pool_rem:
                st.plotly_chart(px.pie(pd.DataFrame(pool_rem), values='現金', names='帳戶', hole=0.4, title="各帳戶實時餘額"), use_container_width=True)

        elif view == "🎯 預算上限達成率":
            # 邏輯：計算動態上限 (固定 $ 或 % * 總收入)
            config_df = pd.DataFrame(st.session_state.pool_configs)
            real_ex = df[df['類型'] == '支出'].groupby('帳戶')['金額'].sum().reset_index()
            real_ex.columns = ['池名', '實際支出']
            
            comp = pd.merge(config_df, real_ex, left_on='池名', right_on='池名', how='left').fillna(0)
            # 計算計算後的上限
            comp['計算上限'] = comp.apply(lambda r: r['上限值'] if r['上限模式'] == "固定金額" else (r['上限值']/100 * total_in), axis=1)
            
            fig = go.Figure()
            fig.add_trace(go.Bar(x=comp['池名'], y=comp['計算上限'], name='警戒上限 (目標)', marker_color='#adb5bd'))
            fig.add_trace(go.Bar(x=comp['池名'], y=comp['實際支出'], name='實際已花費', marker_color='#dc3545'))
            fig.update_layout(barmode='overlay', title="支出控管：動態上限 vs 實際支出")
            st.plotly_chart(fig, use_container_width=True)

# ------------------------------------------
# 【Tab 2：收入金錢分配 (動態手動模式)】
# ------------------------------------------
with tabs[1]:
    st.header("📥 收入金錢分配")
    i_val = st.number_input("本次進帳總額", min_value=0, step=1000)
    i_note = st.text_input("來源說明", value="薪資")
    
    st.markdown("---")
    st.write("👉 **請設定本次收入的派發方式：**")
    
    alloc_results = []
    total_alloc = 0
    
    for p in st.session_state.pool_configs:
        c1, c2, c3 = st.columns([2, 2, 2])
        with c1: st.write(f"**{p['池名']}**")
        with c2:
            mode = st.radio(f"分配模式", ["$", "%"], key=f"am_{p['池名']}", horizontal=True, label_visibility="collapsed")
        with c3:
            if mode == "$":
                amt = st.number_input(f"金額", min_value=0, key=f"av_{p['池名']}", label_visibility="collapsed")
                final_amt = amt
            else:
                pct = st.number_input(f"百分比", min_value=0, max_value=100, key=f"ap_{p['池名']}", label_visibility="collapsed")
                final_amt = int(i_val * (pct/100))
                st.write(f"折合約 ${final_amt}")
            
            total_alloc += final_amt
            alloc_results.append({"池名": p['池名'], "金額": final_amt, "模式": mode})

    st.markdown("---")
    rem = i_val - total_alloc
    if rem > 0: st.info(f"尚有 ${rem} 未分配")
    elif rem < 0: st.error(f"⚠️ 分配超出總額 ${abs(rem)}！")
    
    if i_val > 0 and total_alloc == i_val:
        if st.button("🚀 確認執行戰略分配"):
            today = datetime.now().strftime('%Y-%m-%d')
            rows = [[today, '收入', '總額進帳', i_val, '主帳戶', i_note]]
            for r in alloc_results:
                if r['金額'] > 0:
                    rows.append([today, '轉帳', '金錢分配', r['金額'], r['池名'], f"分配模式: {r['模式']}"])
            worksheet.append_rows(rows)
            st.balloons(); st.rerun()

# ------------------------------------------
# 【Tab 3：支出登錄】
# ------------------------------------------
with tabs[2]:
    st.header("💸 日常支出登錄")
    with st.container(border=True):
        e_n = st.text_input("支出項目")
        e_v = st.number_input("支出金額", min_value=0)
        e_p = st.selectbox("從哪個預算池扣款？", [p['池名'] for p in st.session_state.pool_configs])
        e_t = st.selectbox("支出類別", st.session_state.expense_cats)
        if st.button("🔴 確認寫入支出"):
            if e_v > 0 and e_n:
                worksheet.append_row([datetime.now().strftime('%Y-%m-%d'), '支出', e_t, e_v, e_p, e_n])
                st.success(f"已從 {e_p} 扣除 ${e_v}"); st.rerun()

# ------------------------------------------
# 【Tab 4：數據管理】
# ------------------------------------------
with tabs[3]:
    st.header("📁 數據管理中心")
    if not df.empty:
        new_df = st.data_editor(df, num_rows="dynamic", use_container_width=True)
        if st.button("💾 同步到雲端"):
            worksheet.clear(); worksheet.append_row(["日期", "類型", "類別", "金額", "帳戶", "備註"])
            save_df = new_df.copy(); save_df['日期'] = save_df['日期'].astype(str)
            worksheet.append_rows(save_df.values.tolist())
            st.success("同步成功"); st.rerun()

# ------------------------------------------
# 【Tab 5：類別設定】
# ------------------------------------------
with tabs[4]:
    st.header("⚙️ 類別與上限設定")
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("🛠️ 預算池與警戒上限")
        new_c = []
        for i, config in enumerate(st.session_state.pool_configs):
            with st.container(border=True):
                ca1, ca2 = st.columns([3, 2])
                name = ca1.text_input("池名", config['池名'], key=f"cn_{i}")
                mode = ca2.selectbox("上限模式", ["固定金額", "百分比"], index=0 if config['上限模式']=="固定金額" else 1, key=f"cm_{i}")
                val = st.number_input("警戒值 ($ 或 %)", config['上限值'], key=f"cv_{i}")
                if st.button(f"🗑️ 刪除 {config['池名']}", key=f"cd_{i}"):
                    st.session_state.pool_configs.pop(i); st.rerun()
                new_c.append({"池名": name, "上限模式": mode, "上限值": val})
        st.session_state.pool_configs = new_c
        add_p = st.text_input("新增預算池..."); 
        if st.button("➕ 新增"):
            st.session_state.pool_configs.append({"池名": add_p, "上限模式": "百分比", "上限值": 0}); st.rerun()
    with c2:
        st.subheader("🛠️ 支出類別")
        # (此處維持支出類別管理邏輯)
        for i, ex in enumerate(st.session_state.expense_cats):
            col1, col2 = st.columns([3, 1])
            col1.write(f"🔹 {ex}")
            if col2.button("刪除", key=f"ed_{i}"):
                st.session_state.expense_cats.pop(i); st.rerun()
        ne = st.text_input("新增類別...")
        if st.button("➕ 新增項"): st.session_state.expense_cats.append(ne); st.rerun()
