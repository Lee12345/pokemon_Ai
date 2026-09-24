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
    ("가랏!{P}!", "나옴", "me"),                              # 내 쪽
    ("{T}(는|은){P}(를|을)내보냈다!", "나옴", "opp"),           # 상대 쪽
    # ★ **트레이너 이름이 통째로 빠진다.** 일본어·특수문자라 글자 인식이 아무것도 못 내놓으면
    #   위 틀의 「는/은」 이 갈 곳이 없어 통째로 못 읽는다. 실전 기록(2026-09-24)에서
    #   「한카리아스를 내보냈다!」 가 그래서 버려졌고, 이름표로 알아차릴 때까지 **9초**가
    #   더 걸렸다 (사용자: *"인식이 늦어져서 생각할 시간이 적어짐"*).
    #   「XX를 내보냈다」 는 **언제나 상대 쪽**이다 — 내 쪽은 「가랏! XX!」 다.
    ("{P}(를|을)내보냈다!", "나옴", "opp"),
    ("{P}돌아와!", "들어감"),
    # ★ **상대가 빠지는 문구를 하나도 안 읽고 있었다** (2026-09-24). 실전 기록에
    #   「상대 마스카나는 / soirée의 곁으로 돌아간다!」 가 '못 읽음' 으로 버려졌고,
    #   그 뒤로 15초 동안 창은 **이미 들어간 마스카나**를 상대로 잡고 있었다.
    #   내 쪽은 「XX 돌아와!」, 상대 쪽은 「상대 XX는 (트레이너)의 곁으로 돌아간다!」 다.
    #   트레이너 이름이 일본어·특수문자라 통째로 안 읽히는 일이 잦아 **없는 틀도 같이 둔다.**
    ("{P}(는|은){T}(의|이)곁으로돌아간다!", "들어감", "opp"),
    ("{P}(는|은)곁으로돌아간다!", "들어감", "opp"),
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
    # ★ **올라간 쪽이 없었다.** 떨어진 것만 넣고 있었으니, 상대가 칼춤을 쳐도 창은 몰랐다.
    #   실전 기록에 「상대 따라큐의 / 공격이 크게 올라갔다!」 가 '못 읽음' 으로 남아 있다.
    #   없는 틀은 못 읽는 데서 끝나지 않는다 — **가장 닮은 틀로 가 버린다** (§이김/짐 참고).
    ("{P}(의|이){S}(이|가)올라갔다!", "능력상승"),
    ("{P}(의|이){S}(이|가)크게올라갔다!", "능력크게상승"),
    ("{P}(의|이){S}(이|가)크게떨어졌다!", "능력크게하락"),
    ("{P}(는|은)정신을차려싸울수있게되었다!", "되살아남"),
    ("{P}(는|은)상대를길동무로삼으려하고있다!", "길동무"),
    # 낱말은 **「모두링」 이 맞다** (사용자가 확인해 줌, 2026-09-23). 글자 인식이 네 번 다 그렇게
    # 읽었는데 내가 '메가링' 의 오독이라고 짐작하고 틀에 메가링을 적어 뒀었다 — 짐작이 틀렸다.
    ("{P}(의|이){I}와{T}(의|이)모두링이반응했다!", "메가반응"),
    ("{P}(는|은){X}로메가진화했다!", "메가진화"),
    # ★ 「이겼다」 만 있었더니 실전에서 「승부에서 졌다!」 가 **'이김' 으로 0.89** 에 붙었다
    #   (2026-09-23, 진 판이 이긴 판으로 기록됐다). 반대말은 **반드시 짝으로** 넣는다 —
    #   없는 틀은 '못 읽음' 이 아니라 **가장 닮은 틀**로 가 버린다.
    ("{T}와의승부에서이겼다!", "이김"),
    ("{T}와의승부에서졌다!", "짐"),
    # 스위치 화면(유튜버 방송, 사용자가 줌)에서 — 변환자재로 타입이 바뀜
    ("{P}(는|은){Y}타입이됐다!", "타입바뀜"),
    # ── 실전 기록에서 **실제로 나왔는데 틀이 없던** 것들 (2026-09-24) ──────────
    # 내기록/대전기록 의 '못 읽음' 을 세어서 많은 것부터 넣었다. 틀이 없으면 그 줄이
    # 통째로 버려지고, 그동안 창은 **지난 상황**을 붙들고 있는다.
    ("{P}(는|은)독에의한데미지를입었다!", "독데미지"),
    ("{P}(는|은)몸에맹독이퍼졌다!", "맹독퍼짐"),
    ("{P}(의|이)체력이회복되었다!", "체력회복"),
    ("{P}(의|이)혼란이풀렸다!", "혼란풀림"),
    ("{P}(는|은){I}(으로|로)행동이빨라졌다!", "도구드러남"),
    ("{P}(의|이)탈의정체가드러났다!", "탈벗음"),
    ("{P}(의|이)정체가드러났다!", "탈벗음"),
    ("비가내리기시작했다!", "비시작"),
    ("비가그쳤다!", "비끝"),
    ("발밑에풀이무성해졌다!", "풀필드시작"),
    ("발밑의풀이사라졌다!", "풀필드끝"),
    ("효과가별로인듯하다...", "효과별로"),
    ("급소에맞았다!", "급소"),
    ("항복으로대전이중지되었습니다.", "대전중지"),
    ("그러나{P}(는|은)체력이가득찬상태다!", "이미가득"),
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


