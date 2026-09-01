# -*- coding: utf-8 -*-
"""把健保署原始 CSV 轉成含集團歸屬與醫療特色標籤的中繼資料。

輸入：data/raw/nhi_{medical_center,regional,district}.csv、data/groups.json
輸出：data/processed/hospitals.json
"""
import csv, json, os, re, sys, datetime
from urllib.parse import quote_plus

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from common import normalize_text, canon, split_address  # noqa: E402

LEVELS = {
    "medical_center": "醫學中心",
    "regional": "區域醫院",
    "district": "地區醫院",
}

# 醫療特色標籤：(標籤, 判斷函式)
def _has(items, *keys):
    return any(any(k in i for k in keys) for i in items)


def derive_tags(name, kind, depts, services):
    """由診療科別與服務項目推導醫療特色標籤。

    注意：健保署「服務項目」用全形破折號（復健－物理治療業務），
    正規化後會變成半形，因此一律比對不含破折號的關鍵字。
    """
    tags = []
    if kind == "精神科醫院" or _has(services, "精神科日間住院", "精神病患者居家"):
        tags.append("精神醫療")
    if kind == "慢性醫院":
        tags.append("慢性照護")
    if _has(depts, "放射腫瘤科") or "癌" in name:
        tags.append("癌症治療")
    if _has(depts, "核子醫學科"):
        tags.append("核子醫學")
    if _has(services, "血液透析", "腹膜透析"):
        tags.append("洗腎透析")
    if _has(services, "安寧"):
        tags.append("安寧療護")
    if _has(services, "分娩") and _has(depts, "婦產科"):
        tags.append("婦產分娩")
    if re.search(r"兒童|婦幼|小兒", name) or _has(depts, "兒童牙科"):
        tags.append("兒童醫療")
    if _has(depts, "中醫"):
        tags.append("中醫")
    if _has(depts, "牙科", "口腔"):
        tags.append("牙科口腔")
    if _has(services, "物理治療", "職能治療", "語言治療"):
        tags.append("復健治療")
    if _has(services, "聽力"):
        tags.append("聽力語言治療")
    if _has(services, "急診業務"):
        tags.append("急診")
    if _has(services, "結核病"):
        tags.append("結核病防治")
    if _has(depts, "職業醫學科"):
        tags.append("職業醫學")
    if _has(services, "義肢業務"):
        tags.append("義肢輔具")
    if _has(services, "居家照護", "居家療護"):
        tags.append("居家醫療")
    if re.search(r"骨科|脊椎", name):
        tags.append("骨科脊椎專科")
    if re.search(r"婦幼|婦產|蕙馨|婦女", name):
        tags.append("婦幼專科")
    if re.search(r"眼科", name):
        tags.append("眼科專科")
    return sorted(set(tags))


def load_groups():
    with open(os.path.join(ROOT, "data", "groups.json"), encoding="utf-8") as f:
        g = json.load(f)
    for grp in g["groups"]:
        grp["_re"] = [re.compile(p) for p in grp["patterns"]]
    return g


DELEGATE_RE = re.compile(r"委託(.+?)(?:興建)?(?:經營|辦理|$)")


def classify(name, groups):
    """回傳 (owner_group_id, operator_group_id, delegated_to_text)。

    owner = 產權／設立主體（依院名前綴的法人或政府機關）
    operator = 實際經營團隊（公辦民營時為受託方）
    """
    cname = canon(name)
    # 先切掉「委託 OO 經營」子句，避免受託方名稱蓋掉真正的設立主體
    delegated_to, base = "", cname
    m = DELEGATE_RE.search(cname)
    if m:
        delegated_to = m.group(1).strip("()（）-— ")
        base = cname[:m.start()].rstrip("()（）-— ")

    owner = None
    for grp in groups["groups"]:
        if any(r.search(base) for r in grp["_re"]):
            owner = grp["id"]
            break

    operator = owner
    if delegated_to:
        for kw, gid in groups["operator_keywords"].items():
            if canon(kw) in delegated_to:
                operator = gid
                break
    return owner, operator, delegated_to


