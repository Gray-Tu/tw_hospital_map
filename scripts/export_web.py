# -*- coding: utf-8 -*-
"""把處理後的資料打包成前端用的單一 JSON。

輸入：data/processed/hospitals_geo.json、data/groups.json
輸出：web/data/app_data.json
"""
import json, os, datetime
from collections import Counter, defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 經營型態 -> 大分類（地圖配色與圖例用）
FAMILY_RULES = [
    ("企業財團", "企業財團"),
    ("宗教", "宗教團體"),
    ("大學醫療體系", "大學醫療體系"),
    ("國立大學", "大學醫療體系"),
    ("公立", "公立醫療"),
    ("公營事業", "公立醫療"),
    ("私人醫療法人", "私人醫療法人"),
]
FAMILY_ORDER = ["企業財團", "宗教團體", "大學醫療體系", "公立醫療",
                "私人醫療法人", "其他公益法人", "獨立醫院"]


def family_of(kind):
    if not kind:
        return "獨立醫院"
    for prefix, fam in FAMILY_RULES:
        if kind.startswith(prefix):
            return fam
    return "其他公益法人"


def main():
    with open(os.path.join(ROOT, "data", "processed", "hospitals_geo.json"), encoding="utf-8") as f:
        hospitals = json.load(f)
    with open(os.path.join(ROOT, "data", "groups.json"), encoding="utf-8") as f:
        gdata = json.load(f)
    sites_path = os.path.join(ROOT, "data", "hospital_sites.json")
    sites = {}
    if os.path.exists(sites_path):
        with open(sites_path, encoding="utf-8") as f:
            sites = json.load(f)

    groups = {g["id"]: g for g in gdata["groups"]}
    for g in groups.values():
        g.pop("patterns", None)
        g["family"] = family_of(g["kind"])

    # 前端只需要精簡欄位
    slim = []
    for h in hospitals:
        gid = h.get("operator_group") or h.get("owner_group")
        fam = family_of(groups[gid]["kind"]) if gid in groups else "獨立醫院"
        slim.append({
            "id": h["id"], "n": h["name"], "lv": h["level"], "kd": h["kind"],
            "ph": h["phone"], "ad": h["address"], "ct": h["county"], "tw": h["town"],
            "dp": h["depts"], "tg": h["tags"],
            "og": h.get("owner_group"), "pg": h.get("operator_group"),
            "dl": h.get("delegated_to", ""), "ik": h.get("independent_kind"),
            "fam": fam,
            "lat": h.get("lat"), "lon": h.get("lon"), "gm": h.get("geo_method"),
            "note": h.get("note", ""), "mu": h["map_url"], "su": h["search_url"],
            "web": sites.get(h["id"], ""),
        })

    # 各體系統計
    by_group = defaultdict(list)
    for h in slim:
        gid = h["pg"] or h["og"]
        if gid:
            by_group[gid].append(h)
    gstats = {}
    for gid, hs in by_group.items():
        gstats[gid] = {
            "count": len(hs),
            "counties": [c for c, _ in Counter(h["ct"] for h in hs).most_common()],
            "county_counts": dict(Counter(h["ct"] for h in hs)),
            "levels": dict(Counter(h["lv"] for h in hs)),
            "tags": [t for t, _ in Counter(t for h in hs for t in h["tg"]).most_common(8)],
        }

    county_counts = Counter(h["ct"] for h in slim if h["ct"])
    county_center = Counter()
    for h in slim:
        if h["lv"] == "醫學中心" and h["ct"]:
            county_center[h["ct"]] += 1

    out = {
        "meta": {
            "generated": datetime.date.today().isoformat(),
            "hospital_count": len(slim),
            "sources": [
                {"name": "健保特約醫事機構－醫學中心（衛福部中央健康保險署）",
                 "url": "https://data.gov.tw/dataset/39280"},
                {"name": "健保特約醫事機構－區域醫院（衛福部中央健康保險署）",
                 "url": "https://data.gov.tw/dataset/39281"},
                {"name": "健保特約醫事機構－地區醫院（衛福部中央健康保險署）",
                 "url": "https://data.gov.tw/dataset/39282"},
                {"name": "座標：OpenStreetMap Nominatim 地理編碼",
                 "url": "https://nominatim.openstreetmap.org/"},
            ],
        },
        "family_order": FAMILY_ORDER,
        "groups": groups,
        "group_stats": gstats,
        "hospitals": slim,
        "county_counts": dict(county_counts),
        "county_center_counts": dict(county_center),
    }

    os.makedirs(os.path.join(ROOT, "web", "data"), exist_ok=True)
    with open(os.path.join(ROOT, "web", "data", "app_data.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))

    located = sum(1 for h in slim if h["lat"])
    withsite = sum(1 for h in slim if h["web"])
    print(f"匯出 {len(slim)} 家醫院（已定位 {located}、附官網 {withsite}）、{len(groups)} 個體系")
    print("體系規模 Top 15：")
    for gid, s in sorted(gstats.items(), key=lambda x: -x[1]["count"])[:15]:
        print(f"  {groups[gid]['name']:<34}{s['count']:>3} 家  {'、'.join(s['counties'][:6])}")


if __name__ == "__main__":
    main()
