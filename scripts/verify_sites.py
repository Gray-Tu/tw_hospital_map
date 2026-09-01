# -*- coding: utf-8 -*-
"""驗證人工彙整的官網網址，只保留實際可連通者。

1. 逐一檢查醫院官網候選（同一家可給多個候選，取第一個通的）
2. 一併檢查 data/groups.json 的體系官網，連不通者清空，避免留下死連結

輸出：data/hospital_sites.json（醫事機構代碼 -> 官網）
     並就地更新 data/groups.json 的 website 欄位
用法：python scripts/verify_sites.py      （需要對外網路）
"""
import json, os, ssl
import urllib.request, urllib.error

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"

# 院名關鍵字 -> 官網候選（依序嘗試）。比對時依本清單順序，較具體的關鍵字要排前面。
CANDIDATES = [
    ("國立臺灣大學醫學院附設醫院新竹臺大分院", ["https://www.hch.gov.tw/"]),
    ("國立臺灣大學醫學院附設醫院雲林分院", ["https://www.ylh.gov.tw/"]),
    ("國立臺灣大學醫學院附設醫院", ["https://www.ntuh.gov.tw/"]),
    ("國立成功大學醫學院附設醫院斗六分院", ["https://d6www.hosp.ncku.edu.tw/"]),
    ("國立成功大學醫學院附設醫院", ["https://nckuh.hosp.ncku.edu.tw/", "https://www.hosp.ncku.edu.tw/"]),
    ("國立陽明交通大學附設醫院", ["https://www.ymuh.ym.edu.tw/", "https://www.ymuh.nycu.edu.tw/", "https://www.nycuh.gov.tw/"]),
    ("三軍總醫院", ["https://www.tsgh.ndmctsgh.edu.tw/"]),
    ("臺北榮民總醫院", ["https://www.vghtpe.gov.tw/"]),
    ("臺中榮民總醫院", ["https://www.vghtc.gov.tw/"]),
    ("高雄榮民總醫院", ["https://www.vghks.gov.tw/"]),
    ("屏東榮民總醫院", ["https://www.vhpt.gov.tw/", "https://www.ptvh.gov.tw/"]),
    ("長庚", ["https://www.cgmh.org.tw/"]),
    ("國泰", ["https://www.cgh.org.tw/"]),
    ("新光吳火獅", ["https://www.skh.org.tw/"]),
    ("亞東紀念醫院", ["https://www.femh.org.tw/"]),
    ("馬偕", ["https://www.mmh.org.tw/"]),
    ("慈濟", ["https://www.tzuchi.com.tw/"]),
    ("彰化基督教", ["https://www.cch.org.tw/"]),
    ("奇美", ["https://www.chimei.org.tw/"]),
    ("義大", ["https://www.edah.org.tw/"]),
    ("臺北市立萬芳醫院", ["https://www.wanfang.gov.tw/"]),
    ("衛生福利部雙和醫院", ["https://shh.tmu.edu.tw/"]),
    ("臺北醫學大學附設醫院", ["https://www.tmuh.org.tw/"]),
    ("高雄醫學大學附設中和紀念醫院", ["https://www.kmuh.org.tw/"]),
    ("中國醫藥大學附設醫院", ["https://www.cmuh.cmu.edu.tw/"]),
    ("亞洲大學附屬醫院", ["https://www.auh.org.tw/"]),
    ("中山醫學大學附設醫院", ["https://web.csh.org.tw/"]),
    ("臺南市立安南醫院", ["https://www.tmanh.org.tw/"]),
    ("臺北市立聯合醫院", ["https://tpech.gov.taipei/"]),
    ("振興醫院", ["https://www.chgh.org.tw/"]),
    ("和信治癌中心醫院", ["https://www.kfsyscc.org/"]),
    ("耕莘", ["https://www.cth.org.tw/"]),
    ("羅東聖母醫院", ["https://www.smh.org.tw/"]),
    ("羅東博愛醫院", ["https://www.pohai.org.tw/"]),
    ("嘉義基督教醫院", ["https://www.cych.org.tw/"]),
    ("聖馬爾定醫院", ["https://www.stm.org.tw/"]),
    ("恩主公醫院", ["https://www.eck.org.tw/"]),
    ("童綜合", ["https://www.sltung.com.tw/"]),
    ("光田", ["https://www.ktgh.com.tw/"]),
    ("秀傳", ["https://www.scmh.org.tw/"]),
    ("敏盛", ["https://www.e-ms.com.tw/"]),
    ("聯新國際醫院", ["https://www.landseedhospital.com.tw/"]),
    ("大千", ["https://www.tachien.com.tw/"]),
    ("門諾", ["https://www.mch.org.tw/"]),
    ("屏東基督教醫院", ["https://www.ptch.org.tw/"]),
    ("埔里基督教醫院", ["https://www.pcht.org.tw/", "https://www.puch.org.tw/"]),
    ("恆春基督教醫院", ["https://www.hcch.org.tw/"]),
    ("臺東基督教醫院", ["https://www.tths.org.tw/", "https://www.tch.org.tw/"]),
    ("新樓", ["https://www.sinlau.org.tw/"]),
    ("輔仁大學附設醫院", ["https://www.fjuh.fju.edu.tw/", "https://fjuh.fju.edu.tw/"]),
    ("林新", ["https://www.lshosp.com.tw/", "http://www.lshosp.com.tw/"]),
    ("仁愛醫療財團法人", ["https://www.jah.org.tw/"]),
    ("阮綜合", ["https://www.yuanhosp.com.tw/"]),
    ("員榮", ["https://www.yuanrung.org.tw/"]),
    ("馨蕙馨醫院", ["https://www.shs-h.com.tw/"]),
    ("博愛蕙馨醫院", ["https://www.boaihs.com.tw/"]),
    ("為恭", ["https://www.weigong.org.tw/"]),
    ("天晟", ["https://www.tcmg.com.tw/"]),
    ("東元", ["https://www.tewh.org.tw/", "https://www.teh.org.tw/"]),
    ("臺安醫院", ["https://www.tahsda.org.tw/"]),
    ("仁濟", ["https://www.tjci.org.tw/"]),
]

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE  # 部分院所站台憑證鏈不完整，不代表網址無效
_checked = {}


