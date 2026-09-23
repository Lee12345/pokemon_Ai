# -*- coding: utf-8 -*-
"""
화면 아래 문구 칸의 글 → 대전에서 일어난 일.

    python msgread.py "상대 다크펫의" "폴터가이스트!"

## 왜

사용자가 창에 일어난 일을 치기 힘들다고 했다 (2026-09-21). 게임 화면을 읽어 칸을
채우려면, 문구 칸의 글(「상대 다크펫의 / 폴터가이스트!」)을 '상대 다크펫이 폴터가이스트를
썼다' 로 바꿔야 한다.

## 문장 틀은 어디서 왔나

**사용자 아이패드 녹화 한 판(6분 50초)에서 실제로 나온 문장만** 넣었다 (1초마다 410장을
글자 인식해서 모은 198개 — docs/이어받기.md §10). 본편 기억으로 지어낸 문장은 넣지 않는다
— 게임이 다르게 쓰면 조용히 틀린다. 모르는 문장은 **'못 읽음' 으로 돌려준다** (버리지 않는다).
새 문장이 나오면 그때 틀을 더한다.

## 글자가 틀려도

글자 인식은 자주 틀린다 (「효과가 징장했다」, 「다크뎃」, 「냉동편지」). 그래서 글자를
**자음·모음으로 풀어** 가장 가까운 틀과 이름에 맞춘다. 이름은 게임 자료(포켓몬·기술·도구·
특성)에서만 고른다. 이 판에 나온 포켓몬(`mons`)을 주면 그 안에서 먼저 찾는다.

## 누구 편인가

문장 앞의 「상대」 로 가른다. 「타부자고는 풍선 때문에 떠 있다!」 는 **내** 타부자고였다
(그 판에서 타부자고는 사용자 쪽).
"""

import difflib
import re
import sys

import paths

# ── 한글을 자음·모음으로 ─────────────────────────────────────────────────
_CHO = "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ"
_JUNG = "ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ"
_JONG = " ㄱㄲㄳㄴㄵㄶㄷㄹㄺㄻㄼㄽㄾㄿㅀㅁㅂㅄㅅㅆㅇㅈㅊㅋㅌㅍㅎ"


# 같은 말을 몇 만 번 다시 쪼갠다 — 문구 한 줄을 읽는 데 `jamo` 13만 번 · `sim` 6만 번이었다
# (2026-09-23 에 잼). 답이 글자에만 달렸으니 외워 두면 된다. 외운 것이 너무 불어나면 비운다.
_JAMO_CACHE = {}
_SIM_CACHE = {}
CACHE_MAX = 300000
USE_CACHE = True        # 검사가 끈다 — **안 외우고 잰 값과 같은지** 대 보려면 끌 수 있어야 한다


