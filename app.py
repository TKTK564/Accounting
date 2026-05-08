import streamlit as st
import gspread
import json
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime

# --- 1. 介面設定 (視覺強化) ---
st.set_page_config(page_title="個人財務戰情系統", layout="wide")
st.markdown("""
    <style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    .stTabs [data-baseweb="tab-list"] { gap: 10px; }
    .stTabs [data-baseweb="tab"] { 
        height: 50px; background-color: #adb5bd; color: #343a40; border-radius: 5px; padding: 10px 20px; border: 1px solid #6c757d;
    }
    .stTabs [aria-selected="true"] { 
        background-color: #007bff !important; color: white !important; font-weight: bold;
    }
    </style>
    """, unsafe_allow_html=True)

# --- 2. 雲端連線 ---
credentials = json.loads(st.secrets["gcp_service_account_json"])
gc = gspread.service_account_from_dict(credentials)
sh = gc.open('專屬財務戰情資料庫')
users_sheet = sh.worksheet('使用者名冊')

# --- 3. 初始化 Session State ---
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.username = ""

# 初始化預算類別 (增加 '模式' 欄位)
if 'budget_cats' not in st.session_state:
    st.session_state.budget_cats = [
        {"類別": "生活預算", "模式": "百分比", "數值": 50},
        {"類別": "投資帳戶", "模式": "百分比", "數值": 30},
        {"類別": "儲蓄帳戶", "模式": "百分比", "數值": 20}
    ]

# 初始化支出細分類別
if 'expense_cats' not in st.session_state:
    st.session_state.expense_cats = ["飲食", "交通", "自我提升", "運動訓練", "娛樂"]

# (登入閘門邏輯請保持你原本的代碼...)
if not st.session_state.logged_in:
    # [此處保留你原本的登入/註冊 tab 程式碼]
    st.title("🔐 戰情中心登入")
    # ... 原本的代碼 ...
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
with colA: st.title(f"🛠️ {st.session_state.username} 的戰略指揮所")
with colB: 
    if st.button("登出 👋"):
        st.session_state.logged_in = False
        st.rerun()

tabs = st.tabs(["📊 戰情看板", "📥 收入金錢分配", "💸 支出登錄", "📁 數據管理", "⚙️ 類別設定"])

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
        inc_sum = df[df['類型'] == '收入']['金額'].sum()
        exp_sum = df[df['類型'] == '支出']['金額'].sum()
        bal = inc_sum - exp_sum
        
        c1, c2, c3 = st.columns(3)
        c1.metric("💰 當前總資產", f"${bal:,.0f}")
        c2.metric("📈 累計總收入", f"${inc_sum:,.0f}")
        c3.metric("📉 累計總支出", f"${exp_sum:,.0f}", delta=f"-{exp_sum:,.0f}", delta_color="inverse")
        
        st.markdown("---")
        mode = st.radio("數據分析模式：", ["🏦 預算池剩餘彈藥", "🔥 支出項目佔比", "📈 每日流水趨勢"], horizontal=True)

        if mode == "🏦 預算池剩餘彈藥":
            # 基於「預算池定義」計算各池餘額
            trans = df[df['類型'] == '轉帳'].groupby('帳戶')['金額'].sum()
            exps_pool = df[df['類型'] == '支出'].groupby('帳戶')['金額'].sum()
            
            pool_status = []
            for pool in trans.index:
                rem = trans[pool] - exps_pool.get(pool, 0)
                if rem > 0: pool_status.append({"預算池": pool, "剩餘餘額": rem})
            
            if pool_status:
                fig = px.pie(pd.DataFrame(pool_status), values='剩餘餘額', names='預算池', hole=0.4, title="目前各池子剩餘彈藥")
                st.plotly_chart(fig, use_container_width=True)
                st.dataframe(pd.DataFrame(pool_status).set_index("預算池"))
            else: st.warning("目前預算池都是空的。")

        elif mode == "🔥 支出項目佔比":
            exp_df = df[df['類型'] == '支出']
            if not exp_df.empty:
                fig = px.pie(exp_df, values='金額', names='類別', hole=0.4, title="支出類別佔比")
                st.plotly_chart(fig, use_container_width=True)

