"""
政务准入数据初始化：读取Excel表 → province_master.json
数据来源:
  1. 各省准入状况及工作计划_0315.xlsx (Sheet: 省份行动计划)
  2. 森世海亚-更新政策-带金针_20260320.xlsx
  3. 邮件情报硬编码补丁 (内蒙古红标, 河南新增黄标等)
"""
import json, os, re
import pandas as pd
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
DATA_DIR = BASE / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# ── 省份名称标准化 ──
PROVINCE_NORMALIZE = {
    "河北": "河北省", "安徽": "安徽省", "福建": "福建省", "云南": "云南省",
    "青海": "青海省", "四川": "四川省", "海南": "海南省", "湖北": "湖北省",
    "湖南": "湖南省", "广东": "广东省", "甘肃": "甘肃省", "吉林": "吉林省",
    "浙江": "浙江省", "山东": "山东省", "陕西": "陕西省", "江苏": "江苏省",
    "江西": "江西省", "辽宁": "辽宁省", "河南": "河南省", "山西": "山西省",
    "贵州": "贵州省", "黑龙江": "黑龙江省",
    "上海": "上海市", "北京": "北京市", "天津": "天津市", "重庆": "重庆市",
    "内蒙古": "内蒙古自治区", "广西": "广西壮族自治区", "宁夏": "宁夏回族自治区",
    "新疆": "新疆维吾尔自治区", "西藏": "西藏自治区",
}
def normalize(name):
    if not name or not isinstance(name, str):
        return name
    name = name.strip()
    for short, full in PROVINCE_NORMALIZE.items():
        if short in name:
            return full
    return name

# ── 1. 读取 准入状况及工作计划 (Sheet: 省份行动计划) ──
def load_action_plan():
    fp = BASE / "各省准入状况及工作计划_0315.xlsx"
    df = pd.read_excel(fp, sheet_name="省份行动计划", header=0)
    # Also read Sheet1 for health_index and biz_share
    df1 = pd.read_excel(fp, sheet_name="各省招标平台状态一览图", header=0)
    df1.columns = [str(c).strip() for c in df1.columns]
    # Build province→(biz_share, health_index) map from Sheet1
    s1_map = {}
    prov_col = "省份(PK)"
    if prov_col in df1.columns:
        for _, r in df1.iterrows():
            pname = normalize(str(r.get(prov_col, "")))
            if pname and isinstance(pname, str) and len(pname) > 1:
                s1_map[pname] = {
                    "biz_share": r.get("2025年业务占比", 0),
                    "health_index": r.get("准入健康指数", 0),
                }
    result = {}
    for _, row in df.iterrows():
        pname = normalize(str(row.get("省份", "")))
        if not pname or len(pname) < 2:
            continue
        s1 = s1_map.get(pname, {})
        issues_raw = str(row.get("核心问题", ""))
        issues = [x.strip() for x in re.split(r'[|｜\n]', issues_raw) if x.strip() and x.strip() != "nan"]
        result[pname] = {
            "quadrant": str(row.get("战略象限", "")),
            "priority": str(row.get("优先级", "")),
            "biz_share": float(s1.get("biz_share", 0) or 0),
            "health_index": float(s1.get("health_index", 0) or 0),
            "core_issues": issues,
            "key_contacts": str(row.get("关键人物(待填)", "") or ""),
            "action_plan": str(row.get("行动计划", "") or ""),
            "time_nodes": str(row.get("时间节点", "") or ""),
            "status": str(row.get("状态", "") or "—"),
        }
    return result