def jamo(text):
    got = _JAMO_CACHE.get(text) if USE_CACHE else None
    if got is not None:
        return got
    out = []
    for ch in text:
        c = ord(ch) - 0xAC00
        if 0 <= c < 11172:
            out.append(_CHO[c // 588])
            out.append(_JUNG[(c % 588) // 28])
            if c % 28:
                out.append(_JONG[c % 28])
        else:
            out.append(ch)
    got = "".join(out)
    if USE_CACHE:
        if len(_JAMO_CACHE) >= CACHE_MAX:
            _JAMO_CACHE.clear()
        _JAMO_CACHE[text] = got
    return got


def sim(a, b):
    """0~1 — 자음·모음 단위로 얼마나 같은가."""
    if a == b:
        return 1.0
    if not a or not b:
        return 0.0
    key = (a, b)
    got = _SIM_CACHE.get(key) if USE_CACHE else None
    if got is None:
        got = difflib.SequenceMatcher(None, jamo(a), jamo(b), autojunk=False).ratio()
        if USE_CACHE:
            if len(_SIM_CACHE) >= CACHE_MAX:
                _SIM_CACHE.clear()
            _SIM_CACHE[key] = got
    return got


def forget():
    """외워 둔 것을 비운다 (검사에서 '외운 것과 갓 잰 것이 같은가' 를 볼 때 쓴다)."""
    _JAMO_CACHE.clear()
    _SIM_CACHE.clear()


def normalize(text):
    """글자 인식 결과 → 한글·숫자만. 띄어쓰기는 인식이 멋대로 넣고 빼고, 문장부호(!?.)는 자주
    빠지거나 딴 글자가 된다 (「가랏! 하마된-」). 둘 다 뜻을 가르지 않으므로 뺀다."""
    return re.sub(r"[^가-힣0-9]", "", text)


# ── 문장 틀 ────────────────────────────────────────────────────────────
# {P} 포켓몬(앞에 '상대' 가 붙을 수 있다) · {M} 기술 · {I} 도구 · {A} 특성 · {S} 능력치
# {Y} 타입 · {T} 상대 트레이너 이름 (일본어 등 — 글자 인식이 못 읽어 비거나 깨진다) · {X} 아무 말
# (a|b) 는 조사 갈래. 뒤의 이름표가 돌려줄 일의 종류. 문장부호는 비교할 때 뺀다 (normalize).
# '의' 자리에 '이' 도 받는다 — 글자 인식이 「대쓰여너이」 「다크뎃이」 「보만다이」 로 세 번 읽었다.
TEMPLATES = [
    ("가랏!{P}!", "나옴"),                                   # 내 쪽
    ("{T}(는|은){P}(를|을)내보냈다!", "나옴"),                 # 상대 쪽
    ("{P}돌아와!", "들어감"),
    ("{P}(의|이){M}!", "기술"),
    ("효과가굉장했다!", "효과굉장"),
    ("그러나실패하고말았다!!", "실패"),
    ("{P}(는|은)쓰러졌다!", "쓰러짐"),
    ("{P}(는|은)풍선때문에떠있다!", "풍선"),
    ("{P}의풍선이터졌다!", "풍선터짐"),
    ("{P}(는|은){P}의{I}(을|를)통찰했다!", "통찰"),
    ("모래바람이불기시작했다!", "모래바람시작"),
    ("모래바람이가라앉았다!", "모래바람끝"),
    ("모래바람이{P}(를|을)덮쳤다!", "모래바람데미지"),
    ("상대의주변에뾰족한바위가떠다니기시작했다!", "스텔스록깔림"),
    ("{P}에게뾰족한바위가박혔다!", "스텔스록데미지"),
    ("{P}의졸음을유도했다!", "하품"),
    ("{P}(는|은)앙코르를받았다!", "앙코르"),
    ("{P}(는|은)이미졸린상태다.", "이미졸림"),
    ("{P}(는|은)잠들어버렸다!", "잠듦"),
    ("{P}(는|은)쿨쿨잠들어있다.", "자는중"),
    ("{P}(는|은)눈을떴다!", "깸"),
    ("{P}(의|이){S}(이|가)떨어졌다!", "능력하락"),
    ("{P}(는|은)정신을차려싸울수있게되었다!", "되살아남"),
    ("{P}(는|은)상대를길동무로삼으려하고있다!", "길동무"),
    # '메가링' 은 글자 인식이 세 번 다 「모두링」 으로 읽었다 — 실제 낱말은 확인 전
    ("{P}(의|이){I}와{T}(의|이)메가링이반응했다!", "메가반응"),
    ("{P}(는|은){X}로메가진화했다!", "메가진화"),
    ("{T}와의승부에서이겼다!", "이김"),
    # 스위치 화면(유튜버 방송, 사용자가 줌)에서 — 변환자재로 타입이 바뀜
    ("{P}(는|은){Y}타입이됐다!", "타입바뀜"),
]
STATS = ["공격", "방어", "특수공격", "특수방어", "스피드", "명중률", "회피율"]

_TOKEN = re.compile(r"\{([A-Z])\}|\(([^)]*)\)|([^{(]+)")


def _compile(t):
    out = []
    for slot, alts, lit in _TOKEN.findall(t):
        if slot:
            out.append(("slot", slot))
        elif alts:
            out.append(("lit", alts.split("|")))
        else:
            out.append(("lit", [lit]))
    return out


_COMPILED = [(_compile(re.sub(r"[!?.]", "", t)), kind) for t, kind in TEMPLATES]


class Names:
    """이름 목록 — 게임 자료에서만."""

    def __init__(self, dex, mons=None):
        self.poke = sorted({p["name"] for p in dex.pokemon})
        self.here = sorted(set(mons or []))       # 이 판에 나온 포켓몬 — 먼저 찾는다
        self.moves = [m["name"] for m in dex.moves]
        self.items = [i["name"] for i in dex.items]
        self.abilities = [a["name"] for a in dex.abilities]
        self.types = list(dex.types)

    def best(self, text, pool):
        if not text:
            return None, 0.0
        score, name = max((sim(text, n), n) for n in pool)
        return name, score


SLOT_MIN = 0.62        # 이름이 이만큼은 닮아야 그 이름으로 본다
LIT_MIN = 0.6          # 틀의 고정된 말도 이만큼은 닮아야
ACCEPT = 0.78          # 전체 평균이 이만큼 넘어야 그 틀로 본다


def _slot(kind, text, names):
    """(값, 점수). 값은 {'name':…, 'side':…} 같은 것."""
    if kind == "T" or kind == "X":
        return {"text": text}, 1.0
    if kind == "P":
        side = "me"
        body = text
        if len(text) > 2 and sim(text[:2], "상대") >= 0.7:
            side, body = "opp", text[2:]
        if not body:
            return None, 0.0
        name, sc = names.best(body, names.here) if names.here else (None, 0.0)
        if sc < 0.85:                                 # 이 판 포켓몬에 없으면 도감 전체
            name2, sc2 = names.best(body, names.poke)
            if sc2 > sc:
                name, sc = name2, sc2
        return {"name": name, "side": side, "read": body}, sc
    pool = {"M": names.moves, "I": names.items, "A": names.abilities, "S": STATS,
            "Y": names.types}[kind]
    name, sc = names.best(text, pool)
    return {"name": name, "read": text}, sc


def _match(tokens, text, names, memo, pos=0, ti=0):
    """tokens[ti:] 을 text[pos:] 에 맞춘다 → (점수 합, 개수, 값들) 가장 좋은 것."""
    key = (pos, ti)
    if key in memo:
        return memo[key]
    if ti == len(tokens):
        res = (0.0, 0, []) if pos == len(text) else None
        memo[key] = res
        return res
    kind, arg = tokens[ti]
    best = None
    if kind == "lit":
        for lit in arg:
            n = len(lit)
            for L in range(max(0, n - 2), n + 3):
                if pos + L > len(text):
                    break
                s = sim(text[pos:pos + L], lit)
                if s < LIT_MIN:
                    continue
                rest = _match(tokens, text, names, memo, pos + L, ti + 1)
                if rest is None:
                    continue
                cand = (rest[0] + s * n, rest[1] + n, rest[2])
                if best is None or cand[0] / cand[1] > best[0] / best[1]:
                    best = cand
    else:
        lo = 0 if arg == "T" else 1
        for L in range(lo, min(14, len(text) - pos) + 1):
            val, s = _slot(arg, text[pos:pos + L], names)
            if s < SLOT_MIN or val is None:
                continue
            rest = _match(tokens, text, names, memo, pos + L, ti + 1)
            if rest is None:
                continue
            w = 3 if arg in "PMIASY" else 0           # 이름은 무겁게, 트레이너 이름은 안 셈
            cand = (rest[0] + s * w, rest[1] + w, [(arg, val)] + rest[2])
            if best is None or (cand[1] and (not best[1] or cand[0] / cand[1] > best[0] / best[1])):
                best = cand
    memo[key] = best
    return best


def read(lines, names):
    """문구 칸 한 번(한두 줄) → {'kind': …, …} 또는 {'kind': '못 읽음', 'text': …}."""
    raw = " / ".join(lines) if isinstance(lines, (list, tuple)) else lines
    text = normalize(raw)
    best = None
    for tokens, kind in _COMPILED:
        got = _match(tokens, text, names, {})
        if got is None or not got[1]:
            continue
        score = got[0] / got[1]
        if best is None or score > best[0]:
            best = (score, kind, got[2])
    if best is None or best[0] < ACCEPT:
        return {"kind": "못 읽음", "text": raw, "score": round(best[0], 2) if best else 0.0}
    score, kind, vals = best
    ev = {"kind": kind, "score": round(score, 2)}
    mons = [v for k, v in vals if k == "P"]
    if mons:
        ev["mon"], ev["side"] = mons[0]["name"], mons[0]["side"]
    if len(mons) > 1:
        ev["other"], ev["other_side"] = mons[1]["name"], mons[1]["side"]
    for k, field in (("M", "move"), ("I", "item"), ("S", "stat"), ("Y", "type")):
        for kk, v in vals:
            if kk == k:
                ev[field] = v["name"]
    if kind == "나옴":
        ev["side"] = "opp" if any(k == "T" for k, _ in vals) else "me"
    if kind == "풍선":
        ev["item"] = "풍선"
    if kind == "통찰":
        # 앞 포켓몬이 통찰을 가졌고, 뒤 포켓몬의 도구가 드러났다
        ev["ability"] = "통찰"
    return ev


def main(argv):
    paths.fix_console()
    import calc
    names = Names(calc.Dex())
    print(read(argv, names))


if __name__ == "__main__":
    main(sys.argv[1:])
