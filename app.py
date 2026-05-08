import streamlit as st
import gspread
import json
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
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
except Exception as e:
    st.error(f"❌ 雲端連線失敗：{e}"); st.stop()

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
    st.session_state.expense_cats = ["飲食", "交通", "自我提升", "娛樂", "固定訂閱", "年度稅金"]

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
            st.toast("✅ 註冊成功！", icon="🎉")
    st.stop()

# --- 5. 數據加載與資料表初始化 ---
worksheet = sh.worksheet(st.session_state.username)
records = worksheet.get_all_records()
df = pd.DataFrame(records)
if not df.empty:
    df['金額'] = pd.to_numeric(df['金額'], errors='coerce').fillna(0)
    df['日期'] = pd.to_datetime(df['日期'])
    df['年月'] = df['日期'].dt.strftime('%Y-%m')
    df['年'] = df['日期'].dt.year

# 自動扣款設定表初始化
try:
    rec_ws = sh.worksheet(f"{st.session_state.username}_自動扣款")
except gspread.WorksheetNotFound:
    rec_ws = sh.add_worksheet(title=f"{st.session_state.username}_自動扣款", rows="100", cols="10")
    rec_ws.append_row(["項目名稱", "金額", "預算池", "支出類別", "扣款時間", "週期"])
rec_records = rec_ws.get_all_records()
rec_df = pd.DataFrame(rec_records)

# ==========================================
# --- 6. 主戰情系統 ---
# ==========================================
colA, colB = st.columns([5, 1])
with colA: st.title(f"🛠️ {st.session_state.username} 的財務戰略中心")
with colB: 
    if st.button("登出 👋"): st.session_state.logged_in = False; st.rerun()

tabs = st.tabs(["📊 戰情看板", "📥 收入分配", "💸 支出登錄", "🔄 自動扣款", "📁 數據管理", "⚙️ 設定中心"])

