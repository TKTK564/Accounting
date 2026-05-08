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

# --- 5. 數據獲取與預處理 ---
worksheet = sh.worksheet(st.session_state.username)
records = worksheet.get_all_records()
df = pd.DataFrame(records)
if not df.empty:
    df['金額'] = pd.to_numeric(df['金額'], errors='coerce').fillna(0)
    df['日期'] = pd.to_datetime(df['日期'])
    df['年'] = df['日期'].dt.year
    df['月'] = df['日期'].dt.month
    df['年月'] = df['日期'].dt.strftime('%Y-%m')

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
        # 指標
        total_in = df[df['類型'] == '收入']['金額'].sum()
        total_ex = df[df['類型'] == '支出']['金額'].sum()
        st.columns(3)[0].metric("💰 實質總資產", f"${total_in - total_ex:,.0f}")
        st.columns(3)[1].metric("📈 累計總收入", f"${total_in:,.0f}")
        st.columns(3)[2].metric("📉 累計總支出", f"${total_ex:,.0f}")
        
        st.markdown("---")
        mode = st.radio("監控模式：", ["📉 每日流水趨勢 (月度)", "🏦 帳戶現金分佈", "🎯 預算上限監控"], horizontal=True)

        if mode == "📉 每日流水趨勢 (月度)":
            # 月份選取器
            available_months = sorted(df['年月'].unique(), reverse=True)
            selected_month = st.selectbox("請選擇要檢視的月份：", available_months)
            
            # 篩選該月份數據
            m_df = df[df['年月'] == selected_month].copy()
            m_df['純日期'] = m_df['日期'].dt.date
            
            # 取得該月完整的日期範圍
            y, m = map(int, selected_month.split('-'))
            last_day = calendar.monthrange(y, m)[1]
            full_dates = pd.date_range(start=f"{selected_month}-01", end=f"{selected_month}-{last_day}").date
            
            # 計算每日收入與支出
            daily_in = m_df[m_df['類型'] == '收入'].groupby('純日期')['金額'].sum()
            daily_ex = m_df[m_df['類型'] == '支出'].groupby('純日期')['金額'].sum()
            
            # 建立繪圖用 DataFrame
            plot_df = pd.DataFrame(index=full_dates)
            plot_df['收入'] = daily_in
            plot_df['支出'] = daily_ex
            plot_df = plot_df.fillna(0).reset_index().rename(columns={'index': '日期'})
            
            # 繪製圖表
            fig = go.Figure()
            # 收入柱狀圖 (正值)
            fig.add_trace(go.Bar(
                x=plot_df['日期'], y=plot_df['收入'],
                name='收入', marker_color='#28a745',
                hovertemplate='日期: %{x}<br>收入: $%{y:,.0f}<extra></extra>'
            ))
            # 支出柱狀圖 (顯示為負值)
            fig.add_trace(go.Bar(
                x=plot_df['日期'], y=-plot_df['支出'],
                name='支出', marker_color='#dc3545',
                hovertemplate='日期: %{x}<br>支出: $%{customdata:,.0f}<extra></extra>',
                customdata=plot_df['支出']
            ))
            
            fig.update_layout(
                title=f"📊 {selected_month} 每日流水趨勢",
                xaxis_title="日期", yaxis_title="金額 ($)",
                barmode='relative', # 正負柱狀圖重疊模式
                hovermode="x unified",
                xaxis=dict(type='date', tickformat='%d', tickmode='linear') # X軸強制顯示每一天
            )
            st.plotly_chart(fig, use_container_width=True)

        elif mode == "🏦 帳戶現金分佈":
            in_p = df[df['類型'] == '轉帳'].groupby('帳戶')['金額'].sum()
            out_p = df[df['類型'] == '支出'].groupby('帳戶')['金額'].sum()
            pool_rem = [{"帳戶": n, "現金": in_p[n] - out_p.get(n, 0)} for n in in_p.index if (in_p[n] - out_p.get(n, 0)) != 0]
            if pool_rem: st.plotly_chart(px.pie(pd.DataFrame(pool_rem), values='現金', names='帳戶', hole=0.4), use_container_width=True)

        elif mode == "🎯 預算上限監控":
            config_df = pd.DataFrame(st.session_state.pool_configs)
            real_ex = df[df['類型'] == '支出'].groupby('帳戶')['金額'].sum().reset_index().rename(columns={'帳戶': '池名', '金額': '實際支出'})
            comp = pd.merge(config_df, real_ex, on='池名', how='left').fillna(0)
            comp['計算上限'] = comp.apply(lambda r: r['上限值'] if r['上限模式'] == "固定金額" else (r['上限值']/100 * total_in), axis=1)
            fig = go.Figure()
            fig.add_trace(go.Bar(x=comp['池名'], y=comp['計算上限'], name='上限', marker_color='#adb5bd'))
            fig.add_trace(go.Bar(x=comp['池名'], y=comp['實際支出'], name='實際', marker_color='#dc3545'))
            fig.update_layout(barmode='overlay', title="預算執行率"); st.plotly_chart(fig, use_container_width=True)

