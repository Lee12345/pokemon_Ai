# -*- coding: utf-8 -*-
"""화면을 계속 읽어 판을 따라간다 — 「따라가기」.

    python watch.py            (혼자 돌려 보기 — 읽은 것을 줄마다 찍는다)

창(`gui.py`)은 이 모듈을 부르기만 한다. 판단은 전부 여기 둔다
(CLAUDE.md §9 「창에는 계산을 두지 않는다」 — 창 없이 검사할 수 있어야 한다).

## 왜 이 모듈이 따로 있나

사진 한 장을 읽는 것(`screenread`)과 **한 판을 따라가는 것**은 다르다. 실전 두 판을
기록해 보니(2026-09-23, 903 + 832 프레임) 따라가려면 세 가지가 더 필요했다 —

1. **두 장 연속 같을 때만 믿는다.** 연출 중간에 찍힌 장면은 HP 막대가 줄어드는 도중이고
   문구도 한 글자씩 나온다. 같은 값이 두 번 나와야 그 값이 자리를 잡은 것이다.
2. **같은 일을 두 번 넣지 않는다.** 한 문구가 몇 초씩 떠 있으므로 같은 장면이 대여섯 번
   읽힌다. 「지진!」 을 여섯 번 넣으면 안 된다.
3. **신호가 없으면 말한다.** 캡처보드가 끊기면 까만 화면에 알림창만 뜬다. 그냥 '아무것도
   안 읽힘' 으로 두면 사용자는 도구가 멈춘 줄 안다.

## 잰 것 (2026-09-23, OBS 창 프로젝터 2448x1377)

- 한 장 찍고 읽기까지 **0.47초.**
- 신호 없음 화면은 **95.6%** 가 까맣다. 진짜 게임 화면은 **0.6~13.1%.** → 80% 로 가른다.
"""

import os
import sys
import time

import paths
import pngio
import screenread

NO_SIGNAL = 0.80        # 이만큼 까만 화면이면 신호가 없는 것으로 본다


def _signature(got):
    """읽은 것을 짧은 열쇠로 — 이게 두 번 같으면 믿는다. 믿을 게 없으면 None."""
    if got is None:
        return None
    if got.get("kind") == "선출":
        return ("선출",) + tuple(o.get("key") for o in got.get("opp", []))
    if got.get("kind") == "상태확인":
        return ("상태확인", tuple(got.get("mine") or ()), got.get("opp_hp"))
    ev = got.get("event")
    if not ev or ev.get("kind") == "못 읽음":
        return None
    return ("대전", ev.get("kind"), ev.get("mon"), ev.get("side"), ev.get("move"),
            ev.get("stat"), ev.get("type"), ev.get("item"), ev.get("ability"))


def _hp_signature(got):
    """HP 열쇠. 상대는 **막대와 글자를 맞댄 값**, 내 쪽은 「145/215」 숫자."""
    if got is None or got.get("kind") != "대전":
        return None
    hp, _why = screenread.combine_hp(got.get("opp_hp"), got.get("opp_hp_text"))
    mine = got.get("my_hp")
    if hp is None and mine is None:
        return None
    return (None if hp is None else round(hp), mine)


