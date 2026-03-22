"""
Ada邮件自动解析模块
自动识别Ada Cong的"进口商切换项目启动相关进展更新"邮件
→ 解析每个产品的完成省份列表
→ 与现有数据对比
→ 自动更新 province_master.json
用法: 在 /gov-dashboard 工作流中由Agent通过MCP调用
      或独立运行: python parse_ada_email.py --simulate (用最新邮件模拟)
"""
import json, re
from pathlib import Path
from datetime import datetime

BASE = Path(__file__).resolve().parent.parent
DATA = BASE / "data"
MASTER_FILE = DATA / "province_master.json"

# ── 省份名称标准化 (与 ingest_excel.py 保持一致) ──
PROVINCE_MAP = {
    "河北": "河北省", "安徽": "安徽省", "福建": "福建省", "云南": "云南省",
    "青海": "青海省", "四川": "四川省", "海南": "海南省", "湖北": "湖北省",
    "湖南": "湖南省", "广东": "广东省", "甘肃": "甘肃省", "吉林": "吉林省",
    "浙江": "浙江省", "山东": "山东省", "陕西": "陕西省", "江苏": "江苏省",
    "江西": "江西省", "辽宁": "辽宁省", "河南": "河南省", "山西": "山西省",
    "贵州": "贵州省", "黑龙江": "黑龙江省",
    "上海": "上海市", "北京": "北京市", "天津": "天津市", "重庆": "重庆市",
    "内蒙古": "内蒙古自治区", "广西": "广西壮族自治区", "宁夏": "宁夏回族自治区",
    "新疆": "新疆维吾尔自治区", "西藏": "西藏自治区",
    "新疆自治区": "新疆维吾尔自治区", "新疆兵团": "新疆生产建设兵团",
    "兵团": "新疆生产建设兵团",
}

def normalize_province(name):
    name = name.strip().rstrip("；;、，,。")
    for short, full in PROVINCE_MAP.items():
        if short in name:
            return full
    return name

# ── 产品关键词到标准名称的映射 ──
PRODUCT_PATTERNS = {
    "T20": r"T20完成[（(](\d+)个区域[）)]：(.+?)(?:；|$|\n)",
    "T40": r"T40完成[（(](\d+)个区域[）)]：(.+?)(?:；|$|\n)",
    "T60": r"T60完成[（(](\d+)个区域[）)]：(.+?)(?:；|$|\n)",
    "金滴": r"金滴完成[（(](\d+)个区域[）)]：(.+?)(?:；|$|\n)",
    "威利坦": r"威利坦完成[（(](\d+)个区域[）)]：(.+?)(?:；|$|\n)",
}

def parse_ada_email_body(body_text):
    """
    解析Ada邮件正文，提取每个产品的完成省份列表
    Returns: {product: [province_list], ...}
    """
    results = {}
    for product, pattern in PRODUCT_PATTERNS.items():
        match = re.search(pattern, body_text, re.DOTALL)
        if match:
            count = int(match.group(1))
            provinces_raw = match.group(2)
            # Split by 、 or （...）annotated items
            # Remove annotations like (新增挂网) (变更完成)
            cleaned = re.sub(r'[（(][^）)]*[）)]', '', provinces_raw)
            provinces = [normalize_province(p.strip()) for p in re.split(r'[、，,]', cleaned)
                        if p.strip() and len(p.strip()) >= 2]
            results[product] = {
                "count": count,
                "provinces": provinces,
            }
    return results

def compare_with_master(parsed, master_data):
    """
    对比Ada邮件解析结果与现有master数据
    Returns: list of change dicts
    """
    # Build province→products map from master
    current_status = {}
    for p in master_data:
        prov = p["province"]
        current_status[prov] = {}
        for pk, pv in p.get("products", {}).items():
            current_status[prov][pk] = pv.get("done", False)

    changes = []
    for product, info in parsed.items():
        for prov in info["provinces"]:
            was_done = current_status.get(prov, {}).get(product, False)
            if not was_done:
                changes.append({
                    "province": prov,
                    "product": product,
                    "change": "新增完成",
                    "source": "Ada邮件",
                })
    return changes

