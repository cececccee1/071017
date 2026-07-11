"""
utils/kpi.py
============
集中管理各頁面共用的「資料運算 / KPI 計算」邏輯。

規則：這支檔案裡的函式一律不呼叫任何 st.xxx()（不做畫面顯示），
只負責讀檔、清洗、合併、統計、診斷，回傳 DataFrame / dict / 數值，
讓 Pages 底下的頁面檔案專心處理「畫面呈現」。

檔案結構（依頁面分區）：
    1. Day 8 · 採購供應鏈
    2. Day 7 · 運輸異常
    3. D6   · 儲位重排
    4. 首頁 KPI（給 app.py 用）
"""

import os
import numpy as np
import pandas as pd
import streamlit as st

# --- 路徑設定（重要修正） ---
# 原本寫死 DATA_DIR = "Datas" 是「相對路徑」，會根據程式執行時的
# 工作目錄（cwd）去找，而不是根據這支檔案自己的實際位置。
# 在本機用 VS Code 開啟專案資料夾執行時，cwd 剛好等於專案根目錄，
# 所以不會出錯；但部署到 Streamlit Community Cloud 後，cwd 有可能
# 是 repo 最外層（而不是 app.py 所在的子資料夾），導致找不到 Datas/。
#
# 解法：改成以「這支檔案自己在磁碟上的位置」為基準去反推路徑，
# 不管雲端的 cwd 設在哪裡，都能正確定位到 Datas 資料夾。
# 這支檔案在 utils/kpi.py，所以要往上一層（.. ）才是專案根目錄。
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "Datas")


def _p(filename):
    """組出 Datas 資料夾底下的檔案路徑"""
    return os.path.join(DATA_DIR, filename)


# ============================================================
# 1. Day 8 · 採購供應鏈（採購 / 進貨 / 銷售 三表串接）
# ============================================================

@st.cache_data
def load_supply_chain_data():
    """讀取採購/進貨/銷售三張表。
    找不到檔案時會拋出 FileNotFoundError，由呼叫端（頁面檔）自行
    try/except 並顯示 st.error，這支檔案不負責顯示錯誤訊息。"""
    p = pd.read_csv(_p("purchase.csv"), encoding="utf-8-sig",
                     parse_dates=["下單日", "預計到貨"])
    r = pd.read_csv(_p("receipt.csv"), encoding="utf-8-sig",
                     parse_dates=["實際到貨"])
    s = pd.read_csv(_p("sales.csv"), encoding="utf-8-sig",
                     parse_dates=["出貨日"])
    return p, r, s


def _grade_supplier(score):
    if score >= 4.5: return "A 戰略夥伴"
    if score >= 3.5: return "B 一般合作"
    if score >= 2.5: return "C 觀察名單"
    return "D 淘汰候選"


@st.cache_data
def build_supply_chain_views(p, r, s):
    """
    把採購/進貨/銷售三表串接成：
    - pr       : 採購+進貨明細（含實際LT / 計畫LT）
    - s_cur    : 當月（9月）銷售明細
    - sku_view : 每個 SKU 的積壓量 / 周轉率 / 不良率彙總
    - supplier : 每個供應商的 QDC 評分與等級
    - 已進     : pr 當中已經到貨的明細（拿來算平均 LT 等）
    """
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
    supplier["等級"] = supplier["加權分(QDC)"].apply(_grade_supplier)

    return pr, s_cur, sku_view, supplier, 已進


def label_backlog_cause(row, backlog_threshold):
    """判斷單一 SKU 庫存積壓的主因標籤（可能同時符合多項）"""
    causes = []
    if row["實際進貨量"] > row["前三月平均月銷"] * backlog_threshold and row["庫存積壓量"] > 100:
        causes.append("採購過量")
    if pd.notna(row.get("供應商LT變異")) and row["供應商LT變異"] > 0.30:
        causes.append("LT過長")
    if pd.notna(row["周轉率"]) and row["周轉率"] < 0.20:
        causes.append("銷售下滑")
    if row["不良次數"] >= 1 and row["不良率"] >= 0.05:
        causes.append("品質瑕疵")
    return " / ".join(causes) if causes else "一般庫存"


