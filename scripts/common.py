# -*- coding: utf-8 -*-
"""共用工具：全形轉半形、名稱正規化、地址解析。"""
import re

_TRANS = {ord(c): str(i) for i, c in enumerate("０１２３４５６７８９")}
_TRANS.update({
    ord("－"): "-", ord("～"): "~", ord("（"): "(", ord("）"): ")",
    ord("　"): " ", ord("〈"): "(", ord("〉"): ")", ord("﹑"): "、",
})

COUNTIES = [
    "臺北市", "新北市", "桃園市", "臺中市", "臺南市", "高雄市",
    "基隆市", "新竹市", "新竹縣", "苗栗縣", "彰化縣", "南投縣",
    "雲林縣", "嘉義市", "嘉義縣", "屏東縣", "宜蘭縣", "花蓮縣",
    "臺東縣", "澎湖縣", "金門縣", "連江縣",
]

def normalize_text(s) -> str:
    """全形數字/標點轉半形，保留原字形（不動 台/臺）。"""
    return "" if s is None else str(s).translate(_TRANS).strip()

def canon(s) -> str:
    """比對用正規化：統一 台→臺、去空白與括號。"""
    t = normalize_text(s).replace("台", "臺")
    return re.sub(r"[\s()（）「」]", "", t)

def split_address(addr: str):
    """回傳 (縣市, 鄉鎮市區, 清理後地址)。"""
    a = canon(addr)
    a = re.sub(r"^\d{3,6}", "", a).strip()
    a = re.split(r"[；;,，]", a)[0].strip()
    county = next((c for c in COUNTIES if a.startswith(c)), "")
    town = ""
    if county:
        m = re.match(r"^(.{1,4}?[區鄉鎮市])", a[len(county):])
        if m:
            town = m.group(1)
    return county, town, a

def street_of(addr: str) -> str:
    """取到「路/街/大道」層級（不含縣市鄉鎮），供地址備援地理編碼使用。"""
    county, town, a = split_address(addr)
    rest = a[len(county) + len(town):]
    m = re.search(r"[^\s\d,，;；]{1,8}?(?:路|街|大道)(?:[一二三四五六七八九十]段)?", rest)
    return m.group(0) if m else ""