def apply_changes(master_data, parsed, email_date):
    """
    将Ada邮件解析结果应用到master数据
    """
    prov_map = {p["province"]: p for p in master_data}
    updated_count = 0

    for product, info in parsed.items():
        for prov in info["provinces"]:
            if prov in prov_map:
                products = prov_map[prov].get("products", {})
                if product in products:
                    if not products[product].get("done"):
                        products[product]["done"] = True
                        products[product]["switch_status"] = f"已完成({email_date}Ada邮件确认)"
                        updated_count += 1
                else:
                    # Product not in existing data, add it
                    products[product] = {
                        "listed": True,
                        "done": True,
                        "switch_status": f"已完成({email_date}Ada邮件确认)",
                        "monthly_vol": 0,
                    }
                    updated_count += 1
                prov_map[prov]["products"] = products
                prov_map[prov]["last_updated"] = email_date

    return master_data, updated_count


def run_from_email_text(email_body, email_date="2026-03-20"):
    """
    主入口：传入Ada邮件正文 → 解析 → 对比 → 更新
    Returns: (changes_list, updated_count)
    """
    # 1. Parse
    parsed = parse_ada_email_body(email_body)
    print(f"📧 Ada邮件解析完成:")
    for product, info in parsed.items():
        print(f"  {product}: {info['count']}个区域 ({len(info['provinces'])}个省份识别)")

    # 2. Load current master
    if not MASTER_FILE.exists():
        print("❌ province_master.json 不存在")
        return [], 0
    with open(MASTER_FILE, "r", encoding="utf-8") as f:
        master = json.load(f)

    # 3. Compare
    changes = compare_with_master(parsed, master)
    if changes:
        print(f"\n🔄 发现 {len(changes)} 项新变化:")
        for c in changes:
            print(f"  ✅ {c['province']} {c['product']} {c['change']}")
    else:
        print("\nℹ️ 无新变化（与现有数据一致）")

    # 4. Apply
    master, updated_count = apply_changes(master, parsed, email_date)

    # 5. Save
    with open(MASTER_FILE, "w", encoding="utf-8") as f:
        json.dump(master, f, ensure_ascii=False, indent=2)
    print(f"\n✅ 已更新 {updated_count} 项产品切换状态")

    # 6. Save snapshot
    snap_dir = DATA / "snapshots"
    snap_dir.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M")
    snap = snap_dir / f"snapshot_{ts}.json"
    with open(snap, "w", encoding="utf-8") as f:
        json.dump(master, f, ensure_ascii=False, indent=2)
    print(f"📸 快照已保存: {snap.name}")

    return changes, updated_count


# ── 用于 /gov-dashboard 工作流中Agent调用的简化接口 ──
SAMPLE_ADA_EMAIL = """
l  T20完成（24个区域）：陕西、贵州、湖南、新疆自治区、江西、广东、新疆兵团、福建、山东、青海、浙江、内蒙古、甘肃、海南、吉林、辽宁、山西、黑龙江、北京、江苏、天津、河南、湖北、重庆；

l  T40完成（21个区域）：广东、海南、江西、湖南、新疆兵团、新疆自治区、内蒙古、广西、陕西、重庆、河南、甘肃、贵州、重庆、四川（新增挂网）；山东、浙江、北京、辽宁、天津、湖北（变更完成）；

l  T60完成（2个区域）：北京、辽宁；

l  金滴完成（21个区域）：江西、贵州、广东、山东、浙江、内蒙古、甘肃、海南、福建、湖南、北京、陕西、吉林、辽宁、山西、黑龙江、江苏、天津、河南、湖北、重庆；

l  威利坦完成（23个区域）：新疆自治区、江西、兵团、贵州、山东、广东、浙江、内蒙古、甘肃、海南、福建、湖南、北京、陕西、吉林、辽宁、山西、黑龙江、江苏、天津、河南、湖北、重庆；
"""

if __name__ == "__main__":
    import sys
    if "--simulate" in sys.argv:
        print("🔬 模拟运行：使用Ada 3/20邮件内容")
        run_from_email_text(SAMPLE_ADA_EMAIL, "2026-03-20")
    else:
        print("用法: python parse_ada_email.py --simulate")
        print("或在 /gov-dashboard 工作流中由Agent调用 run_from_email_text()")