def diagnose_backlog(view, supplier, backlog_threshold):
    """
    針對目前篩選範圍內的 SKU，統計四大積壓主因的影響量，
    並給出「主因 + 建議行動」的診斷文字。
    回傳：(notes: list[str], diag: str | None)
    """
    notes = []
    sup_lt_var = supplier.set_index("供應商")["LT變異"].to_dict()
    v2 = view.copy()
    if len(v2) == 0:
        return ["⚠ 篩選範圍下沒有 SKU，無法診斷。"], None
    v2["供應商LT變異"] = v2["供應商"].map(sup_lt_var)

    over_purchase = v2[(v2["實際進貨量"] > v2["前三月平均月銷"] * backlog_threshold) & (v2["庫存積壓量"] > 100)]
    lt_long = v2[v2["供應商LT變異"] > 0.30]
    sales_down = v2[(v2["周轉率"] < 0.20) & (v2["庫存積壓量"] > 100)]
    quality_bad = v2[(v2["不良次數"] >= 1) & (v2["不良率"] >= 0.05)]

    notes.append(f"📊 採購過量 SKU 共 {len(over_purchase)} 支，合計積壓 {over_purchase['庫存積壓量'].sum():,.0f} 件")
    notes.append(f"⏱️ LT過長 SKU 共 {len(lt_long)} 支，合計積壓 {lt_long['庫存積壓量'].sum():,.0f} 件")
    notes.append(f"📉 銷售下滑 SKU 共 {len(sales_down)} 支，合計積壓 {sales_down['庫存積壓量'].sum():,.0f} 件")
    notes.append(f"🔧 品質瑕疵 SKU 共 {len(quality_bad)} 支")

    impacts = {"採購過量": over_purchase["庫存積壓量"].sum(), "LT過長": lt_long["庫存積壓量"].sum(),
              "銷售下滑": sales_down["庫存積壓量"].sum(), "品質瑕疵": quality_bad["庫存積壓量"].sum()}
    if sum(impacts.values()) == 0:
        return notes, "✅ 此範圍下沒有顯著主因 — 庫存大致平衡。"

    main_cause = max(impacts, key=impacts.get)
    supplier_action = supplier[supplier["加權分(QDC)"] < 3.0]["供應商"].tolist()
    diag = (f"**主因 = `{main_cause}`**（影響積壓量 {impacts[main_cause]:,.0f} 件 / "
           f"占範圍內 {impacts[main_cause]/sum(impacts.values()):.0%}）\n\n"
           f"**建議行動**：\n- 對應主因SKU下個月暫停或減半採購\n"
           f"- 弱供應商 {supplier_action if supplier_action else '無'} 啟動雙源備援\n"
           f"- 業務端做SKU級需求review")
    return notes, diag


# ============================================================
# 2. Day 7 · 運輸異常（OTD 診斷 × 異常偵測）
# ============================================================

@st.cache_data
def load_delivery_data():
    """讀取配送紀錄。找不到檔案時拋出 FileNotFoundError，由頁面檔自行處理。"""
    return pd.read_csv(_p("配送紀錄_202509.csv"), encoding="utf-8-sig",
                        parse_dates=["預計到達", "實際到達", "客戶時窗起", "客戶時窗迄"])


@st.cache_data
def process_delivery_records(df):
    """
    在原始配送紀錄上，補上判斷用的欄位：
    - 在窗內 / 完整 / OTD_嚴格
    - 偏移分鐘 / 異常旗標(IQR) / 異常旗標_Z(Z-score)
    - 早到 / 遲到
    """
    df = df.copy()
    df["在窗內"] = (df["實際到達"] >= df["客戶時窗起"]) & (df["實際到達"] <= df["客戶時窗迄"])
    df["完整"] = df["貨損旗標"] == 0
    df["OTD_嚴格"] = df["在窗內"] & df["完整"]

    df["偏移分鐘"] = (df["實際到達"] - df["預計到達"]).dt.total_seconds() / 60

    Q1 = df["偏移分鐘"].quantile(0.25)
    Q3 = df["偏移分鐘"].quantile(0.75)
    IQR = Q3 - Q1
    下界 = Q1 - 1.5 * IQR
    上界 = Q3 + 1.5 * IQR
    df["異常旗標"] = (df["偏移分鐘"] < 下界) | (df["偏移分鐘"] > 上界)

    mu = df["偏移分鐘"].mean()
    sigma = df["偏移分鐘"].std()
    df["z分數"] = (df["偏移分鐘"] - mu) / sigma
    df["異常旗標_Z"] = df["z分數"].abs() > 2

    df["早到"] = df["實際到達"] < df["客戶時窗起"]
    df["遲到"] = df["實際到達"] > df["客戶時窗迄"]

    return df