def fallback_kind(name):
    """未歸入既有體系時，依院名判斷法人型態。"""
    c = canon(name)
    if "醫療財團法人" in c or "財團法人" in c:
        return "單一財團法人醫院"
    if "醫療社團法人" in c:
        return "單一醫療社團法人"
    return "私人獨資／獨立醫院"


def load_overrides():
    path = os.path.join(ROOT, "data", "overrides.json")
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def main():
    groups = load_groups()
    overrides = load_overrides()
    today = datetime.date.today().strftime("%Y%m%d")
    out, skipped = [], []
    for key, level in LEVELS.items():
        path = os.path.join(ROOT, "data", "raw", f"nhi_{key}.csv")
        with open(path, encoding="utf-8-sig", newline="") as fh:
            for r in csv.DictReader(fh):
                name = normalize_text(r["醫事機構名稱"])
                end = normalize_text(r["終止合約或歇業日期"])
                if end and end.isdigit() and end < today:
                    skipped.append((name, end))
                    continue
                addr_raw = normalize_text(r["地址"])
                county, town, addr = split_address(addr_raw)
                depts = [d.strip() for d in normalize_text(r["診療科別"]).split(",") if d.strip()]
                services = [s.strip() for s in normalize_text(r["服務項目"]).split(",") if s.strip()]
                kind = normalize_text(r["醫事機構種類"])
                owner, operator, delegated_to = classify(name, groups)
                ov = overrides.get(normalize_text(r["醫事機構代碼"]), {})
                owner = ov.get("owner_group", owner)
                operator = ov.get("operator_group", operator)
                delegated_to = ov.get("delegated_to", delegated_to)
                out.append({
                    "id": normalize_text(r["醫事機構代碼"]),
                    "name": name,
                    "level": level,
                    "kind": kind,
                    "phone": normalize_text(r["電話"]),
                    "address": addr,
                    "county": county,
                    "town": town,
                    "depts": depts,
                    "services": services,
                    "tags": derive_tags(name, kind, depts, services),
                    "owner_group": owner,
                    "operator_group": operator,
                    "delegated_to": delegated_to,
                    "independent_kind": None if owner else fallback_kind(name),
                    "contract_start": normalize_text(r["合約起日"]),
                    "note": normalize_text(r["備註"]),
                    "nhi_region": normalize_text(r["分區業務組"]),
                    "map_url": "https://www.google.com/maps/search/?api=1&query="
                               + quote_plus(f"{name} {addr}"),
                    "search_url": "https://www.google.com/search?q=" + quote_plus(f"{name} 官方網站"),
                })
    # 同一醫事機構代碼可能重複收錄，保留欄位最完整者
    dedup = {}
    for h in out:
        prev = dedup.get(h["id"])
        if prev is None or len(json.dumps(h, ensure_ascii=False)) > len(json.dumps(prev, ensure_ascii=False)):
            dedup[h["id"]] = h
    out = list(dedup.values())

    os.makedirs(os.path.join(ROOT, "data", "processed"), exist_ok=True)
    with open(os.path.join(ROOT, "data", "processed", "hospitals.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)

    matched = sum(1 for h in out if h["owner_group"])
    print(f"輸出 {len(out)} 家醫院（略過已終止 {len(skipped)} 家）")
    print(f"已歸入既有體系：{matched}（{matched / len(out):.0%}）")
    from collections import Counter
    print("未歸入體系的型態分布：", Counter(h["independent_kind"] for h in out if not h["owner_group"]))
    print("公辦民營案例：")
    for h in out:
        if h["delegated_to"]:
            print("   ", h["name"], "->", h["delegated_to"], f"[operator={h['operator_group']}]")


if __name__ == "__main__":
    main()