def reachable(url):
    """回傳 (是否可用, 說明)。403/405 視為可用：主機存在，只是擋掉了程式化請求。"""
    if url in _checked:
        return _checked[url]
    result = (False, "?")
    for method in ("HEAD", "GET"):
        req = urllib.request.Request(url, method=method, headers={"User-Agent": UA})
        try:
            with urllib.request.urlopen(req, timeout=20, context=CTX) as r:
                result = (r.status < 400, str(r.status))
                break
        except urllib.error.HTTPError as e:
            if e.code in (403, 405):
                result = (True, f"{e.code}(擋爬蟲但站台存在)")
                break
            result = (False, str(e.code))
        except Exception as e:
            result = (False, type(e).__name__ + ": " + str(e)[:40])
    _checked[url] = result
    return result


def main():
    with open(os.path.join(ROOT, "data", "processed", "hospitals.json"), encoding="utf-8") as f:
        hospitals = json.load(f)

    print("── 醫院官網 ──")
    resolved = {}
    for kw, urls in CANDIDATES:
        for u in urls:
            good, why = reachable(u)
            print(f"{'OK ' if good else 'BAD'} {why:<28} {u}")
            if good:
                resolved[kw] = u
                break

    sites = {}
    for h in hospitals:
        for kw, _ in CANDIDATES:
            if kw in resolved and kw in h["name"]:
                sites[h["id"]] = resolved[kw]
                break
    with open(os.path.join(ROOT, "data", "hospital_sites.json"), "w", encoding="utf-8") as f:
        json.dump(sites, f, ensure_ascii=False, indent=1)

    print("\n── 體系官網（連不通者清空）──")
    gpath = os.path.join(ROOT, "data", "groups.json")
    with open(gpath, encoding="utf-8") as f:
        gdata = json.load(f)
    dropped = 0
    for g in gdata["groups"]:
        u = g.get("website")
        if not u:
            continue
        good, why = reachable(u)
        if not good:
            print(f"清空 {g['name']}：{u}（{why}）")
            g["website"] = ""
            dropped += 1
    with open(gpath, "w", encoding="utf-8") as f:
        json.dump(gdata, f, ensure_ascii=False, indent=2)

    print(f"\n{len(resolved)}/{len(CANDIDATES)} 組院名解析出可用官網，涵蓋 {len(sites)} 家醫院；"
          f"體系官網清空 {dropped} 筆")


if __name__ == "__main__":
    main()
