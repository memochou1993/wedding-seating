#!/usr/bin/env python3
"""1122 喜宴的初排：照出席統計試算表的「分類」欄把能出席的賓客分桌，寫進座位表。
會覆蓋雲端所有桌的桌名、歸屬與名單，排好之後就在工作人員版上拖曳調整，不要再重跑。

    python3 tools/arrange_1122.py --dry-run   # 只看分桌結果
    python3 tools/arrange_1122.py             # 寫入

規則：
- 每桌 10 位，一組賓客不拆開。同分類的人盡量同桌（大的組先放，first-fit decreasing）。
- 主婚人親友：周府親友、舅舅阿姨、媽媽親友、扶輪社（北區扶輪社＋扶輪社）、南中之友各自成桌；
  沒填分類、竹棧之友和其他零星分類併成「親友」。
- 新人親友：女方家人（表單上一筆 26 位）拆成 10／10／6 三桌；
  同學、同事人數都不滿兩整桌，照 FRIEND_TABLES 手排，避免有人單獨被拆到別桌。
- 桌號：每一欄由舞台往入口、靠星光大道的欄先編（見 1122/index.html 的 ZONES_1122）。依 ORDER 的順序由 1 號往後放。
  桌子 id 綁在位置上，和桌號不同：table_ids() 把桌號換成 id。
- 主桌留空，給新人自己排。
"""
import csv, io, json, sys, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SB_URL = "https://jkzybhpzihljrluxslmy.supabase.co"
SB_KEY = "sb_publishable__eJX3f2Vw1CY-Dilst5Qfg_cgXw-i16"
EVENT = "zhou-20261122"
TABLE_COUNT = 25
CAP = 10

# 主婚人親友：分類 → 桌名（沒列到的分類都併進「親友」）
PARENT_GROUPS = [("周府親友", ["周府親友"]), ("舅舅阿姨", ["舅舅阿姨"]), ("媽媽親友", ["媽媽親友"]),
                 ("扶輪社", ["北區扶輪社", "扶輪社"]), ("南中之友", ["南中之友"])]
PARENT_REST = "親友"
# 新人親友的朋友桌：[(桌名, [(分類, 取幾位)…])]；取幾位＝從該分類依人數大到小取，None＝全部剩下的
FRIEND_TABLES = [
    ("通徹智慧", [("通徹智慧", 10)]),
    ("通徹・星宇", [("通徹智慧", None), ("星宇航空", None)]),
    ("竹北高中", [("竹北高中", 6), ("新郎親友", None)]),
    ("竹北・淡江", [("竹北高中", None), ("淡江大學", None)]),
]
BRIDE_FAMILY = "新娘親友"
# 放桌順序（由 1 號桌往後）：左區 1–10 給周府親友、舅舅阿姨、媽媽親友與其他親友，右區第一排 11–13 給女方家人
ORDER = ["周府親友", "舅舅阿姨", "媽媽親友", "親友", "女方家人", "南中之友", "扶輪社", "朋友"]


def table_ids():
    """桌號 → id，和 1122/index.html 相同：id 是每排由走道往牆（左區 t1–t10、右區 t11–t25），桌號是每欄由上往下"""
    zones, ids, num, k = [[1, 0], [2, 3, 4]], {}, {}, 1
    for cols in zones:
        for r in range(5):
            for c in cols:
                ids[(c, r)] = f"t{k}"; k += 1
    n = 1
    for cols in zones:
        for c in cols:
            for r in range(5):
                num[str(n)] = ids[(c, r)]; n += 1
    return num


def fetch_rows(sheet_id):
    url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv"
    with urllib.request.urlopen(url) as r:
        return list(csv.DictReader(io.StringIO(r.read().decode("utf-8"))))


def num(v):
    try:
        return int(str(v).strip() or 0)
    except ValueError:
        return 0


def party(r, count=None):
    n = count or max(1, num(r["出席人數"]))
    p = {"name": r["姓名"].strip()[:20], "count": n}
    if num(r["兒童座椅"]): p["child"] = min(n, num(r["兒童座椅"]))
    if num(r["素食份數"]): p["veg"] = min(n, num(r["素食份數"]))
    return p


def pack(parties):
    """first-fit decreasing：大的組先放，放進第一個還塞得下的桌"""
    tables = []
    for p in sorted(parties, key=lambda p: -p["count"]):
        for t in tables:
            if sum(g["count"] for g in t) + p["count"] <= CAP:
                t.append(p); break
        else:
            tables.append([p])
    return tables


