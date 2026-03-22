"""
前瞻性管理引擎 — 从"事后追踪"到"事前布局"
整合5大前置模块：
  ① 下周作战命令（next_week_radar）
  ② 广东联盟到期预警（alliance_expiry）
  ③ T60解锁条件追踪（t60_readiness）
  ④ 切换前置材料检查（pre_switch_checklist）
  ⑤ 挂网管理办法里程碑（policy_milestones）

用法:
  python proactive_engine.py          # 控制台输出
  python proactive_engine.py --html   # 生成HTML报告
  python proactive_engine.py --json   # 输出JSON供Dashboard使用
"""
import json, re
from pathlib import Path
from datetime import datetime, timedelta

BASE = Path(__file__).resolve().parent.parent
DATA = BASE / "data"
MASTER_FILE = DATA / "province_master.json"

# ── Theme ──
MHM_GREEN = "#00a651"
WARN_YELLOW = "#f0ad4e"
WARN_RED = "#d9534f"
ACCENT_CYAN = "#2aa198"
BG_DARK = "#002b36"
BG_CARD = "#073642"
TEXT_WHITE = "#fdf6e3"
TEXT_LIGHT = "#93a1a1"


def load_master():
    with open(MASTER_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


# ═══════════════════════════════════════════════════════
# ① 下周作战命令
# ═══════════════════════════════════════════════════════
def next_week_radar(master, today=None):
    """
    扫描所有省份的switch_status、deadlines、action_plan中的时间窗口
    识别未来7天内将要发生的事件，并生成前置准备清单
    """
    if today is None:
        today = datetime.now()
    next_fri = today + timedelta(days=7)

    # Standard pre-switch materials
    STANDARD_PREP = {
        "T20": ["总代变更确认函", "进口药品注册证", "GMP证书", "授权委托书"],
        "T40": ["总代变更确认函", "进口药品注册证", "GMP证书", "授权委托书", "挂网申请材料"],
        "T60": ["≥3省挂网截图", "进口药品注册证", "GMP证书", "首次挂网申请材料"],
        "金滴": ["总代变更确认函", "进口药品注册证", "授权委托书"],
        "威利坦": ["总代变更确认函", "进口药品注册证", "授权委托书"],
    }

    # Special requirements per province
    SPECIAL_REQS = {
        "上海市": ["海牙认证文件", "领馆认证文件", "翻译公证材料"],
        "浙江省": ["≥5家三级公立医疗机构议价支持", "药物相互作用风险管控方案"],
    }

    actions = []
    for p in master:
        prov = p["province"]
        products = p.get("products", {})

        # Check each product's switch_status for date patterns
        for pk, pv in products.items():
            if pv.get("done"):
                continue
            status = pv.get("switch_status", "")
            # Look for date patterns: "3/23～3/27", "3/23~3/31", "4/27~4/30"
            date_match = re.search(r'(\d{1,2})/(\d{1,2})[～~\-至](\d{1,2})/(\d{1,2})', status)
            if date_match:
                m1, d1, m2, d2 = [int(x) for x in date_match.groups()]
                try:
                    start = datetime(today.year, m1, d1)
                    end = datetime(today.year, m2, d2)
                except ValueError:
                    continue

                # Is this within next 7 days?
                if start <= next_fri and end >= today:
                    days_until = (start - today).days
                    prep_list = STANDARD_PREP.get(pk, ["标准材料"])
                    if prov in SPECIAL_REQS:
                        prep_list = prep_list + SPECIAL_REQS[prov]

                    actions.append({
                        "province": prov,
                        "product": pk,
                        "event": f"{pk}平台切换",
                        "window": f"{m1}/{d1}-{m2}/{d2}",
                        "days_until": max(days_until, 0),
                        "prep_checklist": prep_list,
                        "monthly_vol": pv.get("monthly_vol", 0),
                        "priority": p.get("priority", ""),
                    })

        # Check deadlines
        for dl in p.get("deadlines", []):
            try:
                dt = datetime.strptime(dl["date"], "%Y-%m-%d")
                days_until = (dt - today).days
            except:
                continue
            if 0 <= days_until <= 7:
                actions.append({
                    "province": prov,
                    "product": "—",
                    "event": dl["desc"],
                    "window": dl["date"],
                    "days_until": days_until,
                    "prep_checklist": ["确认进展", "准备应急方案"],
                    "monthly_vol": 0,
                    "priority": dl.get("urgency", "medium"),
                })

    actions.sort(key=lambda x: x["days_until"])
    return actions


# ═══════════════════════════════════════════════════════
# ② 广东联盟到期预警
# ═══════════════════════════════════════════════════════
def alliance_expiry_tracker(master, today=None):
    """
    解析gd_alliance字段中的执行期日期，计算到期倒计时
    """
    if today is None:
        today = datetime.now()

    records = []
    for p in master:
        prov = p["province"]
        gd = p.get("金针", {}).get("gd_alliance", "")
        if not gd or gd in ["×", "√", "参与未报量", ""]:
            continue

        # Parse "2026年3月20日至2027年3月19日" format
        match = re.search(r'(\d{4})年(\d{1,2})月(\d{1,2})日至(\d{4})年(\d{1,2})月(\d{1,2})日', gd)
        if match:
            y1, m1, d1, y2, m2, d2 = [int(x) for x in match.groups()]
            try:
                start = datetime(y1, m1, d1)
                expiry = datetime(y2, m2, d2)
            except ValueError:
                continue

            days_to_expiry = (expiry - today).days
            t90 = expiry - timedelta(days=90)
            t30 = expiry - timedelta(days=30)
            t7 = expiry - timedelta(days=7)

            if days_to_expiry <= 0:
                tier = "🚨 已过期"
                color = WARN_RED
            elif today >= t7:
                tier = "🔴 7天内到期"
                color = WARN_RED
            elif today >= t30:
                tier = "🟠 30天内"
                color = WARN_YELLOW
            elif today >= t90:
                tier = "🟡 启动续签"
                color = WARN_YELLOW
            else:
                tier = "🟢 正常"
                color = MHM_GREEN

            records.append({
                "province": prov,
                "alliance_period": gd,
                "expiry_date": expiry.strftime("%Y-%m-%d"),
                "days_left": days_to_expiry,
                "tier": tier,
                "color": color,
                "t90_date": t90.strftime("%Y-%m-%d"),
                "action_needed": "启动续签策略" if today >= t90 else ("准备备选方案" if today >= t30 else ""),
            })

    records.sort(key=lambda x: x["days_left"])
    return records


# ═══════════════════════════════════════════════════════
# ③ T60解锁条件追踪
# ═══════════════════════════════════════════════════════
def t60_readiness_tracker(master):
    """
    追踪T60挂网进度：已完成省份、解锁条件、下一批目标
    """
    t60_done = []       # 已挂网/已完成
    t60_pending = []    # 有时间窗口
    t60_blocked = []    # 需前提条件

    for p in master:
        prov = p["province"]
        t60 = p.get("products", {}).get("T60", {})
        if not t60:
            continue

        listed = t60.get("listed", False)
        done = t60.get("done", False)
        status = t60.get("switch_status", "")
        biz_share = p.get("biz_share", 0)

        if listed or done:
            t60_done.append({"province": prov, "status": status, "biz_share": biz_share})
        elif re.search(r'\d{1,2}/\d{1,2}', status):
            # Has a date - pending with timeline
            t60_pending.append({"province": prov, "status": status, "biz_share": biz_share})
        else:
            t60_blocked.append({"province": prov, "blocker": status, "biz_share": biz_share})

    # Sort pending by biz_share (high value first)
    t60_pending.sort(key=lambda x: -x["biz_share"])
    t60_blocked.sort(key=lambda x: -x["biz_share"])

    return {
        "done_count": len(t60_done),
        "done_provinces": t60_done,
        "pending_count": len(t60_pending),
        "pending_provinces": t60_pending,
        "blocked_count": len(t60_blocked),
        "blocked_provinces": t60_blocked,
        "unlock_threshold": 3,  # 3省挂网截图即可推广
        "is_unlocked": len(t60_done) >= 3,
    }


# ═══════════════════════════════════════════════════════
# ④ 切换前置材料检查
# ═══════════════════════════════════════════════════════
def pre_switch_checklist(master, today=None):
    """
    对所有即将切换的省份生成材料准备检查清单
    """
    if today is None:
        today = datetime.now()

    checklists = []
    for p in master:
        prov = p["province"]
        products = p.get("products", {})
        pending_products = []

        for pk, pv in products.items():
            if pv.get("done"):
                continue
            status = pv.get("switch_status", "")
            if re.search(r'\d{1,2}/\d{1,2}', status) or "协调中" in status:
                pending_products.append({
                    "product": pk,
                    "status": status,
                    "has_timeline": bool(re.search(r'\d{1,2}/\d{1,2}', status)),
                })

        if pending_products:
            has_urgent = any(pp["has_timeline"] for pp in pending_products)
            checklists.append({
                "province": prov,
                "priority": p.get("priority", ""),
                "products": pending_products,
                "urgent": has_urgent,
                "core_issues": p.get("core_issues", []),
            })

    # Urgent first
    checklists.sort(key=lambda x: (not x["urgent"], x["priority"]))
    return checklists


# ═══════════════════════════════════════════════════════
# ⑤ 政策里程碑（框架，具体由邮件扫描填充）
# ═══════════════════════════════════════════════════════
POLICY_MILESTONES = [
    {
        "policy": "国家药品挂网管理办法",
        "status": "征求意见稿阶段",
        "impact": "可能统一各省挂网规则，影响T20/T40/T60跨省挂网策略",
        "action": "持续关注正式稿发布时间，提前准备应对方案",
        "monitor_keywords": ["挂网管理办法", "药品挂网", "国家医保局"],
    },
    {
        "policy": "广东联盟第十批集采",
        "status": "执行中",
        "impact": "金针中标价格影响各省联动定价",
        "action": "监控各省落地执行时间表",
        "monitor_keywords": ["广东联盟", "集采落地", "联盟采购"],
    },
    {
        "policy": "医保目录动态调整",
        "status": "2026年度窗口预计Q3开放",
        "impact": "路优泰等新品种医保准入机会",
        "action": "Q2启动药经材料准备",
        "monitor_keywords": ["医保目录", "动态调整", "目录内"],
    },
]


# ═══════════════════════════════════════════════════════
# 主引擎：整合输出
# ═══════════════════════════════════════════════════════
def run_all(today_str=None):
    """运行所有前瞻引擎，返回统一结构"""
    if today_str:
        today = datetime.strptime(today_str, "%Y-%m-%d")
    else:
        today = datetime.now()

    master = load_master()

    return {
        "generated_at": today.strftime("%Y-%m-%d %H:%M"),
        "next_week_actions": next_week_radar(master, today),
        "t60_status": t60_readiness_tracker(master),
        "switch_checklists": pre_switch_checklist(master, today),
        "policy_milestones": POLICY_MILESTONES,
    }


def print_console(result):
    """控制台版输出"""
    lines = ["\n" + "=" * 60]
    lines.append("📡 前瞻雷达 | 政务准入事前管理系统")
    lines.append(f"生成时间: {result['generated_at']}")
    lines.append("=" * 60)

    # ① Next week
    actions = result["next_week_actions"]
    lines.append(f"\n📋 下周作战命令 ({len(actions)}项)")
    lines.append("-" * 40)
    for a in actions:
        urgency = "🔴" if a["days_until"] <= 1 else ("🟠" if a["days_until"] <= 3 else "🟡")
        lines.append(f"  {urgency} {a['province']} | {a['event']} | {a['window']} ({a['days_until']}天)")
        if a["prep_checklist"]:
            for prep in a["prep_checklist"][:3]:
                lines.append(f"     📎 {prep}")

    # ② Alliance
    alliances = result["alliance_expiry"]
    if alliances:
        lines.append(f"\n⏰ 广东联盟到期预警 ({len(alliances)}个协议)")
        lines.append("-" * 40)
        for a in alliances:
            lines.append(f"  {a['tier']} {a['province']} | 到期: {a['expiry_date']} ({a['days_left']}天)")
            if a["action_needed"]:
                lines.append(f"     ⚡ {a['action_needed']}")

    # ③ T60
    t60 = result["t60_status"]
    lines.append(f"\n🔓 T60解锁进度")
    lines.append("-" * 40)
    status_icon = "✅ 已解锁" if t60["is_unlocked"] else f"⏳ {t60['done_count']}/{t60['unlock_threshold']}"
    lines.append(f"  状态: {status_icon} ({t60['done_count']}省已挂网)")
    if t60["done_provinces"]:
        done_names = ", ".join(d["province"] for d in t60["done_provinces"])
        lines.append(f"  已完成: {done_names}")
    if t60["pending_provinces"]:
        lines.append(f"  待推进: {len(t60['pending_provinces'])}省有时间窗口")
        for pp in t60["pending_provinces"][:5]:
            lines.append(f"    → {pp['province']}: {pp['status']}")

    # ④ Checklists summary
    checklists = result["switch_checklists"]
    urgent = [c for c in checklists if c["urgent"]]
    lines.append(f"\n📑 切换材料准备 ({len(urgent)}省有明确时间窗口)")
    lines.append("-" * 40)
    for c in urgent[:5]:
        prods = ", ".join(pp["product"] for pp in c["products"] if pp["has_timeline"])
        lines.append(f"  📌 {c['province']} | {prods}")

    # ⑤ Policy
    lines.append(f"\n📅 政策里程碑 ({len(result['policy_milestones'])}项)")
    lines.append("-" * 40)
    for pm in result["policy_milestones"]:
        lines.append(f"  📌 {pm['policy']}: {pm['status']}")
        lines.append(f"     → {pm['action']}")

    lines.append("\n" + "=" * 60)
    return "\n".join(lines)


def generate_html(result):
    """生成HTML前瞻雷达报告"""
    actions = result["next_week_actions"]
    alliances = result["alliance_expiry"]
    t60 = result["t60_status"]

    # Next week actions table
    action_rows = ""
    for a in actions:
        color = WARN_RED if a["days_until"] <= 1 else (WARN_YELLOW if a["days_until"] <= 3 else MHM_GREEN)
        days_txt = "今天" if a["days_until"] == 0 else f"{a['days_until']}天"
        prep_html = "<br>".join(f"📎 {p}" for p in a["prep_checklist"][:3])
        action_rows += f'''<tr>
            <td style="padding:6px 8px;color:{color};font-weight:bold">{days_txt}</td>
            <td style="padding:6px 8px">{a['province']}</td>
            <td style="padding:6px 8px">{a['event']}</td>
            <td style="padding:6px 8px;font-size:11px;color:{TEXT_LIGHT}">{prep_html}</td>
        </tr>'''

    # Alliance rows
    alliance_rows = ""
    for a in alliances:
        alliance_rows += f'''<tr>
            <td style="padding:6px 8px">{a['province']}</td>
            <td style="padding:6px 8px">{a['expiry_date']}</td>
            <td style="padding:6px 8px;color:{a['color']}">{a['days_left']}天</td>
            <td style="padding:6px 8px">{a['tier']}</td>
        </tr>'''

    # T60 progress bar
    t60_pct = min(100, int(t60["done_count"] / max(t60["unlock_threshold"], 1) * 100))
    t60_color = MHM_GREEN if t60["is_unlocked"] else WARN_YELLOW
    t60_text = "✅ 已解锁！可全国推广" if t60["is_unlocked"] else f"⏳ {t60['done_count']}/{t60['unlock_threshold']} 省"
    done_names = ", ".join(d["province"] for d in t60["done_provinces"])

    html = f'''<div style="font-family:'Segoe UI',Arial,sans-serif;max-width:700px;margin:0 auto;color:{TEXT_WHITE}">
    <h2 style="color:{MHM_GREEN};margin:0 0 15px">📡 前瞻雷达 — 下周作战命令</h2>

    <!-- Next Week Actions -->
    <h3 style="color:{ACCENT_CYAN};margin:15px 0 5px">📋 下周行动预测 ({len(actions)}项)</h3>
    <table style="width:100%;border-collapse:collapse;background:{BG_CARD};border-radius:8px">
        <thead><tr style="border-bottom:2px solid {TEXT_LIGHT}">
            <th style="padding:8px;text-align:left;font-size:12px">倒计时</th>
            <th style="padding:8px;text-align:left;font-size:12px">省份</th>
            <th style="padding:8px;text-align:left;font-size:12px">事件</th>
            <th style="padding:8px;text-align:left;font-size:12px">前置准备</th>
        </tr></thead>
        <tbody>{action_rows}</tbody>
    </table>

    <!-- T60 Progress -->
    <h3 style="color:{ACCENT_CYAN};margin:15px 0 5px">🔓 T60全国推广解锁进度</h3>
    <div style="background:{BG_CARD};border-radius:8px;padding:12px">
        <div style="background:#1a1a2e;border-radius:6px;height:24px;overflow:hidden">
            <div style="background:{t60_color};width:{t60_pct}%;height:100%;border-radius:6px;
                text-align:center;line-height:24px;font-size:12px;font-weight:bold">{t60_text}</div>
        </div>
        <p style="color:{TEXT_LIGHT};font-size:11px;margin:5px 0 0">已挂网: {done_names}</p>
    </div>

    <!-- Alliance Expiry -->
    <h3 style="color:{ACCENT_CYAN};margin:15px 0 5px">⏰ 广东联盟到期预警</h3>
    <table style="width:100%;border-collapse:collapse;background:{BG_CARD};border-radius:8px">
        <thead><tr style="border-bottom:2px solid {TEXT_LIGHT}">
            <th style="padding:8px;text-align:left;font-size:12px">省份</th>
            <th style="padding:8px;text-align:left;font-size:12px">到期日</th>
            <th style="padding:8px;text-align:left;font-size:12px">剩余</th>
            <th style="padding:8px;text-align:left;font-size:12px">状态</th>
        </tr></thead>
        <tbody>{alliance_rows}</tbody>
    </table>
</div>'''
    return html


def main():
    import sys
    result = run_all()

    if "--json" in sys.argv:
        out = DATA / "proactive_radar.json"
        with open(out, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2, default=str)
        print(f"✅ JSON输出: {out}")
    elif "--html" in sys.argv:
        html = generate_html(result)
        out = DATA / "reports" / f"proactive_radar_{datetime.now().strftime('%Y%m%d')}.html"
        out.parent.mkdir(exist_ok=True)
        with open(out, "w", encoding="utf-8") as f:
            f.write(f'''<!DOCTYPE html><html><head><meta charset="utf-8"></head>
<body style="background:{BG_DARK};padding:20px">{html}</body></html>''')
        print(f"✅ HTML报告: {out}")
    else:
        print(print_console(result))


if __name__ == "__main__":
    main()