# ------------------------------------------
# 【Tab 2：收入金錢分配 (混和模式)】
# ------------------------------------------
with tabs[1]:
    st.header("📥 收入金錢分配")
    inc_val = st.number_input("本次總進帳金額", min_value=0, step=1000)
    inc_note = st.text_input("來源說明", value="本薪/獎學金")
    
    st.markdown("---")
    st.write("系統會先扣除「固定金額」，剩餘資金再依「百分比」分配。")
    
    # 預算分配計算
    fixed_total = 0
    percent_total = 0
    allocation_list = []
    
    # 第一輪：計算固定金額
    for i, cat in enumerate(st.session_state.budget_cats):
        if cat['模式'] == "固定金額":
            fixed_total += cat['數值']
    
    rem_after_fixed = inc_val - fixed_total
    
    # 顯示與調整
    for i, cat in enumerate(st.session_state.budget_cats):
        c1, c2, c3 = st.columns([3, 2, 2])
        with c1: st.write(f"**{cat['類別']}** ({cat['模式']})")
        with c2:
            if cat['模式'] == "固定金額":
                st.write(f"${cat['數值']}")
                final_amt = cat['數值']
            else:
                st.write(f"{cat['數值']}%")
                final_amt = int(rem_after_fixed * (cat['數值']/100)) if rem_after_fixed > 0 else 0
                percent_total += cat['數值']
        with c3:
            st.write(f"預計分配：**${final_amt}**")
            allocation_list.append({"類別": cat['類別'], "金額": final_amt, "百分比": (final_amt/inc_val*100) if inc_val > 0 else 0})

    st.markdown("---")
    
    # 檢查邏輯
    if fixed_total > inc_val:
        st.error(f"❌ 固定支出 (${fixed_total}) 已超過總收入 (${inc_val})！「請重新計算」")
    elif percent_total != 100 and rem_after_fixed > 0:
        st.warning(f"⚠️ 剩餘資金的百分比總計為 {percent_total}% (應為 100%) -> 「請重新計算」")
    else:
        st.success("✅ 分配邏輯正確")
        if st.button("🚀 執行戰略分配"):
            today = datetime.now().strftime('%Y-%m-%d')
            rows = [[today, '收入', inc_note, inc_val, '主帳戶', '總額進帳']]
            for item in allocation_list:
                rows.append([today, '轉帳', f"{item['類別']}({item['百分比']:.1f}%)", item['金額'], item['類別'], '系統自動分配'])
            worksheet.append_rows(rows)
            st.balloons()
            st.rerun()

# ------------------------------------------
# 【Tab 3：支出登錄】
# ------------------------------------------
with tabs[2]:
    st.header("💸 支出登錄")
    with st.container(border=True):
        e_item = st.text_input("支出項目 (備註)")
        e_amt = st.number_input("支出金額 ", min_value=0)
        
        # 核心：選擇從哪個「預算池」扣錢
        pool_list = [c['類別'] for c in st.session_state.budget_cats]
        e_pool = st.selectbox("從哪個預算池扣款？", pool_list)
        
        # 核心：選擇自定義的「支出類別」
        e_cat = st.selectbox("支出類別", st.session_state.expense_cats)
        
        if st.button("🔴 確認支出"):
            if e_amt > 0 and e_item:
                today = datetime.now().strftime('%Y-%m-%d')
                # 寫入：類別為「支出細項」，帳戶為「預算池」，以達成餘額扣除
                worksheet.append_row([today, '支出', e_cat, e_amt, e_pool, e_item])
                st.success(f"已從 {e_pool} 扣除 ${e_amt}")
                st.rerun()

# ------------------------------------------
# 【Tab 4：數據管理 (修改/刪除)】
# ------------------------------------------
with tabs[3]:
    st.header("📁 數據修正中心")
    if not df.empty:
        # 讓使用者直接在介面修改
        edited_df = st.data_editor(df, num_rows="dynamic", use_container_width=True)
        if st.button("💾 同步更新雲端"):
            worksheet.clear()
            worksheet.append_row(["日期", "類型", "類別", "金額", "帳戶", "備註"])
            # 格式轉換
            edited_df['日期'] = pd.to_datetime(edited_df['日期']).dt.strftime('%Y-%m-%d')
            worksheet.append_rows(edited_df.values.tolist())
            st.success("✅ 資料庫已同步！")
            st.rerun()

# ------------------------------------------
# 【Tab 5：類別設定 (自定義名稱)】
# ------------------------------------------
with tabs[4]:
    st.header("⚙️ 系統類別與模式設定")
    c1, c2 = st.columns(2)
    
    with c1:
        st.subheader("🛠️ 預算池與分配模式")
        new_b_settings = []
        for i, b in enumerate(st.session_state.budget_cats):
            with st.container(border=True):
                ca1, ca2, ca3 = st.columns([2, 2, 1])
                name = ca1.text_input(f"名稱", value=b['類別'], key=f"bn_{i}")
                mode = ca2.selectbox(f"分配模式", ["百分比", "固定金額"], index=0 if b['模式']=="百分比" else 1, key=f"bm_{i}")
                val = ca3.number_input(f"值", value=b['數值'], key=f"bv_{i}")
                if st.button(f"🗑️ 刪除", key=f"bd_{i}"):
                    st.session_state.budget_cats.pop(i)
                    st.rerun()
                new_b_settings.append({"類別": name, "模式": mode, "數值": val})
        st.session_state.budget_cats = new_b_settings
        
        if st.button("➕ 新增分配類別"):
            st.session_state.budget_cats.append({"類別": "新類別", "模式": "百分比", "數值": 0})
            st.rerun()

    with c2:
        st.subheader("🛠️ 支出細項類別管理")
        for i, e in enumerate(st.session_state.expense_cats):
            ca1, ca2 = st.columns([3, 1])
            with ca1: st.write(f"🔹 {e}")
            with ca2:
                if st.button("🗑️", key=f"de_{i}"):
                    st.session_state.expense_cats.pop(i)
                    st.rerun()
        
        new_e = st.text_input("新增支出類別名稱...")
        if st.button("➕ 確認新增細項"):
            if new_e:
                st.session_state.expense_cats.append(new_e)
                st.rerun()