# ------------------------------------------
# 【Tab 1：戰情看板】
# ------------------------------------------
with tabs[0]:
    if df.empty:
        st.info("尚無數據，請先開始記帳。")
    else:
        total_in = df[df['類型'] == '收入']['金額'].sum()
        total_ex = df[df['類型'] == '支出']['金額'].sum()
        st.columns(3)[0].metric("💰 實質總資產", f"${total_in - total_ex:,.0f}")
        st.columns(3)[1].metric("📈 累計總收入", f"${total_in:,.0f}")
        st.columns(3)[2].metric("📉 累計總支出", f"${total_ex:,.0f}")
        
        st.markdown("---")
        available_months = sorted(df['年月'].unique(), reverse=True)
        selected_month = st.selectbox("📅 選擇觀測月份：", available_months)
        m_df = df[df['年月'] == selected_month].copy()
        
        mode = st.radio("監控模式：", 
                        ["📉 每日流水趨勢", "💰 月份收入來源", "💸 月份支出分佈", "🏦 預算剩餘", "🎯 預算上限監控"], 
                        horizontal=True)

        if mode == "📉 每日流水趨勢":
            y, m = map(int, selected_month.split('-'))
            last_day = calendar.monthrange(y, m)[1]
            full_dates = pd.date_range(start=f"{selected_month}-01", end=f"{selected_month}-{last_day}").date
            
            daily_in = m_df[m_df['類型'] == '收入'].groupby(m_df['日期'].dt.date)['金額'].sum()
            daily_ex = m_df[m_df['類型'] == '支出'].groupby(m_df['日期'].dt.date)['金額'].sum()
            
            plot_df = pd.DataFrame(index=full_dates)
            plot_df['收入'] = daily_in
            plot_df['支出'] = daily_ex
            plot_df = plot_df.fillna(0).reset_index().rename(columns={'index': '日期'})
            
            fig = go.Figure()
            fig.add_trace(go.Bar(x=plot_df['日期'], y=plot_df['收入'], name='每日收入', marker_color='#28a745', hovertemplate='收入: $%{y:,.0f}'))
            fig.add_trace(go.Bar(x=plot_df['日期'], y=-plot_df['支出'], name='每日支出', marker_color='#dc3545', customdata=plot_df['支出'], hovertemplate='支出: $%{customdata:,.0f}'))
            fig.update_layout(title=f"📊 {selected_month} 每日流水", barmode='relative', xaxis=dict(type='date', tickformat='%d'))
            st.plotly_chart(fig, use_container_width=True)

        elif mode == "💰 月份收入來源":
            inc_df = m_df[m_df['類型'] == '收入']
            if not inc_df.empty: st.plotly_chart(px.pie(inc_df, values='金額', names='備註', hole=0.4, title=f"{selected_month} 收入來源"), use_container_width=True)
            else: st.write("尚無紀錄。")

        elif mode == "💸 月份支出分佈":
            exp_df = m_df[m_df['類型'] == '支出']
            if not exp_df.empty: st.plotly_chart(px.pie(exp_df, values='金額', names='類別', hole=0.4, title=f"{selected_month} 支出分佈"), use_container_width=True)
            else: st.write("尚無紀錄。")

        elif mode == "🏦 預算剩餘":
            in_p = df[df['類型'] == '轉帳'].groupby('帳戶')['金額'].sum()
            out_p = df[df['類型'] == '支出'].groupby('帳戶')['金額'].sum()
            pool_rem = [{"帳戶": n, "現金": in_p[n] - out_p.get(n, 0)} for n in in_p.index if (in_p[n] - out_p.get(n, 0)) != 0]
            if pool_rem: st.plotly_chart(px.pie(pd.DataFrame(pool_rem), values='現金', names='帳戶', hole=0.4, title="各帳戶預算剩餘"), use_container_width=True)
            else: st.write("尚無紀錄。")

        elif mode == "🎯 預算上限監控":
            config_df = pd.DataFrame(st.session_state.pool_configs)
            real_ex = df[df['類型'] == '支出'].groupby('帳戶')['金額'].sum().reset_index().rename(columns={'帳戶': '池名', '金額': '實際支出'})
            comp = pd.merge(config_df, real_ex, on='池名', how='left').fillna(0)
            comp['計算上限'] = comp.apply(lambda r: r['上限值'] if r['上限模式'] == "固定金額" else (r['上限值']/100 * total_in), axis=1)
            fig = go.Figure()
            fig.add_trace(go.Bar(x=comp['池名'], y=comp['計算上限'], name='預算上限', marker_color='#adb5bd'))
            fig.add_trace(go.Bar(x=comp['池名'], y=comp['實際支出'], name='實際花費', marker_color='#dc3545'))
            fig.update_layout(barmode='overlay', title="預算執行監控"); st.plotly_chart(fig, use_container_width=True)

# ------------------------------------------
# 【Tab 2：收入金錢分配】
# ------------------------------------------
with tabs[1]:
    st.header("📥 收入金錢分配")
    i_val = st.number_input("本次進帳總額", min_value=0, step=1000)
    i_note = st.text_input("來源說明", value="本薪")
    st.markdown("---")
    alloc_res = []; total_alloc = 0
    for p in st.session_state.pool_configs:
        c1, c2, c3 = st.columns([2, 2, 2])
        c1.write(f"**{p['池名']}**")
        mode = c2.radio(f"分配模式", ["$", "%"], key=f"am_{p['池名']}", horizontal=True)
        if mode == "$":
            amt = c3.number_input(f"金額", min_value=0, key=f"av_{p['池名']}")
            final_a = amt
        else:
            pct = c3.number_input(f"百分比", min_value=0, max_value=100, key=f"ap_{p['池名']}")
            final_a = int(i_val * (pct/100))
            c3.write(f"折合 ${final_a}")
        total_alloc += final_a
        alloc_res.append({"池名": p['池名'], "金額": final_a, "模式": mode})
    
    if i_val > 0 and total_alloc == i_val:
        if st.button("🚀 確認分配寫入"):
            today = datetime.now().strftime('%Y-%m-%d')
            rows = [[today, '收入', '總額進帳', i_val, '主帳戶', i_note]]
            for r in alloc_res:
                if r['金額'] > 0: rows.append([today, '轉帳', '分配', r['金額'], r['池名'], f"模式: {r['模式']}"])
            worksheet.append_rows(rows)
            st.toast("✅ 收入分配已寫入！", icon="💸")
            st.rerun()
    elif i_val > 0: st.warning(f"分配總額 (${total_alloc}) 與進帳 (${i_val}) 不符")

