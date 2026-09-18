# -*- coding: utf-8 -*-
"""실전 — 대전하면서 한 턴씩 물어본다.

    python3 live.py

## 왜 따로 만들었나

`search.py` 로도 답은 나오지만, 매 턴 이걸 다시 쳐야 한다 —

    python search.py 한카리아스,아머까오,누리레느 하마돈 --초 8
           --기술 지진,역린,화염방사,칼춤 --봤다 자뭉열매,지진

**74자다.** 챔피언스는 턴당 40초(보유 7분)이고, 폰으로 칠 수도 있다.
그래서 **파티는 한 번만 적고, 매 턴은 짧게** 치도록 따로 만들었다.

## 쓰는 법

파티를 `data/my_party.txt` 에 적어 두면 다음부터 안 물어본다.

    한카리아스 지진,역린,화염방사,칼춤
    아머까오 바디프레스,철벽,날개쉬기,브레이브버드
    누리레느 물거품아리아,냉동빔,아쿠아제트,하품

그 다음부터는 매 턴 한 줄씩 —

    하마돈            상대가 이놈으로 바뀌었다 (약칭 가능)
    +지진 +자뭉열매    이번에 본 기술·도구. **쌓인다** — 다시 안 쳐도 된다
    나70 적40         남은 HP 비율 (안 적으면 그대로)
    >아머까오          내가 이놈으로 바꿨다
    .                그냥 다시 물어본다
    ?                도움말 / q 나가기

한 줄에 섞어 써도 된다:  `하마돈 +지진 나70`

## 기록

한 판이 전부 `data/logs/` 에 남는다. **진 판을 그 파일째로 가져오면
왜 졌는지 되짚을 수 있다.** 그게 이 도구의 최종 목적이다.
"""

import io
import json
import os
import re
import sys
import time

import battle
import best
import calc
import scout
import search

import paths

# **읽는 자리와 쓰는 자리를 가른다.** 하나로 묶은 실행 파일이면 자료는
# 임시 폴더에서 읽지만, 내 파티와 대전 기록은 실행 파일이 놓인 자리에
# 써야 다음에도 남는다 (paths.py 참고).
PARTY_FILE = paths.mine("내파티.txt")
LOG_DIR = paths.mine("대전기록")

# 턴당 40초, 보유 7분. 읽고 누를 시간을 빼고 10초를 기본으로 둔다.
DEFAULT_SECONDS = 10.0


# ---------------------------------------------------------------------------
# 이름 찾기 — 짧게 쳐도 되게, 대신 **무엇으로 읽었는지 보여 준다**
# ---------------------------------------------------------------------------
#
# `dex.find_pokemon` 은 느슨하게 만들지 않는다. 거기는 온 코드가 쓰는
# 자리라, 짧은 글자가 엉뚱한 놈에 붙으면 조용히 틀어진다
# (`페리퍼` 와 `패리퍼` 처럼). 그래서 **여기서만** 앞글자로 찾고,
# 찾은 결과를 화면에 같이 적는다. 잘못 붙으면 눈에 보이게.
def _candidates(items, text, key="name"):
    text = text.strip()
    if not text:
        return []
    exact = [x for x in items if x[key] == text]
    if exact:
        return exact
    return [x for x in items if x[key].startswith(text)]


def find_poke(dex, text):
    """앞글자로 포켓몬 찾기. (포켓몬, 알림글) 또는 (None, 왜 안 되는지)."""
    got = _candidates(dex.pokemon, text)
    if not got:
        return None, None
    # 기본 폼을 먼저 본다. '한카' 는 메가·Z 까지 걸리는데, 상대를
    # 처음 볼 때는 기본 폼 이름으로 부르는 게 보통이다.
    base = [p for p in got if p.get("formNo") == 0]
    pool = base or got
    names = sorted({p["name"] for p in pool})
    if len(names) > 1:
        return None, "'%s' 은 여럿입니다: %s" % (text, ", ".join(names[:6]))
    p = pool[0]
    note = None if p["name"] == text else "%s → %s" % (text, p["name"])
    return p, note


