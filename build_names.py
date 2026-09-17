# -*- coding: utf-8 -*-
"""
일본어 이름표를 만든다 — 구축기사를 그대로 받아 읽기 위한 다리.

    python build_names.py

구축기사(champs.pokedb.tokyo)는 **일본어**다. 우리 데이터는 한국어다.
게임 파일에 두 언어가 같은 번호로 들어 있으므로 그걸 다리로 삼는다.
build_usage.py 가 사용률에 쓰는 것과 같은 방법인데, 그쪽은 로토덱스
수집본(별도 폴더)이 있어야 돌아간다. 이건 이름표만 만들므로 혼자 돈다.

결과: data/names_ja.json — 일본어 이름 -> 한국어 이름
"""

import json
import os
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "raw")
OUT = os.path.join(HERE, "data")
BASE = "https://raw.githubusercontent.com/projectpokemon/champout/main"

JPN = {
    "moves":     ("rom-txt/jpn/wazaname.json", "WAZANAME_", "moves.json"),
    "abilities": ("rom-txt/jpn/tokusei.json",  "TOKUSEI_",  "abilities.json"),
    "items":     ("rom-txt/jpn/itemname.json", "ITEMNAME_", "items.json"),
    "natures":   ("rom-txt/jpn/seikaku.json",  "SEIKAKU_",  "natures.json"),
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
    out = {}
    counts = {}
    for kind, (path, prefix, local) in JPN.items():
        ja = text_table(fetch("jpn_" + kind, path), prefix)
        ko = dict((x["id"], x["name"]) for x in load_local(local))
        table = {}
        for i, jname in ja.items():
            kname = ko.get(i)
            if kname and jname:
                table[jname] = kname
        out[kind] = table
        counts[kind] = len(table)

    # 포켓몬은 게임 파일에서 직접 잇는다 (사용률에 없는 놈도 받기 위해).
    # 폼 이름(메가 등)도 같이 넣는다 — 구축기사는 'メガボーマンダ' 처럼 적는다.
    ja_mons = text_table(fetch("jpn_monsname", "rom-txt/jpn/monsname_syn.json"),
                         "MONSNAME_")
    ko_mons = {}
    for row in load_local("pokemon.json"):
        ko_mons.setdefault(row["dexNo"], row["name"])
    poke = {}
    for i, jname in ja_mons.items():
        kname = ko_mons.get(i)
        if kname and jname:
            poke[jname] = kname
    # 폼 이름(메가 등)을 같이 넣는다. 구축기사는 'メガゲンガー' 처럼 적는다.
    # 폼 라벨('003_000')이 양쪽 언어에서 같으므로 그걸로 잇는다.
    def forms_of(doc):
        out = {}
        for row in doc["mSDataSet"]:
            label = row["LabelName"]
            if label.startswith("ZKN_FORM_"):
                out[label[len("ZKN_FORM_"):]] = row["OriginalText"].strip()
        return out

    ja_form = forms_of(fetch("jpn_zkn_form", "rom-txt/jpn/zkn_form_syn.json"))
    ko_form = {}
    ko_path = os.path.join(RAW, "formname.json")
    if os.path.exists(ko_path):
        with open(ko_path, encoding="utf-8") as f:
            ko_form = forms_of(json.load(f))
    else:
        ko_form = forms_of(fetch("kor_zkn_form", "rom-txt/kor/zkn_form_syn.json"))
    for label, jname in ja_form.items():
        kname = ko_form.get(label)
        if kname and jname:
            poke.setdefault(jname, kname)

    # 사용률 자료의 nameJa 로도 보충
    for fn in ("usage_single.json", "usage_double.json"):
        q = os.path.join(OUT, fn)
        if not os.path.exists(q):
            continue
        with open(q, encoding="utf-8") as f:
            for row in json.load(f).get("pokemon") or []:
                if row.get("nameJa"):
                    poke.setdefault(row["nameJa"], row["name"])
    out["pokemon"] = poke
    counts["pokemon"] = len(poke)

    # 폼까지 구분되는 표. 이름만으로는 폼이 날아가기 때문이다.
    #   イダイトウ (オス) -> 0902-00 (공격112 특공80)
    #   イダイトウ (メス) -> 0902-01 (공격 92 특공100)
    # 둘을 뭉개면 종족값이 20이나 틀린다. 실제로 표본에서 41마리가 걸렸다.
    keys = {}
    for fn in ("usage_single.json", "usage_double.json"):
        q = os.path.join(OUT, fn)
        if not os.path.exists(q):
            continue
        with open(q, encoding="utf-8") as f:
            for row in json.load(f).get("pokemon") or []:
                if row.get("nameJa") and row.get("key"):
                    keys.setdefault(row["nameJa"], row["key"])
    out["pokemonKey"] = keys
    counts["pokemonKey"] = len(keys)

    with open(os.path.join(OUT, "names_ja.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1, sort_keys=True)
    print("data/names_ja.json — " + " / ".join(
        "%s %d" % (k, v) for k, v in sorted(counts.items())))


if __name__ == "__main__":
    build()