# ------------------------------------------
# 【Tab 3：支出登錄】
# ------------------------------------------
with tabs[2]:
    st.header("💸 支出登錄")
    with st.container(border=True):
        en, ev = st.text_input("項目"), st.number_input("金額", min_value=0)
        ep = st.selectbox("扣款池", [p['池名'] for p in st.session_state.pool_configs])
        et = st.selectbox("細項類別", st.session_state.expense_cats)
        if st.button("🔴 確認寫入"):
            if ev > 0 and en:
                worksheet.append_row([datetime.now().strftime('%Y-%m-%d'), '支出', et, ev, ep, en])
                st.toast(f"✅ 已從 {ep} 扣除 ${ev}", icon="📉")
                st.rerun()

# ------------------------------------------
# 【Tab 4：自動扣款】
# ------------------------------------------
with tabs[3]:
    st.header("🔄 定期自動扣款系統")
    st.write("設定每個月或每年的固定支出。系統會自動追蹤，確保不重複扣款。")
    
    today_dt = datetime.now()
    curr_m_str = today_dt.strftime('%Y-%m')
    curr_y = today_dt.year
    curr_m = today_dt.month
    curr_d = today_dt.day
    
    deducted_this_month = []
    deducted_this_year = []
    if not df.empty:
        auto_m = df[(df['年月'] == curr_m_str) & (df['備註'].str.startswith('[自動扣款]'))]
        deducted_this_month = auto_m['備註'].tolist()
        auto_y = df[(df['年'] == curr_y) & (df['備註'].str.startswith('[自動扣款]'))]
        deducted_this_year = auto_y['備註'].tolist()
    
    pending_items = []
    if not rec_df.empty:
        st.subheader("📋 目前的扣款設定")
        st.dataframe(rec_df)
        
        time_col = rec_df.columns[4]
        cycle_col = rec_df.columns[5] if len(rec_df.columns) > 5 else None
        
        for _, row in rec_df.iterrows():
            item_tag = f"[自動扣款] {row['項目名稱']}"
            cycle = str(row[cycle_col]) if cycle_col else "每月"
            time_val = str(row[time_col])
            
            is_pending = False
            if cycle == "每年":
                try:
                    m_str, d_str = time_val.split('-')
                    t_m, t_d = int(m_str), int(d_str)
                except: t_m, t_d = 1, 1
                
                if (curr_m > t_m) or (curr_m == t_m and curr_d >= t_d):
                    if item_tag not in deducted_this_year: is_pending = True
            else:
                try: t_d = int(float(time_val))
                except: t_d = 1
                if curr_d >= t_d and item_tag not in deducted_this_month: is_pending = True
            
            if is_pending: pending_items.append(row)
        
        if pending_items:
            st.warning(f"⚠️ 偵測到 {len(pending_items)} 筆尚未執行的自動扣款！")
            for p in pending_items:
                c_str = str(p[cycle_col]) if cycle_col else "每月"
                st.write(f"🔹 **{p['項目名稱']}**：應扣 ${p['金額']} ({c_str} {p[time_col]} 扣款)")
            
            if st.button("⚡ 執行所有待處理扣款"):
                today_str = today_dt.strftime('%Y-%m-%d')
                auto_rows = []
                for p in pending_items:
                    auto_rows.append([today_str, '支出', p['支出類別'], p['金額'], p['預算池'], f"[自動扣款] {p['項目名稱']}"])
                worksheet.append_rows(auto_rows)
                st.toast("✅ 自動扣款執行完畢！", icon="🤖")
                st.rerun()
        else:
            st.success("✅ 目前所有應扣款項目皆已結清！無待處理事項。")

    st.markdown("---")
    st.subheader("➕ 新增自動扣款規則")
    with st.container(border=True):
        c1, c2, c3 = st.columns(3)
        r_name = c1.text_input("項目名稱 (如：Spotify、牌照稅)")
        r_amt = c2.number_input("扣款金額", min_value=0)
        r_cycle = c3.selectbox("扣款週期", ["每月", "每年"])
        
        c4, c5, c6 = st.columns(3)
        r_pool = c4.selectbox("預算池", [p['池名'] for p in st.session_state.pool_configs])
        r_cat = c5.selectbox("支出分類", st.session_state.expense_cats)
        
        if r_cycle == "每月":
            r_day = c6.number_input("每月幾號扣款？(1-31)", min_value=1, max_value=31, value=1)
            save_time = str(r_day)
        else:
            cc1, cc2 = c6.columns(2)
            rm = cc1.number_input("扣款月份", min_value=1, max_value=12, value=1)
            rd = cc2.number_input("扣款日期", min_value=1, max_value=31, value=1)
            save_time = f"{int(rm):02d}-{int(rd):02d}"
        
        if st.button("💾 儲存自動扣款設定"):
            if r_name and r_amt > 0:
                rec_ws.append_row([r_name, r_amt, r_pool, r_cat, save_time, r_cycle])
                st.toast("✅ 規則已儲存！", icon="📝")
                st.rerun()