def find_move_or_item(dex, text):
    """기술이면 ('기술', 이름), 도구면 ('도구', 이름), 없으면 (None, 이유)."""
    mv = _candidates(dex.moves, text)
    it = _candidates(dex.items, text)
    if len(mv) == 1 and not it:
        return "기술", mv[0]["name"]
    if len(it) == 1 and not mv:
        return "도구", it[0]["name"]
    if not mv and not it:
        return None, "'%s' 이라는 기술·도구를 못 찾았습니다" % text
    names = sorted({x["name"] for x in mv + it})
    if len(names) == 1:
        kind = "기술" if mv else "도구"
        return kind, names[0]
    return None, "'%s' 은 여럿입니다: %s" % (text, ", ".join(names[:6]))


# ---------------------------------------------------------------------------
# 내 파티
# ---------------------------------------------------------------------------
#
# **여기서 한 번 크게 틀렸다.** 처음에는 이름과 기술만 받고, 배분·성격·
# 도구는 `calc.popular_build` 로 **사다리 1위 것을 멋대로 씌웠다.**
# 상대는 모르니까 사용률로 짐작하는 게 맞지만, **내 파티는 내가 안다.**
# 남의 배분으로 내 포켓몬을 계산하고 있었던 것이다.
#
# 얼마나 틀어지나 — 같은 아머까오인데
#     HB 장난꾸러기   방어 172  특방 105
#     HD 신중        방어 125  특방 150
# 방어가 38% 차이다. 이 정도면 "한 대 버티나" 가 뒤집힌다.
#
# 그래서 배분·성격·도구를 받는다. 안 적으면 사용률로 채우되 **화면에
# 큰 소리로 말한다** — 조용히 남의 배분을 쓰는 일이 없게.

# 노력치 표기: A32S32 / H16A22B2S26 처럼 붙여 쓴다
_EV = re.compile(r"([HABCDShabcds])\s*(\d{1,2})")

# 챔피언스 규칙 (README '확인해 둔 게임 규칙' 참고)
EV_MAX = 32          # 한 능력치에 최대
EV_TOTAL = 66        # 합계 최대


def parse_evs(text):
    """'A32S32' -> ({'attack':32,'speed':32}, 알림글). 못 읽으면 (None, 이유)."""
    if not _EV.search(text or ""):
        return None, None
    sp, seen = {}, []
    for key, num in _EV.findall(text):
        stat = calc.SPREAD_KEY.get(key.upper())
        if not stat:
            return None, "'%s' 는 모르는 능력치입니다 (H A B C D S)" % key
        val = int(num)
        if val > EV_MAX:
            return None, ("%s%d — 한 능력치에 %d까지입니다"
                          % (key.upper(), val, EV_MAX))
        sp[stat] = val
        seen.append("%s%d" % (key.upper(), val))
    total = sum(sp.values())
    if total > EV_TOTAL:
        return None, "합이 %d입니다 — %d까지입니다" % (total, EV_TOTAL)
    return sp, " ".join(seen)


def find_ability(dex, poke, text):
    """그 포켓몬이 가질 수 있는 특성 중에서 찾는다.

    **아무 특성이나 받으면 안 된다.** 하마돈에게 '심록' 을 붙일 수는
    없다. 그 포켓몬의 목록 안에서만 고른다.
    """
    for ab in poke.get("abilities") or ():
        if ab["name"] == text:
            return ab["name"]
    for ab in poke.get("abilities") or ():
        if ab["name"].startswith(text):
            return ab["name"]
    return None


def parse_extra(dex, text, poke=None):
    """기술 뒤에 적은 배분·성격·특성·도구를 읽는다.

    돌려주는 것: (sp, nature, ability, item, 못 읽은 낱말들)
    """
    sp = nature = ability = item = None
    unknown = []
    for word in (text or "").replace(",", " ").split():
        got, note = parse_evs(word)
        if got:
            sp = got
            continue
        if note:                       # 노력치처럼 생겼는데 규칙에 안 맞다
            unknown.append("%s (%s)" % (word, note))
            continue
        try:
            nature = dex.find_nature(word)
            continue
        except LookupError:
            pass
        if poke is not None:
            got = find_ability(dex, poke, word)
            if got:
                ability = got
                continue
        kind, name = find_move_or_item(dex, word)
        if kind == "도구":
            item = name
            continue
        unknown.append(word)
    return sp, nature, ability, item, unknown


