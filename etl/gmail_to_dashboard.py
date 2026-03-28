import os, imaplib, email, json, sys
from datetime import datetime, timedelta
from email.header import decode_header
from pathlib import Path
import urllib.request
import urllib.parse
import subprocess

BASE = Path(__file__).resolve().parent.parent
DATA_DIR = BASE / "data"
MASTER_FILE = DATA_DIR / "province_master.json"

GMAIL_USER = os.environ.get("GMAIL_USER")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", os.environ.get("GOOGLE_CSE_API_KEY", ""))

def decode_str(raw):
    if not raw: return ""
    parts = decode_header(raw)
    res = []
    for data, charset in parts:
        if isinstance(data, bytes):
            res.append(data.decode(charset or "utf-8", errors="replace"))
        else:
            res.append(str(data))
    return "".join(res)

def fetch_recent_emails():
    print("📥 Connecting to Gmail...")
    if not GMAIL_USER or not GMAIL_APP_PASSWORD:
        print("❌ Missing GMAIL_USER or GMAIL_APP_PASSWORD")
        sys.exit(1)
        
    mail = imaplib.IMAP4_SSL("imap.gmail.com")
    mail.login(GMAIL_USER, GMAIL_APP_PASSWORD)
    mail.select('"[Gmail]/All Mail"')
    
    # 搜索过去7天的相关邮件
    all_terms = ["挂网", "集采", "黄标", "红标", "调价", "平台切换", "科园", "准入", "联盟", "价格风险"]
    all_ids = set()
    
    for term in all_terms:
        # X-GM-RAW ignores standard IMAP search issues with Chinese
        query_bytes = f'newer_than:7d subject:{term}'.encode('utf-8')
        try:
            tag = mail._new_tag()
            cmd = tag + b' SEARCH CHARSET UTF-8 X-GM-RAW {' + str(len(query_bytes)).encode() + b'}\r\n'
            mail.send(cmd)
            resp = mail.readline()
            if resp.startswith(b'+'):
                mail.send(query_bytes + b'\r\n')
                result_line = b''
                while True:
                    line = mail.readline()
                    if line.startswith(b'* SEARCH'):
                        result_line = line
                    if line.startswith(tag):
                        break
                if result_line:
                    found = result_line.decode().replace('* SEARCH ', '').strip().split()
                    all_ids.update(found)
        except Exception as e:
            print(f"IMAP Search Error for {term}: {e}")

    items = []
    for mid in list(all_ids)[:30]:
        try:
            _, data = mail.fetch(mid, "(RFC822)")
            msg = email.message_from_bytes(data[0][1])
            subject = decode_str(msg["Subject"])
            sender = decode_str(msg["From"])
            date = msg["Date"]
            
            body = ""
            for part in msg.walk():
                if part.get_content_type() == "text/plain":
                    body = part.get_payload(decode=True).decode("utf-8", errors="replace")[:1000]
                    break
            
            items.append(f"Date: {date}\nFrom: {sender}\nSubject: {subject}\nBody: {body}\n---")
        except Exception as e:
            continue
            
    mail.logout()
    print(f"✅ Found {len(items)} relevant emails in the last 7 days.")
    return items

