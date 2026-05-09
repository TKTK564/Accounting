import streamlit as st
import gspread
import json
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
import time
import calendar

# --- 1. APP 質感與圖示設定 (核心品牌化區塊) ---
st.set_page_config(page_title="個人財務紀錄", layout="wide")

# 你的 GitHub 圖片原始連結
ICON_URL = "https://raw.githubusercontent.com/TKTK564/Accounting/refs/heads/main/logo.png"

# 注意：為了防止 Markdown 誤判為代碼塊，這裡的所有 HTML 內容必須「絕對頂格靠左」
st.markdown(f"""
<head>
<link rel="apple-touch-icon" href="{ICON_URL}">
<link rel="icon" sizes="192x192" href="{ICON_URL}">
<link rel="icon" sizes="512x512" href="{ICON_URL}">
</head>
<style>
header {{visibility: hidden;}}
footer {{visibility: hidden;}}
#MainMenu {{visibility: hidden;}}
.block-container {{
padding-top: 1.5rem;
padding-bottom: 0rem;
padding-left: 1.5rem;
padding-right: 1.5rem;
}}
.stTabs [data-baseweb="tab-list"] {{ 
gap: 10px; 
}}
.stTabs [data-baseweb="tab"] {{ 
height: 45px; 
background-color: #f1f3f5; 
color: #495057; 
border-radius: 10px; 
padding: 10px 15px; 
border: none;
}}
.stTabs [aria-selected="true"] {{ 
background-color: #007bff !important; 
color: white !important; 
font-weight: bold; 
box-shadow: 0 4px 6px rgba(0,0,0,0.1);
}}
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

if 'pool_configs' not in st.session_state:
    st.session_state.pool_configs = [
        {"池名": "生活預算", "上限模式": "百分比", "上限值": 50},
        {"池名": "投資帳戶", "上限模式": "固定金額", "上限值": 5000}
    ]

if 'expense_cats' not in st.session_state:
    st.session_state.expense_cats = ["飲食", "交通", "自我提升", "娛樂", "生活用品", "未分類"]

# --- 4. 登入閘門 ---
if not st.session_state.logged_in:
    st.title("🔐 登入/註冊")
    t1, t2 = st.tabs(["🔑 登入", "📝 註冊"])
    with t1:
        u = st.text_input("帳號", key="login_u")
        p = st.text_input("密碼", type="password", key="login_p")
        if st.button("進入指揮所"):
            recs = users_sheet.get_all_records()
            for r in recs:
                if str(r.get("Username")).strip() == u.strip() and str(r.get("Password")).strip() == p.strip():
                    st.session_state.logged_in = True
                    st.session_state.username = u
                    st.rerun()
            st.error("帳密不符")
    with t2:
        nu = st.text_input("新帳號", key="reg_u")
        np = st.text_input("新密碼", type="password", key="reg_p")
        if st.button("確認註冊"):
            users_sheet.append_row([nu, np, "", ""])
            sh.add_worksheet(title=nu, rows="1000", cols="10").append_row(["日期", "類型", "類別", "金額", "帳戶", "備註"])
            st.toast("✅ 註冊成功！", icon="🎉")
    st.stop()

# --- 5. 數據加載 ---
worksheet = sh.worksheet(st.session_state.username)
records = worksheet.get_all_records()
df = pd.DataFrame(records)
if not df.empty:
    df['金額'] = pd.to_numeric(df['金額'], errors='coerce').fillna(0)
    df['日期'] = pd.to_datetime(df['日期'])
    df['年月'] = df['日期'].dt.strftime('%Y-%m')
    df['年'] = df['日期'].dt.year

try:
    rec_ws = sh.worksheet(f"{st.session_state.username}_自動扣款")
except gspread.WorksheetNotFound:
    rec_ws = sh.add_worksheet(title=f"{st.session_state.username}_自動扣款", rows="100", cols="10")
    rec_ws.append_row(["項目名稱", "金額", "預算池", "支出類別", "扣款時間", "週期"])
rec_df = pd.DataFrame(rec_ws.get_all_records())

# ==========================================
# --- 6. 主戰情系統 ---
# ==========================================
colA, colB = st.columns([5, 1])
with colA: st.title(f"🛠️ {st.session_state.username} 的財務戰略中心")
with colB:
    if st.button("登出 👋"): st.session_state.logged_in = False; st.rerun()

tabs = st.tabs(["📥 收入分配", "💸 支出與載具同步", "🔄 自動扣款", "📊 現金流", "📁 數據管理", "⚙️ 設定中心"])

# --- Tab 內容直接承接你原本的詳細邏輯 ---
with tabs[0]:
    st.header("📥 收入金錢分配")
    i_val = st.number_input("本次進帳總額", min_value=0, step=1000, key="income_total_input")
    i_note = st.text_input("來源說明", value="本薪", key="income_note_input")
    st.markdown("---")
    alloc_res = []; total_alloc = 0
    for p in st.session_state.pool_configs:
        c1, c2, c3 = st.columns([2, 2, 2])
        c1.write(f"**{p['池名']}**")
        mode = c2.radio(f"分配模式", ["$", "%"], key=f"am_{p['池名']}", horizontal=True)
        if mode == "$":
            amt = c3.number_input(f"金額", min_value=0, key=f"av_{p['池名']}"); final_a = amt
        else:
            pct = c3.number_input(f"百分比", min_value=0, max_value=100, key=f"ap_{p['池名']}"); final_a = int(i_val * (pct / 100)); c3.write(f"折合 ${final_a}")
        total_alloc += final_a; alloc_res.append({"池名": p['池名'], "金額": final_a, "模式": mode})
    if i_val > 0 and total_alloc == i_val:
        if st.button("🚀 確認分配寫入", key="confirm_income_btn"):
            today = datetime.now().strftime('%Y-%m-%d')
            rows = [[today, '收入', '總額進帳', i_val, '主帳戶', i_note]]
            for r in alloc_res:
                if r['金額'] > 0: rows.append([today, '轉帳', '分配', r['金額'], r['池名'], f"模式: {r['模式']}"])
            worksheet.append_rows(rows); st.toast("✅ 收入分配已寫入！", icon="💸"); st.rerun()
    elif i_val > 0:
        st.warning(f"分配總額 (${total_alloc}) 與進帳 (${i_val}) 不符")

with tabs[1]:
    st.header("💸 支出登錄與載具同步")
    col_man, col_auto = st.columns([1, 1])
    def get_item_category(item_desc, history_df, current_cats):
        if not history_df.empty:
            match = history_df[history_df['備註'].str.endswith(f"- {item_desc}", na=False)]
            if not match.empty:
                last_cat = match.iloc[-1]['類別']
                if last_cat in current_cats: return last_cat
        desc_up = str(item_desc).upper()
        if any(k in desc_up for k in ["餐", "麵", "飯", "飲", "茶", "水", "便當", "咖啡", "拿鐵", "蛋", "奶", "肉", "果", "食"]): return "飲食"
        if any(k in desc_up for k in ["油", "車票", "客運", "停車", "高鐵", "台鐵", "捷運"]): return "交通"
        if any(k in desc_up for k in ["紙", "袋", "洗", "巾", "筆", "袋"]): return "生活用品"
        return "未分類"

    with col_man:
        st.subheader("✍️ 手動輸入")
        with st.container(border=True):
            en = st.text_input("項目", key="manual_exp_name")
            ev = st.number_input("金額", min_value=0, key="manual_exp_val")
            ep = st.selectbox("扣款池", [p['池名'] for p in st.session_state.pool_configs], key="manual_exp_pool")
            et = st.selectbox("細項類別", st.session_state.expense_cats, key="manual_exp_cat")
            if st.button("🔴 確認寫入", key="manual_exp_btn"):
                if ev > 0 and en:
                    worksheet.append_row([datetime.now().strftime('%Y-%m-%d'), '支出', et, ev, ep, en])
                    st.toast(f"✅ 已從 {ep} 扣除 ${ev}", icon="📉"); st.rerun()

    with col_auto:
        st.subheader("📡 載具同步中樞")
        def_pool = st.selectbox("發票預設扣款池", [p['池名'] for p in st.session_state.pool_configs], key="auto_p")
        tab_email, tab_csv = st.tabs(["📧 方案 A: E-mail 全自動管線", "📥 方案 B: CSV 實體空投"])
        with tab_email:
            st.info("💡 戰術設定：讓財政部主動把消費明細寄到信箱。")
            st.link_button("👉 前往開啟 E-mail 消費明細通知", "https://www.einvoice.nat.gov.tw/portal/btc/mobile/btc513w/main")
        with tab_csv:
            st.write("直接拖曳財政部 CSV 檔，啟動 AI 分類記憶引擎！")
            uploaded_file = st.file_uploader("📥 拖曳 CSV 檔至此", type=["csv"], key="csv_uploader")
            if uploaded_file is not None:
                if st.button("⚙️ 解析並匯入 CSV", key="csv_process_btn"):
                    try:
                        try: csv_df = pd.read_csv(uploaded_file, encoding='big5')
                        except: csv_df = pd.read_csv(uploaded_file, encoding='utf-8')
                        date_col = next((c for c in csv_df.columns if "日期" in c), None)
                        store_col = next((c for c in csv_df.columns if "賣方" in c or "商店" in c), None)
                        amt_col = next((c for c in csv_df.columns if "金額" in c or "總計" in c), None)
                        if date_col and store_col and amt_col:
                            new_rows = []; sync_count = 0
                            for _, row in csv_df.iterrows():
                                date_val, store_val = str(row[date_col]).strip(), str(row[store_col]).strip()
                                try: amt_val = float(str(row[amt_col]).replace(',', ''))
                                except: amt_val = 0
                                if len(date_val) == 8 and "/" not in date_val: date_str = f"{date_val[:4]}-{date_val[4:6]}-{date_val[6:]}"
                                elif "/" in date_val: date_str = date_val.replace("/", "-")
                                else: date_str = datetime.now().strftime('%Y-%m-%d')
                                memo = f"[載具] {store_val}"
                                existing = df[(df['日期'].astype(str) == date_str) & (df['備註'] == memo)] if not df.empty else pd.DataFrame()
                                if existing.empty and amt_val > 0:
                                    cat = get_item_category(store_val, df, st.session_state.expense_cats)
                                    new_rows.append([date_str, '支出', cat, amt_val, def_pool, memo])
                                    sync_count += 1
                            if new_rows:
                                worksheet.append_rows(new_rows); st.toast(f"✅ 成功匯入 {sync_count} 筆紀錄！", icon="📦"); time.sleep(1); st.rerun()
                    except Exception as e: st.error(f"❌ 解析失敗：{e}")

with tabs[2]:
    st.header("🔄 定期自動扣款系統")
    today_dt = datetime.now()
    if not df.empty:
        auto_m = df[(df['年月'] == today_dt.strftime('%Y-%m')) & (df['備註'].str.startswith('[自動扣款]'))]
        deducted_m = auto_m['備註'].tolist()
    if not rec_df.empty:
        st.subheader("📋 目前扣款設定")
        st.dataframe(rec_df)
        if st.button("⚡ 執行所有待處理扣款", key="execute_auto_btn"):
            today_str = today_dt.strftime('%Y-%m-%d'); auto_rows = []
            for _, p in rec_df.iterrows():
                if f"[自動扣款] {p['項目名稱']}" not in deducted_m:
                    auto_rows.append([today_str, '支出', p['支出類別'], p['金額'], p['預算池'], f"[自動扣款] {p['項目名稱']}"])
            if auto_rows: worksheet.append_rows(auto_rows); st.toast("✅ 執行完畢！"); st.rerun()
    st.markdown("---")
    st.subheader("➕ 新增自動扣款")
    with st.container(border=True):
        c1, c2 = st.columns(2)
        n = c1.text_input("項目名稱", key="auto_debit_name")
        a = c2.number_input("金額", min_value=0, key="auto_debit_val")
        p_auto = st.selectbox("預算池", [pool['池名'] for pool in st.session_state.pool_configs], key="auto_debit_pool")
        cat_auto = st.selectbox("分類", st.session_state.expense_cats, key="auto_debit_cat")
        if st.button("💾 儲存", key="save_auto_rule_btn"):
            if n and a > 0: rec_ws.append_row([n, a, p_auto, cat_auto, "1", "每月"]); st.toast("✅ 儲存成功！"); st.rerun()

with tabs[3]:
    if df.empty:
        st.info("尚無數據，請先開始記帳。")
    else:
        total_in_all = df[df['類型'] == '收入']['金額'].sum()
        total_ex_all = df[df['類型'] == '支出']['金額'].sum()
        current_assets = total_in_all - total_ex_all
        available_months = sorted(df['年月'].unique(), reverse=True)
        selected_month = st.selectbox("📅 選擇觀測月份：", available_months, key="dash_month_select")
        m_df = df[df['年月'] == selected_month].copy()
        m_in = m_df[m_df['類型'] == '收入']['金額'].sum()
        m_ex = m_df[m_df['類型'] == '支出']['金額'].sum()
        st.markdown("### 📊 財務健康監控")
        st.metric("💰 實質總資產 (全期結餘)", f"${current_assets:,.0f}")
        monthly_delta = df.groupby('年月').apply(lambda x: x[x['類型'] == '收入']['金額'].sum() - x[x['類型'] == '支出']['金額'].sum()).reset_index()
        monthly_delta.columns = ['年月', '月盈餘']
        monthly_delta['累計資產'] = monthly_delta['月盈餘'].cumsum()
        monthly_delta['顯示標籤'] = pd.to_datetime(monthly_delta['年月']).dt.strftime('%m (%Y)')
        fig_assets = px.bar(monthly_delta, x='顯示標籤', y='累計資產', title="每月現金流流向", color_discrete_sequence=['#6c757d'], labels={"顯示標籤": "月份 (年份)", "累計資產": "資產水位"})
        st.plotly_chart(fig_assets, use_container_width=True)
        st.markdown("---")
        st.metric(f"📈 {selected_month} 總收入", f"${m_in:,.0f}")
        inc_df = m_df[m_df['類型'] == '收入']
        if not inc_df.empty:
            fig_inc = px.pie(inc_df, values='金額', names='備註', hole=0.4, title="收入來源比例", color_discrete_sequence=px.colors.sequential.Greens_r)
            st.plotly_chart(fig_inc, use_container_width=True)
        else: st.info("該月尚無收入。")
        st.markdown("---")
        st.metric(f"📉 {selected_month} 總支出", f"${m_ex:,.0f}")
        exp_df = m_df[m_df['類型'] == '支出']
        if not exp_df.empty:
            fig_exp = px.pie(exp_df, values='金額', names='類別', hole=0.4, title="支出分佈比例", color_discrete_sequence=px.colors.sequential.Reds_r)
            st.plotly_chart(fig_exp, use_container_width=True)
        else: st.info("該月尚無支出。")
        st.markdown("---")
        mode = st.radio("監控模式：", ["📉 每日收入與花費", "🎯 預算上限監控"], horizontal=True, key="dash_mode_radio")
        if mode == "📉 每日收入與花費":
            y, m = map(int, selected_month.split('-'))
            last_day = calendar.monthrange(y, m)[1]
            full_dates = pd.date_range(start=f"{selected_month}-01", end=f"{selected_month}-{last_day}").date
            daily_in = m_df[m_df['類型'] == '收入'].groupby(m_df['日期'].dt.date)['金額'].sum()
            daily_ex = m_df[m_df['類型'] == '支出'].groupby(m_df['日期'].dt.date)['金額'].sum()
            plot_df = pd.DataFrame(index=full_dates).fillna(0)
            plot_df['收入'] = daily_in; plot_df['支出'] = daily_ex
            plot_df = plot_df.fillna(0).reset_index().rename(columns={'index': '日期'})
            fig = go.Figure()
            fig.add_trace(go.Bar(x=plot_df['日期'], y=plot_df['收入'], name='每日收入', marker_color='#28a745', text=plot_df['收入'].apply(lambda x: f"+{int(x)}" if x > 0 else ""), textposition='outside'))
            fig.add_trace(go.Bar(x=plot_df['日期'], y=-plot_df['支出'], name='每日支出', marker_color='#dc3545', customdata=plot_df['支出'], text=plot_df['支出'].apply(lambda x: f"-{int(x)}" if x > 0 else ""), textposition='outside', hovertemplate='支出: -%{customdata:,.0f}<extra></extra>'))
            fig.update_layout(title=f"📊 {selected_month} 每日明細", barmode='relative', xaxis=dict(type='date', tickformat='%d'))
            st.plotly_chart(fig, use_container_width=True)
        elif mode == "🎯 預算上限監控":
            config_df = pd.DataFrame(st.session_state.pool_configs)
            real_ex = df[df['類型'] == '支出'].groupby('帳戶')['金額'].sum().reset_index().rename(columns={'帳戶': '池名', '金額': '實際支出'})
            comp = pd.merge(config_df, real_ex, on='池名', how='left').fillna(0)
            comp['計算上限'] = comp.apply(lambda r: r['上限值'] if r['上限模式'] == "固定金額" else (r['上限值'] / 100 * total_in_all), axis=1)
            fig = go.Figure()
            fig.add_trace(go.Bar(x=comp['池名'], y=comp['計算上限'], name='預算上限', marker_color='#adb5bd'))
            fig.add_trace(go.Bar(x=comp['池名'], y=comp['實際支出'], name='實際花費', marker_color='#dc3545'))
            fig.update_layout(barmode='overlay'); st.plotly_chart(fig, use_container_width=True)

with tabs[4]:
    st.header("📁 數據管理")
    if not df.empty:
        m_df_edit = df.drop(columns=['年月', '年'], errors='ignore').copy()
        m_df_edit['日期'] = m_df_edit['日期'].dt.date
        new_df = st.data_editor(m_df_edit, num_rows="dynamic", use_container_width=True, key="data_editor_main")
        if st.button("💾 同步雲端", key="sync_cloud_btn"):
            worksheet.clear()
            worksheet.append_row(["日期", "類型", "類別", "金額", "帳戶", "備註"])
            save_df = new_df.copy()
            save_df['日期'] = save_df['日期'].astype(str)
            worksheet.append_rows(save_df.values.tolist())
            st.toast("✅ 同步成功"); st.rerun()

with tabs[5]:
    st.header("⚙️ 系統核心設定")
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("🛠️ 預算池與警戒上限")
        new_c = []
        for i, config in enumerate(st.session_state.pool_configs):
            with st.container(border=True):
                n_pool = st.text_input("池名", config['池名'], key=f"cn_{i}")
                m_pool = st.selectbox("上限模式", ["固定金額", "百分比"], index=0 if config['上限模式'] == "固定金額" else 1, key=f"cm_{i}")
                v_pool = st.number_input("警戒值", config['上限值'], key=f"cv_{i}")
                if st.button(f"🗑️ 刪除", key=f"cd_{i}"): st.session_state.pool_configs.pop(i); st.rerun()
                new_c.append({"池名": n_pool, "上限模式": m_pool, "上限值": v_pool})
        st.session_state.pool_configs = new_c
        ap_new = st.text_input("新增預算池...", key="add_pool_input")
        if st.button("➕ 新增池", key="add_pool_btn"):
            st.session_state.pool_configs.append({"池名": ap_new, "上限模式": "百分比", "上限值": 0}); st.rerun()
    with c2:
        st.subheader("🛠️ 支出類別")
        for i, ex in enumerate(st.session_state.expense_cats):
            col1, col2 = st.columns([3, 1])
            col1.write(f"🔹 {ex}")
            if col2.button("刪除", key=f"ed_{i}"): st.session_state.expense_cats.pop(i); st.rerun()
        ne_cat = st.text_input("新增類別...", key="add_cat_input")
        if st.button("➕ 新增項", key="add_cat_btn"):
            st.session_state.expense_cats.append(ne_cat); st.rerun()
    st.markdown("---")
    st.subheader("📧 財政部 E-mail 訂閱設定")
    st.write("坐等情報上門！請點擊按鈕開啟每月消費明細寄送，配合 n8n 攔截網即可完成自動化入帳。")
    st.link_button("👉 前往開啟 E-mail 消費明細通知", "https://www.einvoice.nat.gov.tw/portal/btc/mobile/btc513w/main")
