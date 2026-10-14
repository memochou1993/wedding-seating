#!/usr/bin/env python3
"""把試算表裡已排好的桌次（桌名＋賓客）放進席次表。會覆蓋雲端所有桌的桌名、歸屬與名單。

    python3 tools/import_tables.py --dry-run   # 只看對應結果
    python3 tools/import_tables.py             # 寫入

來源（同一份試算表的兩個分頁，ID 在本機 .sheet-id）：
  主婚人親友分頁：A 桌次(1…)、B 桌名、D 姓名、G 出席人數 → 席次表第 1… 桌
  新人親友分頁：  A 桌次(A…)、B 桌名、C 姓名、D 出席人數 → 接在主婚人親友之後的桌號
一組多人記成「姓名 +N」。
"""
import csv, io, json, sys, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SB_URL = "https://jkzybhpzihljrluxslmy.supabase.co"
SB_KEY = "sb_publishable__eJX3f2Vw1CY-Dilst5Qfg_cgXw-i16"
EVENT = "lin-20261025"
PARENTS_GID, COUPLE_GID = "1652681496", "659016309"


# ── 與 index.html 相同的桌位與桌號規則（id 綁位置；桌號由舞台往入口、中間往兩側）──
def table_numbers():
    seat, pitch, a0 = 35, 150, 380
    rows_a = [a0 + k * pitch for k in range(5)]
    rows_b = [a0 + pitch // 2 + k * pitch for k in range(5)]
    cols = [(90 + 20 + seat, rows_a), (250 - 20 - seat, rows_b),
            (300 + 20 + seat, rows_a), (300 + 20 + seat + 50, rows_b),
            (622 - 20 - seat - 50, rows_b), (622 - 20 - seat, rows_a),
            (672 + 17 + seat, rows_b), (822 - 17 - seat, rows_a + [a0 + 5 * pitch])]
    spots = [(x, y) for x, ys in cols for y in ys]
    spots.sort(key=lambda p: (round((p[1] - a0) / (pitch / 2)), p[0]))
    ids = {p: f"t{i + 1}" for i, p in enumerate(spots)}
    zones = [(300, 461), (461, 622), (0, 250), (672, 830)]
    order = [p for x0, x1 in zones for p in sorted((p for p in spots if x0 < p[0] < x1), key=lambda p: p[1])]
    return {str(n + 1): ids[p] for n, p in enumerate(order)}   # 桌號 → id


def fetch(sheet_id, gid):
    url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}"
    with urllib.request.urlopen(url) as r:
        return list(csv.reader(io.StringIO(r.read().decode("utf-8"))))


def entry(name, count):
    n = int(count) if str(count).strip().isdigit() else 1
    return f"{name} +{n - 1}" if n > 1 else name


def parse(rows, num_col, name_col, count_col):
    tables, cur = [], None
    for r in rows[1:]:
        r += [""] * 12
        key = r[0].strip()
        if key.endswith("桌"):            # 頁尾的「7桌 總計」
            break
        if key and (not cur or key != cur["key"]):   # 每一列都可能重複寫桌次，換號才算新的一桌
            cur = {"key": key, "name": r[1].strip(), "guests": [], "seats": 0}
            tables.append(cur)
        if not cur:
            continue
        if r[1].strip():
            cur["name"] = r[1].strip()
        name = r[name_col].strip()
        if not name:
            continue
        if name == "預備桌" and not cur["name"]:   # 這一列是桌名，不是賓客
            cur["name"] = name
            continue
        cur["guests"].append(entry(name, r[count_col]))
        cur["seats"] += int(r[count_col]) if r[count_col].strip().isdigit() else 1
    return tables


def main():
    dry = "--dry-run" in sys.argv
    sheet_id = (ROOT / ".sheet-id").read_text().strip()
    parents = parse(fetch(sheet_id, PARENTS_GID), 0, 3, 6)
    couple = parse(fetch(sheet_id, COUPLE_GID), 0, 2, 3)
    num_to_id = table_numbers()

    payload = {tid: {"num": n, "name": "", "side": "", "cap": 10, "guests": []} for n, tid in num_to_id.items()}
    payload["main"] = {"num": "主桌", "name": "", "side": "", "cap": 10, "guests": []}
    plan = [(t, "主婚人親友") for t in parents] + [(t, "新人親友") for t in couple]
    if len(plan) > len(num_to_id):
        sys.exit(f"桌數不夠：需要 {len(plan)} 桌，會場只有 {len(num_to_id)} 桌")
    for i, (t, side) in enumerate(plan):
        n = str(i + 1)
        payload[num_to_id[n]].update(name=t["name"][:20], side=side, guests=t["guests"])
        flag = "  ⚠ 超過 10 位" if t["seats"] > 10 else ""
        print(f"第 {n:>2} 桌 ← {side} {t['key']:>2}｜{t['name'] or '（無桌名）'}｜{len(t['guests'])} 組 {t['seats']} 位{flag}")
    print(f"共 {len(plan)} 桌、{sum(t['seats'] for t, _ in plan)} 位；其餘 {len(num_to_id) - len(plan)} 桌與主桌留空")
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
