import streamlit as st

from utils.kpi import load_sku_shipment_data, classify_abc, compute_storage_layout
from utils.charts import chart_eiq_scatter, style_storage_grid


def render_page():
    """
    渲染 D6 儲位重排頁面。
    運算邏輯統一放在 utils/kpi.py，圖表建立統一放在 utils/charts.py，
    這支檔案只負責讀檔錯誤處理、版面排版與呼叫上述函式顯示結果。
    """
    try:
        raw_df = load_sku_shipment_data()
    except FileNotFoundError:
        st.error("❌ 找不到數據檔案！請確認您的檔案已放置於： `Datas/SKU_出貨明細_202509.csv`")
        return

    sku = classify_abc(raw_df)

    # ===== 標題區塊 =====
    st.markdown("<h2 style='white-space: nowrap;'>📦 D6 儲位重排：ABC 分類 × 動態熱區</h2>", unsafe_allow_html=True)
    st.markdown("---")

    # ===== 第一層：ABC 概覽與 EIQ 分析圖 =====
    row1_col1, row1_col2 = st.columns([4, 6])

    counts = sku["類別"].value_counts()
    summary = sku.groupby("類別", observed=True)["總出貨量"].sum()
    pct = (summary / summary.sum() * 100).round(1)

    with row1_col1:
        with st.container(border=True):
            st.markdown("<h4 style='margin:0 0 15px 0;'>📊 ABC 分類結構</h4>", unsafe_allow_html=True)

            sub_c1, sub_c2, sub_c3 = st.columns(3)
            sub_c1.metric(label="A類商品", value=f"{counts.get('A', 0)}款", delta=f"{pct.get('A', 0)}% 出貨")
            sub_c2.metric(label="B類商品", value=f"{counts.get('B', 0)}款", delta=f"{pct.get('B', 0)}% 出貨")
            sub_c3.metric(label="C類商品", value=f"{counts.get('C', 0)}款", delta=f"{pct.get('C', 0)}% 出貨")

            st.markdown("<br>", unsafe_allow_html=True)
            st.markdown("##### 💡 管理思維")
            st.caption(f"A類核心品項僅佔少數品類，卻貢獻了近 **{pct.get('A', 0)}%** 的總出貨量，應優先配置於黃金儲位，以最大化揀貨效率並降低跨區搬運工時。")

    with row1_col2:
        with st.container(border=True):
            fig = chart_eiq_scatter(sku)
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

    sku, grid_before, grid_after = compute_storage_layout(sku, sort_method)
    sku_to_cat = sku.set_index("SKU")["類別"].to_dict()

    # ===== 第三層：重排前後儲位圖(左右並排 5:5 視覺對照)=====
    row2_col1, row2_col2 = st.columns(2)

    with row2_col1:
        st.markdown("##### 🏢 重排前儲位圖（對照組）")
        st.dataframe(style_storage_grid(grid_before, sku_to_cat), use_container_width=True)
        st.caption("說明：依原始 SKU 編號由左至右、上至下排列，高熱品項（紅）散落各處。")

    with row2_col2:
        st.markdown(f"##### 🎯 重排後儲位圖（依 {sort_method}）")
        st.dataframe(style_storage_grid(grid_after, sku_to_cat), use_container_width=True)
        st.caption("說明：高熱品項（紅）已成功往左下角（靠近出入口）集中，有效縮短揀貨動線。")
