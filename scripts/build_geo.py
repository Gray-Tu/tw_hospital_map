# -*- coding: utf-8 -*-
"""把縣市界 GeoJSON 簡化成前端可用的輕量檔。

原始檔（g0v/twgeojson，內政部 2010 縣市界）約 9 MB，對網頁太重；
這裡用 Douglas-Peucker 抽稀節點、濾掉極小的離岸礁嶼、座標取到小數 4 位，
並把縣市名正規化成現行名稱（台→臺、桃園縣→桃園市），以便和健保署資料對得起來。

輸入：data/raw/tw_counties_src.json
輸出：web/data/tw_counties.geojson
"""
import json, os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "data", "raw", "tw_counties_src.json")
DST = os.path.join(ROOT, "web", "data", "tw_counties.geojson")

TOLERANCE = 0.0012      # 約 120 公尺，縣市層級的地圖看不出差別
MIN_RING_AREA = 2e-5    # 約 0.2 平方公里以下的礁嶼直接捨去
PRECISION = 4

NAME_FIX = {"桃園縣": "桃園市"}


def normalize_name(n):
    n = NAME_FIX.get(n, n)
    return n.replace("台", "臺")


def perp_distance(p, a, b):
    """點 p 到線段 ab 的垂直距離（以經緯度當平面座標，縣界尺度足夠）。"""
    (px, py), (ax, ay), (bx, by) = p, a, b
    dx, dy = bx - ax, by - ay
    if dx == 0 and dy == 0:
        return ((px - ax) ** 2 + (py - ay) ** 2) ** 0.5
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return ((px - (ax + t * dx)) ** 2 + (py - (ay + t * dy)) ** 2) ** 0.5


def rdp(points, eps):
    """Douglas-Peucker，用堆疊避免遞迴過深（單一環可達數萬點）。"""
    if len(points) < 3:
        return points[:]
    keep = [False] * len(points)
    keep[0] = keep[-1] = True
    stack = [(0, len(points) - 1)]
    while stack:
        i, j = stack.pop()
        if j - i < 2:
            continue
        worst, idx = -1.0, -1
        for k in range(i + 1, j):
            d = perp_distance(points[k], points[i], points[j])
            if d > worst:
                worst, idx = d, k
        if worst > eps:
            keep[idx] = True
            stack.append((i, idx))
            stack.append((idx, j))
    return [p for p, k in zip(points, keep) if k]


def ring_area(ring):
    """鞋帶公式的絕對面積（平方度）。"""
    s = 0.0
    for i in range(len(ring) - 1):
        s += ring[i][0] * ring[i + 1][1] - ring[i + 1][0] * ring[i][1]
    return abs(s) / 2


def clean_ring(ring):
    simplified = rdp(ring, TOLERANCE)
    if len(simplified) < 4:
        return None
    if simplified[0] != simplified[-1]:
        simplified.append(simplified[0])
    return [[round(x, PRECISION), round(y, PRECISION)] for x, y in simplified]


def clean_polygon(poly):
    """poly = [外環, 內環...]；外環太小就整個捨棄。"""
    if ring_area(poly[0]) < MIN_RING_AREA:
        return None
    rings = [clean_ring(poly[0])]
    if rings[0] is None:
        return None
    for hole in poly[1:]:
        if ring_area(hole) >= MIN_RING_AREA:
            r = clean_ring(hole)
            if r:
                rings.append(r)
    return rings


def main():
    with open(SRC, encoding="utf-8") as f:
        src = json.load(f)

    feats, before, after = [], 0, 0
    for ft in src["features"]:
        geom = ft["geometry"]
        polys = [geom["coordinates"]] if geom["type"] == "Polygon" else geom["coordinates"]
        before += sum(len(r) for p in polys for r in p)
        cleaned = [c for c in (clean_polygon(p) for p in polys) if c]
        if not cleaned:
            continue
        after += sum(len(r) for p in cleaned for r in p)
        feats.append({
            "type": "Feature",
            "properties": {"name": normalize_name(ft["properties"]["name"])},
            "geometry": {"type": "MultiPolygon", "coordinates": cleaned},
        })

    out = {"type": "FeatureCollection", "features": feats}
    os.makedirs(os.path.dirname(DST), exist_ok=True)
    with open(DST, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))

    size = os.path.getsize(DST) / 1024
    print(f"{len(feats)} 個縣市，節點 {before:,} -> {after:,}（{after / before:.1%}），"
          f"輸出 {size:,.0f} KB")
    print("縣市：", "、".join(sorted(f["properties"]["name"] for f in feats)))


if __name__ == "__main__":
    main()
