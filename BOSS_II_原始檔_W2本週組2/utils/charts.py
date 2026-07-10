"""
utils/charts.py
================
集中管理各頁面共用的「圖表建立」邏輯。

規則：這支檔案裡的函式只負責用 Plotly 建立圖表物件（回傳 fig），
不呼叫 st.plotly_chart()，顯示動作留在頁面檔案處理。

檔案結構（依頁面分區）：
    1. Day 8 · 採購供應鏈
    2. Day 7 · 運輸異常
    3. D6   · 儲位重排
"""

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots


# ============================================================
# 1. Day 8 · 採購供應鏈
# ============================================================

def style_supplier_table(supplier, show_cols, sel_sup):
    """供應商 QDCS 評分表：選中的供應商整列高亮 + 加權分色階"""
    def _highlight_row(row):
        if sel_sup != "(全部)" and row["供應商"] == sel_sup:
            return ["background-color: rgba(255, 215, 0, 0.35); font-weight: bold"] * len(row)
        return [""] * len(row)

    return (supplier[show_cols].sort_values("加權分(QDC)", ascending=False)
            .style.apply(_highlight_row, axis=1)
            .format({"平均LT": "{:.1f}", "LT變異": "{:.2f}",
                    "不良率": "{:.2%}", "平均單價": "{:.1f}"})
            .background_gradient(subset=["加權分(QDC)"], cmap="RdYlGn"))


def chart_lt_variance_bar(supplier, sel_sup):
    """各供應商 LT 變異(σ/μ)長條圖，選中的供應商用金色標出"""
    sup_sorted = supplier.sort_values("LT變異").copy()
    sup_sorted["highlight"] = sup_sorted["供應商"].apply(lambda x: "選中" if x == sel_sup else "其他")

    if sel_sup != "(全部)":
        fig = px.bar(sup_sorted, x="供應商", y="LT變異", color="highlight",
                     color_discrete_map={"選中": "#FFD700", "其他": "#888888"},
                     text=sup_sorted["LT變異"].round(2))
    else:
        fig = px.bar(sup_sorted, x="供應商", y="LT變異", color="LT變異",
                     color_continuous_scale="Reds", text=sup_sorted["LT變異"].round(2))

    fig.add_hline(y=0.30, line_dash="dash", line_color="red", annotation_text="0.30 警戒")
    fig.update_traces(textposition="outside")
    fig.update_layout(height=400, margin=dict(t=20, b=10), showlegend=(sel_sup != "(全部)"))
    return fig


def chart_defect_vs_price_scatter(supplier, sel_sup):
    """不良率 vs 平均單價散佈圖，選中的供應商加金色外框標記"""
    fig = px.scatter(supplier, x="平均單價", y="不良率", size="總進貨量", text="供應商",
                      color="LT變異", color_continuous_scale="Reds", size_max=50)

    if sel_sup != "(全部)" and sel_sup in supplier["供應商"].values:
        row_sel = supplier[supplier["供應商"] == sel_sup].iloc[0]
        fig.add_trace(go.Scatter(
            x=[row_sel["平均單價"]], y=[row_sel["不良率"]], mode="markers",
            marker=dict(size=row_sel["總進貨量"]/supplier["總進貨量"].max()*50+15,
                       color="rgba(0,0,0,0)", line=dict(color="gold", width=4)),
            showlegend=False, hoverinfo="skip"))

    fig.update_traces(textposition="top center", selector=dict(mode="markers+text"))
    fig.update_layout(height=400, margin=dict(t=20, b=10), yaxis_tickformat=".1%")
    return fig


def chart_cause_pie(cause_count, top_n, filter_tag):
    """Top N 積壓主因占比圓餅圖"""
    fig = px.pie(cause_count, names="主因", values="次數", hole=0.5,
                 title=f"Top {top_n} 主因占比 ({filter_tag})")
    fig.update_layout(height=350, margin=dict(t=40, b=10))
    return fig


def chart_whip_effect_lines(daily, filter_tag):
    """長鞭效應：採購/進貨/銷售 三層每日量級對照折線圖"""
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=daily["日期"], y=daily["銷售出貨量"], name="銷售出貨量(下游)",
                              mode="lines+markers", line=dict(color="#27ae60")))
    fig.add_trace(go.Scatter(x=daily["日期"], y=daily["進貨量"], name="進貨量(中段)",
                              mode="lines+markers", line=dict(color="#f39c12")))
    fig.add_trace(go.Scatter(x=daily["日期"], y=daily["採購下單量"], name="採購下單量(上游)",
                              mode="lines+markers", line=dict(color="#c0392b")))
    fig.update_layout(title=f"三層每日量級對照 ({filter_tag})", height=430,
                       margin=dict(t=50, b=20), legend=dict(orientation="h", y=-0.15),
                       hovermode="x unified")
    return fig


# ============================================================
# 2. Day 7 · 運輸異常
# ============================================================

