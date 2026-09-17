# -*- coding: utf-8 -*-
"""
포켓몬 챔피언스 데이터 빌드 스크립트.

projectpokemon/champout (게임 ROM 덤프, MIT) 에서 원본을 받아
한국어 이름이 붙은 깔끔한 JSON 으로 정리한다.

사용법:
    python build_data.py            # 캐시 사용 (raw/ 에 있으면 재다운로드 안 함)
    python build_data.py --refresh  # 원본을 다시 받는다 (게임 업데이트 후)

만들어지는 파일 (data/ 폴더):
    pokemon.json     포켓몬 (폼 단위) — 종족값·타입·특성
    moves.json       챔피언스에서 쓸 수 있는 기술
    abilities.json   특성 + 설명
    items.json       도구 + 설명
    learnsets.json   포켓몬별로 배울 수 있는 기술
    type_chart.json  타입 상성표
    meta.json        빌드 정보

주의:
  실전 사용률(채용률 %)과 랭킹은 이 데이터에 없다. 그건 게임 파일이 아니라
  사람들의 대전 기록이라서, champs.pokedb.tokyo 수집본(로토덱스)에서 가져와야 한다.
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

# 회원님이 직접 검증한 챔피언스 상성표가 있는 곳 (없으면 건너뛴다)
SYNERGY_TOOL = os.path.join(os.path.dirname(HERE), "pokemon_type_synergy")

# 받아올 원본 파일들
FILES = {
    "personal": "masterdata/personal.json",
    "waza": "masterdata/waza.json",
    "waza_learn": "masterdata/waza_learn.json",
    "item": "masterdata/item.json",
    "monsname": "rom-txt/kor/monsname_syn.json",
    "formname": "rom-txt/kor/zkn_form_syn.json",
    "wazaname": "rom-txt/kor/wazaname.json",
    "wazainfo": "rom-txt/kor/wazainfo_syn.json",
    "tokusei": "rom-txt/kor/tokusei.json",
    "tokuseiinfo": "rom-txt/kor/tokuseiinfo_syn.json",
    "itemname": "rom-txt/kor/itemname.json",
    "iteminfo": "rom-txt/kor/iteminfo_syn.json",
    "typename": "rom-txt/kor/typename.json",
    "seikaku": "rom-txt/kor/seikaku.json",
}

# --- 게임 내부 코드의 의미 (기술 512개 교차검증으로 확인함, 불일치 0건) ---
TYPE_ORDER = [
    "노말", "격투", "비행", "독", "땅", "바위", "벌레", "고스트", "강철",
    "불꽃", "물", "풀", "전기", "에스퍼", "얼음", "드래곤", "악", "페어리",
]
CATEGORY = {"0": "물리", "1": "특수", "2": "변화"}

# 성격 25개의 능력치 보정.
# 게임 내부 순번이 곧 규칙이다: 올라가는 능력치 = 번호 // 5, 내려가는 능력치 = 번호 % 5.
# 두 값이 같으면 보정 없음(무보정 5종). 순서는 공격·방어·스피드·특공·특방.
NATURE_STATS = ["attack", "defense", "speed", "spAtk", "spDef"]


def fetch(name, refresh=False):
    """원본 파일 하나를 받아온다. raw/ 에 캐시해 둔다."""
    path = os.path.join(RAW, name + ".json")
    if os.path.exists(path) and not refresh:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    url = BASE + "/" + FILES[name]
    req = urllib.request.Request(url, headers={"User-Agent": "pokemon-ai-build"})
    with urllib.request.urlopen(req, timeout=120) as r:
        raw = r.read().decode("utf-8")
    os.makedirs(RAW, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(raw)
    print("  받음: %-12s %8d bytes" % (name, len(raw.encode("utf-8"))))
    return json.loads(raw)


def text_table(doc, prefix):
    """게임 텍스트 파일에서 '번호 -> 한국어' 사전을 만든다."""
    out = {}
    for row in doc["mSDataSet"]:
        label = row["LabelName"]
        if not label.startswith(prefix):
            continue
        tail = label[len(prefix):]
        digits = tail.split("_")[0]
        if digits.isdigit():
            out[int(digits)] = row["OriginalText"]
    return out


def form_table(doc):
    """'003_000' 같은 폼 라벨 -> 폼 이름."""
    out = {}
    for row in doc["mSDataSet"]:
        label = row["LabelName"]
        if label.startswith("ZKN_FORM_"):
            out[label[len("ZKN_FORM_"):]] = row["OriginalText"].strip()
    return out


def clean(s):
    """게임 텍스트의 줄바꿈을 공백으로 정리."""
    return " ".join((s or "").split())


def build(refresh=False):
    print("원본 내려받는 중...")
    src = {k: fetch(k, refresh) for k in FILES}

    mons = text_table(src["monsname"], "MONSNAME_")
    forms = form_table(src["formname"])
    wname = text_table(src["wazaname"], "WAZANAME_")
    winfo = text_table(src["wazainfo"], "WAZAINFO_SYN_")
    tname = text_table(src["tokusei"], "TOKUSEI_")
    tinfo = text_table(src["tokuseiinfo"], "TOKUSEIINFO_SYN_")
    iname = text_table(src["itemname"], "ITEMNAME_")
    iinfo = text_table(src["iteminfo"], "ITEMINFO_SYN_")

    types = [r["OriginalText"] for r in src["typename"]["mSDataSet"]]
    if types != TYPE_ORDER:
        print("  ! 경고: 게임의 타입 순서가 예상과 다릅니다. 코드를 확인하세요.")
        print("    게임:", types)

    os.makedirs(OUT, exist_ok=True)

    # ---------- 포켓몬 ----------
    pokemon = []
    for e in src["personal"]:
        if e.get("is_valid") != "1":
            continue
        no, fo = int(e["no"]), int(e["fo"])
        abil, seen = [], set()
        for k in ("toku0", "toku1", "toku2"):
            aid = int(e[k])
            if aid and aid not in seen:
                seen.add(aid)
                abil.append({"id": aid, "name": tname.get(aid, "?")})
        t1, t2 = int(e["type1"]), int(e["type2"])
        stats = {
            "hp": int(e["hp"]), "attack": int(e["atk"]), "defense": int(e["def"]),
            "spAtk": int(e["spatk"]), "spDef": int(e["spdef"]), "speed": int(e["agi"]),
        }
        pokemon.append({
            "key": "%04d-%02d" % (no, fo),          # 로토덱스와 같은 형식
            "dexNo": no,
            "formNo": fo,
            "name": mons.get(no, "?"),
            "formName": forms.get("%03d_%03d" % (no, fo), ""),
            "types": [TYPE_ORDER[t1]] if t1 == t2 else [TYPE_ORDER[t1], TYPE_ORDER[t2]],
            "baseStats": stats,
            "baseStatTotal": sum(stats.values()),
            "abilities": abil,
            "isMega": "메가" in forms.get("%03d_%03d" % (no, fo), ""),
        })
    pokemon.sort(key=lambda p: (p["dexNo"], p["formNo"]))

    # ---------- 기술 ----------
    moves = []
    for e in src["waza"]:
        if e.get("available") != "1":       # 챔피언스에서 못 쓰는 기술은 제외
            continue
        mid = int(e["id"])
        moves.append({
            "id": mid,
            "name": wname.get(mid, "?"),
            "type": TYPE_ORDER[int(e["type"])],
            "category": CATEGORY.get(e["category"], "?"),
            "power": int(e["power"]),
            "accuracy": int(e["accuracy"]),
            "pp": int(e["pp"]),
            "priority": int(e["priority"]),
            "isContact": e["direct"] == "1",
            "target": int(e["target"]),
            "description": clean(winfo.get(mid, "")),
        })
    moves.sort(key=lambda m: m["id"])

    # ---------- 성격 ----------
    sk = text_table(src["seikaku"], "SEIKAKU_")
    natures = []
    for i, nm in sorted(sk.items()):
        up, down = NATURE_STATS[i // 5], NATURE_STATS[i % 5]
        natures.append({
            "id": i,
            "name": nm,
            "up": None if up == down else up,
            "down": None if up == down else down,
            "modifiers": {st: (1.1 if st == up and up != down
                               else 0.9 if st == down and up != down else 1.0)
                          for st in NATURE_STATS},
        })

    # ---------- 특성 ----------
    abilities = [
        {"id": i, "name": n, "description": clean(tinfo.get(i, ""))}
        for i, n in sorted(tname.items())
    ]

    # ---------- 도구 ----------
    valid_items = {int(e["id"]) for e in src["item"]}
    items = [
        {"id": i, "name": n, "description": clean(iinfo.get(i, ""))}
        for i, n in sorted(iname.items()) if i in valid_items
    ]

    # ---------- 배울 수 있는 기술 ----------
    move_ok = {m["id"] for m in moves}
    learnsets = {}
    for e in src["waza_learn"]:
        no, fo = int(e["id"][:4]), int(e["id"][4:7])
        ids = [int(x) for x in e["waza"].split(",") if x.strip().isdigit()]
        learnsets["%04d-%02d" % (no, fo)] = sorted(i for i in ids if i in move_ok)

    # ---------- 타입 상성표 ----------
    chart = None
    tdata = os.path.join(SYNERGY_TOOL, "types_data.py")
    if os.path.exists(tdata):
        sys.path.insert(0, SYNERGY_TOOL)
        try:
            from types_data import EFF  # noqa
            chart = {a: {d: EFF.get(a, {}).get(d, 1.0) for d in TYPE_ORDER}
                     for a in TYPE_ORDER}
            chart_src = "pokemon_type_synergy/types_data.py (사용자 직접 검증)"
        except Exception as exc:
            print("  ! 상성표를 읽지 못했습니다:", exc)
    if chart is None:
        chart_src = "없음 — 직접 넣어야 함"
        print("  ! 타입 상성표를 못 찾았습니다. data/type_chart.json 은 만들지 않습니다.")

    # ---------- 저장 ----------
    def save(fname, obj):
        p = os.path.join(OUT, fname)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=1)
        print("  %-18s %5d항목  %8.1f KB" %
              (fname, len(obj), os.path.getsize(p) / 1024))

    print("\n만드는 중...")
    save("pokemon.json", pokemon)
    save("moves.json", moves)
    save("abilities.json", abilities)
    save("items.json", items)
    save("natures.json", natures)
    save("learnsets.json", learnsets)
    if chart:
        save("type_chart.json", {"types": TYPE_ORDER, "chart": chart})

    meta = {
        "builtAt": str(date.today()),
        "source": "https://github.com/projectpokemon/champout (MIT) — 게임 ROM 덤프",
        "typeChartSource": chart_src,
        "note": "실전 사용률과 랭킹은 여기 없음. champs.pokedb.tokyo 수집본(로토덱스) 참고.",
        "counts": {
            "pokemon": len(pokemon), "moves": len(moves),
            "abilities": len(abilities), "items": len(items),
            "natures": len(natures),
            "learnsets": len(learnsets),
        },
        "codeMeaning": {
            "category": CATEGORY,
            "typeOrder": TYPE_ORDER,
            "note": "기술 512개를 다른 출처와 교차검증해 확정함 (불일치 0건)",
        },
    }
    with open(os.path.join(OUT, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=1)

    mega = sum(1 for p in pokemon if p["isMega"])
    print("\n완료. 포켓몬 %d폼(메가 %d) / 기술 %d / 특성 %d / 도구 %d"
          % (len(pokemon), mega, len(moves), len(abilities), len(items)))


if __name__ == "__main__":
    build(refresh="--refresh" in sys.argv)
