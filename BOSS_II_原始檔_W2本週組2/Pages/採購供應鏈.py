import streamlit as st
import pandas as pd

from utils.kpi import (
    load_supply_chain_data,
    build_supply_chain_views,
    label_backlog_cause,
    diagnose_backlog,
)
from utils.charts import (
    style_supplier_table,
    chart_lt_variance_bar,
    chart_defect_vs_price_scatter,
    chart_cause_pie,
    chart_whip_effect_lines,
)


def render_page():
    """
    渲染 Day 8 供應鏈串接頁面。
    運算邏輯統一放在 utils/kpi.py，圖表建立統一放在 utils/charts.py，
    這支檔案只負責讀檔錯誤處理、篩選面板、版面排版與呼叫上述函式顯示結果。
    """
    try:
        p, r, s = load_supply_chain_data()
    except FileNotFoundError:
        st.error(
            "❌ 找不到數據檔案！請確認您的檔案已放置於："
            "`Datas/purchase.csv`、`Datas/receipt.csv`、`Datas/sales.csv`"
        )
        return

    st.markdown("<h2 style='white-space: nowrap;'>🔗 Day 8 任務 08 · 供應鏈串接</h2>",
                unsafe_allow_html=True)
    st.caption("採購 ↔ 進貨 ↔ 銷售 三表分析 · 自動診斷庫存積壓主因")

    pr, s_cur, sku_view, supplier, 已進 = build_supply_chain_views(p, r, s)

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
        for _fk, _ik in INPUT_KEYS_D8.items():
            st.session_state[_fk] = st.session_state[_ik]

    def reset_filters_d8():
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

        st.dataframe(style_supplier_table(supplier, show_cols, sel_sup), use_container_width=True)

        col_a, col_b = st.columns(2)
        with col_a:
            st.markdown("##### 各供應商 LT 變異(σ/μ)")
            figA = chart_lt_variance_bar(supplier, sel_sup)
            st.plotly_chart(figA, use_container_width=True)
        with col_b:
            st.markdown("##### 不良率 vs 平均單價(反直覺第二點)")
            figB = chart_defect_vs_price_scatter(supplier, sel_sup)
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

        view2["主因"] = (view2.apply(lambda row: label_backlog_cause(row, backlog_threshold), axis=1)
                        if len(view2) else pd.Series([], dtype=object))
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
                    fig3 = chart_cause_pie(cause_count, top_n, filter_tag)
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

            fig4 = chart_whip_effect_lines(daily, filter_tag)
            st.plotly_chart(fig4, use_container_width=True)

            cv_table = pd.DataFrame({
                "層級": ["銷售出貨量(下游)", "進貨量(中段)", "採購下單量(上游)"],
                "平均": [daily["銷售出貨量"].mean(), daily["進貨量"].mean(), daily["採購下單量"].mean()],
                "標準差": [daily["銷售出貨量"].std(), daily["進貨量"].std(), daily["採購下單量"].std()],
            })
            cv_table["變異(CV)"] = (cv_table["標準差"] / cv_table["平均"].replace(0, pd.NA)).round(2).fillna(0)
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

        notes, diag = diagnose_backlog(view, supplier, backlog_threshold)
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
