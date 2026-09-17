# -*- coding: utf-8 -*-
"""
실전 사용률 데이터를 정리해서 붙이는 스크립트.

로토덱스(../pokemon_dashboard, champs.pokedb.tokyo 수집본)의 사용률을 읽어서
data/usage_single.json / data/usage_double.json 으로 만든다.

로토덱스는 **일본어**, 우리 데이터는 **한국어**라서 그대로는 연결이 안 된다.
게임 파일에 두 언어가 같은 번호로 들어있으므로, 그걸 다리로 삼아
일본어 이름 -> 번호 -> 한국어 이름 으로 이어 붙인다.

사용법:
    python build_usage.py

먼저 build_data.py 를 실행해 둬야 한다.
"""

import json
import os
import sys
import urllib.request
from datetime import date

BASE = "https://raw.githubusercontent.com/projectpokemon/champout/main"
HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "raw")
OUT = os.path.join(HERE, "data")
ROTODEX = os.path.join(os.path.dirname(HERE), "pokemon_dashboard", "data")

# 일본어 이름표 (한국어 것은 build_data.py 가 이미 받아둠)
JPN = {
    "jpn_wazaname": "rom-txt/jpn/wazaname.json",
    "jpn_tokusei": "rom-txt/jpn/tokusei.json",
    "jpn_itemname": "rom-txt/jpn/itemname.json",
    "jpn_seikaku": "rom-txt/jpn/seikaku.json",
}