def build_one(dex, poke, sp, nature, ability, item):
    """내가 적은 대로 만든다. 안 적은 것만 사용률로 채운다.

    (빌드, 사용률로 채운 것들) 을 돌려준다.
    """
    base, _note = calc.popular_build(dex, poke)
    filled = []
    if sp is None:
        sp = base.sp
        filled.append("노력치")
    if nature is None:
        nature = base.nature
        filled.append("성격")
    if item is None:
        item = base.item
        filled.append("도구")
    if ability is None:
        # **특성도 조용히 첫 번째 것으로 정해지고 있었다.** 하마돈이
        # 모래의힘이면 날씨가 안 깔려서 판이 통째로 달라진다.
        ability = base.ability
        if len(poke.get("abilities") or ()) > 1:
            filled.append("특성")
    mega = dex.mega_by_item.get(item)
    if mega and not poke.get("isMega") and mega["dexNo"] == poke["dexNo"]:
        poke = mega
        ability = None            # 메가는 특성이 따로 정해져 있다
    return calc.Build(dex, poke, sp=sp, nature=nature, ability=ability,
                      item=item), filled
def read_line(dex, line):
    """파티 파일 한 줄을 읽는다.

        한카리아스 지진,역린,화염방사,칼춤 | 명랑 A32S32 한카리아스나이트Z

    세로줄(|) 뒤는 없어도 된다. 없으면 사용률로 채우고 그렇다고 알린다.
    (빌드, [기술], 사용률로 채운 것들, 문제) 를 돌려준다.
    """
    head, _, tail = line.partition("|")
    bits = head.split(None, 1)
    poke, _note = find_poke(dex, bits[0])
    if poke is None:
        return None, None, None, "'%s' 이라는 포켓몬을 못 찾았습니다" % bits[0]

    moves = []
    for m in (bits[1].replace(",", " ").split() if len(bits) > 1 else []):
        kind, name = find_move_or_item(dex, m)
        if kind != "기술":
            return None, None, None, ("'%s' 을 기술로 못 읽었습니다" % m)
        moves.append(name)

    sp, nature, ability, item, unknown = parse_extra(dex, tail, poke)
    if unknown:
        return None, None, None, ("못 알아들은 말: %s" % ", ".join(unknown))
    build, filled = build_one(dex, poke, sp, nature, ability, item)
    return build, moves, filled, None


def load_party(dex, path=PARTY_FILE):
    """파일에서 내 파티를 읽는다. [(빌드, [기술이름], 사용률로 채운 것들)]."""
    if not os.path.exists(path):
        return None
    out = []
    with io.open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            build, moves, filled, bad = read_line(dex, line)
            if bad:
                print("! 파티 파일: %s" % bad)
                return None
            out.append((build, moves, filled))
    return out or None


PARTY_HELP = u"""내 파티를 적으세요. 한 줄에 한 마리, 빈 줄이면 끝.

  이름 기술,기술,기술,기술 | 성격 노력치 도구

  예)  한카리아스 지진,역린,화염방사,칼춤 | 명랑 A32S32 한카리아스나이트Z
       아머까오 바디프레스,철벽,날개쉬기,브레이브버드 | 장난꾸러기 H32B32 울퉁불퉁멧

  노력치는 A32S32 처럼 붙여 씁니다 (H체력 A공격 B방어 C특공 D특방 S스피드).
  한 칸에 32까지, 합쳐서 66까지 — 게임의 '능력 포인트' 화면 그대로입니다.
  특성도 적을 수 있습니다 (그 포켓몬이 가질 수 있는 것만 받습니다).
  세로줄(|) 뒤는 안 적어도 되는데, 그러면 **사다리에서 제일 흔한 것**으로
  채웁니다. 내 포켓몬인데 남의 배분으로 계산하게 되니 적는 편이 낫습니다."""