# ------------------------------------------
# 【Tab 5：數據管理】
# ------------------------------------------
with tabs[4]:
    st.header("📁 數據管理")
    if not df.empty:
        m_df = df.drop(columns=['年月', '年'], errors='ignore').copy()
        m_df['日期'] = m_df['日期'].dt.date
        new_df = st.data_editor(m_df, num_rows="dynamic", use_container_width=True)
        if st.button("💾 同步雲端"):
            worksheet.clear(); worksheet.append_row(["日期", "類型", "類別", "金額", "帳戶", "備註"])
            save_df = new_df.copy(); save_df['日期'] = save_df['日期'].astype(str)
            worksheet.append_rows(save_df.values.tolist())
            st.toast("✅ 雲端同步成功", icon="☁️")
            st.rerun()

# ------------------------------------------
# 【Tab 6：設定中心 (加入財政部捷徑)】
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
        if st.button("➕ 新增池"): 
            st.session_state.pool_configs.append({"池名": ap, "上限模式": "百分比", "上限值": 0})
            st.toast("✅ 預算池新增成功！", icon="🏦"); st.rerun()
    
    with c2:
        st.subheader("🛠️ 支出類別")
        for i, ex in enumerate(st.session_state.expense_cats):
            col1, col2 = st.columns([3, 1])
            col1.write(f"🔹 {ex}")
            if col2.button("刪除", key=f"ed_{i}"): st.session_state.expense_cats.pop(i); st.rerun()
        ne = st.text_input("新增類別..."); 
        if st.button("➕ 新增項"): 
            st.session_state.expense_cats.append(ne)
            st.toast("✅ 類別新增成功！", icon="🏷️"); st.rerun()

    st.markdown("---")
    st.subheader("📡 財政部載具 API 設定區 (準備中)")
    st.write("要讓發票自動匯入，請先確認您的載具驗證碼，並申請 API 金鑰。您可點擊下方按鈕前往財政部平台處理。")
    
    # 建立快捷通道按鈕
    link_c1, link_c2 = st.columns(2)
    with link_c1:
        st.link_button("🔗 忘記驗證碼？前往重設 (點選忘記驗證碼)", "https://www.einvoice.nat.gov.tw/APCONSUMER/BTC501W/")
    with link_c2:
        st.link_button("🔗 申請發票 API (AppID) 頁面", "https://www.einvoice.nat.gov.tw/APMEMBERVAN/XcaAppId/XcaAppId010W_UI")

    with st.container(border=True):
        st.text_input("手機條碼 (CardNo)", placeholder="/XXXXXXX")
        st.text_input("驗證碼 (CardEncrypt)", type="password")
        st.text_input("API AppID", type="password")
        if st.button("🔒 儲存金鑰 (暫不啟動)"):
            st.toast("金鑰已記錄，待工作流串接後啟動。", icon="🔧")
