import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import folium
from streamlit_folium import st_folium
from pathlib import Path
import os

def render_page():

    @st.cache_data
    def load_and_process_data():
        """只做資料讀取 + 運算,不含任何 st.xxx() 呼叫"""
        file_path = os.path.join("Datas", "配送紀錄_202509.csv")
        df = pd.read_csv(file_path, encoding="utf-8-sig",
                          parse_dates=["預計到達", "實際到達", "客戶時窗起", "客戶時窗迄"])

        # §A 嚴格 OTD(整體)
        df["在窗內"] = (df["實際到達"] >= df["客戶時窗起"]) & (df["實際到達"] <= df["客戶時窗迄"])
        df["完整"] = df["貨損旗標"] == 0
        df["OTD_嚴格"] = df["在窗內"] & df["完整"]

        # §C IQR 抓配送時間異常
        df["偏移分鐘"] = (df["實際到達"] - df["預計到達"]).dt.total_seconds() / 60

        Q1 = df["偏移分鐘"].quantile(0.25)
        Q3 = df["偏移分鐘"].quantile(0.75)
        IQR = Q3 - Q1
        下界 = Q1 - 1.5 * IQR
        上界 = Q3 + 1.5 * IQR
        df["異常旗標"] = (df["偏移分鐘"] < 下界) | (df["偏移分鐘"] > 上界)

        # §C2 Z-score
        mu = df["偏移分鐘"].mean()
        sigma = df["偏移分鐘"].std()
        df["z分數"] = (df["偏移分鐘"] - mu) / sigma
        df["異常旗標_Z"] = df["z分數"].abs() > 2

        # §E 早到/遲到
        df["早到"] = df["實際到達"] < df["客戶時窗起"]
        df["遲到"] = df["實際到達"] > df["客戶時窗迄"]

        return df

    try:
        df = load_and_process_data()
    except FileNotFoundError:
        st.error("❌ 找不到數據檔案!請確認您的檔案已放置於:`Datas/配送紀錄_202509.csv`")
        return

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
    路線_OTD = (df.groupby("路線代碼")
                  .agg(訂單數=("OTD_嚴格", "count"), OTD=("OTD_嚴格", "mean"))
                  .sort_values("OTD"))
    路線_OTD["OTD%"] = (路線_OTD["OTD"] * 100).round(1)

    司機_OTD = (df.groupby("司機代碼")
                  .agg(訂單數=("OTD_嚴格", "count"), OTD=("OTD_嚴格", "mean"))
                  .sort_values("OTD"))
    司機_OTD["OTD%"] = (司機_OTD["OTD"] * 100).round(1)

    c1, c2 = st.columns(2)
    c1.write("**🛣️ 路線 OTD(遞增 · 最差路線在最上面)**")
    c1.dataframe(路線_OTD[["訂單數", "OTD%"]], width="stretch")
    c2.write("**🚚 司機 OTD(遞增 · 最差司機在最上面)**")
    c2.dataframe(司機_OTD[["訂單數", "OTD%"]], width="stretch")

    worst_driver = 司機_OTD.index[0]
    ctrl = (df[df["司機代碼"] == worst_driver]
            .groupby("路線代碼")
            .agg(訂單數=("OTD_嚴格", "count"), OTD=("OTD_嚴格", "mean"))
            .sort_values("OTD"))
    ctrl["OTD%"] = (ctrl["OTD"] * 100).round(1)

    if ctrl["OTD"].std() < 0.10:
        diag_main = "司機"
    else:
        diag_main = "路線"

    st.write(f"最差司機:**{worst_driver}**(整體 OTD {司機_OTD.loc[worst_driver, 'OTD%']}%)"
             f" · 在不同路線 OTD 落差 std = {ctrl['OTD'].std():.2f} → 診斷主因 = **{diag_main}**")
    st.dataframe(ctrl[["訂單數", "OTD%"]], width="stretch")