def ask_party(dex):
    print(PARTY_HELP)
    out = []
    while True:
        try:
            line = raw_input_("> ").strip()
        except EOFError:
            break
        if not line:
            break
        build, moves, filled, bad = read_line(dex, line)
        if bad:
            print("  ! %s" % bad)
            continue
        out.append((build, moves, filled))
        print_card(build, moves)
        if filled:
            print("    ← %s 는 사용률로 채웠습니다 — 게임 화면을 보고 적어 주세요"
                  % "·".join(filled))
    if out:
        save_party_file(out)
        print("\n%s 에 저장했습니다. 다음부터는 안 물어봅니다." % PARTY_FILE)
    return out or None


def party_line(build, moves):
    """한 마리를 파일에 적을 한 줄로."""
    return u"%s %s | %s %s %s %s" % (
        build.poke["name"], ",".join(moves),
        build.nature["name"] if build.nature else "",
        ev_text(build.sp), build.ability or "", build.item or "")


def save_party_file(party, path=PARTY_FILE):
    """[(빌드, [기술], 채운것)] 을 파일로. 글자판과 창이 같이 쓴다."""
    with io.open(path, "w", encoding="utf-8") as f:
        f.write(u"# 이름 기술,기술,기술,기술 | 성격 노력치 특성 도구\n")
        for row in party:
            f.write(party_line(row[0], row[1]) + u"\n")
    return path


def ev_text(sp):
    """{'attack':32} -> 'A32'."""
    back = dict((v, k) for k, v in calc.SPREAD_KEY.items())
    got = [(back[k], v) for k, v in sp.items() if v and k in back]
    got.sort(key=lambda x: "HABCDS".index(x[0]))
    return "".join("%s%d" % (k, v) for k, v in got) or "무투자"


# ---------------------------------------------------------------------------
# 게임 화면처럼 보여 주기
# ---------------------------------------------------------------------------
#
# 게임의 능력치 화면을 그대로 옮긴 것이다. 사용자가 그 화면을 보면서
# 적을 테니, **같은 순서·같은 이름**으로 보여 줘야 눈으로 대조할 수 있다.
# 실제로 그 화면과 대조해서 계산기가 6/6 맞는 것을 확인했다 (하마돈).
STAT_ORDER = [("hp", "HP"), ("attack", "공격"), ("defense", "방어"),
              ("spAtk", "특수공격"), ("spDef", "특수방어"), ("speed", "스피드")]


def stat_card(build, moves=None, bar_width=18):
    """한 마리를 게임 화면처럼 그린다. 줄 목록으로 돌려준다.

    ! **한글은 한 글자가 두 칸이다.** 그냥 %-12s 로 맞추면 테두리가
      들쭉날쭉해진다. best._w / best._pad 가 그걸 세어 준다 —
      이미 있는 것을 쓴다.
    """
    W = 46                      # 테두리 안쪽 너비 (칸 기준)

    def row(text):
        return "│ " + best._pad(text, W - 2) + " │"

    def two(left, right):
        half = (W - 2) // 2
        return "│ " + best._pad(left, half) + best._pad(right, W - 2 - half) + " │"

    L = ["┌" + "─" * W + "┐", row(build.name), "├" + "─" * W + "┤"]
    got = "%d/%d" % (sum(build.sp.values()), EV_TOTAL)
    L.append(row(best._pad("능력 포인트", W - 2 - best._w(got)) + got))

    up = (build.nature or {}).get("up")
    down = (build.nature or {}).get("down")
    for key, ko in STAT_ORDER:
        val = build.stat(key)
        ev = build.sp.get(key, 0)
        n = int(round(bar_width * ev / float(EV_MAX)))
        bar = "█" * n + "·" * (bar_width - n)
        mark = "▲" if key == up else ("▼" if key == down else " ")
        # ! 화살표(▲▼)도 한글처럼 두 칸이다. 그래서 여기도 _pad 로 센다.
        head = best._pad(ko, 9) + "%3d" % val + mark + " "
        L.append(row(best._pad(head, 15) + bar + " %2d" % ev))

    L.append("├" + "─" * W + "┤")
    L.append(two("보정  " + ((build.nature or {}).get("name") or "-"),
                 "특성  " + (build.ability or "-")))
    L.append(row("도구  " + (build.item or "없음")))
    if moves:
        L.append("├" + "─" * W + "┤")
        for i in range(0, len(moves), 2):
            pair = moves[i:i + 2]
            L.append(two(pair[0], pair[1] if len(pair) > 1 else ""))
    L.append("└" + "─" * W + "┘")
    return L