def take(pool, n):
    """從 pool 依人數大到小取剛好 n 位（取不剛好就盡量接近），None＝全部"""
    pool.sort(key=lambda p: -p["count"])
    if n is None:
        out, pool[:] = pool[:], []
        return out
    out, left = [], n
    for p in pool[:]:
        if p["count"] <= left:
            out.append(p); pool.remove(p); left -= p["count"]
    return out


def numbered(name, tables):
    """同一分類好幾桌都叫同一個名字，網頁會依桌號自動加上 1、2、3"""
    return [(name, t) for t in tables]


def main():
    dry = "--dry-run" in sys.argv
    rows = [r for r in fetch_rows((ROOT / ".sheet-id-1122").read_text().strip()) if (r["是否出席"].strip() == "能出席" or (not r["是否出席"].strip() and num(r["出席人數"]) > 0))
            and r.get("分類", "").strip() != "無法出席"]   # 表單填能出席、後來才說不能來的，分類會改成「無法出席」
    seen = {}
    for r in rows:   # 同一人填了兩次：保留最後一筆
        seen[(r["姓名"].strip(), r["賓客類別"].strip())] = r
    rows = list(seen.values())
    by = {}
    for r in rows:
        side = "主婚人親友" if r["賓客類別"].startswith("主婚人") else "新人親友"
        by.setdefault((side, r["分類"].strip()), []).append(r)

    blocks = {}   # 放桌順序的區塊名 → [(桌名, 歸屬, [賓客…])]
    used = set()
    for name, cats in PARENT_GROUPS:
        ps = [party(r) for c in cats for r in by.get(("主婚人親友", c), [])]
        used.update(("主婚人親友", c) for c in cats)
        blocks[name] = [(n, "主婚人親友", t) for n, t in numbered(name, pack(ps))]
    rest = [k for k in by if k[0] == "主婚人親友" and k not in used]
    blocks[PARENT_REST] = [(n, "主婚人親友", t) for n, t in numbered(PARENT_REST, pack([party(r) for k in rest for r in by[k]]))]

    fam = by.get(("新人親友", BRIDE_FAMILY), [])
    fam_tables = []
    for r in fam:   # 一筆填了一大家子：拆成每桌 10 位
        n = max(1, num(r["出席人數"]))
        while n > 0:
            fam_tables.append([party(r, min(CAP, n))]); n -= CAP
    blocks["女方家人"] = [(n, "新人親友", t) for n, t in numbered("女方家人", fam_tables)]

    pools = {c: [party(r) for r in by.get(("新人親友", c), [])] for (s, c) in by if s == "新人親友" and c != BRIDE_FAMILY}
    friends = []
    for name, picks in FRIEND_TABLES:
        friends.append((name, "新人親友", [p for c, n in picks for p in take(pools.get(c, []), n)]))
    left = [p for ps in pools.values() for p in ps]
    if left:
        friends += [("朋友", "新人親友", t) for t in pack(left)]
    blocks["朋友"] = friends

    plan = [t for b in ORDER for t in blocks[b]]
    if len(plan) > TABLE_COUNT:
        sys.exit(f"桌數不夠：需要 {len(plan)} 桌，會場只有 {TABLE_COUNT} 桌")
    num_to_id = table_ids()
    payload = {tid: {"num": n, "name": "", "side": "", "cap": CAP, "guests": []} for n, tid in num_to_id.items()}
    payload["main"] = {"num": "主桌", "name": "", "side": "", "cap": CAP, "guests": []}
    for i, (name, side, guests) in enumerate(plan):
        seats = sum(g["count"] for g in guests)
        payload[num_to_id[str(i + 1)]].update(name=name, side=side, guests=guests)
        flag = "  ⚠ 超過 10 位" if seats > CAP else ""
        who = "、".join(g["name"] + (f"×{g['count']}" if g["count"] > 1 else "") for g in guests)
        print(f"第 {i + 1:>2} 桌｜{side}｜{name}｜{len(guests)} 組 {seats} 位：{who}{flag}")
    total = sum(g["count"] for _, _, gs in plan for g in gs)
    print(f"共 {len(plan)} 桌、{total} 位；其餘 {TABLE_COUNT - len(plan)} 桌與主桌留空")
    if dry:
        return
    key = (ROOT / ".edit-key").read_text().strip()
    body = json.dumps({"p_event": EVENT, "p_key": key, "p_tables": payload}).encode()
    req = urllib.request.Request(f"{SB_URL}/rest/v1/rpc/seating_save", data=body, method="POST",
                                 headers={"apikey": SB_KEY, "Content-Type": "application/json"})
    with urllib.request.urlopen(req) as r:
        print("已寫入：", json.loads(r.read()))


if __name__ == "__main__":
    main()