def fetch(name, path):
    p = os.path.join(RAW, name + ".json")
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    req = urllib.request.Request(BASE + "/" + path,
                                 headers={"User-Agent": "pokemon-ai-build"})
    with urllib.request.urlopen(req, timeout=120) as r:
        raw = r.read().decode("utf-8")
    os.makedirs(RAW, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write(raw)
    print("  받음: %s" % name)
    return json.loads(raw)


def text_table(doc, prefix):
    out = {}
    for row in doc["mSDataSet"]:
        label = row["LabelName"]
        if not label.startswith(prefix):
            continue
        digits = label[len(prefix):].split("_")[0]
        if digits.isdigit():
            out[int(digits)] = row["OriginalText"]
    return out


def load_local(name):
    p = os.path.join(OUT, name)
    if not os.path.exists(p):
        sys.exit("먼저 build_data.py 를 실행하세요. (%s 없음)" % name)
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def build():
    if not os.path.isdir(ROTODEX):
        sys.exit("로토덱스 폴더를 찾을 수 없습니다: %s" % ROTODEX)

    print("이름표 준비 중...")
    ja_move = text_table(fetch("jpn_wazaname", JPN["jpn_wazaname"]), "WAZANAME_")
    ja_abil = text_table(fetch("jpn_tokusei", JPN["jpn_tokusei"]), "TOKUSEI_")
    ja_item = text_table(fetch("jpn_itemname", JPN["jpn_itemname"]), "ITEMNAME_")
    ja_nat = text_table(fetch("jpn_seikaku", JPN["jpn_seikaku"]), "SEIKAKU_")

    moves = {m["id"]: m for m in load_local("moves.json")}
    abils = {a["id"]: a for a in load_local("abilities.json")}
    items = {i["id"]: i for i in load_local("items.json")}
    pokes = {p["key"]: p for p in load_local("pokemon.json")}
    nats = {n["id"]: n for n in load_local("natures.json")}

    # 일본어 이름 -> 번호  (기호 차이를 흡수하려고 공백 제거)
    def norm(s):
        return (s or "").replace(" ", "").replace("　", "")

    def as_list(v):
        """로토덱스 JSON은 항목이 1개뿐이면 배열이 아니라 객체 하나로 저장돼 있다.
        (PowerShell 이 단일 항목 배열을 벗겨버리는 문제. scrape.ps1 은 고쳤지만
         예전에 수집해 둔 파일은 그대로라서 여기서도 받아준다.)"""
        if v is None:
            return []
        if isinstance(v, dict):
            return [v]
        return list(v)

    ja2move = {norm(v): k for k, v in ja_move.items()}
    ja2abil = {norm(v): k for k, v in ja_abil.items()}
    ja2item = {norm(v): k for k, v in ja_item.items()}
    ja2nat = {norm(v): k for k, v in ja_nat.items()}

    missing = {"기술": set(), "특성": set(), "도구": set(), "성격": set()}
    report = {}

    for mode in ("single", "double"):
        src = os.path.join(ROTODEX, mode)
        if not os.path.isdir(src):
            print("  건너뜀: %s 없음" % mode)
            continue

        rank = {}
        rpath = os.path.join(src, "ranking.json")
        season = updated = None
        if os.path.exists(rpath):
            with open(rpath, encoding="utf-8") as f:
                r = json.load(f)
            season, updated = r.get("season"), r.get("updatedAt")
            for row in r.get("pokemon", []):
                rank[row["key"]] = row["rank"]

        out = []
        for fname in sorted(os.listdir(src)):
            if not fname.endswith(".json") or fname == "ranking.json":
                continue
            with open(os.path.join(src, fname), encoding="utf-8") as f:
                d = json.load(f)
            key = d.get("key") or fname[:-5]

            def conv(rows, lookup, table, kind):
                res = []
                for x in as_list(rows):
                    mid = lookup.get(norm(x.get("name")))
                    if mid is None:
                        missing[kind].add(x.get("name"))
                        res.append({"id": None, "name": x.get("name"),
                                    "pct": x.get("pct")})
                        continue
                    ent = table.get(mid)
                    item = {"id": mid,
                            "name": ent["name"] if ent else x.get("name"),
                            "pct": x.get("pct")}
                    if kind == "기술" and ent:
                        item["type"] = ent["type"]
                        item["category"] = ent["category"]
                        item["power"] = ent["power"]
                    res.append(item)
                return res

            def conv_nature(rows):
                res = []
                for x in rows:
                    nid = ja2nat.get(norm(x.get("name")))
                    if nid is None:
                        missing["성격"].add(x.get("name"))
                        res.append({"id": None, "name": x.get("name"),
                                    "pct": x.get("pct")})
                        continue
                    n = nats.get(nid, {})
                    res.append({"id": nid, "name": n.get("name", x.get("name")),
                                "pct": x.get("pct"),
                                "up": n.get("up"), "down": n.get("down")})
                return res

            evs = []
            for e in as_list(d.get("evs")):
                spread = {}
                for c in as_list(e.get("chips")):
                    v = c.get("value")
                    if isinstance(v, str) and v.isdigit():
                        spread[c.get("label")] = int(v)
                evs.append({"name": e.get("name"), "pct": e.get("pct"),
                            "spread": spread, "total": sum(spread.values())})

            out.append({
                "key": key,
                "name": pokes.get(key, {}).get("name", d.get("ja", "?")),
                "nameJa": d.get("ja"),
                "rank": rank.get(key, d.get("rank")),
                "moves": conv(d.get("moves"), ja2move, moves, "기술"),
                "abilities": conv(d.get("abilities"), ja2abil, abils, "특성"),
                "items": conv(d.get("items"), ja2item, items, "도구"),
                "natures": conv_nature(as_list(d.get("natures"))),
                "evs": evs,
            })

        out.sort(key=lambda x: (x["rank"] is None, x["rank"] or 0))
        path = os.path.join(OUT, "usage_%s.json" % mode)
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"mode": mode, "season": season, "updatedAt": updated,
                       "builtAt": str(date.today()), "pokemon": out},
                      f, ensure_ascii=False, indent=1)
        report[mode] = (len(out), season, updated,
                        os.path.getsize(path) / 1024)
        print("  usage_%s.json  %d마리  시즌%s  수집일 %s  %.1f KB"
              % (mode, len(out), season, updated, report[mode][3]))

    print("\n이름을 못 찾은 항목:")
    for kind, s in missing.items():
        print("  %s: %d개 %s" % (kind, len(s), sorted(s)[:8] if s else ""))

    # 우리 포켓몬 데이터와 대조
    pk_keys = set(pokes)
    for mode in report:
        with open(os.path.join(OUT, "usage_%s.json" % mode), encoding="utf-8") as f:
            u = json.load(f)
        unknown = [p["key"] for p in u["pokemon"] if p["key"] not in pk_keys]
        print("  %s: 게임 데이터에 없는 포켓몬 %d마리 %s"
              % (mode, len(unknown), unknown[:5]))


if __name__ == "__main__":
    build()