# ===== §C 配送時間偏移分布(IQR)— Plotly 版(修正 bin 寬度與白邊)=====
    skew = df["偏移分鐘"].skew()

    st.subheader("📊 配送時間偏移分布(IQR)")
    st.caption(f"偏態 skew = {skew:+.2f}({'右偏' if skew > 0 else '左偏' if skew < 0 else '對稱'})")

    # 用資料實際範圍去算出「切50等份」對應的精確 bin 寬度
    data_min = df["偏移分鐘"].min()
    data_max = df["偏移分鐘"].max()
    bin_size = (data_max - data_min) / 50

    fig_c = make_subplots(rows=1, cols=2, column_widths=[0.6, 0.4],
                           subplot_titles=("配送時間偏移分布", "箱型圖 · 看 IQR + outliers"))

    fig_c.add_trace(
        go.Histogram(
            x=df["偏移分鐘"],
            xbins=dict(start=data_min, end=data_max, size=bin_size),  # 明確指定區間,不再讓 Plotly 自己決定
            marker=dict(
                color="#1f3a5f",
                line=dict(color="white", width=1)  # 每根直條之間的白色間隔
            ),
            name="偏移分鐘",
            showlegend=False
        ),
        row=1, col=1
    )

    y_max_count = pd.cut(df["偏移分鐘"], bins=50).value_counts().max()
    fig_c.add_trace(
        go.Scatter(x=[0, 0], y=[0, y_max_count * 1.05], mode="lines",
                    line=dict(color="gray", dash="dash"),
                    name="準時 (0 min)"),
        row=1, col=1
    )

    fig_c.add_trace(
        go.Box(x=df["偏移分鐘"], name="偏移分鐘", marker_color="#1f3a5f",
                fillcolor="rgba(31,58,95,0.4)", line_color="#1f3a5f",
                showlegend=False),
        row=1, col=2
    )

    fig_c.update_xaxes(title_text="實際 - 預計(分鐘)", row=1, col=1)
    fig_c.update_yaxes(title_text="筆數", row=1, col=1)
    fig_c.update_xaxes(title_text="實際 - 預計(分鐘)", row=1, col=2)

    fig_c.update_layout(
        template="plotly_white",
        height=420,
        margin=dict(t=70, b=40, l=40, r=20),
        legend=dict(
            bordercolor="black", borderwidth=1,
            x=0.98, y=0.98, xanchor="right", yanchor="top"
        ),
        font=dict(color="black"),
    )

    st.plotly_chart(fig_c, use_container_width=True)
