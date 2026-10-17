#!/usr/bin/env python3
"""把出席調查試算表的「能出席」名單匯入座位表的出席名單（工作人員專用）。

    python3 tools/import_roster.py            # 匯入
    python3 tools/import_roster.py --dry-run  # 只看結果、不上傳

需要兩個不進版控的本機檔案：
    .sheet-id   試算表 ID（網址 /d/ 與 /edit 之間那段）
    .edit-key   工作人員編輯金鑰
只上傳排座位需要的欄位：姓名、人數、歸屬、關係、單位、素食、兒童椅。電話與祝福留言不會上傳。
"""
import csv, io, json, sys, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SB_URL = "https://jkzybhpzihljrluxslmy.supabase.co"
SB_KEY = "sb_publishable__eJX3f2Vw1CY-Dilst5Qfg_cgXw-i16"
EVENT = "lin-20261025"
SIDES = {"主婚人的親友": "主婚人親友", "新人的親友": "新人親友"}


def num(v):
    try:
        return int(str(v).strip() or 0)
    except ValueError:
        return 0


def fetch_rows(sheet_id):
    url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv"
    with urllib.request.urlopen(url) as r:
        return list(csv.DictReader(io.StringIO(r.read().decode("utf-8"))))


def build(rows):
    people, seen, notes = [], {}, []
    for r in rows:
        if r.get("是否出席", "").strip() != "能出席":
            continue
        name = r.get("姓名", "").strip()
        if not name:
            continue
        side = SIDES.get(r.get("賓客類別", "").strip(), "")
        count = num(r.get("出席人數"))
        p = {
            "name": name[:20],
            "count": max(count, 1),
            "side": side,
            "relation": r.get("與主婚人的關係", "").strip()[:20],
            "unit": r.get("單位名稱", "").strip()[:30],
            "veg": num(r.get("素食份數")),
            "child": num(r.get("兒童座椅")),
            "note": "表單人數填 0，請確認" if count == 0 else "",
        }
        key = (name, side)
        if key in seen:   # 同一人填了兩次：保留最後一筆（試算表依時間排序）
            notes.append(f"重複回覆，保留最後一筆：{name}")
            people[seen[key]] = p
        else:
            seen[key] = len(people)
            people.append(p)
    return people, notes


def main():
    dry = "--dry-run" in sys.argv
    sheet_id = (ROOT / ".sheet-id").read_text().strip()
    people, notes = build(fetch_rows(sheet_id))
    total = sum(p["count"] for p in people)
    by_side = {}
    for p in people:
        by_side.setdefault(p["side"] or "未分類", [0, 0])
        by_side[p["side"] or "未分類"][0] += 1
        by_side[p["side"] or "未分類"][1] += p["count"]
    print(f"能出席 {len(people)} 組、{total} 位")
    for side, (n, c) in by_side.items():
        print(f"  {side}：{n} 組、{c} 位")
    for n in notes:
        print("  " + n)
    zero = [p["name"] for p in people if p["note"]]
    if zero:
        print(f"  人數填 0（先算 1 位，請確認）：{'、'.join(zero)}")
    if dry:
        return
    key = (ROOT / ".edit-key").read_text().strip()
    body = json.dumps({"p_event": EVENT, "p_key": key, "p_people": people}).encode()
    req = urllib.request.Request(f"{SB_URL}/rest/v1/rpc/seating_set_roster", data=body, method="POST",
                                 headers={"apikey": SB_KEY, "Content-Type": "application/json"})
    with urllib.request.urlopen(req) as r:
        print("已上傳：", json.loads(r.read()))


if __name__ == "__main__":
    main()
