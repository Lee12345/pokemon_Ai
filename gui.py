# -*- coding: utf-8 -*-
"""창으로 쓰는 실전 도구 — 게임의 능력치 화면처럼.

    python3 gui.py          창을 연다
    python3 gui.py --점검    창을 안 띄우고 짜임새만 확인한다

## 왜 `--점검` 이 있나

**이 창은 리눅스에서 만들어졌는데 리눅스에서 볼 수가 없다.**
개발 컨테이너에 `tkinter` 도 화면도 없다. 윈도우에서만 돌아간다.

지금까지 윈도우에서만 나는 고장을 네 번 만났다 (CLAUDE.md §9).
창 UI 는 그보다 더 나올 수 있다. 그래서 **창을 띄우지 않고 위젯을
전부 만들어 보는 모드**를 넣었다. 깃허브의 윈도우가 그걸 돌려서
"만들다가 터지지는 않는지" 를 본다. 눌러 봐야 아는 것은 여전히
사용자가 확인해야 하지만, 적어도 켜자마자 죽는 일은 막는다.

## 짜임새

계산은 전부 이미 시험된 곳(`live` · `search` · `calc`)에 있다.
여기는 **보여 주고 받아 적는 일만** 한다. 그래야 창에서 고장이 나도
계산이 틀어지지 않는다.
"""

import os
import sys
import threading

import best
import calc
import live
import paths
import scout
import search


# 게임 화면 느낌의 색
BG = "#2b2b3a"
CARD = "#3a3a4e"
LINE = "#4d4d66"
TEXT = "#e8e8f0"
DIM = "#a0a0b8"
BAR = "#f0a830"
BAR_BG = "#22222e"
GOOD = "#5fd18c"
WARN = "#f07070"

STAT_ORDER = live.STAT_ORDER


def have_tk():
    """tkinter 가 있나. 없으면 왜 없는지도 알려 준다."""
    try:
        import tkinter  # noqa: F401
        return True, None
    except ImportError as e:
        return False, str(e)