class Watcher(object):
    """한 판을 따라간다. `source` 는 `.grab() -> (사진 자리, 너비, 높이, 점들)` 이면 된다."""

    def __init__(self, source=None, title=None, log=None):
        self.source = source if source is not None else screenread.Window(
            title or screenread.PROJECTOR)
        self.reset()
        self.frames = 0
        self.trouble = None
        # 판이 끝난 뒤 "뭘 어떻게 읽었나" 를 다시 볼 수 있게 남긴다 (창은 글이 밀려 올라간다)
        self.log = log
        self._say("─── 시작 %s ───" % time.strftime("%Y-%m-%d %H:%M:%S"))

    def _say(self, text):
        if not self.log:
            return
        try:
            with open(self.log, "a", encoding="utf-8") as f:
                f.write("%s  %s\n" % (time.strftime("%H:%M:%S"), text))
        except OSError:
            self.log = None     # 못 쓰면 조용히 그만둔다 — 기록 때문에 따라가기가 멈추면 안 된다

    def reset(self):
        """새 판. 넣은 것을 잊는다 (안 잊으면 다음 판에서 같은 일을 안 넣는다)."""
        self.pending = self.applied = None
        self.pending_hp = self.applied_hp = None

    def _forget(self):
        """화면을 못 읽었으면 **기다리던 것을 버린다** — 끊긴 앞뒤 두 장을 같다고 보면 안 된다."""
        self.pending = self.pending_hp = None

    def step(self, board, dex, names):
        """한 장 찍어 읽고, 믿을 만한 것만 판에 넣는다.

        → {"trouble": None 또는 알림, "notes": [(넣었나, 한 줄)], "changed": 판이 바뀌었나,
           "kind": 화면 종류, "size": (너비, 높이), "lines": 문구 줄들}
        """
        out = {"trouble": None, "notes": [], "changed": False,
               "kind": None, "size": None, "lines": []}
        try:
            path, w, h, px = self.source.grab()
        except Exception as e:
            self.trouble = "화면을 못 찍었습니다 — %s" % e
            out["trouble"] = self.trouble
            self._say("! " + self.trouble)
            self._forget()
            return out
        self.frames += 1
        out["size"] = (w, h)
        share = pngio.dark_share(w, h, px)
        if share >= NO_SIGNAL:
            self.trouble = ("신호가 없습니다 (화면의 %.0f%% 가 까맣습니다) — "
                            "캡처보드나 게임기를 봐 주세요" % (share * 100))
            out["trouble"] = self.trouble
            self._say("! " + self.trouble)
            self._forget()
            return out
        self.trouble = None
        got = screenread.read_screen(path, dex, names, img=(w, h, px))
        out["kind"] = got.get("kind")
        out["lines"] = got.get("lines") or []

        sig = _signature(got)
        if sig is not None and sig == self.pending and sig != self.applied:
            out["notes"] += self._put(board, got, dex)
            self.applied = sig
            out["changed"] = True
        hp_sig = _hp_signature(got)
        if hp_sig is not None and hp_sig == self.pending_hp and hp_sig != self.applied_hp:
            notes = screenread.apply_hp(board, got)
            if notes:
                out["notes"] += notes
                out["changed"] = True
            self.applied_hp = hp_sig
        self.pending, self.pending_hp = sig, hp_sig
        for ok, text in out["notes"]:
            self._say("%s %s" % ("O" if ok else "-", text))
        return out

    def _put(self, board, got, dex):
        if got.get("kind") == "선출":
            return screenread.apply_preview(board, got.get("opp", []), dex)
        if got.get("kind") == "상태확인":
            return screenread.apply_status(board, got, dex)
        ev = got.get("event")
        return screenread.apply(board, ev, dex) if ev else []


def main(argv):
    """혼자 돌려 보기 — 창 없이 읽은 것만 찍는다."""
    paths.fix_console()
    import calc
    import msgread
    secs = float(argv[0]) if argv else 60.0
    dex = calc.Dex()
    names = msgread.Names(dex, [])
    board = screenread.Board([{"poke": None, "hp": 100.0, "brought": False} for _ in range(6)],
                             [{"poke": None, "hp": 100.0, "brought": False} for _ in range(6)])
    w = Watcher()
    end = time.time() + secs
    said = None
    while time.time() < end:
        got = w.step(board, dex, names)
        if got["trouble"]:
            if got["trouble"] != said:
                print("! %s" % got["trouble"])
                said = got["trouble"]
            time.sleep(1.0)
            continue
        said = None
        for ok, text in got["notes"]:
            print("  %s %s" % ("O" if ok else "-", text))
    print("프레임 %d개" % w.frames)
    screenread.stop_worker()


if __name__ == "__main__":
    main(sys.argv[1:])
