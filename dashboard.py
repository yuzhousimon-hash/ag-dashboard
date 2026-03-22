"""
全国准入状况作战指挥 Dashboard
技术栈: Streamlit + Plotly | Solarized Dark + MHM绿色主题
启动: streamlit run dashboard.py --server.port 8502
"""
import json, os, sys, glob
from datetime import datetime, timedelta
from pathlib import Path
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd

# ── Config ──
BASE = Path(__file__).resolve().parent
DATA = BASE / "data"
MASTER_FILE = DATA / "province_master.json"
SNAP_DIR = DATA / "snapshots"
POLICY_SCAN_FILE = DATA / "policy_scan.json"
COMPETITOR_FILE = DATA / "competitor_intel.json"
SCAN_CONFIG_FILE = DATA / "scan_config.json"

# ── Theme ──
BG_DARK = "#002b36"
BG_CARD = "#073642"
MHM_GREEN = "#00a651"
MHM_GREEN_LIGHT = "#33cc77"
WARN_YELLOW = "#f0ad4e"
WARN_RED = "#d9534f"
TEXT_LIGHT = "#93a1a1"
TEXT_WHITE = "#fdf6e3"
ACCENT_CYAN = "#2aa198"

st.set_page_config(page_title="政务准入作战指挥台", page_icon="🗺️", layout="wide")
st.markdown(f"""<style>
    .stApp {{ background-color: {BG_DARK}; color: {TEXT_WHITE}; }}
    .stTabs [data-baseweb="tab-list"] {{ gap: 8px; }}
    .stTabs [data-baseweb="tab"] {{ background-color: {BG_CARD}; color: {TEXT_LIGHT}; border-radius: 8px; padding: 8px 20px; font-weight: 600; }}
    .stTabs [aria-selected="true"] {{ background-color: {MHM_GREEN}; color: white; }}
    div[data-testid="stMetric"] {{ background: {BG_CARD}; border-radius: 12px; padding: 16px; border-left: 4px solid {MHM_GREEN}; }}
    div[data-testid="stMetric"] label {{ color: {TEXT_LIGHT}; font-size: 0.85rem; }}
    div[data-testid="stMetric"] [data-testid="stMetricValue"] {{ color: {TEXT_WHITE}; font-size: 1.6rem; font-weight: 700; }}
    .block-container {{ padding-top: 1rem; }}
    h1, h2, h3 {{ color: {TEXT_WHITE}; }}
    .stDataFrame {{ border-radius: 8px; }}
</style>""", unsafe_allow_html=True)