# ------------------------------------------
# 【Tab 2：收入金錢分配】
# ------------------------------------------
with tabs[1]:
    st.header("📥 收入金錢分配")
    i_val = st.number_input("本次進帳總額", min_value=0, step=1000)
    i_note = st.text_input("來源備註", value="薪資")
    st.markdown("---")
    alloc_res = []; total_alloc = 0
    for p in st.session_state.pool_configs:
        c1, c2, c3 = st.columns([2, 2, 2])
        mode = c2.radio(f"模式", ["$", "%"], key=f"am_{p['池名']}", horizontal=True)
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
        if st.button("🚀 確認分配"):
            today = datetime.now().strftime('%Y-%m-%d')
            rows = [[today, '收入', '總額進帳', i_val, '主帳戶', i_note]]
            for r in alloc_res:
                if r['金額'] > 0: rows.append([today, '轉帳', '分配', r['金額'], r['池名'], f"模式: {r['模式']}"])
            worksheet.append_rows(rows); st.balloons(); st.rerun()
    elif i_val > 0: st.warning(f"分配總額 (${total_alloc}) 與進帳 (${i_val}) 不符")

# ------------------------------------------
# 【Tab 3：支出登錄】
# ------------------------------------------
with tabs[2]:
    st.header("💸 支出登錄")
    with st.container(border=True):
        en, ev = st.text_input("項目"), st.number_input("金額", min_value=0)
        ep = st.selectbox("扣款池", [p['池名'] for p in st.session_state.pool_configs])
        et = st.selectbox("類別", st.session_state.expense_cats)
        if st.button("🔴 確認寫入"):
            if ev > 0 and en:
                worksheet.append_row([datetime.now().strftime('%Y-%m-%d'), '支出', et, ev, ep, en])
                st.success(f"已從 {ep} 扣除"); st.rerun()

# ------------------------------------------
# 【Tab 4：數據管理】
# ------------------------------------------
with tabs[3]:
    st.header("📁 數據管理")
    if not df.empty:
        # 修正：轉換日期格式供編輯器顯示，並過濾掉輔助欄位
        m_df = df.drop(columns=['年', '月', '年月']).copy()
        m_df['日期'] = m_df['日期'].dt.date
        new_df = st.data_editor(m_df, num_rows="dynamic", use_container_width=True)
        if st.button("💾 同步雲端"):
            worksheet.clear(); worksheet.append_row(["日期", "類型", "類別", "金額", "帳戶", "備註"])
            save_df = new_df.copy(); save_df['日期'] = save_df['日期'].astype(str)
            worksheet.append_rows(save_df.values.tolist()); st.success("同步成功"); st.rerun()

# ------------------------------------------
# 【Tab 5：類別設定】
# ------------------------------------------
with tabs[4]:
    st.header("⚙️ 類別設定")
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("預算池與上限")
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
        if st.button("➕ 新增"): st.session_state.pool_configs.append({"池名": ap, "上限模式": "百分比", "上限值": 0}); st.rerun()
    with c2:
        st.subheader("支出類別")
        for i, ex in enumerate(st.session_state.expense_cats):
            col1, col2 = st.columns([3, 1])
            col1.write(f"🔹 {ex}")
            if col2.button("刪除", key=f"ed_{i}"): st.session_state.expense_cats.pop(i); st.rerun()
        ne = st.text_input("新增類別..."); 
        if st.button("➕ 新增項"): st.session_state.expense_cats.append(ne); st.rerun()