# ── 2. 读取 更新政策-带金针 ──
def load_policy_update():
    fp = BASE / "森世海亚-更新政策-带金针_20260320.xlsx"
    df = pd.read_excel(fp, header=0)
    df.columns = [str(c).strip() for c in df.columns]
    result = {}
    for _, row in df.iterrows():
        pname = normalize(str(row.get("省份", "")))
        if not pname or len(pname) < 2:
            continue
        def safe_float(v):
            try: return float(v) if pd.notna(v) else 0
            except: return 0
        def safe_str(v):
            return str(v).strip() if pd.notna(v) and str(v).strip() != "nan" else ""

        t20_listed = safe_str(row.get("T20是否挂网", "")) == "已挂网"
        t20_switch = safe_str(row.get("T20转换预计达成时间", ""))
        t20_done = "已完成" in t20_switch
        t20_vol = safe_float(row.get("T20月均销量（盒）", 0))

        t40_listed = safe_str(row.get("T40是否挂网", "")) == "已挂网"
        t40_switch = safe_str(row.get("T40新增与转换预计达成时间", ""))
        t40_done = "已完成" in t40_switch
        t40_vol = safe_float(row.get("T40月均销量（盒）", 0))

        t60_listed = safe_str(row.get("T60是否挂网", "")) in ["已挂网"]
        t60_switch = safe_str(row.get("T60挂网预计达成时间", ""))

        jd_listed = safe_str(row.get("金滴是否挂网", "")) == "已挂网"
        jd_switch = safe_str(row.get("转换预计周期", ""))
        jd_vol = safe_float(row.get("金滴月均销售（盒）", 0))

        wlt_listed = safe_str(row.get("威利坦是否挂网", "")) == "已挂网"
        # 威利坦转换周期 is the second "转换预计周期" column – use index-based access
        cols = list(df.columns)
        wlt_switch_idx = [i for i, c in enumerate(cols) if "转换预计周期" in c]
        wlt_switch = safe_str(row.iloc[wlt_switch_idx[1]]) if len(wlt_switch_idx) > 1 else ""
        wlt_vol = safe_float(row.get("威利坦月均销售（盒）", 0))

        jz_sellable_raw = safe_str(row.get("金针是否可售", ""))
        jz_sellable = jz_sellable_raw == "已挂网"
        jz_color_raw = safe_str(row.get("金针是否有颜色标识", ""))
        jz_color = None
        if "是" in jz_color_raw:
            jz_color = "yellow"  # default yellow, overrides applied later

        gd_alliance = safe_str(row.get("广东联盟执行情况", ""))
        region = safe_str(row.get("大区", ""))
        suggestion = safe_str(row.get("行动建议", ""))

        result[pname] = {
            "region": region,
            "products": {
                "T20": {"listed": t20_listed, "switch_status": t20_switch, "done": t20_done, "monthly_vol": round(t20_vol)},
                "T40": {"listed": t40_listed, "switch_status": t40_switch, "done": t40_done, "monthly_vol": round(t40_vol)},
                "T60": {"listed": t60_listed, "switch_status": t60_switch, "done": False, "monthly_vol": 0},
                "金滴": {"listed": jd_listed, "switch_status": jd_switch, "done": "已完成" in jd_switch, "monthly_vol": round(jd_vol)},
                "威利坦": {"listed": wlt_listed, "switch_status": wlt_switch, "done": "已完成" in wlt_switch, "monthly_vol": round(wlt_vol)},
            },
            "金针": {"can_sell": jz_sellable, "color_label": jz_color, "gd_alliance": gd_alliance, "price_status": jz_sellable_raw},
            "stocking_advice": suggestion,
        }
    return result

# ── 3. 邮件情报补丁 (hardcoded from email scan 2026-03-20 19:30) ──
# 数据来源:
#   - Ada Cong 进口商切换周报 2026-03-20 (T20→24区, 金滴→21区, 威利坦→23区)
#   - Simon Yu 直接输入 2026-03-20 19:31 (江苏金针24.1元中标 + 40T/60T挂网)
#   - 此前周报: 内蒙古红标, 河南黄标, 宁夏价格风险等
EMAIL_PATCHES = {
    "内蒙古自治区": {
        "金针_color_override": "red",  # 升级为红标
        "alert": {"type": "color_upgrade", "desc": "金针从黄标升级为红标", "date": "2026-03-20"},
    },
    "河南省": {
        "金针_color_override": "yellow",  # 新增黄标 3/18
        "alert": {"type": "new_color_label", "desc": "金针新增黄标(3/18广药确认)", "date": "2026-03-18"},
    },
    "宁夏回族自治区": {
        "alert": {"type": "price_risk", "desc": "T20/威利坦挂网价疑似高于药店零售价，需3/31前自查调整", "date": "2026-03-19"},
        "deadline": {"date": "2026-03-31", "desc": "宁夏挂网价格风险自查截止", "urgency": "critical"},
    },
    "山东省": {
        "alert": {"type": "inactive_zone_resolved", "desc": "金滴不活跃区已解决(3/20有订单+调入活跃区)", "date": "2026-03-20"},
    },
    "天津市": {
        "alert": {"type": "info_confirm", "desc": "威利坦/路优泰挂网标准化信息确认(3/19-3/23)", "date": "2026-03-19"},
        "deadline": {"date": "2026-03-23", "desc": "天津挂网标准化信息确认截止", "urgency": "high"},
    },
    # ── 2026-03-20 19:31 新增 ──
    "江苏省": {
        "金针_bid_price": 24.1,  # 集采中标价
        "product_overrides": {
            "T40": {"listed": True, "done": True, "switch_status": "已完成(3/20挂网成功)"},
            "T60": {"listed": True, "done": False, "switch_status": "已挂网(3/20)"},
        },
        "alert": {"type": "jinzhen_bid", "desc": "金针集采中标24.1元，40T/60T挂网成功", "date": "2026-03-20"},
    },
    "重庆市": {
        # Ada邮件3/20确认：T20/金滴/威利坦切换完成
        "product_overrides": {
            "T20": {"done": True, "switch_status": "已完成(3/20确认)"},
            "金滴": {"done": True, "switch_status": "已完成(3/20确认)"},
            "威利坦": {"done": True, "switch_status": "已完成(3/20确认)"},
        },
        "alert": {"type": "switch_complete", "desc": "T20/金滴/威利坦切换完成(Ada 3/20确认)", "date": "2026-03-20"},
    },
}