def chart_offset_distribution(df):
    """配送時間偏移分布：直方圖 + 箱型圖並排（修正 bin 寬度與白邊）
    回傳：(fig, skew)"""
    skew = df["偏移分鐘"].skew()
    data_min = df["偏移分鐘"].min()
    data_max = df["偏移分鐘"].max()
    bin_size = (data_max - data_min) / 50

    fig = make_subplots(rows=1, cols=2, column_widths=[0.6, 0.4],
                         subplot_titles=("配送時間偏移分布", "箱型圖 · 看 IQR + outliers"))

    fig.add_trace(
        go.Histogram(
            x=df["偏移分鐘"],
            xbins=dict(start=data_min, end=data_max, size=bin_size),
            marker=dict(color="#1f3a5f", line=dict(color="white", width=1)),
            name="偏移分鐘", showlegend=False
        ),
        row=1, col=1
    )

    y_max_count = pd.cut(df["偏移分鐘"], bins=50).value_counts().max()
    fig.add_trace(
        go.Scatter(x=[0, 0], y=[0, y_max_count * 1.05], mode="lines",
                    line=dict(color="gray", dash="dash"), name="準時 (0 min)"),
        row=1, col=1
    )

    fig.add_trace(
        go.Box(x=df["偏移分鐘"], name="偏移分鐘", marker_color="#1f3a5f",
                fillcolor="rgba(31,58,95,0.4)", line_color="#1f3a5f", showlegend=False),
        row=1, col=2
    )

    fig.update_xaxes(title_text="實際 - 預計(分鐘)", row=1, col=1)
    fig.update_yaxes(title_text="筆數", row=1, col=1)
    fig.update_xaxes(title_text="實際 - 預計(分鐘)", row=1, col=2)

    fig.update_layout(
        template="plotly_white", height=420,
        margin=dict(t=70, b=40, l=40, r=20),
        legend=dict(bordercolor="black", borderwidth=1,
                    x=0.98, y=0.98, xanchor="right", yanchor="top"),
        font=dict(color="black"),
    )
    return fig, skew


def chart_zscore_histogram(df):
    """Z-score 異常偵測直方圖，標出 μ 與 ±2σ"""
    mu = df["偏移分鐘"].mean()
    sigma = df["偏移分鐘"].std()
    data_min = df["偏移分鐘"].min()
    data_max = df["偏移分鐘"].max()
    bin_size = (data_max - data_min) / 50

    fig = go.Figure()
    fig.add_trace(go.Histogram(
        x=df["偏移分鐘"],
        xbins=dict(start=data_min, end=data_max, size=bin_size),
        marker=dict(color="#4c72b0", line=dict(color="white", width=1)),
        name="偏移分鐘"
    ))
    fig.add_vline(x=mu, line_dash="dot", line_color="gray",
                  annotation_text=f"平均 μ = {mu:.1f} min", annotation_position="top")
    fig.add_vline(x=mu - 2 * sigma, line_dash="dash", line_color="red",
                  annotation_text=f"-2σ = {mu - 2 * sigma:.0f} min", annotation_position="top")
    fig.add_vline(x=mu + 2 * sigma, line_dash="dash", line_color="red",
                  annotation_text=f"+2σ = {mu + 2 * sigma:.0f} min", annotation_position="top")
    fig.update_layout(
        template="plotly_white",
        title="Z-score 異常偵測(|z| > 2 標紅線)",
        xaxis_title="實際 - 預計(分鐘)", yaxis_title="筆數",
        height=650, margin=dict(t=80, b=50), showlegend=False,
    )
    return fig


def chart_rolling_anomaly(每日):
    """Rolling 異常偵測：N 日滾動平均 ±2σ 區間圖"""
    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=每日.index, y=每日["下界"], mode="lines",
        line=dict(width=0), showlegend=False, hoverinfo="skip"
    ))
    fig.add_trace(go.Scatter(
        x=每日.index, y=每日["上界"], mode="lines",
        line=dict(width=0), fill="tonexty", fillcolor="rgba(255,165,0,0.15)",
        name="滾動 ±2σ 區間", hoverinfo="skip"
    ))
    fig.add_trace(go.Scatter(
        x=每日.index, y=每日["日平均偏移分鐘"], mode="lines+markers",
        line=dict(color="#1f3a5f"), marker=dict(size=4), name="日平均偏移分鐘"
    ))
    fig.add_trace(go.Scatter(
        x=每日.index, y=每日["滾動平均"], mode="lines",
        line=dict(color="orange"), name="7 日滾動平均"
    ))

    異常日 = 每日[每日["異常日"]]
    fig.add_trace(go.Scatter(
        x=異常日.index, y=異常日["日平均偏移分鐘"], mode="markers",
        marker=dict(color="red", size=9), name="異常日"
    ))

    fig.update_layout(
        title="Rolling 異常偵測(7 日滾動 ±2σ)",
        xaxis_title="日期", yaxis_title="日平均偏移分鐘", height=420,
    )
    return fig


# ============================================================
# 3. D6 · 儲位重排
# ============================================================

def chart_eiq_scatter(sku):
    """EIQ 分析散佈圖：IK(出貨筆數) × IQ(總出貨量)，依 ABC 類別上色"""
    ABC_COLORS = {"A": "#d62728", "B": "#2ca02c", "C": "#bdbdbd"}
    fig = px.scatter(sku, x="出貨筆數", y="總出貨量", color="類別",
                     color_discrete_map=ABC_COLORS,
                     category_orders={"類別": ["A", "B", "C"]},
                     hover_data=["SKU", "品名"])
    fig.update_layout(
        title=dict(text="EIQ 分析: IK(出貨筆數) × IQ(總出貨量)", y=0.95, x=0.02),
        margin=dict(l=15, r=15, t=50, b=15), height=320,
        legend=dict(orientation="h", yanchor="bottom", y=1.02,
                    xanchor="right", x=1, title=dict(text="商品類別:"))
    )
    return fig


def style_storage_grid(grid_df, sku_to_cat):
    """儲位格子依 SKU 對應的 ABC 類別上色"""
    def _color_by_category(val):
        cat = sku_to_cat.get(val, "")
        color_map = {
            "A": "background-color: #d62728; color: white;",
            "B": "background-color: #2ca02c; color: white;",
            "C": "background-color: #bdbdbd; color: black;"
        }
        return color_map.get(cat, "")
    return grid_df.style.map(_color_by_category)
