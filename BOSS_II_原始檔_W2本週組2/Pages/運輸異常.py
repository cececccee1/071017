import streamlit as st
import folium
from streamlit_folium import st_folium

from utils.kpi import (
    load_delivery_data,
    process_delivery_records,
    compute_route_driver_otd,
    diagnose_main_cause,
    detect_rolling_anomaly,
    build_delivery_diagnosis_text,
)
from utils.charts import (
    chart_offset_distribution,
    chart_zscore_histogram,
    chart_rolling_anomaly,
)


def render_page():
    """
    渲染 Day 7 運輸異常頁面。
    運算邏輯統一放在 utils/kpi.py，圖表建立統一放在 utils/charts.py，
    這支檔案只負責讀檔錯誤處理、版面排版與呼叫上述函式顯示結果。
    """
    try:
        df = load_delivery_data()
    except FileNotFoundError:
        st.error("❌ 找不到數據檔案!請確認您的檔案已放置於:`Datas/配送紀錄_202509.csv`")
        return

    df = process_delivery_records(df)

    st.markdown("<h2 style='white-space: nowrap;'>🕵️ D7 遲到偵探:OTD 診斷 × 異常偵測</h2>", unsafe_allow_html=True)

    st.subheader("📋 資料概況")
    c1, c2, c3 = st.columns(3)
    c1.metric("資料筆數", f"{len(df):,}")
    c2.metric("路線數", df["路線代碼"].nunique())
    c3.metric("司機數", df["司機代碼"].nunique())

    整體_OTD = df["OTD_嚴格"].mean()
    在窗率 = df["在窗內"].mean()
    完整率 = df["完整"].mean()

    st.subheader("🎯 整體 OTD 指標")
    c1, c2, c3 = st.columns(3)
    c1.metric("在窗率(時窗內)", f"{在窗率:.1%}")
    c2.metric("完整率(無貨損)", f"{完整率:.1%}")
    c3.metric("嚴格 OTD", f"{整體_OTD:.1%}")
    if 整體_OTD < 0.90:
        st.error("🔴 警戒區:< 90%,屬於系統性問題,不是個別事件")
    elif 整體_OTD < 0.95:
        st.warning("🟠 偏低:需深度檢視路線/時段")
    else:
        st.success("🟡 健康:可以維持現況")

    # §B 拆三層(路線 / 司機)+ 控制變量
    路線_OTD, 司機_OTD = compute_route_driver_otd(df)

    c1, c2 = st.columns(2)
    c1.write("**🛣️ 路線 OTD(遞增 · 最差路線在最上面)**")
    c1.dataframe(路線_OTD[["訂單數", "OTD%"]], width="stretch")
    c2.write("**🚚 司機 OTD(遞增 · 最差司機在最上面)**")
    c2.dataframe(司機_OTD[["訂單數", "OTD%"]], width="stretch")

    worst_driver = 司機_OTD.index[0]
    ctrl, diag_main = diagnose_main_cause(df, worst_driver)

    st.write(f"最差司機:**{worst_driver}**(整體 OTD {司機_OTD.loc[worst_driver, 'OTD%']}%)"
             f" · 在不同路線 OTD 落差 std = {ctrl['OTD'].std():.2f} → 診斷主因 = **{diag_main}**")
    st.dataframe(ctrl[["訂單數", "OTD%"]], width="stretch")

    # ===== §C 配送時間偏移分布(IQR)=====
    st.subheader("📊 配送時間偏移分布(IQR)")
    fig_c, skew = chart_offset_distribution(df)
    st.caption(f"偏態 skew = {skew:+.2f}({'右偏' if skew > 0 else '左偏' if skew < 0 else '對稱'})")
    st.plotly_chart(fig_c, use_container_width=True)

    # ===== §C2 Z-score 異常偵測 =====
    st.subheader("📊 Z-score 異常偵測(適合對稱分布)")
    fig_z = chart_zscore_histogram(df)
    st.plotly_chart(fig_z, use_container_width=True)

    # ===== §C3 Rolling 異常偵測 =====
    每日 = detect_rolling_anomaly(df, window=7)
    st.subheader("📊 Rolling 異常偵測(適合有季節性的時序)")
    fig_r = chart_rolling_anomaly(每日)
    st.plotly_chart(fig_r, use_container_width=True)

    st.write(f"滾動窗格 = 7 天 · 異常日數 = {int(每日['異常日'].sum())} / {len(每日)} 天")
    if 每日["異常日"].any():
        st.dataframe(每日.loc[每日["異常日"], ["日平均偏移分鐘", "滾動平均", "上界", "下界"]].round(1),
                     width="stretch")

    # §D 異常的 pattern
    anomalies = df[df["異常旗標"]]

    st.subheader("🔍 異常 Pattern")
    c1, c2 = st.columns(2)
    c1.write("異常 by 路線 Top 5")
    c1.dataframe(anomalies["路線代碼"].value_counts().head())
    c2.write("異常 by 司機 Top 5")
    c2.dataframe(anomalies["司機代碼"].value_counts().head())
    c1, c2 = st.columns(2)
    c1.write("異常 by 小時段 Top 5")
    c1.dataframe(anomalies["預計到達"].dt.hour.value_counts().head())
    c2.write("異常 by 路線 × 司機交互 Top 5")
    cross = (anomalies.groupby(["路線代碼", "司機代碼"])
             .size().sort_values(ascending=False).head())
    c2.dataframe(cross)

    # §E 早到也是異常
    c1, c2, c3 = st.columns(3)
    c1.metric("早到佔比", f"{df['早到'].mean():.1%}", f"{df['早到'].sum():,} 筆")
    c2.metric("遲到佔比", f"{df['遲到'].mean():.1%}", f"{df['遲到'].sum():,} 筆")
    c3.metric("在窗內", f"{df['在窗內'].mean():.1%}", f"{df['在窗內'].sum():,} 筆")

    st.download_button("⬇️ 下載異常配送清單 CSV",
                        anomalies.to_csv(index=False).encode("utf-8-sig"),
                        file_name="異常配送清單.csv", mime="text/csv")

    # §G 病灶診斷
    diag = build_delivery_diagnosis_text(df, anomalies, worst_driver, ctrl, diag_main, 整體_OTD)
    st.subheader("🩺 病灶診斷")
    st.info(diag)

    # §I Folium 互動地圖看板 — 標出異常紅燈區域
    map_container = st.container()
    with map_container:
        st.subheader("🗺️ 異常紅燈地圖")
        center_lat = df["客戶緯度"].mean()
        center_lon = df["客戶經度"].mean()
        m = folium.Map(location=[center_lat, center_lon], zoom_start=11, tiles="OpenStreetMap")

        for _, row in df.iterrows():
            is_anomaly = bool(row["異常旗標"])
            folium.CircleMarker(
                location=[row["客戶緯度"], row["客戶經度"]],
                radius=6 if is_anomaly else 3,
                color="#d62728" if is_anomaly else "#2ca02c",
                fill=True,
                fill_color="#d62728" if is_anomaly else "#2ca02c",
                fill_opacity=0.7 if is_anomaly else 0.4,
                popup=folium.Popup(
                    f"<b>{row['訂單編號']}</b><br>"
                    f"路線:{row['路線代碼']} · 司機:{row['司機代碼']}<br>"
                    f"偏移:{row['偏移分鐘']:.0f} 分鐘<br>"
                    f"狀態:{'🔴 異常' if is_anomaly else '🟢 正常'}",
                    max_width=250
                ),
            ).add_to(m)

        legend_html = """
        <div style="position: fixed; bottom: 30px; left: 30px; z-index: 9999;
                    background: white; padding: 10px 14px; border: 2px solid #333;
                    border-radius: 6px; font-family: sans-serif; font-size: 13px;">
          <b>圖例</b><br>
          <span style="color:#d62728;">●</span> 異常配送(IQR判定)<br>
          <span style="color:#2ca02c;">●</span> 正常配送
        </div>
        """
        m.get_root().html.add_child(folium.Element(legend_html))

        st.caption(f"地圖上共標示 {len(df):,} 個配送點,其中 {int(df['異常旗標'].sum())} 個為異常(紅色)")
        st_folium(m, width=None, height=500)