def print_card(build, moves=None):
    for line in stat_card(build, moves):
        print("  " + line)


def describe_member(build, moves, filled):
    """한 마리를 한 줄로. **사용률로 채운 것은 반드시 드러낸다.**"""
    out = "%s | %s %s | %s | %s" % (
        build.name, build.nature["name"] if build.nature else "-",
        ev_text(build.sp), build.ability or "-", build.item or "도구없음")
    if moves:
        out += " | " + "/".join(moves)
    else:
        out += " | 기술 안 적음"
    if filled:
        out += "   ← %s 는 사용률로 채웠습니다" % "·".join(filled)
    return out


def raw_input_(prompt):
    sys.stdout.write(prompt)
    sys.stdout.flush()
    line = sys.stdin.readline()
    if not line:
        raise EOFError
    return line.rstrip("\n")



# ---------------------------------------------------------------------------
# 지금 판의 상태
# ---------------------------------------------------------------------------
class Fight(object):
    """한 판 동안 들고 다니는 것. **본 것은 쌓인다.**"""

    def __init__(self, dex, party):
        self.dex = dex
        self.party = party                  # [(빌드, [기술])]
        self.my_active = 0
        self.my_hp = [100.0] * len(party)
        self.opp = None                     # 지금 나와 있는 상대 (포켓몬)
        self.opp_hp = 100.0
        self.seen = {}                      # 상대 이름 -> 본 기술/도구 집합
        self.seconds = DEFAULT_SECONDS
        self.turn = 0
        self.lines = []                     # 기록

    def note(self, text):
        self.lines.append(text)

    def seen_of(self, poke=None):
        key = (poke or self.opp or {}).get("name")
        return self.seen.setdefault(key, set())

    def builds(self):
        return [row[0] for row in self.party]

    def moves(self):
        return self.party[self.my_active][1] or None

    def state(self):
        """탐색에 넘길 '지금 판의 상태'.

        ! **상대 HP 를 빼먹었다가 고쳤다.** 화면에는 '상대 55%' 라고
          찍히는데 계산은 만피로 하고 있었다. 물붓기가 장식이었던 것과
          같은 종류다 — 눈에 보이는 것과 실제로 쓰이는 것이 다르면
          조용히 틀어진다. 넣는 값은 반드시 여기까지 와야 한다.
        """
        return {"my_hp": list(self.my_hp), "my_active": self.my_active,
                "opp_hp": [self.opp_hp]}

    def evidence(self):
        got = self.seen_of()
        if not got:
            return None
        mv = [x for kind, x in got if kind == "기술"]
        it = [x for kind, x in got if kind == "도구"]
        ev = scout.Evidence(seen_moves=mv)
        # Evidence 가 도구를 안 받으면 기술만 준다. 있으면 같이 준다.
        if it and hasattr(ev, "item"):
            ev.item = it[0]
        return ev

    def summary(self):
        me = self.party[self.my_active][0]
        got = sorted(x for _k, x in self.seen_of())
        return ("나 %s %.0f%%   |   상대 %s %.0f%%%s"
                % (me.name, self.my_hp[self.my_active],
                   self.opp["name"] if self.opp else "?", self.opp_hp,
                   ("   본 것: " + ", ".join(got)) if got else ""))