def compute_route_driver_otd(df):
    """依路線 / 司機分別統計 OTD，由低到高排序（最差的在最上面）"""
    路線_OTD = (df.groupby("路線代碼")
                  .agg(訂單數=("OTD_嚴格", "count"), OTD=("OTD_嚴格", "mean"))
                  .sort_values("OTD"))
    路線_OTD["OTD%"] = (路線_OTD["OTD"] * 100).round(1)

    司機_OTD = (df.groupby("司機代碼")
                  .agg(訂單數=("OTD_嚴格", "count"), OTD=("OTD_嚴格", "mean"))
                  .sort_values("OTD"))
    司機_OTD["OTD%"] = (司機_OTD["OTD"] * 100).round(1)
    return 路線_OTD, 司機_OTD


def diagnose_main_cause(df, worst_driver):
    """
    控制變量分析：把最差司機的訂單依路線拆開，
    看 OTD 落差是「司機造成」還是「路線造成」。
    回傳：(ctrl: DataFrame, diag_main: '司機'|'路線')
    """
    ctrl = (df[df["司機代碼"] == worst_driver]
            .groupby("路線代碼")
            .agg(訂單數=("OTD_嚴格", "count"), OTD=("OTD_嚴格", "mean"))
            .sort_values("OTD"))
    ctrl["OTD%"] = (ctrl["OTD"] * 100).round(1)
    diag_main = "司機" if ctrl["OTD"].std() < 0.10 else "路線"
    return ctrl, diag_main


@st.cache_data
def detect_rolling_anomaly(df, window=7):
    """用 N 日滾動平均 ±2 個標準差，偵測「有季節性」的每日平均偏移是否異常。"""
    每日 = (df.groupby(df["預計到達"].dt.date)["偏移分鐘"]
              .mean().rename("日平均偏移分鐘").to_frame())
    每日.index = pd.to_datetime(每日.index)
    每日["滾動平均"] = 每日["日平均偏移分鐘"].rolling(window, min_periods=3).mean()
    每日["滾動標準差"] = 每日["日平均偏移分鐘"].rolling(window, min_periods=3).std()
    每日["上界"] = 每日["滾動平均"] + 2 * 每日["滾動標準差"]
    每日["下界"] = 每日["滾動平均"] - 2 * 每日["滾動標準差"]
    每日["異常日"] = (每日["日平均偏移分鐘"] > 每日["上界"]) | (每日["日平均偏移分鐘"] < 每日["下界"])
    return 每日


def build_delivery_diagnosis_text(df, anomalies, worst_driver, ctrl, diag_main, 整體_OTD):
    """組出病灶診斷的完整敘述文字"""
    top_route = anomalies["路線代碼"].value_counts().index[0]
    top_drv = anomalies["司機代碼"].value_counts().index[0]
    top_hour = int(anomalies["預計到達"].dt.hour.value_counts().index[0])

    diag = (
        f"整體嚴格 OTD = {整體_OTD:.1%}，屬於"
        f"{'警戒' if 整體_OTD < 0.90 else '偏低' if 整體_OTD < 0.95 else '健康'}區間。"
        f"異常筆數 {df['異常旗標'].sum():,} 筆（{df['異常旗標'].mean():.1%}），"
        f"集中在路線 {top_route}（{anomalies['路線代碼'].value_counts().iloc[0]} 筆）"
        f"與司機 {top_drv}（{anomalies['司機代碼'].value_counts().iloc[0]} 筆），"
        f"時段以 {top_hour:02d}:00 為高峰。"
        f"控制變量分析顯示最差司機 {worst_driver} 在不同路線落差 std = {ctrl['OTD'].std():.2f}，"
        f"診斷主因為【{diag_main}】。"
        f"一週內可動行動：把 {worst_driver} 暫時移出 {top_route} 路線，"
        f"觀察 7 天 OTD 是否回升。"
    )
    return diag


# ============================================================
# 3. D6 · 儲位重排（ABC 分類 × 動態熱區）
# ============================================================