class App(object):
    """창 하나. 위젯을 만드는 일과 계산을 부르는 일만 한다."""

    def __init__(self, dex, headless=False):
        import tkinter as tk
        from tkinter import ttk

        self.tk = tk
        self.ttk = ttk
        self.dex = dex
        self.headless = headless
        self.party = live.load_party(dex) or []
        self.fight = None
        self.busy = False

        self.root = tk.Tk()
        self.root.title("포켓몬 챔피언스 — 무엇을 둘까")
        self.root.configure(bg=BG)
        if headless:
            # 점검 모드 — 화면이 없어도 위젯은 다 만들어 본다
            self.root.withdraw()

        self._build()

    # -- 만들기 -----------------------------------------------------------
    def _build(self):
        tk = self.tk
        outer = tk.Frame(self.root, bg=BG, padx=12, pady=10)
        outer.pack(fill="both", expand=True)

        tk.Label(outer, text="포켓몬 챔피언스 — 무엇을 둘까",
                 bg=BG, fg=TEXT, font=("Malgun Gothic", 15, "bold")
                 ).pack(anchor="w")

        body = tk.Frame(outer, bg=BG)
        body.pack(fill="both", expand=True, pady=(8, 0))

        self.left = tk.Frame(body, bg=BG)
        self.left.pack(side="left", fill="y")
        self.right = tk.Frame(body, bg=BG)
        self.right.pack(side="left", fill="both", expand=True, padx=(12, 0))

        self._build_party(self.left)
        self._build_turn(self.right)

    def _card(self, parent, title):
        tk = self.tk
        box = tk.Frame(parent, bg=CARD, highlightbackground=LINE,
                       highlightthickness=1, padx=10, pady=8)
        box.pack(fill="x", pady=(0, 8))
        tk.Label(box, text=title, bg=CARD, fg=DIM,
                 font=("Malgun Gothic", 9)).pack(anchor="w")
        return box

    def _build_party(self, parent):
        """내 파티 — 게임의 능력치 화면처럼 그린다."""
        tk = self.tk
        self.party_box = self._card(parent, "내 파티")
        self.party_rows = tk.Frame(self.party_box, bg=CARD)
        self.party_rows.pack(fill="x")
        self._draw_party()

        edit = tk.Frame(self.party_box, bg=CARD)
        edit.pack(fill="x", pady=(6, 0))
        tk.Label(edit, text="한 줄에 한 마리:", bg=CARD, fg=DIM,
                 font=("Malgun Gothic", 9)).pack(anchor="w")
        self.party_text = tk.Text(edit, height=5, width=52, bg=BAR_BG,
                                  fg=TEXT, insertbackground=TEXT,
                                  font=("Malgun Gothic", 9),
                                  relief="flat", padx=6, pady=4)
        self.party_text.pack(fill="x")
        self.party_text.insert("1.0", self._party_as_text())
        tk.Label(edit,
                 text="이름 기술,기술,기술,기술 | 성격 노력치 특성 도구",
                 bg=CARD, fg=DIM, font=("Malgun Gothic", 8)).pack(anchor="w")
        tk.Button(edit, text="이대로 저장", command=self.save_party,
                  bg=LINE, fg=TEXT, relief="flat",
                  font=("Malgun Gothic", 9)).pack(anchor="e", pady=(4, 0))
        self.party_msg = tk.Label(edit, text="", bg=CARD, fg=WARN,
                                  font=("Malgun Gothic", 9),
                                  wraplength=380, justify="left")
        self.party_msg.pack(anchor="w")

    def _party_as_text(self):
        out = []
        for build, moves, _f in self.party:
            out.append("%s %s | %s %s %s %s"
                       % (build.poke["name"], ",".join(moves),
                          build.nature["name"] if build.nature else "",
                          live.ev_text(build.sp), build.ability or "",
                          build.item or ""))
        return "\n".join(out)

    def _draw_party(self):
        """능력치 카드들을 다시 그린다."""
        tk = self.tk
        for w in self.party_rows.winfo_children():
            w.destroy()
        if not self.party:
            tk.Label(self.party_rows, text="아직 없습니다 — 아래에 적으세요",
                     bg=CARD, fg=DIM, font=("Malgun Gothic", 9)).pack()
            return
        for i, (build, moves, filled) in enumerate(self.party):
            self._draw_one(self.party_rows, i, build, moves, filled)

    def _draw_one(self, parent, idx, build, moves, filled):
        tk = self.tk
        box = tk.Frame(parent, bg=CARD)
        box.pack(fill="x", pady=(4, 6))

        head = tk.Frame(box, bg=CARD)
        head.pack(fill="x")
        tk.Label(head, text="%d. %s" % (idx + 1, build.name), bg=CARD,
                 fg=TEXT, font=("Malgun Gothic", 11, "bold")).pack(side="left")
        tk.Label(head, text="능력 포인트 %d/%d"
                 % (sum(build.sp.values()), live.EV_TOTAL),
                 bg=CARD, fg=DIM, font=("Malgun Gothic", 9)).pack(side="right")

        up = (build.nature or {}).get("up")
        down = (build.nature or {}).get("down")
        for key, ko in STAT_ORDER:
            row = tk.Frame(box, bg=CARD)
            row.pack(fill="x")
            mark = " ▲" if key == up else (" ▼" if key == down else "")
            tk.Label(row, text=ko, width=6, anchor="w", bg=CARD, fg=DIM,
                     font=("Malgun Gothic", 9)).pack(side="left")
            tk.Label(row, text="%d%s" % (build.stat(key), mark), width=7,
                     anchor="e", bg=CARD,
                     fg=(GOOD if key == up else
                         (WARN if key == down else TEXT)),
                     font=("Malgun Gothic", 9)).pack(side="left")
            ev = build.sp.get(key, 0)
            cv = tk.Canvas(row, width=150, height=10, bg=BAR_BG,
                           highlightthickness=0)
            cv.pack(side="left", padx=6)
            if ev:
                cv.create_rectangle(
                    0, 0, 150.0 * ev / live.EV_MAX, 10, fill=BAR, width=0)
            tk.Label(row, text="%d" % ev, width=3, anchor="e", bg=CARD,
                     fg=DIM, font=("Malgun Gothic", 9)).pack(side="left")

        foot = "보정 %s   특성 %s   도구 %s" % (
            (build.nature or {}).get("name", "-"),
            build.ability or "-", build.item or "없음")
        tk.Label(box, text=foot, bg=CARD, fg=DIM,
                 font=("Malgun Gothic", 9)).pack(anchor="w")
        if moves:
            tk.Label(box, text="   ".join(moves), bg=CARD, fg=TEXT,
                     font=("Malgun Gothic", 9)).pack(anchor="w")
        if filled:
            tk.Label(box, text="← %s 는 사용률로 채웠습니다" % "·".join(filled),
                     bg=CARD, fg=WARN,
                     font=("Malgun Gothic", 9)).pack(anchor="w")

    def _build_turn(self, parent):
        tk = self.tk
        box = self._card(parent, "이번 턴")

        line = tk.Frame(box, bg=CARD)
        line.pack(fill="x", pady=(4, 0))
        tk.Label(line, text="상대", bg=CARD, fg=DIM,
                 font=("Malgun Gothic", 9)).pack(side="left")
        self.opp_var = tk.StringVar()
        tk.Entry(line, textvariable=self.opp_var, width=14, bg=BAR_BG,
                 fg=TEXT, insertbackground=TEXT, relief="flat",
                 font=("Malgun Gothic", 10)).pack(side="left", padx=6)

        tk.Label(line, text="내 HP%", bg=CARD, fg=DIM,
                 font=("Malgun Gothic", 9)).pack(side="left")
        self.my_hp = tk.StringVar(value="100")
        tk.Entry(line, textvariable=self.my_hp, width=5, bg=BAR_BG, fg=TEXT,
                 insertbackground=TEXT, relief="flat",
                 font=("Malgun Gothic", 10)).pack(side="left", padx=(4, 8))
        tk.Label(line, text="상대 HP%", bg=CARD, fg=DIM,
                 font=("Malgun Gothic", 9)).pack(side="left")
        self.opp_hp = tk.StringVar(value="100")
        tk.Entry(line, textvariable=self.opp_hp, width=5, bg=BAR_BG, fg=TEXT,
                 insertbackground=TEXT, relief="flat",
                 font=("Malgun Gothic", 10)).pack(side="left", padx=4)

        line2 = tk.Frame(box, bg=CARD)
        line2.pack(fill="x", pady=(6, 0))
        tk.Label(line2, text="본 것", bg=CARD, fg=DIM,
                 font=("Malgun Gothic", 9)).pack(side="left")
        self.seen_var = tk.StringVar()
        tk.Entry(line2, textvariable=self.seen_var, width=30, bg=BAR_BG,
                 fg=TEXT, insertbackground=TEXT, relief="flat",
                 font=("Malgun Gothic", 10)).pack(side="left", padx=6)
        tk.Label(line2, text="초", bg=CARD, fg=DIM,
                 font=("Malgun Gothic", 9)).pack(side="left")
        self.secs = tk.StringVar(value="10")
        tk.Entry(line2, textvariable=self.secs, width=4, bg=BAR_BG, fg=TEXT,
                 insertbackground=TEXT, relief="flat",
                 font=("Malgun Gothic", 10)).pack(side="left", padx=4)

        line3 = tk.Frame(box, bg=CARD)
        line3.pack(fill="x", pady=(6, 0))
        tk.Label(line3, text="나와 있는 내 포켓몬", bg=CARD, fg=DIM,
                 font=("Malgun Gothic", 9)).pack(side="left")
        self.active = tk.StringVar(value="1")
        tk.Entry(line3, textvariable=self.active, width=4, bg=BAR_BG, fg=TEXT,
                 insertbackground=TEXT, relief="flat",
                 font=("Malgun Gothic", 10)).pack(side="left", padx=6)
        self.go = tk.Button(line3, text="무엇을 둘까?", command=self.ask,
                            bg=BAR, fg="#2b2b3a", relief="flat",
                            font=("Malgun Gothic", 10, "bold"))
        self.go.pack(side="right")

        self.out = tk.Text(parent, height=22, bg=BAR_BG, fg=TEXT,
                           font=("Malgun Gothic", 10), relief="flat",
                           padx=8, pady=6, wrap="word")
        self.out.pack(fill="both", expand=True)
        self.say("파티를 확인하고, 상대 이름을 적은 뒤 '무엇을 둘까?' 를 누르세요.")

    # -- 움직이기 ---------------------------------------------------------
    def say(self, text, clear=False):
        if clear:
            self.out.delete("1.0", "end")
        self.out.insert("end", text + "\n")
        self.out.see("end")

    def save_party(self):
        lines = self.party_text.get("1.0", "end").strip().splitlines()
        out, bad = [], []
        for line in lines:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            build, moves, filled, why = live.read_line(self.dex, line)
            if why:
                bad.append("%s — %s" % (line.split()[0], why))
                continue
            out.append((build, moves, filled))
        if bad:
            self.party_msg.config(text="\n".join(bad), fg=WARN)
            return
        if not out:
            self.party_msg.config(text="한 마리도 못 읽었습니다", fg=WARN)
            return
        self.party = out
        live.save_party_file(out)
        self.party_msg.config(text="저장했습니다 (%s)" % live.PARTY_FILE,
                              fg=GOOD)
        self._draw_party()

    def ask(self):
        """탐색은 **다른 갈래에서 돌린다.** 안 그러면 창이 10초 동안 언다."""
        if self.busy:
            return
        if not self.party:
            self.say("먼저 파티를 저장하세요.", clear=True)
            return
        poke, note = live.find_poke(self.dex, self.opp_var.get().strip())
        if poke is None:
            self.say("상대를 못 찾았습니다: %s" % (note or ""), clear=True)
            return

        try:
            idx = max(0, min(len(self.party) - 1, int(self.active.get()) - 1))
        except ValueError:
            idx = 0
        my_hp = [100.0] * len(self.party)
        try:
            my_hp[idx] = float(self.my_hp.get())
        except ValueError:
            pass
        try:
            opp_hp = float(self.opp_hp.get())
        except ValueError:
            opp_hp = 100.0
        try:
            secs = max(1.0, float(self.secs.get()))
        except ValueError:
            secs = 10.0

        seen_moves = []
        for word in self.seen_var.get().replace(",", " ").split():
            kind, name = live.find_move_or_item(self.dex, word)
            if kind == "기술":
                seen_moves.append(name)
        ev = scout.Evidence(seen_moves=seen_moves) if seen_moves else None

        self.busy = True
        self.go.config(text="생각하는 중...", state="disabled")
        self.say("%s 을(를) 상대로 %.0f초 생각합니다...%s"
                 % (poke["name"], secs,
                    ("  (본 것: %s)" % ", ".join(seen_moves))
                    if seen_moves else ""), clear=True)

        state = {"my_hp": my_hp, "my_active": idx, "opp_hp": [opp_hp]}
        args = (poke, ev, secs, state, idx)
        if self.headless:
            self._work(*args)              # 점검 모드는 그냥 돌린다
        else:
            threading.Thread(target=self._work, args=args,
                             daemon=True).start()

    def _work(self, poke, ev, secs, state, idx):
        try:
            got = search.best_action(
                self.dex, [row[0] for row in self.party], poke,
                my_moves=self.party[idx][1] or None, evidence=ev,
                seconds=secs, state=state)
        except Exception as e:
            import traceback
            got = None
            text = "문제가 생겼습니다:\n%s" % traceback.format_exc()
        if got is not None:
            text = self._format(got)
        # 창은 만든 갈래에서만 건드린다
        if self.headless:
            self._show(text)
        else:
            self.root.after(0, lambda: self._show(text))

    def _show(self, text):
        self.say(text)
        self.busy = False
        self.go.config(text="무엇을 둘까?", state="normal")

    def _format(self, got):
        rows = got["rows"]
        full = [r for r in rows if not r["dropped"]] or rows
        top = max(full, key=lambda r: r["score"])
        L = ["", "%-18s %6s %8s %7s" % ("수", "점수", "판수", "오차")]
        L.append("-" * 44)
        for r in rows[:7]:
            L.append("%-18s %5.1f %8d  ±%4.1f%s"
                     % (r["name"][:18], r["score"] * 100, r["n"],
                        search._err(r["n"]) * 100,
                        "  (접음)" if r["dropped"] else ""))
        L.append("-" * 44)
        L.append("=> %s   (%.1f점 ±%.1f, %d판)"
                 % (top["name"], top["score"] * 100,
                    search._err(top["n"]) * 100, top["n"]))
        close = [r for r in rows if r is not top
                 and r["score"] + search._err(r["n"])
                 >= top["score"] - search._err(top["n"])]
        if close:
            L.append("! 겹치는 수: %s — 확실하지 않습니다"
                     % ", ".join(r["name"] for r in close[:2]))
        if got.get("thin"):
            L.append("! 예산이 모자라 제대로 못 잰 수: %s"
                     % ", ".join(got["thin"][:3]))
        if got["shallow"]:
            L.append("! 끝까지 못 보고 끊었습니다 — 초를 늘려 보세요")
        if got["guessed"]:
            L.append("! 내 기술을 사용률로 짐작했습니다")
        return "\n".join(L)

    def run(self):
        self.root.mainloop()


