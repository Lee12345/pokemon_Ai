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
import sys
import time

import battle
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
def load_party(dex, path=PARTY_FILE):
    """파일에서 내 파티를 읽는다. [(빌드, [기술이름])]."""
    if not os.path.exists(path):
        return None
    out = []
    with io.open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            bits = line.split(None, 1)
            poke, _note = find_poke(dex, bits[0])
            if poke is None:
                print("! 파티 파일에서 '%s' 을 못 읽었습니다" % bits[0])
                return None
            moves = []
            if len(bits) > 1:
                for m in bits[1].replace(",", " ").split():
                    kind, name = find_move_or_item(dex, m)
                    if kind != "기술":
                        print("! '%s' 을 기술로 못 읽었습니다 (%s)"
                              % (m, name if kind is None else kind))
                        return None
                    moves.append(name)
            build = calc.popular_build(dex, poke)[0]
            out.append((build, moves))
    return out or None


def ask_party(dex):
    print("내 파티를 적으세요. 한 줄에 한 마리, 빈 줄이면 끝.")
    print("  예)  한카리아스 지진,역린,화염방사,칼춤")
    out = []
    while True:
        try:
            line = raw_input_("> ").strip()
        except EOFError:
            break
        if not line:
            break
        bits = line.split(None, 1)
        poke, note = find_poke(dex, bits[0])
        if poke is None:
            print("  ! %s" % (note or "못 찾았습니다"))
            continue
        moves = []
        bad = False
        for m in (bits[1].replace(",", " ").split() if len(bits) > 1 else []):
            kind, name = find_move_or_item(dex, m)
            if kind != "기술":
                print("  ! %s" % (name if kind is None else "'%s' 은 기술이 아닙니다" % m))
                bad = True
                break
            moves.append(name)
        if bad:
            continue
        build = calc.popular_build(dex, poke)[0]
        out.append((build, moves))
        print("  %s%s" % (build.name, (" — " + "/".join(moves)) if moves else
                          "  (기술을 안 적어서 사용률로 짐작합니다)"))
    if out:
        try:
            os.makedirs(os.path.dirname(PARTY_FILE))
        except OSError:
            pass
        with io.open(PARTY_FILE, "w", encoding="utf-8") as f:
            for build, moves in out:
                f.write("%s %s\n" % (build.poke["name"], ",".join(moves)))
        print("\n%s 에 저장했습니다. 다음부터는 안 물어봅니다." % PARTY_FILE)
    return out or None


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
        return [b for b, _m in self.party]

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
        for i, (b, _m) in enumerate(fight.party):
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
                % ", ".join(b.name for b, _m in fight.party))
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
        print("내 파티 (%s):" % PARTY_FILE)
        for b, m in party:
            print("  %s — %s" % (b.name, "/".join(m) if m
                                 else "기술 안 적음 (사용률로 짐작)"))
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
        search.best_action(dex, [b for b, _m in party], party[0][0].poke,
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
