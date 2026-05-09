import streamlit as st
import gspread
import json
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
import time
import calendar

# --- 1. 介面與主題設定 ---
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
    
    headers = users_sheet.row_values(1)
    while len(headers) < 4: headers.append("")
    if headers[0] != "Username" or headers[2] != "CardNo":
        users_sheet.update('A1:D1', [["Username", "Password", "CardNo", "CardEncrypt"]])
except Exception as e:
    st.error(f"❌ 雲端連線失敗：{e}"); st.stop()

# --- 3. 初始化 Session State ---
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.username = ""

if 'card_no' not in st.session_state: st.session_state.card_no = ""
if 'card_encrypt' not in st.session_state: st.session_state.card_encrypt = ""

if 'pool_configs' not in st.session_state:
    st.session_state.pool_configs = [
        {"池名": "生活預算", "上限模式": "百分比", "上限值": 50},
        {"池名": "投資帳戶", "上限模式": "固定金額", "上限值": 5000}
    ]

if 'expense_cats' not in st.session_state:
    st.session_state.expense_cats = ["飲食", "交通", "自我提升", "娛樂", "生活用品", "未分類"]

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
                    st.session_state.username = u
                    st.session_state.card_no = str(r.get("CardNo", ""))
                    st.session_state.card_encrypt = str(r.get("CardEncrypt", ""))
                    st.rerun()
            st.error("帳密不符")
    with t2:
        nu = st.text_input("新帳號"); np = st.text_input("新密碼", type="password")
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

# 按照要求調整分頁順序，將「現金流」移動到「數據管理」前面
tabs = st.tabs(["📥 收入分配", "💸 支出與載具同步", "🔄 自動扣款", "📊 現金流", "📁 數據管理", "⚙️ 設定中心"])

# ------------------------------------------
# 【Tab 1：收入金錢分配】 (維持不變)
# ------------------------------------------
with tabs[0]:
    st.header("📥 收入金錢分配")
    i_val = st.number_input("本次進帳總額", min_value=0, step=1000)
    i_note = st.text_input("來源說明", value="本薪")
    st.markdown("---")
    alloc_res = []; total_alloc = 0
    for p in st.session_state.pool_configs:
        c1, c2, c3 = st.columns([2, 2, 2])
        c1.write(f"**{p['池名']}**")
        mode = c2.radio(f"分配模式", ["$", "%"], key=f"am_{p['池名']}", horizontal=True)
        if mode == "$": amt = c3.number_input(f"金額", min_value=0, key=f"av_{p['池名']}"); final_a = amt
        else: pct = c3.number_input(f"百分比", min_value=0, max_value=100, key=f"ap_{p['池名']}"); final_a = int(i_val * (pct/100)); c3.write(f"折合 ${final_a}")
        total_alloc += final_a; alloc_res.append({"池名": p['池名'], "金額": final_a, "模式": mode})
    if i_val > 0 and total_alloc == i_val:
        if st.button("🚀 確認分配寫入"):
            today = datetime.now().strftime('%Y-%m-%d'); rows = [[today, '收入', '總額進帳', i_val, '主帳戶', i_note]]
            for r in alloc_res:
                if r['金額'] > 0: rows.append([today, '轉帳', '分配', r['金額'], r['池名'], f"模式: {r['模式']}"])
            worksheet.append_rows(rows); st.toast("✅ 收入分配已寫入！", icon="💸"); st.rerun()
    elif i_val > 0: st.warning(f"分配總額 (${total_alloc}) 與進帳 (${i_val}) 不符")

# ------------------------------------------
# 【Tab 2：支出登錄與載具同步】 (維持不變)
# ------------------------------------------
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
            en, ev = st.text_input("項目"), st.number_input("金額", min_value=0)
            ep = st.selectbox("扣款池", [p['池名'] for p in st.session_state.pool_configs])
            et = st.selectbox("細項類別", st.session_state.expense_cats)
            if st.button("🔴 確認寫入"):
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
            uploaded_file = st.file_uploader("📥 拖曳 CSV 檔至此", type=["csv"])
            if uploaded_file is not None:
                if st.button("⚙️ 解析並匯入 CSV"):
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