def analyze_emails_with_gemini(emails_list):
    if not emails_list:
        return {}
    if not GEMINI_API_KEY:
        print("❌ Missing GEMINI_API_KEY")
        return {}

    print("🧠 Analyzing emails with Gemini...")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}"
    
    prompt = """你是政务准入部门的高级数据分析师。请阅读以下过去7天的原始工作邮件，提取其中涉及各省份的“红黄标变化”、“挂网状态达成”、“预警提示”等有效业务进展，并输出为严格的 JSON 格式补丁（无需任何Markdown包装，直接输出大括号包裹的JSON）。

可支持的 JSON 数据结构定义如下：
{
  "省份名称（必须全称如 江西省、内蒙古自治区）": {
    "金针_color_override": "red" 或 "yellow",   // 如果金针颜色升级或降级
    "alert": {"type": "类型", "desc": "高度浓缩的警报描述", "date": "2026-03-27"}, // 如果有预警或完成确认
    "product_overrides": {
      "金针": {"can_sell": true, "price_status": "已完成挂网..."}, // 如果挂网成功
      "T40": {"listed": true, "done": true, "switch_status": "完成..."}
    }
  }
}
如果没有提取到任何有效信息，请输出 {}。只输出那些发生状态改变的省份。

近期邮件原文：
""" + "\n\n".join(emails_list)

    req_data = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.1}
    }).encode("utf-8")
    
    try:
        req = urllib.request.Request(url, data=req_data, headers={"Content-Type": "application/json"})
        resp = urllib.request.urlopen(req, timeout=60)
        res_json = json.loads(resp.read().decode("utf-8"))
        text = res_json["candidates"][0]["content"]["parts"][0]["text"]
        
        # Strip markdown if Gemini ignores instructions
        text = text.strip()
        if text.startswith("```json"):
            text = text[7:]
        if text.endswith("```"):
            text = text[:-3]
            
        patches = json.loads(text.strip())
        print(f"✅ Gemini generated patches for {len(patches)} provinces.")
        return patches
    except Exception as e:
        print(f"❌ Gemini Analysis Error: {e}")
        return {}

def inject_patches_to_master(patches):
    if not MASTER_FILE.exists():
        print("❌ province_master.json not found!")
        return
        
    with open(MASTER_FILE, "r", encoding="utf-8") as f:
        master = json.load(f)
        
    updated_count = 0
    now_str = datetime.now().strftime("%Y-%m-%dT%H:%M")
    
    for prov_name, patch in patches.items():
        # Find province in master
        prov_record = next((p for p in master if p["province"] == prov_name), None)
        if not prov_record:
            continue
            
        print(f"  📝 Patching {prov_name}...")
        
        # Color override
        if "金针_color_override" in patch:
            if "金针" not in prov_record:
                prov_record["金针"] = {}
            prov_record["金针"]["color_label"] = patch["金针_color_override"]
            
        # Product overrides
        if "product_overrides" in patch:
            for pk, pv in patch["product_overrides"].items():
                if pk == "金针":
                    if "金针" not in prov_record: prov_record["金针"] = {}
                    prov_record["金针"].update(pv)
                else:
                    if "products" not in prov_record: prov_record["products"] = {}
                    if pk not in prov_record["products"]: prov_record["products"][pk] = {}
                    prov_record["products"][pk].update(pv)
                    
        # Alerts
        if "alert" in patch:
            if "alerts" not in prov_record: prov_record["alerts"] = []
            # Prevent duplicate alerts by desc
            if not any(a.get("desc") == patch["alert"].get("desc") for a in prov_record["alerts"]):
                prov_record["alerts"].append(patch["alert"])
                
        prov_record["last_updated"] = now_str
        updated_count += 1
        
    with open(MASTER_FILE, "w", encoding="utf-8") as f:
        json.dump(master, f, ensure_ascii=False, indent=2)
        
    # Save snapshot
    snap_dir = DATA_DIR / "snapshots"
    snap_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M")
    snap_file = snap_dir / f"snapshot_{ts}.json"
    with open(snap_file, "w", encoding="utf-8") as f:
        json.dump(master, f, ensure_ascii=False, indent=2)
        
    print(f"✅ Successfully patched {updated_count} provinces and saved to {snap_file.name}")

def main():
    print(f"🚀 Starting Auto Gmail Updater at {datetime.now()}")
    emails = fetch_recent_emails()
    patches = analyze_emails_with_gemini(emails)
    if patches:
        inject_patches_to_master(patches)
    else:
        print("ℹ️ No patches to apply.")

if __name__ == "__main__":
    main()