# Known deadlines from action plan data
GLOBAL_DEADLINES = [
    {"province": "上海市", "date": "2026-03-27", "desc": "20T/40T平台切换+海牙认证递交", "urgency": "critical"},
    {"province": "山西省", "date": "2026-03-31", "desc": "40T平台切换", "urgency": "high"},
    {"province": "吉林省", "date": "2026-03-27", "desc": "40T平台切换", "urgency": "high"},
    {"province": "宁夏回族自治区", "date": "2026-03-31", "desc": "40T挂网+GT20总代变更", "urgency": "high"},
    {"province": "福建省", "date": "2026-04-30", "desc": "60片挂网", "urgency": "medium"},
]

# ── 4. Merge all sources ──
def merge_all():
    action = load_action_plan()
    policy = load_policy_update()
    all_provinces = sorted(set(list(action.keys()) + list(policy.keys())))
    master = []
    for pname in all_provinces:
        a = action.get(pname, {})
        p = policy.get(pname, {})
        patch = EMAIL_PATCHES.get(pname, {})

        products = p.get("products", {})
        jinzhen = p.get("金针", {})
        # Apply email patches for color
        if patch.get("金针_color_override"):
            jinzhen["color_label"] = patch["金针_color_override"]
        # Apply email patches for bid price
        if patch.get("金针_bid_price"):
            jinzhen["bid_price"] = patch["金针_bid_price"]
        # Apply product overrides from email
        if patch.get("product_overrides"):
            for pk, pv in patch["product_overrides"].items():
                if pk in products:
                    products[pk].update(pv)
                else:
                    products[pk] = pv

        alerts = []
        deadlines = []
        if patch.get("alert"):
            alerts.append(patch["alert"])
        if patch.get("deadline"):
            deadlines.append(patch["deadline"])
        # Add global deadlines
        for d in GLOBAL_DEADLINES:
            if d["province"] == pname:
                deadlines.append({"date": d["date"], "desc": d["desc"], "urgency": d["urgency"]})

        rec = {
            "province": pname,
            "region": p.get("region", ""),
            "quadrant": a.get("quadrant", ""),
            "priority": a.get("priority", ""),
            "biz_share": a.get("biz_share", 0),
            "health_index": a.get("health_index", 0),
            "products": products,
            "金针": jinzhen,
            "core_issues": a.get("core_issues", []),
            "key_contacts": a.get("key_contacts", ""),
            "action_plan": a.get("action_plan", ""),
            "time_nodes": a.get("time_nodes", ""),
            "status": a.get("status", "—"),
            "stocking_advice": p.get("stocking_advice", ""),
            "alerts": alerts,
            "deadlines": deadlines,
            "last_updated": "2026-03-20T19:31",
        }
        master.append(rec)
    return master

def main():
    from datetime import datetime
    master = merge_all()
    out = DATA_DIR / "province_master.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(master, f, ensure_ascii=False, indent=2)
    print(f"✅ Wrote {len(master)} provinces to {out}")
    # Also save a snapshot with timestamp
    snap_dir = DATA_DIR / "snapshots"
    snap_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M")
    snap = snap_dir / f"snapshot_{ts}.json"
    with open(snap, "w", encoding="utf-8") as f:
        json.dump(master, f, ensure_ascii=False, indent=2)
    print(f"✅ Snapshot saved to {snap}")

if __name__ == "__main__":
    main()