# ── Load Data ──
@st.cache_data
def load_master():
    with open(MASTER_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def load_prev_snapshot():
    snaps = sorted(glob.glob(str(SNAP_DIR / "snapshot_*.json")))
    if len(snaps) < 2:
        return None
    with open(snaps[-2], "r", encoding="utf-8") as f:
        return json.load(f)

data = load_master()
prev_data = load_prev_snapshot()
df = pd.DataFrame(data)

# ── Province → ISO code mapping for choropleth ──
PROVINCE_ISO = {
    "北京市":"CN-BJ","天津市":"CN-TJ","河北省":"CN-HE","山西省":"CN-SX",
    "内蒙古自治区":"CN-NM","辽宁省":"CN-LN","吉林省":"CN-JL","黑龙江省":"CN-HL",
    "上海市":"CN-SH","江苏省":"CN-JS","浙江省":"CN-ZJ","安徽省":"CN-AH",
    "福建省":"CN-FJ","江西省":"CN-JX","山东省":"CN-SD","河南省":"CN-HA",
    "湖北省":"CN-HB","湖南省":"CN-HN","广东省":"CN-GD","广西壮族自治区":"CN-GX",
    "海南省":"CN-HI","重庆市":"CN-CQ","四川省":"CN-SC","贵州省":"CN-GZ",
    "云南省":"CN-YN","西藏自治区":"CN-XZ","陕西省":"CN-SN","甘肃省":"CN-GS",
    "青海省":"CN-QH","宁夏回族自治区":"CN-NX","新疆维吾尔自治区":"CN-XJ",
}

# ── Helper functions ──
def count_color_labels(color):
    return sum(1 for p in data if p.get("金针", {}).get("color_label") == color)

def count_switch_done(product_key):
    return sum(1 for p in data if p.get("products", {}).get(product_key, {}).get("done", False))

def count_switch_total(product_key):
    return sum(1 for p in data if p.get("products", {}).get(product_key, {}).get("listed", False) or p.get("products", {}).get(product_key, {}).get("done", False) or p.get("products", {}).get(product_key, {}).get("switch_status", ""))

def get_all_deadlines():
    items = []
    for p in data:
        for d in p.get("deadlines", []):
            items.append({**d, "province": p["province"]})
        for a in p.get("alerts", []):
            items.append({"date": a.get("date", ""), "desc": a.get("desc", ""), "urgency": a.get("type", ""), "province": p["province"]})
    items.sort(key=lambda x: x.get("date", "9999"))
    return items

# ── HEADER ──
st.markdown(f"<h1 style='text-align:center; margin-bottom:0;'>🗺️ 全国准入状况作战指挥台</h1>", unsafe_allow_html=True)
st.markdown(f"<p style='text-align:center; color:{TEXT_LIGHT}; margin-top:0;'>数据截至 2026-03-20 | 覆盖 {len(data)} 个省级行政区</p>", unsafe_allow_html=True)

# ── TABS ──
tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs(["📊 全国态势总览", "🔄 产品切换进度", "⚠️ 风险预警", "⚡ 紧急行动看板", "📡 前瞻雷达", "📱 政策扫描", "🎯 竞品矩阵"])

# ═══════════════════════════════════════════
# TAB 1: 全国态势总览
# ═══════════════════════════════════════════
with tab1:
    c1, c2, c3, c4 = st.columns(4)
    avg_hi = df["health_index"].mean()
    yellow_count = count_color_labels("yellow")
    red_count = count_color_labels("red")
    alert_count = sum(len(p.get("alerts", [])) for p in data)

    c1.metric("平均健康指数", f"{avg_hi:.1f}", delta=None)
    c2.metric("黄标省份", f"{yellow_count} 省", delta=None)
    c3.metric("红标省份", f"{red_count} 省", delta="⚠ 内蒙古升级" if red_count > 0 else None)
    c4.metric("活跃预警数", f"{alert_count} 个", delta=None)

    col_map, col_table = st.columns([3, 2])

    with col_map:
        st.subheader("准入健康指数全国地图")
        map_df = pd.DataFrame([{
            "province": p["province"],
            "iso": PROVINCE_ISO.get(p["province"], ""),
            "health_index": p["health_index"],
            "biz_share": p["biz_share"],
            "quadrant": p["quadrant"],
            "status": p["status"],
        } for p in data if PROVINCE_ISO.get(p["province"])])

        fig = go.Figure()
        # Use a scatter geo as choropleth requires geojson
        # Instead, create a sortable bar chart of health index
        map_df_sorted = map_df.sort_values("health_index")
        colors = []
        for hi in map_df_sorted["health_index"]:
            if hi >= 80: colors.append(MHM_GREEN)
            elif hi >= 65: colors.append(WARN_YELLOW)
            else: colors.append(WARN_RED)

        fig = go.Figure(go.Bar(
            y=map_df_sorted["province"],
            x=map_df_sorted["health_index"],
            orientation="h",
            marker_color=colors,
            text=map_df_sorted["health_index"].apply(lambda x: f"{x:.0f}"),
            textposition="outside",
            textfont=dict(color=TEXT_WHITE, size=11),
        ))
        fig.update_layout(
            height=700,
            paper_bgcolor=BG_DARK,
            plot_bgcolor=BG_CARD,
            font=dict(color=TEXT_LIGHT),
            xaxis=dict(title="健康指数", range=[0, 105], gridcolor="#1a3a45"),
            yaxis=dict(title=""),
            margin=dict(l=120, r=40, t=10, b=30),
        )
        # Add threshold lines using shapes + annotations (avoid add_vline bug)
        fig.add_shape(type="line", x0=80, x1=80, y0=0, y1=1, yref="paper", line=dict(dash="dash", color=MHM_GREEN, width=1))
        fig.add_shape(type="line", x0=65, x1=65, y0=0, y1=1, yref="paper", line=dict(dash="dash", color=WARN_YELLOW, width=1))
        fig.add_annotation(x=80, y=1, yref="paper", text="良好 ≥80", showarrow=False, font=dict(color=MHM_GREEN, size=10))
        fig.add_annotation(x=65, y=1, yref="paper", text="关注 ≥65", showarrow=False, font=dict(color=WARN_YELLOW, size=10))
        st.plotly_chart(fig, use_container_width=True)

    with col_table:
        st.subheader("战略象限分布")
        quadrant_counts = {}
        for p in data:
            q = p.get("quadrant", "")
            if q:
                quadrant_counts[q] = quadrant_counts.get(q, 0) + 1
        q_df = pd.DataFrame([{"象限": k, "省份数": v} for k, v in sorted(quadrant_counts.items())]) if quadrant_counts else pd.DataFrame()
        if not q_df.empty:
            fig_q = go.Figure(go.Pie(
                labels=q_df["象限"], values=q_df["省份数"],
                marker_colors=[MHM_GREEN, "#e67e22", ACCENT_CYAN, TEXT_LIGHT],
                textinfo="label+value",
                textfont=dict(size=13),
                hole=0.45,
            ))
            fig_q.update_layout(
                height=250,
                paper_bgcolor=BG_DARK,
                font=dict(color=TEXT_WHITE),
                margin=dict(l=10, r=10, t=10, b=10),
                showlegend=False,
            )
            st.plotly_chart(fig_q, use_container_width=True)

        st.subheader("业务占比 TOP10")
        biz_df = pd.DataFrame([{"省份": p["province"], "占比": p["biz_share"]} for p in data])
        biz_df = biz_df.sort_values("占比", ascending=False).head(10)
        fig_biz = go.Figure(go.Bar(
            x=biz_df["省份"], y=biz_df["占比"],
            marker_color=MHM_GREEN,
            text=biz_df["占比"].apply(lambda x: f"{x*100:.1f}%"),
            textposition="outside",
            textfont=dict(color=TEXT_WHITE, size=10),
        ))
        fig_biz.update_layout(
            height=300,
            paper_bgcolor=BG_DARK, plot_bgcolor=BG_CARD,
            font=dict(color=TEXT_LIGHT),
            xaxis=dict(tickangle=-45), yaxis=dict(title="占比", tickformat=".0%"),
            margin=dict(l=50, r=20, t=10, b=80),
        )
        st.plotly_chart(fig_biz, use_container_width=True)

# ═══════════════════════════════════════════
# TAB 2: 产品切换进度
# ═══════════════════════════════════════════
with tab2:
    st.subheader("进口商切换进度总览")
    products = ["T20", "T40", "T60", "金滴", "威利坦"]
    progress_data = []
    for pk in products:
        done = 0; in_progress = 0; not_started = 0
        for p in data:
            prod = p.get("products", {}).get(pk, {})
            if not prod:
                not_started += 1
            elif prod.get("done"):
                done += 1
            elif prod.get("switch_status") and prod["switch_status"] not in ["", "/"]:
                in_progress += 1
            else:
                not_started += 1
        total = done + in_progress + not_started
        progress_data.append({"product": pk, "已完成": done, "进行中": in_progress, "未开始": not_started, "total": total})

    prog_df = pd.DataFrame(progress_data)

    fig_prog = go.Figure()
    fig_prog.add_trace(go.Bar(name="已完成", y=prog_df["product"], x=prog_df["已完成"],
                               orientation="h", marker_color=MHM_GREEN, text=prog_df["已完成"], textposition="inside"))
    fig_prog.add_trace(go.Bar(name="进行中", y=prog_df["product"], x=prog_df["进行中"],
                               orientation="h", marker_color=WARN_YELLOW, text=prog_df["进行中"], textposition="inside"))
    fig_prog.add_trace(go.Bar(name="未开始", y=prog_df["product"], x=prog_df["未开始"],
                               orientation="h", marker_color="#586e75", text=prog_df["未开始"], textposition="inside"))
    fig_prog.update_layout(
        barmode="stack", height=300,
        paper_bgcolor=BG_DARK, plot_bgcolor=BG_CARD,
        font=dict(color=TEXT_WHITE),
        legend=dict(orientation="h", y=1.15),
        margin=dict(l=80, r=20, t=40, b=20),
        xaxis=dict(title="省份数"),
    )
    st.plotly_chart(fig_prog, use_container_width=True)

    # Detail table
    st.subheader("逐省切换详情")
    product_filter = st.selectbox("选择产品", products, key="prod_filter")
    detail_rows = []
    for p in data:
        prod = p.get("products", {}).get(product_filter, {})
        if not prod:
            continue
        status_emoji = "✅" if prod.get("done") else ("🔄" if prod.get("switch_status") and prod["switch_status"] not in ["", "/"] else "⬜")
        detail_rows.append({
            "状态": status_emoji,
            "省份": p["province"],
            "大区": p.get("region", ""),
            "是否挂网": "✅" if prod.get("listed") else "❌",
            "切换状态": prod.get("switch_status", ""),
            "月均销量(盒)": f"{prod.get('monthly_vol', 0):,}",
        })
    detail_df = pd.DataFrame(detail_rows)
    st.dataframe(detail_df, use_container_width=True, height=500)

# ═══════════════════════════════════════════
# TAB 3: 风险预警
# ═══════════════════════════════════════════
with tab3:
    col_label, col_keyuan = st.columns(2)

    with col_label:
        st.subheader("🏷️ 金针颜色标识分布")
        label_rows = []
        for p in data:
            jz = p.get("金针", {})
            cl = jz.get("color_label")
            if cl:
                label_rows.append({
                    "省份": p["province"],
                    "标识": "🔴 红标" if cl == "red" else "🟡 黄标",
                    "color": cl,
                    "可售状态": jz.get("price_status", ""),
                    "广东联盟": jz.get("gd_alliance", ""),
                    "健康指数": p["health_index"],
                    "业务占比": f"{p['biz_share']*100:.1f}%" if p['biz_share'] else "—",
                })
        label_df = pd.DataFrame(label_rows)
        if not label_df.empty:
            # Sort: red first, then by health_index
            label_df["sort_key"] = label_df["color"].map({"red": 0, "yellow": 1})
            label_df = label_df.sort_values(["sort_key", "健康指数"])
            st.dataframe(label_df[["标识", "省份", "可售状态", "广东联盟", "健康指数", "业务占比"]], use_container_width=True, height=400)
        else:
            st.info("暂无颜色标识预警")

        # Color label bar chart
        fig_cl = go.Figure()
        for _, row in label_df.iterrows():
            fig_cl.add_trace(go.Bar(
                x=[row["省份"]], y=[row["健康指数"]],
                marker_color=WARN_RED if row["color"] == "red" else WARN_YELLOW,
                showlegend=False,
                text=[f"{row['健康指数']:.0f}"],
                textposition="outside",
                textfont=dict(color=TEXT_WHITE),
            ))
        fig_cl.update_layout(
            height=250,
            paper_bgcolor=BG_DARK, plot_bgcolor=BG_CARD,
            font=dict(color=TEXT_LIGHT),
            xaxis=dict(tickangle=-45),
            yaxis=dict(title="健康指数"),
            margin=dict(l=50, r=20, t=10, b=80),
        )
        st.plotly_chart(fig_cl, use_container_width=True)

    with col_keyuan:
        st.subheader("🏗️ 科园阻碍攻克看板")
        keyuan_rows = []
        for p in data:
            issues = p.get("core_issues", [])
            for issue in issues:
                if "科园" in issue:
                    conquered = "已攻克" in issue
                    attacking = "进攻" in issue
                    status = "✅ 已攻克" if conquered else ("⚔️ 进攻中" if attacking else "🔒 受阻")
                    keyuan_rows.append({
                        "省份": p["province"],
                        "状态": status,
                        "详情": issue,
                        "健康指数": p["health_index"],
                    })
        keyuan_df = pd.DataFrame(keyuan_rows) if keyuan_rows else pd.DataFrame()
        if not keyuan_df.empty:
            # Sort: 受阻 first, then 进攻中, then 已攻克
            order = {"🔒 受阻": 0, "⚔️ 进攻中": 1, "✅ 已攻克": 2}
            keyuan_df["sort_key"] = keyuan_df["状态"].map(order)
            keyuan_df = keyuan_df.sort_values("sort_key")
            st.dataframe(keyuan_df[["状态", "省份", "详情", "健康指数"]], use_container_width=True, height=400)

            # Summary metrics
            conquered = sum(1 for r in keyuan_rows if "已攻克" in r["状态"])
            attacking = sum(1 for r in keyuan_rows if "进攻" in r["状态"])
            blocked = sum(1 for r in keyuan_rows if "受阻" in r["状态"])
            kc1, kc2, kc3 = st.columns(3)
            kc1.metric("已攻克", f"{conquered} 省", delta=None)
            kc2.metric("进攻中", f"{attacking} 省", delta=None)
            kc3.metric("受阻", f"{blocked} 省", delta=None)

    # Alerts section
    st.subheader("🚨 本周预警事件")
    alert_rows = []
    for p in data:
        for a in p.get("alerts", []):
            urgency_map = {"price_risk": "🔴 价格风险", "color_upgrade": "🔴 标色升级",
                          "new_color_label": "🟡 新增标色", "inactive_zone_resolved": "🟢 已解决",
                          "info_confirm": "🟡 信息确认"}
            alert_rows.append({
                "级别": urgency_map.get(a.get("type", ""), "🟡 " + a.get("type", "")),
                "省份": p["province"],
                "事件": a.get("desc", ""),
                "日期": a.get("date", ""),
            })
    if alert_rows:
        st.dataframe(pd.DataFrame(alert_rows), use_container_width=True)

# ═══════════════════════════════════════════
# TAB 4: 紧急行动看板
# ═══════════════════════════════════════════
with tab4:
    st.subheader("⚡ 按紧急程度排序的行动清单")

    today = datetime(2026, 3, 20)
    all_actions = []

    # Collect deadlines
    for p in data:
        for d in p.get("deadlines", []):
            try:
                dt = datetime.strptime(d["date"], "%Y-%m-%d")
            except:
                continue
            days_left = (dt - today).days
            if days_left < 0:
                urgency_label = "🔴 已过期"
                urgency_score = -1
            elif days_left <= 3:
                urgency_label = "🔴 极紧急"
                urgency_score = 0
            elif days_left <= 7:
                urgency_label = "🟠 本周"
                urgency_score = 1
            elif days_left <= 14:
                urgency_label = "🟡 下周"
                urgency_score = 2
            else:
                urgency_label = "🟢 本月"
                urgency_score = 3
            all_actions.append({
                "紧急度": urgency_label,
                "sort": urgency_score,
                "days_left": days_left,
                "截止日期": d["date"],
                "剩余天数": f"{days_left}天" if days_left >= 0 else f"已过期{-days_left}天",
                "省份": p["province"],
                "事项": d["desc"],
                "类型": d.get("urgency", ""),
            })

    # Also add alerts with dates as action items
    for p in data:
        for a in p.get("alerts", []):
            if a.get("type") in ["price_risk", "color_upgrade", "new_color_label"]:
                # These need action
                all_actions.append({
                    "紧急度": "🔴 极紧急" if a.get("type") == "price_risk" else "🟠 本周",
                    "sort": 0 if a.get("type") == "price_risk" else 1,
                    "days_left": 0,
                    "截止日期": a.get("date", ""),
                    "剩余天数": "需立即处理",
                    "省份": p["province"],
                    "事项": a.get("desc", ""),
                    "类型": a.get("type", ""),
                })

    if all_actions:
        action_df = pd.DataFrame(all_actions).sort_values(["sort", "days_left"])
        # KPI cards
        ac1, ac2, ac3, ac4 = st.columns(4)
        critical = sum(1 for a in all_actions if a["sort"] <= 0)
        this_week = sum(1 for a in all_actions if a["sort"] == 1)
        next_week = sum(1 for a in all_actions if a["sort"] == 2)
        later = sum(1 for a in all_actions if a["sort"] >= 3)
        ac1.metric("🔴 极紧急", f"{critical} 项")
        ac2.metric("🟠 本周", f"{this_week} 项")
        ac3.metric("🟡 下周", f"{next_week} 项")
        ac4.metric("🟢 稍后", f"{later} 项")

        st.dataframe(
            action_df[["紧急度", "省份", "事项", "截止日期", "剩余天数"]],
            use_container_width=True,
            height=500,
        )

        # Timeline visualization
        st.subheader("📅 时间线视图")
        timeline_df = action_df[action_df["截止日期"] != ""].copy()
        if not timeline_df.empty:
            timeline_df["date_parsed"] = pd.to_datetime(timeline_df["截止日期"], errors="coerce")
            timeline_df = timeline_df.dropna(subset=["date_parsed"])
            fig_tl = go.Figure()
            color_map = {"🔴 极紧急": WARN_RED, "🔴 已过期": WARN_RED, "🟠 本周": "#e67e22", "🟡 下周": WARN_YELLOW, "🟢 本月": MHM_GREEN}
            for _, row in timeline_df.iterrows():
                fig_tl.add_trace(go.Scatter(
                    x=[row["date_parsed"]],
                    y=[row["省份"]],
                    mode="markers+text",
                    marker=dict(size=16, color=color_map.get(row["紧急度"], TEXT_LIGHT)),
                    text=[row["事项"][:15]],
                    textposition="middle right",
                    textfont=dict(size=10, color=TEXT_WHITE),
                    showlegend=False,
                    hovertext=f"{row['省份']}: {row['事项']}",
                ))
            # Today line (use add_shape to avoid Plotly annotation bug)
            fig_tl.add_shape(type="line", x0="2026-03-20", x1="2026-03-20", y0=0, y1=1, yref="paper", line=dict(dash="dash", color=ACCENT_CYAN, width=1))
            fig_tl.add_annotation(x="2026-03-20", y=1, yref="paper", text="今天 3/20", showarrow=False, font=dict(color=ACCENT_CYAN, size=10))
            fig_tl.update_layout(
                height=350,
                paper_bgcolor=BG_DARK, plot_bgcolor=BG_CARD,
                font=dict(color=TEXT_LIGHT),
                xaxis=dict(title="日期", gridcolor="#1a3a45"),
                yaxis=dict(title=""),
                margin=dict(l=120, r=40, t=10, b=30),
            )
            st.plotly_chart(fig_tl, use_container_width=True)
    else:
        st.success("暂无紧急事项 🎉")

# ═══════════════════════════════════════════
# TAB 5: 前瞻雷达
# ═══════════════════════════════════════════
with tab5:
    radar_file = DATA / "proactive_radar.json"
    if radar_file.exists():
        with open(radar_file, "r", encoding="utf-8") as f:
            radar = json.load(f)
    else:
        radar = None

    if radar:
        # KPI cards
        actions = radar.get("next_week_actions", [])
        alliances = radar.get("alliance_expiry", [])
        t60 = radar.get("t60_status", {})
        checklists = radar.get("switch_checklists", [])

        rc1, rc2, rc3 = st.columns(3)
        rc1.metric("📋 下周行动", f"{len(actions)} 项")
        urgent_actions = sum(1 for a in actions if a.get('days_until', 99) <= 3)
        rc2.metric("🔴 紧急(≤ 3天)", f"{urgent_actions} 项")
        rc3.metric("🔓 T60进度", f"{t60.get('done_count', 0)}/{t60.get('unlock_threshold', 3)}省",
                   delta="✅ 已解锁" if t60.get('is_unlocked') else None)

        # ── Next week actions ──
        st.subheader("📋 下周作战命令")
        if actions:
            act_rows = []
            for a in actions:
                days = a.get("days_until", 0)
                if days <= 1:
                    urgency = "🔴 立即"
                elif days <= 3:
                    urgency = "🟠 3天内"
                else:
                    urgency = "🟡 本周"
                prep = " | ".join(a.get("prep_checklist", [])[:3])
                act_rows.append({
                    "紧急度": urgency,
                    "省份": a["province"],
                    "事件": a["event"],
                    "时间窗口": a["window"],
                    "倒计时": f"{days}天" if days >= 0 else "已开始",
                    "前置准备": prep,
                })
            st.dataframe(pd.DataFrame(act_rows), use_container_width=True, height=350)

            # Timeline chart for next week actions
            fig_nw = go.Figure()
            for a in actions:
                days = a.get("days_until", 0)
                color = WARN_RED if days <= 1 else (WARN_YELLOW if days <= 3 else MHM_GREEN)
                fig_nw.add_trace(go.Bar(
                    y=[f"{a['province']}-{a['event']}"],
                    x=[max(days, 0.3)],
                    orientation="h",
                    marker_color=color,
                    text=[f"{days}天"],
                    textposition="outside",
                    textfont=dict(color=TEXT_WHITE, size=10),
                    showlegend=False,
                ))
            fig_nw.update_layout(
                height=max(200, len(actions) * 32),
                paper_bgcolor=BG_DARK, plot_bgcolor=BG_CARD,
                font=dict(color=TEXT_LIGHT),
                xaxis=dict(title="倒计天数", gridcolor="#1a3a45"),
                yaxis=dict(title=""),
                margin=dict(l=200, r=40, t=10, b=30),
            )
            st.plotly_chart(fig_nw, use_container_width=True)

        # ── T60 Unlock ──
        st.subheader("🔓 T60全国推广解锁进度")
        done_count = t60.get("done_count", 0)
        threshold = t60.get("unlock_threshold", 3)
        pct = min(100, int(done_count / max(threshold, 1) * 100))
        is_unlocked = t60.get("is_unlocked", False)

        status_text = "✅ 已解锁！可全国推广" if is_unlocked else f"⏳ {done_count}/{threshold}省"
        st.progress(pct / 100, text=status_text)

        col_done, col_pending = st.columns(2)
        with col_done:
            done_names = [d["province"] for d in t60.get("done_provinces", [])]
            st.markdown(f"**已挂网**: {', '.join(done_names)}")
        with col_pending:
            pending = t60.get("pending_provinces", [])
            if pending:
                st.markdown("**待推进** (有时间窗口):")
                for pp in pending:
                    st.markdown(f"- {pp['province']}: {pp['status']}")
        # ── Policy Milestones ──
        st.subheader("📅 政策里程碑")
        milestones = radar.get("policy_milestones", [])
        for pm in milestones:
            st.markdown(f"""
            <div style='background:{BG_CARD};border-radius:8px;padding:10px 14px;margin-bottom:8px;
                        border-left:4px solid {ACCENT_CYAN}'>
                <strong style='color:{TEXT_WHITE}'>📌 {pm['policy']}</strong>
                <span style='color:{TEXT_LIGHT};font-size:0.85em'> | {pm['status']}</span><br>
                <span style='color:{TEXT_LIGHT};font-size:0.85em'>→ {pm['action']}</span>
            </div>
            """, unsafe_allow_html=True)
    else:
        st.warning("⚠️ 前瞻雷达数据未生成。请先运行: python etl/proactive_engine.py --json")

# ═══════════════════════════════════════════
# TAB 6: 政策扫描
# ═══════════════════════════════════════════
with tab6:
    # Load policy scan data
    policy_scan = None
    if POLICY_SCAN_FILE.exists():
        with open(POLICY_SCAN_FILE, "r", encoding="utf-8") as f:
            policy_scan = json.load(f)

    if policy_scan:
        meta = policy_scan.get("scan_metadata", {})
        st.markdown(f"<p style='color:{TEXT_LIGHT};font-size:0.85rem'>扫描时间: {meta.get('generated_at','-')} | "
                    f"总结果: {meta.get('total_results',0)} | 预警: {meta.get('total_alerts',0)}</p>",
                    unsafe_allow_html=True)

        # ── Domain stats KPI row ──
        domain_stats = policy_scan.get("domain_stats", {})
        if domain_stats:
            cols = st.columns(len(domain_stats))
            for i, (dk, ds) in enumerate(domain_stats.items()):
                cols[i].metric(f"{ds.get('emoji','')} {ds.get('label','')}", f"{ds.get('count',0)} 条")

        # ── Alerts section ──
        alerts = policy_scan.get("alerts", [])
        if alerts:
            st.subheader("🚨 政策预警触发")
            for alert in alerts:
                severity = alert.get("severity", "medium")
                color = WARN_RED if severity == "critical" else (WARN_YELLOW if severity == "high" else ACCENT_CYAN)
                matches_text = "\n".join(f"- {m.get('title','N/A')[:80]}" for m in alert.get("matches",[])[:3])
                st.markdown(f"""
                <div style='background:{BG_CARD};border-left:4px solid {color};
                            border-radius:6px;padding:10px 14px;margin:6px 0'>
                    <strong style='color:{color}'>[{severity.upper()}] {alert.get('rule_name','')}</strong>
                    <span style='color:{TEXT_LIGHT};font-size:0.85em'> — {alert.get('matched_count',0)}条匹配 → {alert.get('action','')}</span>
                </div>
                """, unsafe_allow_html=True)
                with st.expander(f"查看匹配项 ({alert.get('matched_count',0)})" ):
                    for m in alert.get("matches", [])[:5]:
                        url = m.get('url', '#')
                        title = m.get('title', 'N/A')[:100]
                        st.markdown(f"📌 [{title}]({url})")

        # ── Domain results tabs ──
        st.subheader("📋 六域扫描结果")
        domain_results = policy_scan.get("domain_results", {})
        if domain_results:
            domain_names = list(domain_results.keys())
            domain_labels = [f"{domain_results[dk]['emoji']} {domain_results[dk]['label']}" for dk in domain_names]
            selected_domain = st.selectbox("选择域", domain_names, format_func=lambda x: f"{domain_results[x]['emoji']} {domain_results[x]['label']} ({len(domain_results[x]['items'])}条)", key="domain_select")

            if selected_domain and selected_domain in domain_results:
                items = domain_results[selected_domain]["items"]
                if items:
                    for item in items[:20]:
                        title = item.get("title", "N/A")
                        url = item.get("url", "#")
                        date = item.get("date", "")
                        source = item.get("domain_label", "")
                        st.markdown(f"""
                        <div style='background:{BG_CARD};border-left:3px solid {MHM_GREEN};
                                    border-radius:4px;padding:10px 14px;margin:6px 0'>
                            <a href='{url}' target='_blank' style='color:{ACCENT_CYAN};text-decoration:none;font-weight:bold;font-size:1.05em;'>{title}</a>
                            <div style='color:{TEXT_LIGHT};font-size:0.85em;margin-top:6px'>
                                <span style='background:#1a3a45;padding:2px 6px;border-radius:4px;'>📅 {date}</span> 
                                <span style='background:#1a3a45;padding:2px 6px;border-radius:4px;margin-left:8px'>📡 {source}</span>
                            </div>
                        </div>
                        """, unsafe_allow_html=True)
                else:
                    st.info("该域暂无扫描结果")

        # ── Domain result count bar chart ──
        if domain_stats:
            st.subheader("📊 各域情报分布")
            ds_df = pd.DataFrame([{
                "域": f"{v['emoji']} {v['label']}",
                "条数": v["count"],
            } for v in domain_stats.values()])
            ds_df = ds_df.sort_values("条数", ascending=True)
            fig_ds = go.Figure(go.Bar(
                y=ds_df["域"], x=ds_df["条数"],
                orientation="h",
                marker_color=MHM_GREEN,
                text=ds_df["条数"],
                textposition="outside",
                textfont=dict(color=TEXT_WHITE, size=12),
            ))
            fig_ds.update_layout(
                height=max(200, len(ds_df)*40),
                paper_bgcolor=BG_DARK, plot_bgcolor=BG_CARD,
                font=dict(color=TEXT_LIGHT),
                xaxis=dict(title="情报条数", gridcolor="#1a3a45"),
                yaxis=dict(title=""),
                margin=dict(l=160, r=40, t=10, b=30),
            )
            st.plotly_chart(fig_ds, use_container_width=True)

        # ── ⏰ Policy Timeline Calendar ──
        timeline_path = DATA / "policy_timeline.json"
        if timeline_path.exists():
            with open(timeline_path, "r", encoding="utf-8") as f:
                tl_data = json.load(f)

            st.markdown("---")
            st.subheader("⏰ 政策落地行动日历")
            st.caption(f"共 {tl_data['meta']['total_milestones']} 个关键里程碑 | 数据生成于 {tl_data['meta']['generated'][:10]}")

            # Priority filter
            pri_options = ["ALL"] + sorted(set(t["priority"] for t in tl_data["policy_tracks"]))
            pri_map = {"CRITICAL": "🔴", "HIGH": "🟠", "MEDIUM": "🟡", "ALL": "🌐"}
            sel_pri = st.selectbox(
                "按优先级筛选",
                pri_options,
                format_func=lambda x: f"{pri_map.get(x, '')} {x}",
            )

            tracks = tl_data["policy_tracks"]
            if sel_pri != "ALL":
                tracks = [t for t in tracks if t["priority"] == sel_pri]

            # Status color map
            status_colors = {
                "已落地": "#4caf50",
                "已公布": "#4caf50",
                "进行中": "#ff9800",
                "即将执行": "#ff9800",
                "待启动": "#2196f3",
                "待发布": "#2196f3",
                "待施行": "#2196f3",
                "规划中": "#9e9e9e",
                "周期性": "#ab47bc",
            }
            pri_colors = {"CRITICAL": "#ff1744", "HIGH": "#ff9100", "MEDIUM": "#ffc400"}

            from datetime import datetime, date as dt_date
            today = dt_date.today()

            for track in tracks:
                pri_color = pri_colors.get(track["priority"], TEXT_LIGHT)
                st.markdown(f"""
                <div style='background:{BG_CARD};border-radius:8px;padding:14px 18px;margin:12px 0;
                            border-left:4px solid {pri_color}'>
                    <div style='display:flex;justify-content:space-between;align-items:center;margin-bottom:8px'>
                        <span style='color:{TEXT_WHITE};font-size:1.15em;font-weight:bold'>
                            {track['track_icon']} {track['track']}
                        </span>
                        <span style='background:{pri_color};color:#fff;padding:2px 10px;border-radius:12px;
                                     font-size:0.8em;font-weight:bold'>{track['priority']}</span>
                    </div>
                    <div style='color:{TEXT_LIGHT};font-size:0.88em;margin-bottom:10px'>{track['description']}</div>
                </div>
                """, unsafe_allow_html=True)

                for ms in track["milestones"]:
                    ms_date = ms["date"]
                    st_color = status_colors.get(ms["status"], TEXT_LIGHT)
                    try:
                        d = datetime.strptime(ms_date, "%Y-%m-%d").date()
                        days_diff = (d - today).days
                        if days_diff < 0:
                            urgency = f"已过 {abs(days_diff)} 天"
                        elif days_diff == 0:
                            urgency = "⚡ 今天"
                        elif days_diff <= 7:
                            urgency = f"⚡ {days_diff} 天后"
                        elif days_diff <= 30:
                            urgency = f"📅 {days_diff} 天后"
                        else:
                            urgency = f"🗓️ {days_diff} 天后"
                    except Exception:
                        urgency = ""

                    st.markdown(f"""
                    <div style='background:#0d2b33;border-radius:6px;padding:10px 14px;margin:4px 0 4px 24px;
                                border-left:3px solid {st_color}'>
                        <div style='display:flex;justify-content:space-between;align-items:center'>
                            <span style='color:{TEXT_WHITE};font-weight:bold'>{ms['event']}</span>
                            <div>
                                <span style='background:{st_color};color:#fff;padding:1px 8px;border-radius:10px;
                                             font-size:0.75em'>{ms['status']}</span>
                                <span style='color:{ACCENT_CYAN};font-size:0.8em;margin-left:8px'>{urgency}</span>
                            </div>
                        </div>
                        <div style='color:{TEXT_LIGHT};font-size:0.85em;margin-top:6px'>
                            <span style='background:#1a3a45;padding:2px 6px;border-radius:4px'>📅 {ms_date}</span>
                            <span style='background:#1a3a45;padding:2px 6px;border-radius:4px;margin-left:8px'>🌍 {ms['scope']}</span>
                        </div>
                        <div style='color:{MHM_GREEN};font-size:0.88em;margin-top:8px;font-style:italic'>
                            🎯 行动: {ms['action']}
                        </div>
                    </div>
                    """, unsafe_allow_html=True)

            # Timeline Gantt-style chart
            all_ms = []
            for track in tl_data["policy_tracks"]:
                for ms in track["milestones"]:
                    try:
                        d = datetime.strptime(ms["date"], "%Y-%m-%d").date()
                        all_ms.append({
                            "track": track["track"],
                            "event": ms["event"][:30],
                            "date": d,
                            "priority": track["priority"],
                        })
                    except Exception:
                        pass
            if all_ms:
                all_ms.sort(key=lambda x: x["date"])
                future_ms = [m for m in all_ms if m["date"] >= today]
                if future_ms:
                    st.markdown("---")
                    st.subheader("📅 未来里程碑时间轴")
                    tl_df = pd.DataFrame(future_ms)
                    tl_df["date_str"] = tl_df["date"].apply(lambda d: d.strftime("%m-%d"))
                    pri_color_map = {"CRITICAL": "#ff1744", "HIGH": "#ff9100", "MEDIUM": "#ffc400"}
                    tl_df["color"] = tl_df["priority"].map(pri_color_map)

                    fig_tl = go.Figure()
                    for _, row in tl_df.iterrows():
                        fig_tl.add_trace(go.Scatter(
                            x=[row["date"]],
                            y=[row["track"]],
                            mode="markers+text",
                            marker=dict(size=14, color=row["color"], symbol="diamond"),
                            text=row["date_str"],
                            textposition="top center",
                            textfont=dict(color=TEXT_WHITE, size=9),
                            hovertext=f"{row['event']}<br>{row['date']}",
                            showlegend=False,
                        ))

                    fig_tl.add_shape(
                        type="line",
                        x0=str(today), x1=str(today),
                        y0=0, y1=1, yref="paper",
                        line=dict(color=ACCENT_CYAN, dash="dash", width=2),
                    )
                    fig_tl.add_annotation(
                        x=str(today), y=1.05, yref="paper",
                        text="今天", showarrow=False,
                        font=dict(color=ACCENT_CYAN, size=11),
                    )
                    fig_tl.update_layout(
                        height=max(300, len(set(tl_df["track"]))*60),
                        paper_bgcolor=BG_DARK, plot_bgcolor=BG_CARD,
                        font=dict(color=TEXT_LIGHT),
                        xaxis=dict(gridcolor="#1a3a45", title=""),
                        yaxis=dict(title=""),
                        margin=dict(l=180, r=40, t=20, b=40),
                    )
                    st.plotly_chart(fig_tl, use_container_width=True)

        # ── 🔗 Province-Policy Impact Matrix ──
        st.markdown(f"<h3 style='color:{MHM_GREEN};border-bottom:2px solid {MHM_GREEN};padding-bottom:6px'>"
                    f"🔗 省级政策冲击矩阵</h3>", unsafe_allow_html=True)
        st.markdown(f"<p style='color:{TEXT_LIGHT};font-size:0.85rem;margin-bottom:12px'>"
                    f"将政策里程碑落地省份 × 省级健康指数交叉比对，定位风险放大区</p>",
                    unsafe_allow_html=True)

        # Build province -> milestones mapping (active/upcoming only)
        today_str = datetime.now().strftime("%Y-%m-%d")
        prov_ms_map = {}  # province_name -> list of milestone dicts
        scope_alias = {"广东联盟": "广东省"}  # normalize alliance names
        for trk in tl_data.get("policy_tracks", []):
            for ms in trk.get("milestones", []):
                scope_raw = ms.get("scope", "")
                if scope_raw == "全国":
                    continue  # skip nationwide — affects all, not differentiating
                prov_name = scope_alias.get(scope_raw, scope_raw + "省" if not scope_raw.endswith(("省","市","自治区")) else scope_raw)
                if prov_name not in prov_ms_map:
                    prov_ms_map[prov_name] = []
                prov_ms_map[prov_name].append({
                    "track": trk["track"],
                    "track_icon": trk["track_icon"],
                    "event": ms["event"],
                    "date": ms["date"],
                    "status": ms["status"],
                    "priority": trk["priority"],
                    "action": ms.get("action", ""),
                })

        # Cross-reference with province health indices
        hi_lookup = {p["province"]: p["health_index"] for p in data}
        impact_rows = []
        for prov, milestones in prov_ms_map.items():
            hi = hi_lookup.get(prov, None)
            if hi is None:
                continue
            active_count = sum(1 for m in milestones if m["status"] not in ("已落地", "已公布"))
            total_count = len(milestones)
            critical_count = sum(1 for m in milestones if m["priority"] == "CRITICAL")
            # Risk score: lower health + more active milestones + critical = higher risk
            risk_score = round((100 - hi) * 0.5 + active_count * 15 + critical_count * 10, 1)
            impact_rows.append({
                "province": prov, "health_index": hi,
                "total_ms": total_count, "active_ms": active_count,
                "critical_ms": critical_count, "risk_score": risk_score,
                "milestones": milestones,
            })

        impact_rows.sort(key=lambda x: x["risk_score"], reverse=True)

        if impact_rows:
            for row in impact_rows:
                hi = row["health_index"]
                rs = row["risk_score"]
                # Risk zone color
                if rs >= 40:
                    zone_color, zone_label = "#d9534f", "🔴 高风险"
                elif rs >= 25:
                    zone_color, zone_label = "#f0ad4e", "🟡 关注"
                else:
                    zone_color, zone_label = MHM_GREEN, "🟢 可控"

                hi_color = "#d9534f" if hi < 60 else ("#f0ad4e" if hi < 75 else MHM_GREEN)

                upcoming = [m for m in row["milestones"] if m["status"] not in ("已落地", "已公布")]
                upcoming.sort(key=lambda m: m["date"])

                card_html = f"""
                <div style='background:{BG_CARD};border-radius:10px;padding:14px 18px;margin-bottom:10px;
                            border-left:5px solid {zone_color}'>
                    <div style='display:flex;justify-content:space-between;align-items:center;margin-bottom:8px'>
                        <div>
                            <span style='color:{TEXT_WHITE};font-size:1.1em;font-weight:700'>{row["province"]}</span>
                            <span style='background:{zone_color};color:#fff;padding:2px 8px;border-radius:10px;
                                        font-size:0.75em;margin-left:8px'>{zone_label}</span>
                        </div>
                        <div style='text-align:right'>
                            <span style='color:{hi_color};font-size:1.3em;font-weight:700'>{hi}</span>
                            <span style='color:{TEXT_LIGHT};font-size:0.8em'> 健康指数</span>
                        </div>
                    </div>
                    <div style='display:flex;gap:16px;margin-bottom:8px'>
                        <span style='color:{TEXT_LIGHT};font-size:0.85em'>📊 总里程碑 <b style="color:{TEXT_WHITE}">{row["total_ms"]}</b></span>
                        <span style='color:{TEXT_LIGHT};font-size:0.85em'>⚡ 活跃 <b style="color:#f0ad4e">{row["active_ms"]}</b></span>
                        <span style='color:{TEXT_LIGHT};font-size:0.85em'>🔴 CRITICAL <b style="color:#d9534f">{row["critical_ms"]}</b></span>
                        <span style='color:{TEXT_LIGHT};font-size:0.85em'>⚠️ 风险分 <b style="color:{zone_color}">{rs}</b></span>
                    </div>"""

                if upcoming:
                    card_html += f"<div style='border-top:1px solid {BG_DARK};padding-top:8px'>"
                    for um in upcoming[:3]:  # top 3 upcoming
                        d_date = datetime.strptime(um["date"], "%Y-%m-%d").date()
                        d_diff = (d_date - datetime.now().date()).days
                        if d_diff <= 0:
                            urgency = f"<span style='color:#d9534f;font-weight:700'>⚡ 今天</span>"
                        elif d_diff <= 7:
                            urgency = f"<span style='color:#d9534f;font-weight:700'>⚡ {d_diff}天后</span>"
                        elif d_diff <= 30:
                            urgency = f"<span style='color:#f0ad4e'>📅 {d_diff}天后</span>"
                        else:
                            urgency = f"<span style='color:{TEXT_LIGHT}'>🗓️ {d_diff}天后</span>"
                        card_html += f"""
                        <div style='margin-bottom:4px'>
                            <span style='color:{TEXT_WHITE};font-size:0.85em'>{um["track_icon"]} {um["event"]}</span>
                            <span style='color:{TEXT_LIGHT};font-size:0.8em'> | {um["date"]}</span>
                            {urgency}
                        </div>"""
                    card_html += "</div>"

                card_html += "</div>"
                st.markdown(card_html, unsafe_allow_html=True)

            # Risk scatter: health_index vs active milestones
            scatter_df = pd.DataFrame(impact_rows)
            fig_risk = go.Figure()
            for _, r in scatter_df.iterrows():
                rs = r["risk_score"]
                clr = "#d9534f" if rs >= 40 else ("#f0ad4e" if rs >= 25 else MHM_GREEN)
                fig_risk.add_trace(go.Scatter(
                    x=[r["health_index"]], y=[r["active_ms"]],
                    mode="markers+text",
                    marker=dict(size=max(12, r["risk_score"] * 0.6), color=clr, opacity=0.85),
                    text=[r["province"].replace("省","").replace("市","").replace("自治区","")],
                    textposition="top center",
                    textfont=dict(color=TEXT_WHITE, size=10),
                    showlegend=False,
                    hovertemplate=f"<b>{r['province']}</b><br>健康指数: {r['health_index']}<br>"
                                 f"活跃里程碑: {r['active_ms']}<br>风险分: {r['risk_score']}<extra></extra>",
                ))
            fig_risk.add_shape(type="rect", x0=0, x1=65, y0=0, y1=10,
                               fillcolor="rgba(217,83,79,0.08)", line_width=0)
            fig_risk.add_annotation(x=50, y=4, text="⚠ 危险区", showarrow=False,
                                    font=dict(color="#d9534f", size=14), opacity=0.5)
            fig_risk.update_layout(
                height=350,
                xaxis=dict(title="健康指数 →", color=TEXT_LIGHT, gridcolor=BG_CARD, range=[30, 100]),
                yaxis=dict(title="活跃政策里程碑数 ↑", color=TEXT_LIGHT, gridcolor=BG_CARD),
                plot_bgcolor=BG_DARK, paper_bgcolor=BG_DARK,
                font=dict(color=TEXT_WHITE),
                margin=dict(l=60, r=20, t=30, b=50),
            )
            st.plotly_chart(fig_risk, use_container_width=True)
        else:
            st.info("暂无省级政策里程碑联动数据")

    else:
        st.warning("⚠️ 政策扫描数据未生成。")
        st.markdown(f"""
        <div style='background:{BG_CARD};border-radius:8px;padding:16px;margin-top:12px'>
            <h3 style='color:{MHM_GREEN};margin-top:0'>首次使用？</h3>
            <p style='color:{TEXT_LIGHT}'>运行 <code>/policy-scanner</code> 工作流执行首次全量扫描，
            结果将自动加载到此页面。</p>
            <p style='color:{TEXT_LIGHT};font-size:0.85em'>扫描覆盖 6大域 × 3层信源 + 20个WeChat公众号 + 11个竞品</p>
        </div>
        """, unsafe_allow_html=True)

# ═══════════════════════════════════════════
# TAB 7: 竞品矩阵
# ═══════════════════════════════════════════
with tab7:
    # Load competitor data
    competitor_data = None
    if COMPETITOR_FILE.exists():
        with open(COMPETITOR_FILE, "r", encoding="utf-8") as f:
            competitor_data = json.load(f)

    # Also load config for static matrix display
    scan_config = None
    if SCAN_CONFIG_FILE.exists():
        with open(SCAN_CONFIG_FILE, "r", encoding="utf-8") as f:
            scan_config = json.load(f)

    if scan_config:
        competitors = scan_config.get("competitors", {})

        # KPI row
        total_rivals = sum(len(pc["rivals"]) for pc in competitors.values())
        high_threat = sum(1 for pc in competitors.values() for r in pc["rivals"] if r["threat_level"] == "high")
        product_lines = len(competitors)

        kc1, kc2, kc3 = st.columns(3)
        kc1.metric("🎯 监控竞品", f"{total_rivals} 个")
        kc2.metric("🔴 高威胁", f"{high_threat} 个")
        kc3.metric("💊 产品线", f"{product_lines} 条")

        # Product line selector
        product_keys = list(competitors.keys())
        product_labels = {k: v["mhm_product"] for k, v in competitors.items()}
        selected_product = st.selectbox("选择产品线", product_keys,
            format_func=lambda x: f"💊 {product_labels[x]}", key="comp_product")

        if selected_product:
            pc = competitors[selected_product]
            st.markdown(f"**规格**: {', '.join(pc['specs'])}")

            # Rival cards
            for rival in pc["rivals"]:
                threat = rival["threat_level"]
                if threat == "high":
                    tcolor = WARN_RED
                    ticon = "🔴"
                elif threat == "medium":
                    tcolor = WARN_YELLOW
                    ticon = "🟡"
                else:
                    tcolor = MHM_GREEN
                    ticon = "🟢"

                mfrs = ", ".join(rival.get("manufacturers", [])) if rival.get("manufacturers") else "—"
                watches = " • ".join(rival.get("watch", []))

                st.markdown(f"""
                <div style='background:{BG_CARD};border-left:4px solid {tcolor};
                            border-radius:6px;padding:12px 16px;margin:8px 0'>
                    <div style='display:flex;justify-content:space-between;align-items:center'>
                        <strong style='color:{TEXT_WHITE};font-size:1.05em'>{ticon} {rival['name']}</strong>
                        <span style='color:{tcolor};font-size:0.85em;font-weight:bold'>{threat.upper()}</span>
                    </div>
                    <p style='color:{TEXT_LIGHT};font-size:0.85em;margin:4px 0 2px'>厂商: {mfrs} | 规格: {rival.get('specs','—')}</p>
                    <p style='color:{ACCENT_CYAN};font-size:0.8em;margin:2px 0 0'>📎 监控: {watches}</p>
                </div>
                """, unsafe_allow_html=True)

            # Threat distribution chart
            st.subheader("威胁等级分布")
            threat_counts = {"high": 0, "medium": 0, "low": 0}
            for r in pc["rivals"]:
                threat_counts[r["threat_level"]] = threat_counts.get(r["threat_level"], 0) + 1
            fig_threat = go.Figure(go.Pie(
                labels=["🔴 高威胁", "🟡 中等", "🟢 低威胁"],
                values=[threat_counts["high"], threat_counts["medium"], threat_counts["low"]],
                marker_colors=[WARN_RED, WARN_YELLOW, MHM_GREEN],
                textinfo="label+value",
                textfont=dict(size=13),
                hole=0.5,
            ))
            fig_threat.update_layout(
                height=250,
                paper_bgcolor=BG_DARK,
                font=dict(color=TEXT_WHITE),
                margin=dict(l=10, r=10, t=10, b=10),
                showlegend=False,
            )
            st.plotly_chart(fig_threat, use_container_width=True)

        # Intelligence section (if available)
        if competitor_data:
            intel = competitor_data.get("intelligence", {})
            if intel:
                st.subheader("📡 最新竞品情报")
                for pk, items in intel.items():
                    with st.expander(f"💊 {pk} ({len(items)}条)"):
                        for item in items[:5]:
                            st.markdown(f"📌 [{item.get('title','N/A')[:80]}]({item.get('url','#')})")
    else:
        st.warning("⚠️ 竞品配置未加载。请确认 scan_config.json 存在。")

# ── Footer ──
st.markdown(f"<p style='text-align:center; color:{TEXT_LIGHT}; font-size:0.8rem; margin-top:2rem;'>森世海亚策略中心 | 政务准入作战指挥台 v3.0 | {datetime.now().strftime('%Y-%m-%d %H:%M')}</p>", unsafe_allow_html=True)