# ===== §C2 Z-score 異常偵測 — Plotly 版(拉高圖表)=====
    mu = df["偏移分鐘"].mean()
    sigma = df["偏移分鐘"].std()

    st.subheader("📊 Z-score 異常偵測(適合對稱分布)")

    bin_size_z = (data_max - data_min) / 50

    fig_z = go.Figure()
    fig_z.add_trace(go.Histogram(
        x=df["偏移分鐘"],
        xbins=dict(start=data_min, end=data_max, size=bin_size_z),
        marker=dict(
            color="#4c72b0",
            line=dict(color="white", width=1)
        ),
        name="偏移分鐘"
    ))
    fig_z.add_vline(x=mu, line_dash="dot", line_color="gray",
                     annotation_text=f"平均 μ = {mu:.1f} min", annotation_position="top")
    fig_z.add_vline(x=mu - 2 * sigma, line_dash="dash", line_color="red",
                     annotation_text=f"-2σ = {mu - 2 * sigma:.0f} min", annotation_position="top")
    fig_z.add_vline(x=mu + 2 * sigma, line_dash="dash", line_color="red",
                     annotation_text=f"+2σ = {mu + 2 * sigma:.0f} min", annotation_position="top")
    fig_z.update_layout(
        template="plotly_white",
        title="Z-score 異常偵測(|z| > 2 標紅線)",
        xaxis_title="實際 - 預計(分鐘)",
        yaxis_title="筆數",
        height=650,   # 從 400 拉高到 650,讓整張圖上下更寬敞
        margin=dict(t=80, b=50),
        showlegend=False,
    )
    st.plotly_chart(fig_z, use_container_width=True)
    # ===== §C3 Rolling 異常偵測 — Plotly 版 =====
    每日 = (df.groupby(df["預計到達"].dt.date)["偏移分鐘"]
              .mean().rename("日平均偏移分鐘").to_frame())
    每日.index = pd.to_datetime(每日.index)
    每日["滾動平均"] = 每日["日平均偏移分鐘"].rolling(7, min_periods=3).mean()
    每日["滾動標準差"] = 每日["日平均偏移分鐘"].rolling(7, min_periods=3).std()
    每日["上界"] = 每日["滾動平均"] + 2 * 每日["滾動標準差"]
    每日["下界"] = 每日["滾動平均"] - 2 * 每日["滾動標準差"]
    每日["異常日"] = (每日["日平均偏移分鐘"] > 每日["上界"]) | (每日["日平均偏移分鐘"] < 每日["下界"])

    st.subheader("📊 Rolling 異常偵測(適合有季節性的時序)")

    fig_r = go.Figure()

    # 滾動 ±2σ 區間(先畫下界,再畫上界並 fill)
    fig_r.add_trace(go.Scatter(
        x=每日.index, y=每日["下界"], mode="lines",
        line=dict(width=0), showlegend=False, hoverinfo="skip"
    ))
    fig_r.add_trace(go.Scatter(
        x=每日.index, y=每日["上界"], mode="lines",
        line=dict(width=0), fill="tonexty", fillcolor="rgba(255,165,0,0.15)",
        name="滾動 ±2σ 區間", hoverinfo="skip"
    ))

    # 日平均偏移分鐘
    fig_r.add_trace(go.Scatter(
        x=每日.index, y=每日["日平均偏移分鐘"], mode="lines+markers",
        line=dict(color="#1f3a5f"), marker=dict(size=4),
        name="日平均偏移分鐘"
    ))

    # 7 日滾動平均
    fig_r.add_trace(go.Scatter(
        x=每日.index, y=每日["滾動平均"], mode="lines",
        line=dict(color="orange"), name="7 日滾動平均"
    ))

    # 異常日標記
    異常日 = 每日[每日["異常日"]]
    fig_r.add_trace(go.Scatter(
        x=異常日.index, y=異常日["日平均偏移分鐘"], mode="markers",
        marker=dict(color="red", size=9), name="異常日"
    ))

    fig_r.update_layout(
        title="Rolling 異常偵測(7 日滾動 ±2σ)",
        xaxis_title="日期",
        yaxis_title="日平均偏移分鐘",
        height=420,
    )
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
    top_route = anomalies["路線代碼"].value_counts().index[0]
    top_drv = anomalies["司機代碼"].value_counts().index[0]
    top_hour = int(anomalies["預計到達"].dt.hour.value_counts().index[0])

    diag = (
        f"整體嚴格 OTD = {整體_OTD:.1%},屬於"
        f"{'警戒' if 整體_OTD < 0.90 else '偏低' if 整體_OTD < 0.95 else '健康'}區間。"
        f"異常筆數 {df['異常旗標'].sum():,} 筆({df['異常旗標'].mean():.1%}),"
        f"集中在路線 {top_route}({anomalies['路線代碼'].value_counts().iloc[0]} 筆)"
        f"與司機 {top_drv}({anomalies['司機代碼'].value_counts().iloc[0]} 筆),"
        f"時段以 {top_hour:02d}:00 為高峰。"
        f"控制變量分析顯示最差司機 {worst_driver} 在不同路線落差 std = {ctrl['OTD'].std():.2f},"
        f"診斷主因為【{diag_main}】。"
        f"一週內可動行動:把 {worst_driver} 暫時移出 {top_route} 路線,"
        f"觀察 7 天 OTD 是否回升。"
    )
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