def check():
    """창을 안 띄우고 **짜임새만** 확인한다. 빌드가 이걸 돌린다."""
    ok, why = have_tk()
    if not ok:
        print("tkinter 가 없습니다: %s" % why)
        return 1
    dex = calc.Dex()
    app = App(dex, headless=True)
    # 위젯이 다 만들어졌는지
    need = ["party_text", "opp_var", "my_hp", "opp_hp", "secs", "out", "go"]
    missing = [n for n in need if not hasattr(app, n)]
    if missing:
        print("위젯이 빠졌습니다: %s" % missing)
        return 1
    # 파티를 실제로 읽어서 그려 보는가
    app.party_text.delete("1.0", "end")
    app.party_text.insert(
        "1.0", "하마돈 지진,하품,게으름피우기,스텔스록 | 무사태평 H32B22D12 모래날림 자뭉열매")
    app.save_party()
    if not app.party:
        print("파티를 못 읽었습니다: %s" % app.party_msg.cget("text"))
        return 1
    got = app.party[0][0]
    if got.stat("defense") != 176:
        print("능력치가 게임 화면과 다릅니다: 방어 %d" % got.stat("defense"))
        return 1
    # 한 턴 물어보기까지 돌려 본다 (짧게)
    app.opp_var.set("한카리아스")
    app.secs.set("2")
    app.ask()
    text = app.out.get("1.0", "end")
    if "=>" not in text:
        print("추천이 안 나왔습니다:\n%s" % text)
        return 1
    print("창 짜임새 확인 끝 — 파티 · 능력치 · 추천까지 돌았습니다")
    print(text.strip().splitlines()[-1])
    app.root.destroy()
    return 0


def main():
    paths.fix_console()
    if "--점검" in sys.argv or "--check" in sys.argv:
        sys.exit(check())
    ok, why = have_tk()
    if not ok:
        print("이 컴퓨터의 파이썬에는 창을 그리는 부품(tkinter)이 없습니다.")
        print("  %s" % why)
        print("글자판으로 쓰시려면:  python3 live.py")
        return
    dex = calc.Dex()
    App(dex).run()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        print("\n문제가 생겼습니다 — 아래를 통째로 알려 주시면 고칩니다.\n")
        traceback.print_exc()
    if paths.frozen():
        try:
            live.raw_input_("\n창을 닫으려면 엔터를 누르세요. ")
        except (EOFError, KeyboardInterrupt):
            pass