# 틀은 (글, 일의 종류) 또는 (글, 일의 종류, 어느 쪽인지) 다. 쪽을 적어 두면 문장에
# 「상대」 가 안 붙어 있어도 그쪽으로 본다 — 「XX를 내보냈다」 는 언제나 상대 쪽이다.
_COMPILED = [(_compile(re.sub(r"[!?.]", "", t[0])), t[1],
              t[2] if len(t) > 2 else None) for t in TEMPLATES]


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


WHO_MIN = 0.75         # 문구 앞머리의 이름은 이만큼 닮아야 '그놈이 나와 있다' 로 본다
WHO_GAP = 0.08         # 그리고 2등보다 이만큼은 앞서야 한다 (비슷한 이름끼리 헷갈리면 안 넣는다)
WHO_LEN = 8            # 앞에서 이만큼까지만 이름 후보로 본다


def who(lines, pool):
    """문구 줄 **앞머리의 이름** → ('me'|'opp', 이름) 또는 None.

    ★ **틀에 안 맞아도 이름은 쓸 수 있다.** 실전에서 「상대 패리퍼들 / 독에 의한데미지를
      입었다!」 가 '못 읽음' 으로 통째로 버려졌고, 그 23초 동안 창은 **이미 들어간
      저승갓숭**을 나와 있는 상대로 잡고 있었다 (2026-09-23, 따라간기록_0923_2335).
      문구를 못 알아들어도 **누가 나와 있는지는 그 한 줄에 적혀 있다.**

    ★ **2등과의 차이까지 본다.** 닮은 정도만 보면 「크Ä/까자리」 같은 깨진 글자가
      아무 이름에나 붙는다. 이 판의 12마리 중 확실히 앞서는 것만 쓴다.

    `pool` 은 이 판에 나온 이름들(`Names.here`). 어느 쪽인지는 **「상대」 가 붙었나**로
    가른다 — 양쪽에 같은 종이 있어도(내 보만다 · 상대 보만다) 그래서 안 헷갈린다.
    """
    if not pool:
        return None
    for line in (lines or []):
        text = re.sub(r"^[^가-힣]+", "", line or "")
        side = "me"
        if len(text) > 2 and sim(text[:2], "상대") >= 0.7:
            side, text = "opp", text[2:].lstrip()
        if len(text) < 2:
            continue
        scores = [(max(sim(text[:L], name)
                       for L in range(2, min(WHO_LEN, len(text)) + 1)), name)
                  for name in pool]
        if not scores:
            continue
        scores.sort(reverse=True)
        top = scores[0]
        second = scores[1][0] if len(scores) > 1 else 0.0
        if top[0] >= WHO_MIN and top[0] - second >= WHO_GAP:
            return side, top[1]
    return None


def read(lines, names):
    """문구 칸 한 번(한두 줄) → {'kind': …, …} 또는 {'kind': '못 읽음', 'text': …}."""
    raw = " / ".join(lines) if isinstance(lines, (list, tuple)) else lines
    text = normalize(raw)
    best = None
    for tokens, kind, hint in _COMPILED:
        got = _match(tokens, text, names, {})
        if got is None or not got[1]:
            continue
        score = got[0] / got[1]
        if best is None or score > best[0]:
            best = (score, kind, got[2], hint)
    if best is None or best[0] < ACCEPT:
        return {"kind": "못 읽음", "text": raw, "score": round(best[0], 2) if best else 0.0}
    score, kind, vals, hint = best
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
    if hint:
        ev["side"] = hint
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
