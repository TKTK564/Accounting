import streamlit as st
import gspread
import json
from datetime import datetime  # 補上這個：用來抓取今天的日期

# 讀取我們包裝好的字串，並轉回原本的字典格式
credentials = json.loads(st.secrets["gcp_service_account_json"])
gc = gspread.service_account_from_dict(credentials)

sh = gc.open('專屬財務戰情資料庫')
worksheet = sh.sheet1

# 隱藏網頁預設的選單，讓它更像一個 APP
st.set_page_config(page_title="個人財務戰情系統", layout="centered")
st.markdown("""
    <style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    </style>
    """, unsafe_allow_html=True)

st.title("📊 財務戰情中心")

# 1. 收入輸入區
st.header("1. 資金匯入")
income_amount = st.number_input("請輸入本次進帳金額", min_value=0, value=10000, step=1000)
source_name = st.text_input("資金來源備註", value="本薪/獎學金")

# 2. 動態預算分配器 (核心介面)
st.header("2. 戰略分配設定")
st.write("滑動以調整本次預算比例，請確保總和為 100%")

# 使用滑桿讓你在手機上可以直接拖曳調整
col1, col2, col3 = st.columns(3)
with col1:
    living_ratio = st.slider("生活預算 %", 0, 100, 50)
with col2:
    invest_ratio = st.slider("投資預算 %", 0, 100, 30)
with col3:
    saving_ratio = st.slider("儲蓄預算 %", 0, 100, 20)

total_ratio = living_ratio + invest_ratio + saving_ratio

# 3. 視覺化預覽與防呆機制
if total_ratio != 100:
    st.error(f"⚠️ 目前總和為 {total_ratio}%，必須剛好等於 100% 才能執行。")
else:
    st.success("✅ 比例分配完美")

    # 預覽計算結果
    st.write(f"**生活預算池：** ${int(income_amount * (living_ratio / 100))}")
    st.write(f"**投資帳戶：** ${int(income_amount * (invest_ratio / 100))}")
    st.write(f"**儲蓄帳戶：** ${int(income_amount * (saving_ratio / 100))}")

    # 執行按鈕
    if st.button("⚡ 確認寫入戰情資料庫"):
        # 【補上核心寫入邏輯】
        today = datetime.now().strftime('%Y-%m-%d')
        records_to_add = []

        # 1. 紀錄總收入 (寫入第一筆)
        records_to_add.append([today, '收入', source_name, income_amount, '主帳戶', '收入進帳'])

        # 2. 紀錄分配轉帳 (寫入後續三筆)
        records_to_add.append(
            [today, '轉帳', f'生活預算({living_ratio}%)', int(income_amount * (living_ratio / 100)), '生活預算池',
             '系統自動預算分配'])
        records_to_add.append(
            [today, '轉帳', f'投資預算({invest_ratio}%)', int(income_amount * (invest_ratio / 100)), '投資帳戶',
             '系統自動預算分配'])
        records_to_add.append(
            [today, '轉帳', f'儲蓄預算({saving_ratio}%)', int(income_amount * (saving_ratio / 100)), '儲蓄帳戶',
             '系統自動預算分配'])

        # 3. 實際把資料推送到 Google Sheets
        try:
            worksheet.append_rows(records_to_add)
            st.balloons()  # 寫入成功後的視覺回饋
            st.success("✅ 戰術執行成功！資料已同步至雲端資料庫。")
        except Exception as e:
            st.error(f"❌ 寫入失敗，請檢查權限或連