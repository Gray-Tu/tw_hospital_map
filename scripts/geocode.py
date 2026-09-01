# -*- coding: utf-8 -*-
"""以 OpenStreetMap Nominatim 為醫院取得座標，結果寫入快取可重複執行。

策略（逐級退回，並用「回傳地址的縣市是否相符」把關）：
  1. 院名主體（去掉法人前綴、委託字句、分院括號）
  2. 院名主體 + 縣市
  3. 縣市 + 鄉鎮市區 + 路street
  4. 縣市 + 鄉鎮市區（區中心，僅供概略定位）

輸出：data/processed/geocode_cache.json（查詢字串 -> 結果）
      data/processed/hospitals_geo.json（醫院清單附座標）
"""
import json, os, re, sys, time
import urllib.parse, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from common import canon, lane_of, street_of  # noqa: E402

CACHE_PATH = os.path.join(ROOT, "data", "processed", "geocode_cache.json")
LIMIT = 5   # 取多筆候選，再挑行政區相符者，避免比對到同名的別家機構
UA = "tw-hospital-map/0.1 (open-data research)"
BBOX = (21.5, 26.5, 118.0, 122.3)  # 南, 北, 西, 東（北界須含馬祖 26.2N，金門在西界 118.2E）
SLEEP = 1.1

# 院名主體萃取：砍掉法人／基金會前綴與委託子句
PREFIX_RE = re.compile(r"^.*(?:醫療財團法人|醫療社團法人|財團法人|社團法人|基金會)")
DELEGATE_RE = re.compile(r"[-－]?委託.*$")


def core_name(name: str) -> str:
    n = DELEGATE_RE.sub("", canon(name))
    n = PREFIX_RE.sub("", n)
    n = re.sub(r"附設民眾診療服務處$", "", n)
    n = re.sub(r"[(（].*?[)）]", "", n)
    return n.strip() or canon(name)


def load_cache():
    if os.path.exists(CACHE_PATH):
        with open(CACHE_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_cache(cache):
    with open(CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=0)


OFFLINE = "--offline" in sys.argv  # 只用快取、不連網（供背景任務進行中先行預覽）


def nominatim(query, cache):
    """回傳候選清單 [{lat, lon, display}, ...]（可能為空）。"""
    if query in cache:
        return cache[query]
    if OFFLINE:
        return []
    url = (f"https://nominatim.openstreetmap.org/search?format=jsonv2&limit={LIMIT}"
           "&countrycodes=tw&accept-language=zh-TW&q=" + urllib.parse.quote(query))
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read().decode("utf-8"))
    except Exception as e:  # 網路失敗不寫入快取，下次重試
        print("   ! 查詢失敗", query, e)
        return None
    res = [{"lat": float(d["lat"]), "lon": float(d["lon"]),
            "display": d.get("display_name", "")} for d in data]
    cache[query] = res
    time.sleep(SLEEP)
    return res


def nominatim_structured(street, city, cache):
    """結構化查詢（street + city）。自由字串查不到的台灣路名，這個介面常常查得到。"""
    key = f"S|{city}|{street}"
    if key in cache:
        return cache[key]
    if OFFLINE:
        return []
    url = (f"https://nominatim.openstreetmap.org/search?format=jsonv2&limit={LIMIT}"
           "&countrycodes=tw&accept-language=zh-TW"
           f"&street={urllib.parse.quote(street)}&city={urllib.parse.quote(city)}")
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read().decode("utf-8"))
    except Exception as e:
        print("   ! 結構化查詢失敗", key, e)
        return None
    res = [{"lat": float(d["lat"]), "lon": float(d["lon"]),
            "display": d.get("display_name", "")} for d in data]
    cache[key] = res
    time.sleep(SLEEP)
    return res


def in_taiwan(r):
    return BBOX[0] <= r["lat"] <= BBOX[1] and BBOX[2] <= r["lon"] <= BBOX[3]


def county_ok(r, county):
    """Nominatim 回傳的地址字串是否落在預期縣市（台/臺 視為相同）。"""
    if not county:
        return True
    disp = canon(r.get("display", ""))
    return county in disp or county.rstrip("市縣") in disp


def town_ok(r, town):
    """鄉鎮市區是否相符。用來擋掉「同縣市但比對到別家同名醫院／診所」的情形。"""
    if not town:
        return True
    return town in canon(r.get("display", ""))


def geocode_one(h, cache):
    county, town = h["county"], h["town"]
    core = core_name(h["name"])
    attempts = [
        (core, "name"),
        (f"{core} {county}", "name+county"),
    ]
    st = street_of(h["address"])
    lane = lane_of(h["address"])
    if st:
        attempts.append((f"{county}{town}{st}", "street"))
    if lane:
        attempts.append(((lane, county), "lane-structured"))
    if st:
        attempts.append(((st, county), "street-structured"))
    if county and town:
        attempts.append((f"{county}{town}", "town-centroid"))

    # 先要求鄉鎮市區也相符（擋掉同縣市的同名機構）；全部落空再放寬到只比對縣市
    for strict in (True, False):
        for q, method in attempts:
            hits = (nominatim_structured(q[0], q[1], cache) if isinstance(q, tuple)
                    else nominatim(q, cache))
            for r in hits or []:
                if not (in_taiwan(r) and county_ok(r, county)):
                    continue
                if strict and method != "town-centroid" and not town_ok(r, town):
                    continue
                return {"lat": r["lat"], "lon": r["lon"],
                        "geo_method": method if strict else method + "~",
                        "geo_query": " ".join(q) if isinstance(q, tuple) else q,
                        "geo_display": r["display"]}
    return {"lat": None, "lon": None, "geo_method": "failed", "geo_query": core,
            "geo_display": ""}


def main():
    with open(os.path.join(ROOT, "data", "processed", "hospitals.json"), encoding="utf-8") as f:
        hospitals = json.load(f)
    cache = load_cache()
    out = []
    for i, h in enumerate(hospitals, 1):
        g = geocode_one(h, cache)
        h.update(g)
        out.append(h)
        if i % 10 == 0 and not OFFLINE:
            save_cache(cache)
            print(f"  {i}/{len(hospitals)} …", flush=True)
    if not OFFLINE:
        save_cache(cache)
    with open(os.path.join(ROOT, "data", "processed", "hospitals_geo.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)

    from collections import Counter
    c = Counter(h["geo_method"] for h in out)
    print("定位方法分布：", dict(c))
    fails = [h["name"] for h in out if h["geo_method"] == "failed"]
    print(f"定位失敗 {len(fails)} 家：", fails[:30])


if __name__ == "__main__":
    main()
