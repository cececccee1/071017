import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import os

def render_page():
    """
    渲染 Day 8 供應鏈串接頁面
    (讀檔方式對齊 Day 6：直接從 Datas 資料夾讀取，並以 try/except 處理找不到檔案的情況)
    """

    # ===== 1. 讀取與處理資料 =====
    @st.cache_data
    def load_data_d8():
        csv_p = os.path.join("Datas", "purchase.csv")
        csv_r = os.path.join("Datas", "receipt.csv")
        csv_s = os.path.join("Datas", "sales.csv")
        p = pd.read_csv(csv_p, encoding="utf-8-sig", parse_dates=["下單日", "預計到貨"])
        r = pd.read_csv(csv_r, encoding="utf-8-sig", parse_dates=["實際到貨"])
        s = pd.read_csv(csv_s, encoding="utf-8-sig", parse_dates=["出貨日"])
        return p, r, s

    try:
        p, r, s = load_data_d8()
    except FileNotFoundError:
        st.error(
            "❌ 找不到數據檔案！請確認您的檔案已放置於："
            "`Datas/purchase.csv`、`Datas/receipt.csv`、`Datas/sales.csv`"
        )
        return

    st.markdown("<h2 style='white-space: nowrap;'>🔗 Day 8 任務 08 · 供應鏈串接(完整版)</h2>",
                unsafe_allow_html=True)
    st.caption("採購 ↔ 進貨 ↔ 銷售 三表分析 · 自動診斷庫存積壓主因")

    # ---- Step 1 + Step 2 Merge (包進快取,只有 p/r/s 內容改變時才重算) ----
    @st.cache_data
    def build_views_d8(p, r, s):
        pr = p.merge(r, on=["採購單號", "SKU"], how="left")
        pr["實際LT"] = (pr["實際到貨"] - pr["下單日"]).dt.days
        pr["計畫LT"] = (pr["預計到貨"] - pr["下單日"]).dt.days
        pr["LT延遲日"] = pr["實際LT"] - pr["計畫LT"]

        s_cur = s[s["出貨日"].dt.month == 9].copy()
        s_prev = s[s["出貨日"].dt.month.isin([6, 7, 8])].copy()

        sku_sales = (s_cur.groupby("SKU", as_index=False)
                     .agg(九月銷量=("出貨量", "sum"), 銷售筆數=("銷售單號", "count")))
        prev_sales = (s_prev.groupby("SKU", as_index=False).agg(前三月銷量=("出貨量", "sum")))
        prev_sales["前三月平均月銷"] = (prev_sales["前三月銷量"] / 3).round(1)

        full = pr.merge(sku_sales, on="SKU", how="left")
        for col in ["九月銷量", "銷售筆數", "實際數量", "品質旗標"]:
            full[col] = full[col].fillna(0).astype(int)

        sku_view = (full.groupby(["SKU", "品類", "供應商"], as_index=False)
                    .agg(訂購量=("訂購量", "sum"), 實際進貨量=("實際數量", "sum"),
                         九月銷量=("九月銷量", "first"), 不良次數=("品質旗標", "sum")))
        sku_view = sku_view.merge(prev_sales[["SKU", "前三月平均月銷"]], on="SKU", how="left")
        sku_view["前三月平均月銷"] = sku_view["前三月平均月銷"].fillna(0)
        sku_view["庫存積壓量"] = sku_view["實際進貨量"] - sku_view["九月銷量"]
        sku_view["周轉率"] = (sku_view["九月銷量"] / sku_view["實際進貨量"].replace(0, np.nan)).round(2)
        sku_view["不良率"] = (sku_view["不良次數"] / sku_view["實際進貨量"].replace(0, np.nan)).fillna(0)

        已進 = full[full["實際到貨"].notna()].copy()
        supplier = (已進.groupby("供應商", as_index=False)
                    .agg(平均LT=("實際LT", "mean"),
                         LT變異=("實際LT", lambda x: x.std() / x.mean() if x.mean() > 0 else 0),
                         不良率=("品質旗標", "mean"), 平均單價=("單價", "mean"),
                         採購單數=("採購單號", "nunique"), 總進貨量=("實際數量", "sum")))
        supplier["D 達交分"] = pd.cut(supplier["LT變異"], bins=[-0.01, 0.10, 0.20, 0.30, 0.45, 99],
                                    labels=[5, 4, 3, 2, 1]).astype(int)
        supplier["Q 品質分"] = pd.cut(supplier["不良率"], bins=[-0.001, 0.005, 0.01, 0.02, 0.04, 1],
                                    labels=[5, 4, 3, 2, 1]).astype(int)
        supplier["C 成本分"] = pd.cut(supplier["平均單價"], bins=[0, 80, 95, 110, 130, 999],
                                    labels=[5, 4, 3, 2, 1]).astype(int)
        supplier["加權分(QDC)"] = (supplier["Q 品質分"]*0.40 + supplier["D 達交分"]*0.40
                                  + supplier["C 成本分"]*0.20).round(2)

        def 等級(score):
            if score >= 4.5: return "A 戰略夥伴"
            if score >= 3.5: return "B 一般合作"
            if score >= 2.5: return "C 觀察名單"
            return "D 淘汰候選"
        supplier["等級"] = supplier["加權分(QDC)"].apply(等級)

        return pr, s_cur, sku_view, supplier, 已進

    pr, s_cur, sku_view, supplier, 已進 = build_views_d8(p, r, s)


    # ---- 頁面內 Container 篩選面板 ----
    # 說明：
    # - "*_input" 是使用者正在調整、尚未套用的「暫存值」，綁在 widget 上
    # - "*_filter" 是真正拿去篩選/計算用的「已套用值」，只有按下「套用篩選」才會更新
    # 這樣拖動滑桿或切換下拉選單時，不會馬上觸發整頁重算，避免每次互動都要等待。
    DEFAULTS_D8 = {"cat_filter": "(全部)", "sup_filter": "(全部)", "topn_filter": 5, "thr_filter": 2.0}
    INPUT_KEYS_D8 = {"cat_filter": "cat_input", "sup_filter": "sup_input",
                     "topn_filter": "topn_input", "thr_filter": "thr_input"}

    for _k, _v in DEFAULTS_D8.items():
        if _k not in st.session_state:
            st.session_state[_k] = _v
        _input_k = INPUT_KEYS_D8[_k]
        if _input_k not in st.session_state:
            st.session_state[_input_k] = st.session_state[_k]

    def apply_filters_d8():
        # 把使用者暫存的輸入值,一次性複製到真正套用的篩選值
        for _fk, _ik in INPUT_KEYS_D8.items():
            st.session_state[_fk] = st.session_state[_ik]

    def reset_filters_d8():
        # 暫存值與已套用值一起重置回預設
        for k, v in DEFAULTS_D8.items():
            st.session_state[k] = v
            st.session_state[INPUT_KEYS_D8[k]] = v

    with st.container(border=True):
        st.markdown("### 🎯 供應鏈過濾器與範疇摘要")
        filter_col, stats_col = st.columns([2, 1])

        with filter_col:
            st.markdown("**控制項配置**(調整後請按「套用篩選」才會生效)")
            cat_options = ["(全部)"] + sorted(sku_view["品類"].unique().tolist())
            sup_options = ["(全部)"] + sorted(sku_view["供應商"].unique().tolist())

            c1, c2 = st.columns(2)
            with c1:
                st.selectbox("品類", cat_options, key="cat_input")
            with c2:
                st.selectbox("供應商", sup_options, key="sup_input")

            c3, c4 = st.columns(2)
            with c3:
                st.slider("Top N 積壓 SKU", 3, 20, key="topn_input")
            with c4:
                st.number_input("採購過量倍率閾值(進貨量 ÷ 前三月平均月銷)", 1.0, 8.0, step=0.5, key="thr_input")

            btn_apply, btn_reset = st.columns(2)
            with btn_apply:
                st.button("✅ 套用篩選", on_click=apply_filters_d8,
                          use_container_width=True, type="primary")
            with btn_reset:
                st.button("🔄 重置篩選", on_click=reset_filters_d8, use_container_width=True)

            # 提示使用者目前調整的條件跟已套用的條件是否不一致
            pending_changed = any(
                st.session_state[_ik] != st.session_state[_fk]
                for _fk, _ik in INPUT_KEYS_D8.items()
            )
            if pending_changed:
                st.caption("⚠️ 篩選條件已變更但尚未套用,請按「✅ 套用篩選」更新下方結果。")

        sel_cat = st.session_state["cat_filter"]
        sel_sup = st.session_state["sup_filter"]
        top_n = st.session_state["topn_filter"]
        backlog_threshold = st.session_state["thr_filter"]
        is_filtered = (sel_cat != "(全部)") or (sel_sup != "(全部)")

        view = sku_view.copy()
        if sel_cat != "(全部)":
            view = view[view["品類"] == sel_cat]
        if sel_sup != "(全部)":
            view = view[view["供應商"] == sel_sup]

        view_skus = set(view["SKU"].tolist())
        p_view = p[p["SKU"].isin(view_skus)] if is_filtered else p
        r_view = r[r["SKU"].isin(view_skus)] if is_filtered else r
        s_view = s_cur[s_cur["SKU"].isin(view_skus)] if is_filtered else s_cur
        已進_view = 已進[已進["SKU"].isin(view_skus)] if is_filtered else 已進

        with stats_col:
            st.markdown("**目前數據範疇**")
            filter_tag = "篩選後" if is_filtered else "全體"
            st.info(f"📌 **當前模式**: {filter_tag}")
            st.markdown(f"**符合條件的 SKU** : `{len(view)}` 支")
            st.markdown(f"**採購單號數** : `{p_view['採購單號'].nunique()}` 筆")
            st.markdown(f"**進貨記錄數** : `{len(r_view)}` 筆")
            st.markdown(f"**銷售(9 月)** : `{len(s_view):,}` 筆")

    # ---- KPI 4卡 ----
    if is_filtered:
        st.info(f"🎯 目前篩選範圍:**品類 = {sel_cat} · 供應商 = {sel_sup}**(共 {len(view)} 支 SKU)。")

    d1, d2, d3, d4 = st.columns(4)
    d1.metric(f"採購單數 ({filter_tag})", f"{p_view['採購單號'].nunique():,}")
    if len(已進_view) > 0:
        overall_lt = 已進_view["實際LT"].mean()
        plan_lt = 已進_view["計畫LT"].mean()
        d2.metric(f"平均 LT ({filter_tag})", f"{overall_lt:.1f} 天",
                  delta=f"{overall_lt-plan_lt:+.1f} 天 vs 計畫", delta_color="inverse")
    else:
        d2.metric(f"平均 LT ({filter_tag})", "—")
    if len(view) > 0:
        top1 = view.sort_values("庫存積壓量", ascending=False).iloc[0]
        d3.metric(f"Top1 積壓 · {top1['SKU']}", f"{int(top1['庫存積壓量']):,} 件",
                  delta=f"{top1['品類']} / {top1['供應商']}")
    else:
        d3.metric("Top1 積壓", "—", delta="無符合 SKU")
    total_in = view["實際進貨量"].sum() if len(view) else 0
    total_out = view["九月銷量"].sum() if len(view) else 0
    backlog_ratio = (total_in - total_out) / total_in if total_in else 0
    d4.metric(f"積壓率 ({filter_tag})", f"{backlog_ratio:.1%}" if total_in else "—",
              delta=f"進 {total_in:,} / 銷 {total_out:,}")

    st.divider()

    # ---- Tabs 內容區 ----
    d8sub1, d8sub2, d8sub3, d8sub4 = st.tabs([
        "🏭 供應商 QDCS", "📦 SKU 積壓主因", "📈 長鞭效應", "🎯 自動診斷 + 反直覺三問",
    ])

    with d8sub1:
        st.subheader("供應商績效矩陣 QDCS")
        if sel_sup != "(全部)":
            st.caption(f"💡 已選 **{sel_sup}** — 整列高亮顯示。")
        show_cols = ["供應商", "等級", "加權分(QDC)", "Q 品質分", "D 達交分", "C 成本分",
                     "平均LT", "LT變異", "不良率", "平均單價", "採購單數", "總進貨量"]

        def _highlight_row(row):
            if sel_sup != "(全部)" and row["供應商"] == sel_sup:
                return ["background-color: rgba(255, 215, 0, 0.35); font-weight: bold"] * len(row)
            return [""] * len(row)

        styled_supplier = (supplier[show_cols].sort_values("加權分(QDC)", ascending=False)
                            .style.apply(_highlight_row, axis=1)
                            .format({"平均LT": "{:.1f}", "LT變異": "{:.2f}",
                                    "不良率": "{:.2%}", "平均單價": "{:.1f}"})
                            .background_gradient(subset=["加權分(QDC)"], cmap="RdYlGn"))
        st.dataframe(styled_supplier, use_container_width=True)

        col_a, col_b = st.columns(2)
        with col_a:
            st.markdown("##### 各供應商 LT 變異(σ/μ)")
            sup_sorted = supplier.sort_values("LT變異").copy()
            sup_sorted["highlight"] = sup_sorted["供應商"].apply(lambda x: "選中" if x == sel_sup else "其他")
            if sel_sup != "(全部)":
                figA = px.bar(sup_sorted, x="供應商", y="LT變異", color="highlight",
                              color_discrete_map={"選中": "#FFD700", "其他": "#888888"},
                              text=sup_sorted["LT變異"].round(2))
            else:
                figA = px.bar(sup_sorted, x="供應商", y="LT變異", color="LT變異",
                              color_continuous_scale="Reds", text=sup_sorted["LT變異"].round(2))
            figA.add_hline(y=0.30, line_dash="dash", line_color="red", annotation_text="0.30 警戒")
            figA.update_traces(textposition="outside")
            figA.update_layout(height=400, margin=dict(t=20, b=10), showlegend=(sel_sup != "(全部)"))
            st.plotly_chart(figA, use_container_width=True)
        with col_b:
            st.markdown("##### 不良率 vs 平均單價(反直覺第二點)")
            figB = px.scatter(supplier, x="平均單價", y="不良率", size="總進貨量", text="供應商",
                              color="LT變異", color_continuous_scale="Reds", size_max=50)
            if sel_sup != "(全部)" and sel_sup in supplier["供應商"].values:
                row_sel = supplier[supplier["供應商"] == sel_sup].iloc[0]
                figB.add_trace(go.Scatter(
                    x=[row_sel["平均單價"]], y=[row_sel["不良率"]], mode="markers",
                    marker=dict(size=row_sel["總進貨量"]/supplier["總進貨量"].max()*50+15,
                               color="rgba(0,0,0,0)", line=dict(color="gold", width=4)),
                    showlegend=False, hoverinfo="skip"))
            figB.update_traces(textposition="top center", selector=dict(mode="markers+text"))
            figB.update_layout(height=400, margin=dict(t=20, b=10), yaxis_tickformat=".1%")
            st.plotly_chart(figB, use_container_width=True)

        st.markdown("##### ⚠️ 「便宜換來的」反直覺警示")
        median_price = supplier["平均單價"].median()
        便宜不穩 = supplier[(supplier["平均單價"] < median_price) & (supplier["LT變異"] > 0.30)]
        if len(便宜不穩) > 0:
            names = "、".join(便宜不穩["供應商"].tolist())
            st.error(f"⚠ **{names}** 屬於『單價低於中位數但LT變異>0.30』— 真實TCO可能比報價貴5-15%。")
            st.dataframe(便宜不穩[["供應商", "平均單價", "LT變異", "不良率", "等級"]]
                         .style.format({"平均單價": "{:.1f}", "LT變異": "{:.2f}", "不良率": "{:.2%}"}),
                         use_container_width=True)
        else:
            st.success("✅ 目前沒有『便宜但LT不穩』的供應商。")

    with d8sub2:
        st.subheader(f"Top {top_n} 庫存積壓 SKU + 主因標籤")
        sup_lt_var = supplier.set_index("供應商")["LT變異"].to_dict()
        view2 = view.copy()
        view2["供應商LT變異"] = view2["供應商"].map(sup_lt_var)

        def 主因標籤(row):
            causes = []
            if row["實際進貨量"] > row["前三月平均月銷"] * backlog_threshold and row["庫存積壓量"] > 100:
                causes.append("採購過量")
            if pd.notna(row["供應商LT變異"]) and row["供應商LT變異"] > 0.30:
                causes.append("LT過長")
            if pd.notna(row["周轉率"]) and row["周轉率"] < 0.20:
                causes.append("銷售下滑")
            if row["不良次數"] >= 1 and row["不良率"] >= 0.05:
                causes.append("品質瑕疵")
            return " / ".join(causes) if causes else "一般庫存"

        view2["主因"] = view2.apply(主因標籤, axis=1) if len(view2) else pd.Series([], dtype=object)
        top = view2.sort_values("庫存積壓量", ascending=False).head(top_n)

        if len(top) == 0:
            st.warning("⚠ 目前篩選條件下沒有任何 SKU。請放寬篩選或按重置。")
        else:
            st.dataframe(
                top[["SKU", "品類", "供應商", "訂購量", "實際進貨量", "九月銷量",
                    "前三月平均月銷", "庫存積壓量", "周轉率", "供應商LT變異", "不良率", "主因"]]
                    .style.format({"前三月平均月銷": "{:.1f}", "周轉率": "{:.2f}",
                                   "供應商LT變異": "{:.2f}", "不良率": "{:.2%}"})
                    .background_gradient(subset=["庫存積壓量"], cmap="Reds"),
                use_container_width=True)

            主因s = top["主因"].dropna().astype(str)
            if len(主因s) == 0:
                cause_count = pd.DataFrame(columns=["主因", "次數"])
            else:
                cause_count = 主因s.str.split(" / ").explode().value_counts().reset_index()
                cause_count.columns = ["主因", "次數"]
            if len(cause_count):
                col_a, col_b = st.columns([1, 1])
                with col_a:
                    fig3 = px.pie(cause_count, names="主因", values="次數", hole=0.5,
                                 title=f"Top {top_n} 主因占比 ({filter_tag})")
                    fig3.update_layout(height=350, margin=dict(t=40, b=10))
                    st.plotly_chart(fig3, use_container_width=True)
                with col_b:
                    st.markdown("##### 行動建議")
                    for _, r2 in cause_count.iterrows():
                        action = {
                            "採購過量": "🛑 暫停採購、檢討業務forecast、清庫存promo",
                            "LT過長": "🔄 啟動雙源備援 / 重議LT罰則",
                            "銷售下滑": "📉 業務追蹤客流 / 促銷或下架",
                            "品質瑕疵": "🔧 退換貨 / 啟動品質升級SQA監控",
                            "一般庫存": "—",
                        }.get(r2["主因"], "—")
                        st.markdown(f"- **{r2['主因']}**({r2['次數']} 例):{action}")

    with d8sub3:
        st.subheader(f"長鞭效應自檢 · {filter_tag}")
        st.caption("反直覺第一點:從消費端往上游,變異會逐級放大。")
        if is_filtered:
            st.info(f"📌 目前看的是 **{sel_cat} / {sel_sup}** 子集(共 {len(view)} 支 SKU)。")

        if len(p_view) == 0 or len(r_view) == 0 or len(s_view) == 0:
            st.warning("⚠ 目前篩選範圍下,三表至少有一表為空,無法畫長鞭效應。")
        else:
            daily = pd.DataFrame({
                "採購下單量": p_view.groupby("下單日")["訂購量"].sum(),
                "進貨量": r_view.groupby("實際到貨")["實際數量"].sum(),
                "銷售出貨量": s_view.groupby("出貨日")["出貨量"].sum(),
            }).fillna(0).sort_index()
            daily.index.name = "日期"
            daily = daily.reset_index()

            fig4 = go.Figure()
            fig4.add_trace(go.Scatter(x=daily["日期"], y=daily["銷售出貨量"], name="銷售出貨量(下游)",
                                      mode="lines+markers", line=dict(color="#27ae60")))
            fig4.add_trace(go.Scatter(x=daily["日期"], y=daily["進貨量"], name="進貨量(中段)",
                                      mode="lines+markers", line=dict(color="#f39c12")))
            fig4.add_trace(go.Scatter(x=daily["日期"], y=daily["採購下單量"], name="採購下單量(上游)",
                                      mode="lines+markers", line=dict(color="#c0392b")))
            fig4.update_layout(title=f"三層每日量級對照 ({filter_tag})", height=430,
                               margin=dict(t=50, b=20), legend=dict(orientation="h", y=-0.15),
                               hovermode="x unified")
            st.plotly_chart(fig4, use_container_width=True)

            cv_table = pd.DataFrame({
                "層級": ["銷售出貨量(下游)", "進貨量(中段)", "採購下單量(上游)"],
                "平均": [daily["銷售出貨量"].mean(), daily["進貨量"].mean(), daily["採購下單量"].mean()],
                "標準差": [daily["銷售出貨量"].std(), daily["進貨量"].std(), daily["採購下單量"].std()],
            })
            cv_table["變異(CV)"] = (cv_table["標準差"] / cv_table["平均"].replace(0, np.nan)).round(2).fillna(0)
            st.dataframe(cv_table.style.format({"平均": "{:.1f}", "標準差": "{:.1f}"}),
                        use_container_width=True)

            cv_sales = cv_table.iloc[0]["變異(CV)"]
            cv_orders = cv_table.iloc[2]["變異(CV)"]
            if cv_sales > 0 and cv_orders > cv_sales * 1.5:
                st.error(f"⚠ **長鞭效應確認** · 上游變異{cv_orders:.2f} > 下游{cv_sales:.2f}×1.5")
            else:
                st.success("✅ 此範圍下長鞭效應尚未明顯放大。")

    with d8sub4:
        st.subheader(f"🤖 自動診斷:這份庫存的問題是什麼?({filter_tag})")

        def auto_diagnose(sku_view_in, supplier_all):
            notes = []
            sup_lt_var_ = supplier_all.set_index("供應商")["LT變異"].to_dict()
            v2 = sku_view_in.copy()
            if len(v2) == 0:
                return ["⚠ 篩選範圍下沒有 SKU,無法診斷。"], None
            v2["供應商LT變異"] = v2["供應商"].map(sup_lt_var_)

            over_purchase = v2[(v2["實際進貨量"] > v2["前三月平均月銷"] * backlog_threshold) & (v2["庫存積壓量"] > 100)]
            lt_long = v2[v2["供應商LT變異"] > 0.30]
            sales_down = v2[(v2["周轉率"] < 0.20) & (v2["庫存積壓量"] > 100)]
            quality_bad = v2[(v2["不良次數"] >= 1) & (v2["不良率"] >= 0.05)]

            notes.append(f"📊 採購過量 SKU 共 {len(over_purchase)} 支,合計積壓 {over_purchase['庫存積壓量'].sum():,.0f} 件")
            notes.append(f"⏱️ LT過長 SKU 共 {len(lt_long)} 支,合計積壓 {lt_long['庫存積壓量'].sum():,.0f} 件")
            notes.append(f"📉 銷售下滑 SKU 共 {len(sales_down)} 支,合計積壓 {sales_down['庫存積壓量'].sum():,.0f} 件")
            notes.append(f"🔧 品質瑕疵 SKU 共 {len(quality_bad)} 支")

            impacts = {"採購過量": over_purchase["庫存積壓量"].sum(), "LT過長": lt_long["庫存積壓量"].sum(),
                      "銷售下滑": sales_down["庫存積壓量"].sum(), "品質瑕疵": quality_bad["庫存積壓量"].sum()}
            if sum(impacts.values()) == 0:
                return notes, "✅ 此範圍下沒有顯著主因 — 庫存大致平衡。"

            main_cause = max(impacts, key=impacts.get)
            supplier_action = supplier_all[supplier_all["加權分(QDC)"] < 3.0]["供應商"].tolist()
            diag = (f"**主因 = `{main_cause}`**(影響積壓量 {impacts[main_cause]:,.0f} 件 / "
                   f"占範圍內 {impacts[main_cause]/sum(impacts.values()):.0%})\n\n"
                   f"**建議行動**:\n- 對應主因SKU下個月暫停或減半採購\n"
                   f"- 弱供應商 {supplier_action if supplier_action else '無'} 啟動雙源備援\n"
                   f"- 業務端做SKU級需求review")
            return notes, diag

        notes, diag = auto_diagnose(view, supplier)
        for n in notes:
            st.markdown(n)
        if diag:
            st.divider()
            st.success(diag)

        st.divider()
        st.subheader("🤔 反直覺三問")
        base_for_q1 = view if len(view) else sku_view
        q1_top1 = base_for_q1.sort_values("庫存積壓量", ascending=False).iloc[0]
        with st.expander("❓ Q1 · 庫存積壓最大的SKU,真的是『賣不好』嗎?"):
            st.markdown(f"Top1 `{q1_top1['SKU']}`:進貨 {int(q1_top1['實際進貨量']):,}件,"
                       f"前三月均銷{q1_top1['前三月平均月銷']:.1f}件,是**"
                       f"{q1_top1['實際進貨量']/max(q1_top1['前三月平均月銷'],1):.1f}倍**。"
                       f">2倍代表採購過量,不是業務問題。")
        with st.expander("❓ Q2 · 單價最便宜的供應商,真的最划算嗎?"):
            cheap = supplier.sort_values("平均單價").iloc[0]
            st.markdown(f"`{cheap['供應商']}` 最便宜(單價{cheap['平均單價']:.1f}元)但LT變異"
                       f"**{cheap['LT變異']:.2f}**,真實TCO可能比同業貴5-15%。")
        with st.expander("❓ Q3 · 你選how='left'還是'inner',反映什麼?"):
            not_received = pr[pr["實際到貨"].isna()]
            st.markdown(f"用left才看得到「訂了但還沒到」的採購單共**{len(not_received)}**筆,"
                       f"這是最早期的斷貨警訊。**Merge不是技術題,是商業假設題。**")