def apply_token(fight, tok):
    """한 낱말을 읽어서 상태에 반영. 사람이 읽을 알림글을 돌려준다."""
    dex = fight.dex
    if tok in (".", "?", "q", "ㅂ"):
        return tok
    if tok.startswith(">"):                  # 내가 교체했다
        poke, note = find_poke(dex, tok[1:])
        if poke is None:
            return "! %s" % (note or "못 찾았습니다")
        for i, row in enumerate(fight.party):
            b = row[0]
            if b.poke["name"] == poke["name"] or b.name == poke["name"]:
                fight.my_active = i
                return "내가 %s 로 바꿨다" % b.name
        return "! %s 는 내 파티에 없습니다" % poke["name"]
    if tok.startswith("+"):                  # 상대에게서 본 것
        kind, name = find_move_or_item(dex, tok[1:])
        if kind is None:
            return "! %s" % name
        fight.seen_of().add((kind, name))
        return "봤다: %s (%s)" % (name, kind)
    if tok.startswith("나"):
        try:
            fight.my_hp[fight.my_active] = float(tok[1:])
            return "내 HP %s%%" % tok[1:]
        except ValueError:
            pass
    if tok.startswith("적"):
        try:
            fight.opp_hp = float(tok[1:])
            return "상대 HP %s%%" % tok[1:]
        except ValueError:
            pass
    if tok.startswith("초"):
        try:
            fight.seconds = max(1.0, float(tok[1:]))
            return "생각할 시간 %.0f초" % fight.seconds
        except ValueError:
            pass
    poke, note = find_poke(dex, tok)         # 상대가 이놈이다
    if poke is not None:
        fresh = fight.opp is None or poke["name"] != fight.opp["name"]
        fight.opp = poke
        if fresh:
            fight.opp_hp = 100.0
        return note or ("상대: %s" % poke["name"])
    return "! '%s' 을 못 알아들었습니다 (? 로 도움말)" % tok


HELP = u"""
  하마돈             상대가 이놈이다 (앞글자만 쳐도 된다)
  +지진 +자뭉열매     상대에게서 본 기술·도구. **쌓인다**
  나70 적40          남은 HP 비율
  >아머까오           내가 이놈으로 바꿨다
  초20               이번 턴만 더 오래 생각한다 (보유시간을 쓸 때)
  .                 그냥 다시 물어본다
  새판                기록을 닫고 새 판을 시작한다
  q                 나가기
"""


# ---------------------------------------------------------------------------
# 한 턴 물어보기
# ---------------------------------------------------------------------------
def advise(fight):
    """지금 상태로 탐색해서 화면에 뿌린다. 화면은 폰에서도 읽히게 좁게."""
    if fight.opp is None:
        return "상대를 먼저 적어 주세요 (예: 하마돈)"
    t0 = time.time()
    got = search.best_action(
        fight.dex, fight.builds(), fight.opp,
        my_moves=fight.moves(), evidence=fight.evidence(),
        seconds=fight.seconds, state=fight.state(),
        seed=fight.turn + 1)
    full = [r for r in got["rows"] if not r["dropped"]] or got["rows"]
    top = max(full, key=lambda r: r["score"])

    L = ["", "  " + fight.summary(), "  " + "-" * 42]
    for r in got["rows"][:6]:
        mark = " (접음)" if r["dropped"] else ""
        L.append("   %-16s %5.1f  ±%.1f  %d판%s"
                 % (r["name"][:16], r["score"] * 100,
                    search._err(r["n"]) * 100, r["n"], mark))
    L.append("  " + "-" * 42)
    L.append("   => %s   (%.1f점 ±%.1f, %d판)"
             % (top["name"], top["score"] * 100,
                search._err(top["n"]) * 100, top["n"]))
    close = [r for r in got["rows"] if r is not top
             and r["score"] + search._err(r["n"])
             >= top["score"] - search._err(top["n"])]
    if close:
        L.append("   ! 겹치는 수: %s — 확실하지 않다"
                 % ", ".join(r["name"] for r in close[:2]))
    if got.get("thin"):
        L.append("   ! 예산이 모자라 제대로 못 잰 수: %s"
                 % ", ".join(got["thin"][:3]))
    if got["shallow"]:
        L.append("   ! 끝까지 못 보고 끊었다 — 초20 처럼 늘려 보세요")
    if got["guessed"]:
        L.append("   ! 내 기술을 사용률로 짐작했다 (파티 파일에 적으세요)")
    L.append("   (%.1f초)" % (time.time() - t0))

    fight.note("[%d턴] %s" % (fight.turn, fight.summary()))
    for r in got["rows"]:
        fight.note("    %-18s %5.1f  %d판%s"
                   % (r["name"], r["score"] * 100, r["n"],
                      " (접음)" if r["dropped"] else ""))
    fight.note("    => %s" % top["name"])
    return "\n".join(L)