# ------------------------------------------
# 【Tab 3：自動扣款】 (維持不變)
# ------------------------------------------
with tabs[2]:
    st.header("🔄 定期自動扣款系統")
    today_dt = datetime.now()
    if not df.empty:
        auto_m = df[(df['年月'] == today_dt.strftime('%Y-%m')) & (df['備註'].str.startswith('[自動扣款]'))]
        deducted_m = auto_m['備註'].tolist()
    if not rec_df.empty:
        st.subheader("📋 目前扣款設定")
        st.dataframe(rec_df)
        if st.button("⚡ 執行所有待處理扣款"):
            today_str = today_dt.strftime('%Y-%m-%d'); auto_rows = []
            for _, p in rec_df.iterrows():
                if f"[自動扣款] {p['項目名稱']}" not in deducted_m:
                    auto_rows.append([today_str, '支出', p['支出類別'], p['金額'], p['預算池'], f"[自動扣款] {p['項目名稱']}"])
            if auto_rows: worksheet.append_rows(auto_rows); st.toast("✅ 執行完畢！"); st.rerun()
    st.markdown("---")
    st.subheader("➕ 新增自動扣款")
    with st.container(border=True):
        c1, c2 = st.columns(2)
        n = c1.text_input("項目名稱"); a = c2.number_input("金額", min_value=0)
        p = st.selectbox("預算池", [pool['池名'] for pool in st.session_state.pool_configs])
        cat = st.selectbox("分類", st.session_state.expense_cats)
        if st.button("💾 儲存"):
            if n and a > 0: rec_ws.append_row([n, a, p, cat, "1", "每月"]); st.toast("✅ 儲存成功！"); st.rerun()

# ------------------------------------------
# 【Tab 4：現金流】 (核心升級：垂直排列與色彩戰術)
# ------------------------------------------
with tabs[3]:
    if df.empty:
        st.info("尚無數據，請先開始記帳。")
    else:
        # 計算全期總額
        total_in_all = df[df['類型'] == '收入']['金額'].sum()
        total_ex_all = df[df['類型'] == '支出']['金額'].sum()
        current_assets = total_in_all - total_ex_all
        
        # 月份選擇
        available_months = sorted(df['年月'].unique(), reverse=True)
        selected_month = st.selectbox("📅 選擇觀測月份：", available_months)
        m_df = df[df['年月'] == selected_month].copy()
        m_in = m_df[m_df['類型'] == '收入']['金額'].sum()
        m_ex = m_df[m_df['類型'] == '支出']['金額'].sum()

        st.markdown("---")
        
        # 【垂直戰術佈局】
        # 1. 實質總資產
        st.metric("💰 實質總資產 (全期結餘)", f"${current_assets:,.0f}")
        # 新增：月份資產直方圖 (計算每個月的資產水位)
        monthly_delta = df.groupby('年月').apply(lambda x: x[x['類型']=='收入']['金額'].sum() - x[x['類型']=='支出']['金額'].sum()).reset_index()
        monthly_delta.columns = ['年月', '月盈餘']
        monthly_delta['累計資產'] = monthly_delta['月盈餘'].cumsum()
        fig_assets = px.bar(monthly_delta, x='年月', y='累計資產', title="每月資產水位趨勢", color_discrete_sequence=['#6c757d'])
        st.plotly_chart(fig_assets, use_container_width=True)
        
        st.markdown("---")
        
        # 2. 月份總收入 (垂直配置)
        st.metric(f"📈 {selected_month} 總收入", f"${m_in:,.0f}")
        inc_df = m_df[m_df['類型'] == '收入']
        if not inc_df.empty:
            # 更改為綠色系
            fig_inc = px.pie(inc_df, values='金額', names='備註', hole=0.4, title="收入來源比例",
                            color_discrete_sequence=px.colors.sequential.Greens_r)
            st.plotly_chart(fig_inc, use_container_width=True)
        else: st.info("該月尚無收入。")

        st.markdown("---")
        
        # 3. 月份總支出 (垂直配置)
        st.metric(f"📉 {selected_month} 總支出", f"${m_ex:,.0f}")
        exp_df = m_df[m_df['類型'] == '支出']
        if not exp_df.empty:
            # 更改為紅色系
            fig_exp = px.pie(exp_df, values='金額', names='類別', hole=0.4, title="支出分佈比例",
                            color_discrete_sequence=px.colors.sequential.OrRd_r)
            st.plotly_chart(fig_exp, use_container_width=True)
        else: st.info("該月尚無支出。")

        st.markdown("---")
        
        # 監控模式 (更名並強化互動)
        mode = st.radio("監控模式：", ["📉 每日收入與花費", "🎯 預算上限監控"], horizontal=True)

        if mode == "📉 每日收入與花費":
            y, m = map(int, selected_month.split('-'))
            last_day = calendar.monthrange(y, m)[1]
            full_dates = pd.date_range(start=f"{selected_month}-01", end=f"{selected_month}-{last_day}").date
            daily_in = m_df[m_df['類型'] == '收入'].groupby(m_df['日期'].dt.date)['金額'].sum()
            daily_ex = m_df[m_df['類型'] == '支出'].groupby(m_df['日期'].dt.date)['金額'].sum()
            plot_df = pd.DataFrame(index=full_dates)
            plot_df['收入'] = daily_in; plot_df['支出'] = daily_ex
            plot_df = plot_df.fillna(0).reset_index().rename(columns={'index': '日期'})
            
            fig = go.Figure()
            # 收入 Bar: 顯示 + 號
            fig.add_trace(go.Bar(
                x=plot_df['日期'], y=plot_df['收入'], 
                name='每日收入', marker_color='#28a745',
                text=plot_df['收入'].apply(lambda x: f"+{int(x)}" if x > 0 else ""),
                textposition='outside'
            ))
            # 支出 Bar: 顯示 - 號 (以負值繪圖但顯示正數標籤)
            fig.add_trace(go.Bar(
                x=plot_df['日期'], y=-plot_df['支出'], 
                name='每日支出', marker_color='#dc3545',
                customdata=plot_df['支出'],
                text=plot_df['支出'].apply(lambda x: f"-{int(x)}" if x > 0 else ""),
                textposition='outside',
                hovertemplate='支出: -%{customdata:,.0f}<extra></extra>'
            ))
            fig.update_layout(title=f"📊 {selected_month} 每日明細", barmode='relative', xaxis=dict(type='date', tickformat='%d'))
            st.plotly_chart(fig, use_container_width=True)
            
        elif mode == "🎯 預算上限監控":
            config_df = pd.DataFrame(st.session_state.pool_configs)
            real_ex = df[df['類型'] == '支出'].groupby('帳戶')['金額'].sum().reset_index().rename(columns={'帳戶': '池名', '金額': '實際支出'})
            comp = pd.merge(config_df, real_ex, on='池名', how='left').fillna(0)
            comp['計算上限'] = comp.apply(lambda r: r['上限值'] if r['上限模式'] == "固定金額" else (r['上限值']/100 * total_in_all), axis=1)
            fig = go.Figure()
            fig.add_trace(go.Bar(x=comp['池名'], y=comp['計算上限'], name='預算上限', marker_color='#adb5bd'))
            fig.add_trace(go.Bar(x=comp['池名'], y=comp['實際支出'], name='實際花費', marker_color='#dc3545'))
            fig.update_layout(barmode='overlay'); st.plotly_chart(fig, use_container_width=True)

