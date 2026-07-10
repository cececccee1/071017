import streamlit as st
import pandas as pd
import plotly.express as px
import os

def render_page():
    # ===== 1. 讀取與處理資料 =====
    @st.cache_data
    def load_and_process_data():
        file_path = os.path.join("Datas", "SKU_出貨明細_202509.csv")
        df = pd.read_csv(file_path, encoding="utf-8-sig", parse_dates=["訂單日期"])
        
        sku_df = (df.groupby(["SKU", "品名"])
                 .agg(總出貨量=("數量", "sum"),
                      出貨筆數=("訂單編號", "nunique"))
                 .reset_index()
                 .sort_values("總出貨量", ascending=False))
        
        sku_df["累計佔比"] = sku_df["總出貨量"].cumsum() / sku_df["總出貨量"].sum()
        sku_df["類別"] = pd.cut(sku_df["累計佔比"],
                            bins=[0, 0.80, 0.95, 1.0001],
                            labels=["A", "B", "C"])
        return sku_df

    try:
        sku = load_and_process_data()
    except FileNotFoundError:
        st.error("❌ 找不到數據檔案！請確認您的檔案已放置於： `Datas/SKU_出貨明細_202509.csv`")
        return

    # ===== 標題區塊 =====
    st.markdown("<h2 style='white-space: nowrap;'>📦 D6 儲位重排：ABC 分類 × 動態熱區</h2>", unsafe_allow_html=True)
    st.markdown("---")

    # ===== 第一層：ABC 概覽與 EIQ 分析圖 (調整比例與圖表尺寸) =====
    # 將左右比例調整為 4:6，給予右邊圖表更寬敞的空間
    row1_col1, row1_col2 = st.columns([4, 6]) 

    # 計算分類數據
    counts = sku["類別"].value_counts()
    summary = sku.groupby("類別", observed=True)["總出貨量"].sum()
    pct = (summary / summary.sum() * 100).round(1)

    with row1_col1:
        with st.container(border=True):
            st.markdown("<h4 style='margin:0 0 15px 0;'>📊 ABC 分類結構</h4>", unsafe_allow_html=True)
            
            # 卡片排列
            sub_c1, sub_c2, sub_c3 = st.columns(3)
            sub_c1.metric(label="A類商品", value=f"{counts.get('A', 0)}款", delta=f"{pct.get('A', 0)}% 出貨")
            sub_c2.metric(label="B類商品", value=f"{counts.get('B', 0)}款", delta=f"{pct.get('B', 0)}% 出貨")
            sub_c3.metric(label="C類商品", value=f"{counts.get('C', 0)}款", delta=f"{pct.get('C', 0)}% 出貨")
            
            st.markdown("<br>", unsafe_allow_html=True) # 稍微增加一點內距
            st.markdown("##### 💡 管理思維")
            st.caption(f"A類核心品項僅佔少數品類，卻貢獻了近 **{pct.get('A', 0)}%** 的總出貨量，應優先配置於黃金儲位，以最大化揀貨效率並降低跨區搬運工時。")

    with row1_col2:
        with st.container(border=True):
            # 視覺化散佈圖
            ABC_COLORS = {"A": "#d62728", "B": "#2ca02c", "C": "#bdbdbd"}
            fig = px.scatter(sku, x="出貨筆數", y="總出貨量", color="類別",
                             color_discrete_map=ABC_COLORS,
                             category_orders={"類別": ["A", "B", "C"]},
                             hover_data=["SKU", "品名"])
            
            # 🔥 關鍵優化：將 height 從 220 放大到 320，並將圖例移到更醒目的右上角，完美填滿外框
            fig.update_layout(
                title=dict(text="EIQ 分析: IK(出貨筆數) × IQ(總出貨量)", y=0.95, x=0.02),
                margin=dict(l=15, r=15, t=50, b=15), 
                height=320, 
                legend=dict(
                    orientation="h", 
                    yanchor="bottom", 
                    y=1.02, 
                    xanchor="right", 
                    x=1,
                    title=dict(text="商品類別:")
                )
            )
            st.plotly_chart(fig, use_container_width=True)

    st.markdown("---")

    # ===== 第二層：儲位優化策略與控制器 =====
    st.subheader("🎯 儲位優化對照表")
    
    with st.container(border=True):
        sort_method = st.radio(
            "請選擇儲位重排依據：",
            ["IQ(總出貨量)", "IK(出貨筆數)", "IQ×IK 綜合分數"],
            horizontal=True,
            help="反直覺思考：只看 IQ 會忽略『被點得勤但單次量小（高 IK）』的品項，導致揀貨員無效走動。"
        )
        st.caption(f"💡 目前計算邏輯：**{sort_method}** · 模擬出入口設在 **左下角 (E列, 1排)**")

    # ===== 演算法邏輯：計算重排資料 =====
    rows = ["A列", "B列", "C列", "D列", "E列"]
    cols = [f"{i}排" for i in range(1, 11)]

    # 原始排列資料
    sku_before = sku.sort_values("SKU").reset_index(drop=True)
    before_queue = sku_before["SKU"].tolist()
    grid_before_arr = [["" for _ in range(10)] for _ in range(5)]
    for idx in range(min(50, len(before_queue))):
        r, c = idx // 10, idx % 10
        grid_before_arr[r][c] = before_queue[idx]
    grid_before = pd.DataFrame(grid_before_arr, index=rows, columns=cols)

    # 依條件排序新佇列
    if sort_method == "IQ(總出貨量)":
        queue = sku.sort_values("總出貨量", ascending=False)["SKU"].tolist()
    elif sort_method == "IK(出貨筆數)":
        queue = sku.sort_values("出貨筆數", ascending=False)["SKU"].tolist()
    else:
        sku["IK_norm"] = sku["出貨筆數"] / sku["出貨筆數"].max()
        sku["IQ_norm"] = sku["總出貨量"] / sku["總出貨量"].max()
        sku["綜合分數"] = sku["IK_norm"] * 0.4 + sku["IQ_norm"] * 0.6
        queue = sku.sort_values("綜合分數", ascending=False)["SKU"].tolist()

    # 計算曼哈頓距離
    distances = []
    for r in range(5):
        for c in range(10):
            d = abs(r - 4) + abs(c - 0)
            distances.append((d, r, c))
    distances.sort(key=lambda x: x)

    grid_after_arr = [["" for _ in range(10)] for _ in range(5)]
    for idx, (d, r, c) in enumerate(distances[:50]):
        grid_after_arr[r][c] = queue[idx]
    grid_after = pd.DataFrame(grid_after_arr, index=rows, columns=cols)

    # 上色函數
    sku_to_cat = sku.set_index("SKU")["類別"].to_dict()
    def color_by_category(val):
        cat = sku_to_cat.get(val, "")
        color_map = {
            "A": "background-color: #d62728; color: white;",
            "B": "background-color: #2ca02c; color: white;",
            "C": "background-color: #bdbdbd; color: black;"
        }
        return color_map.get(cat, "")

    # ===== 第三層：重排前後儲位圖 (左右並排 5:5 視覺對照) =====
    row2_col1, row2_col2 = st.columns(2)

    with row2_col1:
        st.markdown("##### 🏢 重排前儲位圖（對照組）")
        st.dataframe(grid_before.style.map(color_by_category), use_container_width=True)
        st.caption("說明：依原始 SKU 編號由左至右、上至下排列，高熱品項（紅）散落各處。")

    with row2_col2:
        st.markdown(f"##### 🎯 重排後儲位圖（依 {sort_method}）")
        st.dataframe(grid_after.style.map(color_by_category), use_container_width=True)
        st.caption("說明：高熱品項（紅）已成功往左下角（靠近出入口）集中，有效縮短揀貨動線。")