def save_log(fight):
    if not fight.lines:
        return None
    try:
        os.makedirs(LOG_DIR)
    except OSError:
        pass
    path = os.path.join(LOG_DIR,
                        time.strftime("%Y%m%d-%H%M%S") + ".txt")
    with io.open(path, "w", encoding="utf-8") as f:
        f.write(u"# 실전 기록 — %s\n" % time.strftime("%Y-%m-%d %H:%M"))
        f.write(u"# 내 파티: %s\n\n"
                % ", ".join(describe_member(b, m, f2)
                            for b, m, f2 in fight.party))
        f.write(u"\n".join(fight.lines) + u"\n")
    return path


def main():
    paths.fix_console()
    print("=" * 46)
    print("  포켓몬 챔피언스 — 무엇을 둘까")
    print("=" * 46)
    dex = calc.Dex()
    party = load_party(dex)
    if party:
        print("내 파티 (%s)\n" % PARTY_FILE)
        for build, moves, filled in party:
            print_card(build, moves)
            if filled:
                print("    ← %s 는 사용률로 채웠습니다" % "·".join(filled))
            print("")
        guessed = sorted(set(x for _b, _m, f in party for x in (f or [])))
        if guessed:
            print("")
            print("  ! %s 를 사용률로 채웠습니다. 내 포켓몬인데 남의 값으로"
                  % "·".join(guessed))
            print("    계산하게 됩니다. %s 를 고쳐서 적어 주세요 —"
                  % PARTY_FILE)
            print("    예)  한카리아스 지진,역린 | 명랑 A32S32 기합의띠")
    else:
        party = ask_party(dex)
    if not party:
        print("파티가 없어 끝냅니다.")
        return

    # **첫 턴 전에 캐시를 덥혀 둔다.** 처음 한 판은 2ms 가 아니라
    # 400ms 넘게 걸린다 (형태 모델·도구 규칙·데미지 표를 처음 만든다).
    # 그대로 두면 1턴에 탐색이 "예산이 모자라다" 고 판단해 얕게 돌고,
    # 점수가 전부 만점처럼 나온다. 여기서 미리 데워 두면 그 일이 없다.
    print("\n준비 중입니다 (처음 한 번만 걸립니다)...")
    t0 = time.time()
    try:
        search.best_action(dex, [row[0] for row in party], party[0][0].poke,
                           my_moves=party[0][1] or None, seconds=1.0)
    except Exception as e:
        print("  ! 준비 중에 문제가 있었습니다: %s" % e)
    print("  준비 끝 (%.1f초)" % (time.time() - t0))

    fight = Fight(dex, party)
    print(HELP)
    print("상대가 무엇인지 적으면 시작합니다.")
    while True:
        try:
            line = raw_input_("\n%d> " % (fight.turn + 1)).strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not line:
            continue
        stop = False
        for tok in line.split():
            got = apply_token(fight, tok)
            if got in ("q", "ㅂ"):
                stop = True
                break
            if got == "?":
                print(HELP)
                got = None
            if tok == "새판":
                path = save_log(fight)
                if path:
                    print("  기록: %s" % path)
                fight = Fight(dex, party)
                print("  새 판을 시작합니다.")
                got = None
            if got and got != ".":
                print("  %s" % got)
        if stop:
            break
        if fight.opp is not None:
            fight.turn += 1
            print(advise(fight))

    path = save_log(fight)
    if path:
        print("\n기록을 남겼습니다: %s" % path)
        print("진 판이면 그 파일을 대화창에 가져오면 왜 졌는지 볼 수 있습니다.")


def _wait_before_closing():
    """**더블클릭으로 켰을 때 창이 바로 닫히지 않게 한다.**

    터미널에서 켰으면 그냥 끝나면 되지만, 실행 파일을 두 번 눌러서
    켰으면 창이 순식간에 사라져서 무슨 일이 있었는지 못 본다.
    오류가 났을 때 특히 그렇다.
    """
    if not paths.frozen():
        return
    try:
        raw_input_("\n창을 닫으려면 엔터를 누르세요. ")
    except (EOFError, KeyboardInterrupt):
        pass


if __name__ == "__main__":
    try:
        main()
    except Exception:
        # 묶인 프로그램에서 오류가 나면 창이 닫히기 전에 보여 준다.
        import traceback
        print("\n문제가 생겼습니다 — 아래를 통째로 알려 주시면 고칩니다.\n")
        traceback.print_exc()
    _wait_before_closing()
