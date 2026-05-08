import streamlit as st
from datetime import datetime

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
        # 這裡放入我們上一個步驟寫好的 gspread 寫入邏輯
        # 把資料傳送到 Google Sheets

        st.balloons()  # 寫入成功後的視覺回饋
        st.success("資料已成功同步至資料庫！")