@st.cache_data
def load_sku_shipment_data():
    """讀取 SKU 出貨明細。找不到檔案時拋出 FileNotFoundError，由頁面檔自行處理。"""
    return pd.read_csv(_p("SKU_出貨明細_202509.csv"), encoding="utf-8-sig", parse_dates=["訂單日期"])


@st.cache_data
def classify_abc(df):
    """依出貨量做 ABC 分類：累計佔比 80% 內為 A、95% 內為 B，其餘為 C"""
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


def compute_storage_layout(sku, sort_method):
    """
    依指定排序依據（IQ / IK / 綜合分數）計算「重排前」與「重排後」的儲位分布，
    重排後的邏輯是把熱門品項依曼哈頓距離，由近到遠塞進以左下角（E列，1排）為出入口的貨架。
    回傳：(sku 可能新增 IK_norm/IQ_norm/綜合分數欄位, grid_before, grid_after)
    """
    rows = ["A列", "B列", "C列", "D列", "E列"]
    cols = [f"{i}排" for i in range(1, 11)]

    sku_before = sku.sort_values("SKU").reset_index(drop=True)
    before_queue = sku_before["SKU"].tolist()
    grid_before_arr = [["" for _ in range(10)] for _ in range(5)]
    for idx in range(min(50, len(before_queue))):
        r, c = idx // 10, idx % 10
        grid_before_arr[r][c] = before_queue[idx]
    grid_before = pd.DataFrame(grid_before_arr, index=rows, columns=cols)

    sku = sku.copy()
    if sort_method == "IQ(總出貨量)":
        queue = sku.sort_values("總出貨量", ascending=False)["SKU"].tolist()
    elif sort_method == "IK(出貨筆數)":
        queue = sku.sort_values("出貨筆數", ascending=False)["SKU"].tolist()
    else:
        sku["IK_norm"] = sku["出貨筆數"] / sku["出貨筆數"].max()
        sku["IQ_norm"] = sku["總出貨量"] / sku["總出貨量"].max()
        sku["綜合分數"] = sku["IK_norm"] * 0.4 + sku["IQ_norm"] * 0.6
        queue = sku.sort_values("綜合分數", ascending=False)["SKU"].tolist()

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

    return sku, grid_before, grid_after


# ============================================================
# 4. 首頁 KPI（給 app.py 主頁三張 KPI 卡使用）
# ============================================================
# 下面三個函式是 app.py 主頁 KPI 卡片（整體 OTD / 庫存周轉率 / 供應商平均 LT）
# 的實際實作。原本 app.py 只有「找不到 utils.kpi 就用假數值」的防呆，
# 現在這個模組已經存在，請務必確認 app.py 的 try/except 有攔截到
# FileNotFoundError（例如改成 except Exception），否則資料檔案缺少時
# 網站會直接壞掉，而不是顯示預設假數值。

def calc_otd():
    """回傳整體嚴格 OTD（0~1 之間的比率），取自配送紀錄。"""
    df = load_delivery_data()
    df = process_delivery_records(df)
    return df["OTD_嚴格"].mean()


def calc_turnover():
    """
    回傳 9 月庫存周轉率。
    目前定義 = 9月銷量 ÷ 9月實際進貨量（月度周轉率，數值通常介於 0~1）。

    ⚠️ 這是暫時代入的定義，不是老師指定的正式公式。
    如果老師對「庫存周轉率」有指定算法（例如年化周轉率、
    COGS ÷ 平均庫存），只需要調整這個函式內部的計算方式即可，
    其他頁面不會受影響。
    """
    p, r, s = load_supply_chain_data()
    _, _, sku_view, _, _ = build_supply_chain_views(p, r, s)
    total_in = sku_view["實際進貨量"].sum()
    total_out = sku_view["九月銷量"].sum()
    return (total_out / total_in) if total_in else 0


def calc_supplier_lt():
    """回傳所有供應商的平均前置時間（以採購單數加權平均，單位：天）。"""
    p, r, s = load_supply_chain_data()
    _, _, _, supplier, _ = build_supply_chain_views(p, r, s)
    if supplier["採購單數"].sum() == 0:
        return supplier["平均LT"].mean()
    return float(np.average(supplier["平均LT"], weights=supplier["採購單數"]))