# ------------------------------------------
# 【Tab 5：數據管理】
# ------------------------------------------
with tabs[4]:
    st.header("📁 數據管理")
    if not df.empty:
        m_df_edit = df.drop(columns=['年月', '年'], errors='ignore').copy()
        m_df_edit['日期'] = m_df_edit['日期'].dt.date
        new_df = st.data_editor(m_df_edit, num_rows="dynamic", use_container_width=True)
        if st.button("💾 同步雲端"):
            worksheet.clear(); worksheet.append_row(["日期", "類型", "類別", "金額", "帳戶", "備註"])
            save_df = new_df.copy(); save_df['日期'] = save_df['日期'].astype(str)
            worksheet.append_rows(save_df.values.tolist()); st.toast("✅ 同步成功"); st.rerun()

# ------------------------------------------
# 【Tab 6：設定中心】
# ------------------------------------------
with tabs[5]:
    st.header("⚙️ 系統核心設定")
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("🛠️ 預算池與警戒上限")
        new_c = []
        for i, config in enumerate(st.session_state.pool_configs):
            with st.container(border=True):
                n = st.text_input("池名", config['池名'], key=f"cn_{i}")
                m = st.selectbox("上限模式", ["固定金額", "百分比"], index=0 if config['上限模式']=="固定金額" else 1, key=f"cm_{i}")
                v = st.number_input("警戒值", config['上限值'], key=f"cv_{i}")
                if st.button(f"🗑️ 刪除", key=f"cd_{i}"): st.session_state.pool_configs.pop(i); st.rerun()
                new_c.append({"池名": n, "上限模式": m, "上限值": v})
        st.session_state.pool_configs = new_c
        ap = st.text_input("新增預算池..."); 
        if st.button("➕ 新增池"): st.session_state.pool_configs.append({"池名": ap, "上限模式": "百分比", "上限值": 0}); st.toast("✅ 新增成功！"); st.rerun()
    with c2:
        st.subheader("🛠️ 支出類別")
        for i, ex in enumerate(st.session_state.expense_cats):
            col1, col2 = st.columns([3, 1])
            col1.write(f"🔹 {ex}")
            if col2.button("刪除", key=f"ed_{i}"): st.session_state.expense_cats.pop(i); st.rerun()
        ne = st.text_input("新增類別..."); 
        if st.button("➕ 新增項"): st.session_state.expense_cats.append(ne); st.toast("✅ 新增成功！"); st.rerun()

    st.markdown("---")
    st.subheader("📡 載具金鑰綁定")
    with st.container(border=True):
        c_no = st.text_input("手機條碼", value=st.session_state.card_no)
        c_pw = st.text_input("驗證碼", value=st.session_state.card_encrypt, type="password")
        if st.button("🔒 綁定金鑰"):
            if c_no and c_pw:
                recs = users_sheet.get_all_records()
                for idx, r in enumerate(recs):
                    if str(r.get("Username")).strip() == st.session_state.username:
                        users_sheet.update_cell(idx + 2, 3, c_no)
                        users_sheet.update_cell(idx + 2, 4, c_pw)
                        st.session_state.card_no, st.session_state.card_encrypt = c_no, c_pw
                        st.toast("✅ 綁定成功！"); break
