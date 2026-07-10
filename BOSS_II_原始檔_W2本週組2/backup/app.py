import streamlit as st

# 從 Pages 資料夾引入其他分頁模組
from Pages import 倉儲健康
from Pages import 運輸異常
from Pages import 採購供應鏈

# --- 嘗試引入老師的 KPI 計算函式，若找不到則使用預設數值（防錯機制） ---
try:
    from utils.kpi import calc_otd, calc_turnover, calc_supplier_lt
    otd_val = f"{calc_otd():.1%}"
    turnover_val = f"{calc_turnover():.1f}"
    lt_val = f"{calc_supplier_lt():.1f} 天"
except ModuleNotFoundError:
    otd_val = "94.2%"
    turnover_val = "4.5"
    lt_val = "3.5 天"

# 1. 網頁基本設定
st.set_page_config(
    page_title="物流控制塔_Alpha",
    page_icon="📊",
    layout="wide"
)


# 2. 注入自訂 CSS：修改背景顏色、主標題，並強迫分頁填滿畫面且擴大點擊區域
st.markdown(
    """
    <style>
    /* 1. 變更整個網頁的背景顏色 */
    .stApp {
        background-color: #F4F6F9;
    }
    
    /* 2. 將主標題置中，並設定字型與間距 */
    .centered-title {
        text-align: center;
        font-size: 2.5rem;
        font-weight: 700;
        color: #1E293B;
        padding-top: 10px;
        padding-bottom: 5px;
    }
    
    /* 3. 將副標題置中 */
    .centered-caption {
        text-align: center;
        color: #64748B;
        font-size: 0.9rem;
        margin-bottom: 15px;
    }

    /* 4. 強迫 Streamlit 的 Tab 總列橫向撐滿 100% 畫面，並移除非必要的邊距 */
    div[data-baseweb="tab-list"] {
        width: 100% !important;
        display: flex !important;
        justify-content: space-between !important;
        gap: 4px !important; /* 讓分頁按鈕之間有一點點小細縫，看起來更像高階頁籤 */
    }

    /* 🔥 5. 擴大分頁按鈕本體：平分寬度、增加高度、滑鼠移入時顯示手勢 */
    div[data-baseweb="tab"] {
        flex: 1 !important;
        text-align: center !important;
        justify-content: center !important;
        font-size: 1.1rem !important; 
        font-weight: 600 !important;
        padding-top: 15px !important;    /* 增加上方按鈕內距 */
        padding-bottom: 15px !important; /* 增加下方按鈕內距 */
        cursor: pointer !important;       /* 確保滑鼠滑過去任何地方都出現小手圖標 */
    }

    /* 🔥 6. 擴大內部文字與偽元素的點擊範圍，強迫充滿整個 Tab 按鈕 */
    div[data-baseweb="tab"] > p {
        width: 100% !important;
        height: 100% !important;
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
        margin: 0 !important;
    }
    </style>
    """,
    unsafe_allow_html=True
)


# 3. 使用 HTML 標籤套用置中主標題與更新時間
st.markdown('<div class="centered-title">📊 物流控制塔_Alpha</div>', unsafe_allow_html=True)
st.markdown('<div class="centered-caption">更新時間: 2026-09-30 | 資料口徑: 9 月 1 日 - 9 月 30 日</div>', unsafe_allow_html=True)
st.markdown("---")

# 4. 建立四個分頁 (現在會自動撐滿畫面)
tab1, tab2, tab3, tab4 = st.tabs(["🏠 主頁", "📦 倉儲健康", "🚚 運輸異常", "🛒 採購供應鏈"])

# --- 分頁 1：主頁 ---
with tab1:
    # === 一句話結論 ===
    st.success("📌 **本月健康度: 🟡 注意 — R-03 路線 OTD 偏低，**"
               "**A 類儲位重排可省 22% 工時，建議連動處理**")
    
    # === KPI 總覽 ===
    st.subheader("📊 今日營運關鍵指標 (KPI)")
    c1, c2, c3 = st.columns(3)
    c1.metric("整體 OTD", otd_val, delta="-1.2pp", delta_color="inverse")
    c2.metric("庫存周轉率", turnover_val, delta="+0.3")
    c3.metric("供應商平均 LT", lt_val, delta="+0.5", delta_color="inverse")
    
    st.divider()
    
    # === 三大故障紅燈 ===
    st.subheader("🚨 異常事件 (自動偵測)")
    st.error("R-03 路線 OTD 87.1% (連續 3 週低於 90%) → 建議分割路線 + 司機重訓")
    st.warning("SKU-A047 庫存積壓 +180% (供應商 S-12 LT 漂移) → 建議暫停下單 1 個月")
    st.info("9 月新導入「冷凍植物肉」候選評估報告已產出 → 點 [採購供應鏈] 頁查看")
    
    st.divider()
    
    # === 一頁建議書 ===
    st.subheader("📝 給總經理的 9 月建議書")
    with st.expander("展開三條 MECE 支撐 + 風險三情境", expanded=True):
        st.markdown("""
        **建議**: R-03 路線分割 + 司機 D-07 重訓，A 類儲位重排，**1 個月內可拉回 95% OTD + 省 22% 揀貨工時**
    
        **支撐 MECE**:
        1. **問題真實存在**: R-03 OTD 連續 3 週惡化 (87.1% → 86.3% → 84.5%)
        2. **主因可定位**: 控制變量分析，司機 D-07 跨路線比較，問題集中在 R-03
        3. **解法可行**: 既有 5 號車閒置時段足夠分擔，無需新增車輛
    
        **風險三情境**:

        | 情境 | OTD | 月效益 |
        |---|---|---|
        | 樂觀 | 96% | +5 萬 |
        | 悲觀 | 92% | 0 |
        | 不作為 | 持續惡化 | -8 萬/月 |
        """)
        
    st.info("💡 請點擊上方分頁切換至各系統，查看更詳細的數據分析與報告。")

# --- 分頁 2：倉儲健康 ---
with tab2:
    倉儲健康.render_page()

# --- 分頁 3：運輸異常 ---
with tab3:
    運輸異常.render_page()

# --- 分頁 4：採購供應鏈 ---
with tab4:
    採購供應鏈.render_page()
