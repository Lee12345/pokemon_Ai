# -*- coding: utf-8 -*-
"""창으로 쓰는 실전 도구 — 게임의 능력치 화면처럼.

    python3 gui.py          창을 연다
    python3 gui.py --점검    창을 안 띄우고 짜임새만 확인한다

## 어떻게 적나

**한 줄씩 타자로 적지 않는다.** 칸마다 치면 후보가 뜨고 골라 넣는다.
사용자가 그렇게 해 달라고 했다 (2026-09-18).

  포켓몬  치면 후보 (231마리, 메가는 도구로 정해지므로 안 보인다)
  성격    25개 중에서 (무엇이 오르내리는지 같이 보여 준다)
  특성    **그 포켓몬이 가질 수 있는 것만**
  도구    166개 중에서
  기술    **그 포켓몬이 배울 수 있는 것만** (하마돈이면 51개)
  노력치  칸마다 0~32, 합계가 게임처럼 66/66 으로 보인다

## 왜 `--점검` 이 있나

**이 창은 리눅스에서 만들어졌는데 리눅스에서 볼 수가 없다.**
개발 컨테이너에 `tkinter` 도 화면도 없다. 윈도우에서만 돌아간다.

지금까지 윈도우에서만 나는 고장을 네 번 만났다 (CLAUDE.md §9).
그래서 **창을 띄우지 않고 위젯을 전부 만들어 보는 모드**를 넣었다.
깃허브의 윈도우가 그걸 돌려서 만들다가 터지지는 않는지 본다.

## 짜임새

고르는 규칙(무엇이 먼저 오나, 무엇을 보여 주나)은 **`live.py` 에 있고
거기서 시험한다.** 창은 보여 주고 받아 적는 일만 한다. 그래야 창에서
고장이 나도 계산이 틀어지지 않는다.
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
FIELD = "#22222e"
TEXT = "#e8e8f0"
DIM = "#a0a0b8"
BAR = "#f0a830"
GOOD = "#5fd18c"
WARN = "#f07070"

FONT = ("Malgun Gothic", 10)
FONT_S = ("Malgun Gothic", 9)
FONT_B = ("Malgun Gothic", 11, "bold")

STAT_ORDER = live.STAT_ORDER


def have_tk():
    """tkinter 가 있나. 없으면 왜 없는지도 알려 준다."""
    try:
        import tkinter  # noqa: F401
        return True, None
    except ImportError as e:
        return False, str(e)


class Picker(object):
    """치면 후보가 뜨고, 고르면 칸에 들어가는 입력칸.

    ! **tkinter 에는 이런 부품이 없다.** Entry + Listbox 를 손으로
      붙여야 한다. 고르는 규칙(무엇이 먼저 오나)은 `live.rank_hits`
      에 있고 거기서 시험한다 — 창은 보여 주기만 한다.
    """

    def __init__(self, parent, tk, label, width=16, on_pick=None,
                 rows=6):
        self.tk = tk
        self.on_pick = on_pick
        self.items = []          # [(보여줄 글, 값)]
        self.value = None

        self.box = tk.Frame(parent, bg=CARD)
        if label:
            tk.Label(self.box, text=label, bg=CARD, fg=DIM, width=5,
                     anchor="w", font=FONT_S).pack(side="left")
        self.var = tk.StringVar()
        self.entry = tk.Entry(self.box, textvariable=self.var, width=width,
                              bg=FIELD, fg=TEXT, insertbackground=TEXT,
                              relief="flat", font=FONT)
        self.entry.pack(side="left")
        self.mark = tk.Label(self.box, text="", bg=CARD, fg=DIM,
                             font=FONT_S)
        self.mark.pack(side="left", padx=(4, 0))

        # 후보는 창 위에 떠야 다른 칸을 안 밀어낸다
        self.pop = tk.Toplevel(parent)
        self.pop.withdraw()
        self.pop.overrideredirect(True)
        self.list = tk.Listbox(self.pop, height=rows, bg=FIELD, fg=TEXT,
                               selectbackground=BAR, selectforeground=BG,
                               relief="flat", font=FONT,
                               highlightthickness=1,
                               highlightbackground=LINE)
        self.list.pack(fill="both", expand=True)

        self.var.trace_add("write", lambda *_a: self.refresh())
        self.entry.bind("<Down>", self._down)
        self.entry.bind("<Return>", self._enter)
        self.entry.bind("<Escape>", lambda _e: self.hide())
        self.entry.bind("<FocusOut>", lambda _e: self.box.after(150,
                                                               self.hide))
        self.list.bind("<Double-Button-1>", self._enter)
        self.list.bind("<Return>", self._enter)

    def pack(self, **kw):
        self.box.pack(**kw)
        return self

    def source(self, items):
        """[(보여줄 글, 값)] 로 후보를 갈아 끼운다."""
        self.items = list(items)
        return self

    def set(self, text, value=None, quiet=True):
        self._quiet = quiet
        self.var.set(text or "")
        self.value = value
        self.hide()
        self._mark()

    def get(self):
        return self.value

    def _mark(self):
        typed = self.var.get().strip()
        if self.value is not None and typed:
            self.mark.config(text="✓", fg=GOOD)
        elif typed:
            self.mark.config(text="?", fg=WARN)
        else:
            self.mark.config(text="")

    def refresh(self):
        typed = self.var.get().strip()
        # 정확히 같은 글이면 그걸로 고른 것으로 본다
        exact = [v for t, v in self.items if t == typed]
        self.value = exact[0] if exact else None
        self._mark()
        if not typed or exact:
            self.hide()
            return
        hits = [(t, v) for t, v in self.items
                if t.startswith(typed)] + [(t, v) for t, v in self.items
                                           if typed in t and
                                           not t.startswith(typed)]
        self.list.delete(0, "end")
        for t, _v in hits[:40]:
            self.list.insert("end", t)
        self._hits = hits[:40]
        if hits:
            self.show()
        else:
            self.hide()

    def show(self):
        self.entry.update_idletasks()
        x = self.entry.winfo_rootx()
        y = self.entry.winfo_rooty() + self.entry.winfo_height()
        self.pop.geometry("+%d+%d" % (x, y))
        self.pop.deiconify()
        self.pop.lift()

    def hide(self):
        try:
            self.pop.withdraw()
        except Exception:
            pass

    def _down(self, _e):
        if self.pop.winfo_viewable():
            self.list.focus_set()
            self.list.selection_clear(0, "end")
            self.list.selection_set(0)
        return "break"

    def _enter(self, _e=None):
        sel = self.list.curselection()
        hits = getattr(self, "_hits", [])
        if sel and hits:
            text, value = hits[sel[0]]
        elif hits:
            text, value = hits[0]
        else:
            return "break"
        self.var.set(text)
        self.value = value
        self.hide()
        self._mark()
        self.entry.focus_set()
        if self.on_pick:
            self.on_pick(value)
        return "break"


class Slot(object):
    """파티 한 자리. 칸에 골라 넣으면 능력치가 바로 다시 그려진다."""

    def __init__(self, app, parent, index):
        tk = app.tk
        self.app = app
        self.dex = app.dex
        self.index = index
        self.poke = None
        self.moves = [None] * 4

        self.box = tk.Frame(parent, bg=CARD, highlightbackground=LINE,
                            highlightthickness=1, padx=8, pady=6)
        self.box.pack(fill="x", pady=(0, 6))

        # -- 이름 줄 ------------------------------------------------------
        top = tk.Frame(self.box, bg=CARD)
        top.pack(fill="x")
        tk.Label(top, text="%d." % (index + 1), bg=CARD, fg=DIM,
                 font=FONT_B, width=2).pack(side="left")
        self.name = Picker(top, tk, "", width=13, on_pick=self.on_poke)
        self.name.pack(side="left")
        self.name.source([(p["name"], p)
                          for p in live.pickable_pokemon(self.dex)])
        self.title = tk.Label(top, text="", bg=CARD, fg=TEXT, font=FONT_B)
        self.title.pack(side="left", padx=(8, 0))
        tk.Button(top, text="비우기", command=self.clear, bg=LINE, fg=TEXT,
                  relief="flat", font=FONT_S).pack(side="right")

        # -- 성격 · 특성 · 도구 ---------------------------------------------
        row = tk.Frame(self.box, bg=CARD)
        row.pack(fill="x", pady=(4, 0))
        self.nature = Picker(row, tk, "성격", width=16,
                             on_pick=lambda _v: self.redraw())
        self.nature.pack(side="left")
        self.nature.source([(live.nature_label(self.dex, n), n)
                            for n in live.nature_names(self.dex)])
        self.ability = Picker(row, tk, "특성", width=12,
                              on_pick=lambda _v: self.redraw())
        self.ability.pack(side="left", padx=(8, 0))
        self.item = Picker(row, tk, "도구", width=15,
                           on_pick=lambda _v: self.redraw())
        self.item.pack(side="left", padx=(8, 0))
        self.item.source([(it["name"], it["name"]) for it in self.dex.items])

        # -- 능력치 · 노력치 -------------------------------------------------
        mid = tk.Frame(self.box, bg=CARD)
        mid.pack(fill="x", pady=(6, 0))
        self.stat_rows = {}
        for key, ko in STAT_ORDER:
            r = tk.Frame(mid, bg=CARD)
            r.pack(fill="x")
            tk.Label(r, text=ko, width=6, anchor="w", bg=CARD, fg=DIM,
                     font=FONT_S).pack(side="left")
            val = tk.Label(r, text="-", width=6, anchor="e", bg=CARD,
                           fg=TEXT, font=FONT_S)
            val.pack(side="left")
            cv = tk.Canvas(r, width=130, height=10, bg=FIELD,
                           highlightthickness=0)
            cv.pack(side="left", padx=6)
            ev = tk.StringVar(value="0")
            sp = tk.Spinbox(r, from_=0, to=live.EV_MAX, width=3,
                            textvariable=ev, bg=FIELD, fg=TEXT,
                            insertbackground=TEXT, relief="flat",
                            buttonbackground=LINE, font=FONT_S,
                            command=self.redraw)
            sp.pack(side="left")
            ev.trace_add("write", lambda *_a: self.redraw())
            self.stat_rows[key] = {"label": val, "bar": cv, "ev": ev}

        self.total = tk.Label(self.box, text="능력 포인트 0/%d" % live.EV_TOTAL,
                              bg=CARD, fg=DIM, font=FONT_S)
        self.total.pack(anchor="e")

        # -- 기술 4칸 ------------------------------------------------------
        mv = tk.Frame(self.box, bg=CARD)
        mv.pack(fill="x", pady=(4, 0))
        self.move_pickers = []
        for i in range(4):
            r = mv if i < 2 else None
            if i == 2:
                r = tk.Frame(self.box, bg=CARD)
                r.pack(fill="x")
                self._mv2 = r
            pk = Picker(r if i < 2 else self._mv2, tk,
                        "기술" if i in (0, 2) else "", width=14,
                        on_pick=lambda _v: self.redraw())
            pk.pack(side="left", padx=(0, 6))
            self.move_pickers.append(pk)

        self.note = tk.Label(self.box, text="", bg=CARD, fg=WARN,
                             font=FONT_S, wraplength=430, justify="left")
        self.note.pack(anchor="w")

    # -- 움직이기 ---------------------------------------------------------
    def on_poke(self, poke):
        """포켓몬을 고르면 특성·기술 후보가 그놈 것으로 바뀐다."""
        self.poke = poke
        abils = live.abilities_of(self.dex, poke)
        self.ability.source([(a, a) for a in abils])
        if len(abils) == 1:
            self.ability.set(abils[0], abils[0])
        elif self.ability.get() not in abils:
            self.ability.set("", None)
        moves, known = live.learnable(self.dex, poke)
        for pk in self.move_pickers:
            pk.source([(m["name"], m["name"]) for m in moves])
            if pk.get() and pk.get() not in [m["name"] for m in moves]:
                pk.set("", None)
        if not known:
            self.note.config(
                text="이 포켓몬은 배우는 기술 자료가 없어 전체에서 고릅니다")
        self.redraw()

    def clear(self):
        self.poke = None
        self.name.set("", None)
        for pk in [self.nature, self.ability, self.item] + self.move_pickers:
            pk.set("", None)
        for key, _ko in STAT_ORDER:
            self.stat_rows[key]["ev"].set("0")
        self.redraw()

    def evs(self):
        sp = {}
        for key, _ko in STAT_ORDER:
            try:
                sp[key] = max(0, int(self.stat_rows[key]["ev"].get() or 0))
            except ValueError:
                sp[key] = 0
        return sp

    def build(self):
        """지금 칸 내용으로 만든 Build. 못 만들면 (None, 왜)."""
        if self.poke is None:
            return None, None
        sp = self.evs()
        why = live.ev_problem(sp)
        if why:
            return None, why
        nature = None
        if self.nature.get():
            try:
                nature = self.dex.find_nature(self.nature.get())
            except LookupError:
                pass
        b, _filled = live.build_one(self.dex, self.poke, sp, nature,
                                    self.ability.get(), self.item.get())
        return b, None

    def move_names(self):
        return [pk.get() for pk in self.move_pickers if pk.get()]

    def redraw(self):
        b, why = self.build()
        self.note.config(text=why or "")
        if b is None:
            self.title.config(text="")
            for key, _ko in STAT_ORDER:
                self.stat_rows[key]["label"].config(text="-")
                self.stat_rows[key]["bar"].delete("all")
            self.total.config(text="능력 포인트 0/%d" % live.EV_TOTAL)
            return
        self.title.config(text=b.name if b.name != (self.poke or {}).get("name")
                          else "")
        up = (b.nature or {}).get("up")
        down = (b.nature or {}).get("down")
        sp = self.evs()
        for key, _ko in STAT_ORDER:
            mark = " ▲" if key == up else (" ▼" if key == down else "")
            row = self.stat_rows[key]
            row["label"].config(
                text="%d%s" % (b.stat(key), mark),
                fg=(GOOD if key == up else (WARN if key == down else TEXT)))
            row["bar"].delete("all")
            ev = sp.get(key, 0)
            if ev:
                row["bar"].create_rectangle(
                    0, 0, 130.0 * ev / live.EV_MAX, 10, fill=BAR, width=0)
        total = sum(sp.values())
        self.total.config(
            text="능력 포인트 %d/%d" % (total, live.EV_TOTAL),
            fg=(WARN if total > live.EV_TOTAL else DIM))
        self.app.party_changed()

    def fill_from(self, build, moves):
        """저장돼 있던 것을 칸에 올린다."""
        base = build.poke
        if base.get("isMega"):
            same = [p for p in live.pickable_pokemon(self.dex)
                    if p["dexNo"] == base["dexNo"]]
            if same:
                base = same[0]
        self.name.set(base["name"], base)
        self.on_poke(base)
        if build.nature:
            self.nature.set(live.nature_label(self.dex, build.nature["name"]),
                            build.nature["name"])
        if build.ability:
            self.ability.set(build.ability, build.ability)
        if build.item:
            self.item.set(build.item, build.item)
        for key, _ko in STAT_ORDER:
            self.stat_rows[key]["ev"].set(str(build.sp.get(key, 0)))
        for i, name in enumerate(moves[:4]):
            self.move_pickers[i].set(name, name)
        self.redraw()


class App(object):
    """창 하나. 왼쪽은 내 파티, 오른쪽은 이번 턴."""

    def __init__(self, dex, headless=False):
        import tkinter as tk

        self.tk = tk
        self.dex = dex
        self.headless = headless
        self.busy = False
        self.slots = []

        self.root = tk.Tk()
        self.root.title("포켓몬 챔피언스 — 무엇을 둘까")
        self.root.configure(bg=BG)
        if headless:
            self.root.withdraw()
        self._build()
        self._load_saved()

    # -- 만들기 -----------------------------------------------------------
    def _build(self):
        tk = self.tk
        outer = tk.Frame(self.root, bg=BG, padx=10, pady=8)
        outer.pack(fill="both", expand=True)
        tk.Label(outer, text="포켓몬 챔피언스 — 무엇을 둘까", bg=BG, fg=TEXT,
                 font=("Malgun Gothic", 14, "bold")).pack(anchor="w")
        tk.Label(outer, text="칸에 치면 후보가 뜹니다. ↓ 로 고르고 엔터.",
                 bg=BG, fg=DIM, font=FONT_S).pack(anchor="w")

        body = tk.Frame(outer, bg=BG)
        body.pack(fill="both", expand=True, pady=(6, 0))

        # 왼쪽 — 파티 (스크롤이 필요하다. 세 마리면 길다)
        left = tk.Frame(body, bg=BG)
        left.pack(side="left", fill="y")
        canvas = tk.Canvas(left, bg=BG, highlightthickness=0, width=500)
        bar = tk.Scrollbar(left, orient="vertical", command=canvas.yview)
        self.party_box = tk.Frame(canvas, bg=BG)
        self.party_box.bind(
            "<Configure>",
            lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=self.party_box, anchor="nw")
        canvas.configure(yscrollcommand=bar.set)
        canvas.pack(side="left", fill="y", expand=False)
        bar.pack(side="left", fill="y")
        self.canvas = canvas

        for i in range(3):
            self.slots.append(Slot(self, self.party_box, i))
        add = tk.Frame(self.party_box, bg=BG)
        add.pack(fill="x", pady=(0, 8))
        tk.Button(add, text="자리 하나 더", command=self.add_slot, bg=LINE,
                  fg=TEXT, relief="flat", font=FONT_S).pack(side="left")
        self.save_msg = tk.Label(add, text="", bg=BG, fg=GOOD, font=FONT_S)
        self.save_msg.pack(side="left", padx=(8, 0))

        # 오른쪽 — 이번 턴
        right = tk.Frame(body, bg=BG)
        right.pack(side="left", fill="both", expand=True, padx=(10, 0))
        self._build_turn(right)

    def add_slot(self):
        if len(self.slots) >= 6:
            return
        self.slots.append(Slot(self, self.party_box, len(self.slots)))

    def _build_turn(self, parent):
        tk = self.tk
        box = tk.Frame(parent, bg=CARD, highlightbackground=LINE,
                       highlightthickness=1, padx=10, pady=8)
        box.pack(fill="x")
        tk.Label(box, text="이번 턴", bg=CARD, fg=DIM,
                 font=FONT_S).pack(anchor="w")

        r1 = tk.Frame(box, bg=CARD)
        r1.pack(fill="x", pady=(4, 0))
        self.opp = Picker(r1, tk, "상대", width=14)
        self.opp.pack(side="left")
        self.opp.source([(p["name"], p)
                         for p in live.pickable_pokemon(self.dex)])
        tk.Label(r1, text="상대 HP%", bg=CARD, fg=DIM,
                 font=FONT_S).pack(side="left", padx=(10, 2))
        self.opp_hp = tk.StringVar(value="100")
        tk.Spinbox(r1, from_=1, to=100, increment=5, width=4,
                   textvariable=self.opp_hp, bg=FIELD, fg=TEXT,
                   insertbackground=TEXT, relief="flat",
                   buttonbackground=LINE, font=FONT_S).pack(side="left")

        r2 = tk.Frame(box, bg=CARD)
        r2.pack(fill="x", pady=(6, 0))
        tk.Label(r2, text="나와 있는 내 포켓몬", bg=CARD, fg=DIM,
                 font=FONT_S).pack(side="left")
        self.active = tk.StringVar(value="1")
        tk.Spinbox(r2, from_=1, to=6, width=3, textvariable=self.active,
                   bg=FIELD, fg=TEXT, insertbackground=TEXT, relief="flat",
                   buttonbackground=LINE, font=FONT_S).pack(side="left",
                                                            padx=4)
        tk.Label(r2, text="내 HP%", bg=CARD, fg=DIM,
                 font=FONT_S).pack(side="left", padx=(10, 2))
        self.my_hp = tk.StringVar(value="100")
        tk.Spinbox(r2, from_=1, to=100, increment=5, width=4,
                   textvariable=self.my_hp, bg=FIELD, fg=TEXT,
                   insertbackground=TEXT, relief="flat",
                   buttonbackground=LINE, font=FONT_S).pack(side="left")

        r3 = tk.Frame(box, bg=CARD)
        r3.pack(fill="x", pady=(6, 0))
        tk.Label(r3, text="상대에게서 본 기술", bg=CARD, fg=DIM,
                 font=FONT_S).pack(side="left")
        self.seen = Picker(r3, tk, "", width=13, on_pick=self.add_seen)
        self.seen.pack(side="left", padx=(6, 0))
        self.seen.source([(m["name"], m["name"]) for m in self.dex.moves])
        self.seen_list = []
        self.seen_label = tk.Label(box, text="본 것: 없음", bg=CARD, fg=TEXT,
                                   font=FONT_S, wraplength=380,
                                   justify="left")
        self.seen_label.pack(anchor="w", pady=(2, 0))
        tk.Button(box, text="본 것 지우기", command=self.clear_seen, bg=LINE,
                  fg=TEXT, relief="flat", font=FONT_S).pack(anchor="e")

        r4 = tk.Frame(box, bg=CARD)
        r4.pack(fill="x", pady=(6, 0))
        tk.Label(r4, text="생각할 시간(초)", bg=CARD, fg=DIM,
                 font=FONT_S).pack(side="left")
        self.secs = tk.StringVar(value="10")
        tk.Spinbox(r4, from_=1, to=120, increment=5, width=4,
                   textvariable=self.secs, bg=FIELD, fg=TEXT,
                   insertbackground=TEXT, relief="flat",
                   buttonbackground=LINE, font=FONT_S).pack(side="left",
                                                            padx=4)
        self.go = tk.Button(r4, text="무엇을 둘까?", command=self.ask,
                            bg=BAR, fg=BG, relief="flat",
                            font=("Malgun Gothic", 11, "bold"))
        self.go.pack(side="right")

        self.out = tk.Text(parent, height=20, bg=FIELD, fg=TEXT, font=FONT,
                           relief="flat", padx=8, pady=6, wrap="word")
        self.out.pack(fill="both", expand=True, pady=(8, 0))
        self.say("왼쪽에 파티를 채우고, 상대를 고른 뒤 '무엇을 둘까?' 를 누르세요.")

    # -- 움직이기 ---------------------------------------------------------
    def say(self, text, clear=False):
        if clear:
            self.out.delete("1.0", "end")
        self.out.insert("end", text + "\n")
        self.out.see("end")

    def add_seen(self, name):
        if name and name not in self.seen_list:
            self.seen_list.append(name)
        self.seen.set("", None)
        self._draw_seen()

    def clear_seen(self):
        self.seen_list = []
        self._draw_seen()

    def _draw_seen(self):
        self.seen_label.config(
            text="본 것: " + (", ".join(self.seen_list) or "없음"))

    def party(self):
        """칸이 채워진 자리들만. [(빌드, [기술])]."""
        out = []
        for s in self.slots:
            b, why = s.build()
            if b is not None and not why:
                out.append((b, s.move_names()))
        return out

    def party_changed(self):
        """칸이 바뀔 때마다 조용히 저장해 둔다. 다음에 켜면 그대로 있다."""
        if self.headless:
            return
        got = self.party()
        if not got:
            return
        try:
            live.save_party_file([(b, m, []) for b, m in got])
            self.save_msg.config(text="저장됨", fg=GOOD)
        except Exception as e:
            self.save_msg.config(text="저장 실패: %s" % e, fg=WARN)

    def _load_saved(self):
        saved = live.load_party(self.dex)
        if not saved:
            return
        while len(self.slots) < len(saved):
            self.add_slot()
        for slot, row in zip(self.slots, saved):
            slot.fill_from(row[0], row[1])

    def ask(self):
        """탐색은 **다른 갈래에서 돌린다.** 안 그러면 창이 10초 동안 언다."""
        if self.busy:
            return
        party = self.party()
        if not party:
            self.say("먼저 왼쪽에 파티를 채우세요.", clear=True)
            return
        poke = self.opp.get()
        if poke is None:
            self.say("상대를 고르세요 (칸에 치면 후보가 뜹니다).", clear=True)
            return

        def num(var, default):
            try:
                return float(var.get())
            except (ValueError, AttributeError):
                return default

        idx = int(max(1, min(len(party), num(self.active, 1)))) - 1
        my_hp = [100.0] * len(party)
        my_hp[idx] = max(1.0, min(100.0, num(self.my_hp, 100)))
        state = {"my_hp": my_hp, "my_active": idx,
                 "opp_hp": [max(1.0, min(100.0, num(self.opp_hp, 100)))]}
        secs = max(1.0, num(self.secs, 10))
        ev = (scout.Evidence(seen_moves=list(self.seen_list))
              if self.seen_list else None)

        self.busy = True
        self.go.config(text="생각하는 중...", state="disabled")
        self.say("%s 을(를) 상대로 %.0f초 생각합니다...%s"
                 % (poke["name"], secs,
                    ("  (본 것: %s)" % ", ".join(self.seen_list))
                    if self.seen_list else ""), clear=True)

        args = (party, poke, ev, secs, state, idx)
        if self.headless:
            self._work(*args)
        else:
            threading.Thread(target=self._work, args=args,
                             daemon=True).start()

    def _work(self, party, poke, ev, secs, state, idx):
        try:
            got = search.best_action(
                self.dex, [b for b, _m in party], poke,
                my_moves=party[idx][1] or None, evidence=ev,
                seconds=secs, state=state)
            text = self._format(got)
        except Exception:
            import traceback
            text = "문제가 생겼습니다:\n%s" % traceback.format_exc()
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
        L = ["", "%-18s %6s %8s %7s" % ("수", "점수", "판수", "오차"),
             "-" * 44]
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
    """창을 안 띄우고 **칸을 실제로 채워 보며** 확인한다.

    깃허브의 윈도우가 이걸 돌린다. 여기(리눅스)에서는 tkinter 가 없어서
    아예 못 돌린다 — 그래서 이 함수가 유일한 방어선이다.
    """
    ok, why = have_tk()
    if not ok:
        print("tkinter 가 없습니다: %s" % why)
        return 1

    dex = calc.Dex()
    app = App(dex, headless=True)
    slot = app.slots[0]

    # ① 포켓몬을 고르면 특성·기술 후보가 그놈 것으로 바뀌는가
    hama = dex.find_pokemon("하마돈")
    slot.name.set("하마돈", hama)
    slot.on_poke(hama)
    abils = [t for t, _v in slot.ability.items]
    if abils != ["모래날림", "모래의힘"]:
        print("특성 후보가 그 포켓몬 것이 아닙니다: %s" % abils)
        return 1
    mv = [t for t, _v in slot.move_pickers[0].items]
    if "지진" not in mv or "역린" in mv:
        print("기술 후보가 배우는 것만이 아닙니다 (지진 %s / 역린 %s)"
              % ("지진" in mv, "역린" in mv))
        return 1

    # ② 칸을 채우면 능력치가 게임 화면과 맞는가
    slot.nature.set(live.nature_label(dex, "무사태평"), "무사태평")
    slot.ability.set("모래날림", "모래날림")
    slot.item.set("자뭉열매", "자뭉열매")
    for key, val in (("hp", 32), ("defense", 22), ("spDef", 12)):
        slot.stat_rows[key]["ev"].set(str(val))
    for i, name in enumerate(["지진", "하품", "게으름피우기", "스텔스록"]):
        slot.move_pickers[i].set(name, name)
    slot.redraw()
    build, why = slot.build()
    if build is None:
        print("칸을 다 채웠는데 못 만듭니다: %s" % why)
        return 1
    screen = {"hp": 215, "attack": 132, "defense": 176,
              "spAtk": 88, "spDef": 104, "speed": 60}
    off = [(k, build.stat(k), v) for k, v in screen.items()
           if build.stat(k) != v]
    if off:
        print("능력치가 게임 화면과 다릅니다: %s" % off)
        return 1

    # ③ 노력치 규칙이 화면에 뜨는가
    slot.stat_rows["attack"]["ev"].set("32")      # 합 98 — 넘는다
    slot.redraw()
    if "66" not in slot.note.cget("text"):
        print("노력치 합이 넘었는데 아무 말이 없습니다: %r"
              % slot.note.cget("text"))
        return 1
    slot.stat_rows["attack"]["ev"].set("0")
    slot.redraw()

    # ④ 두 번째 자리도 채우고, 한 턴 물어보기까지 돌려 본다
    kao = dex.find_pokemon("아머까오")
    s2 = app.slots[1]
    s2.name.set("아머까오", kao)
    s2.on_poke(kao)
    s2.nature.set(live.nature_label(dex, "장난꾸러기"), "장난꾸러기")
    s2.stat_rows["hp"]["ev"].set("32")
    s2.stat_rows["defense"]["ev"].set("32")
    for i, name in enumerate(["바디프레스", "철벽", "날개쉬기", "브레이브버드"]):
        s2.move_pickers[i].set(name, name)
    s2.redraw()
    if len(app.party()) != 2:
        print("파티가 두 마리로 안 잡힙니다: %d" % len(app.party()))
        return 1

    app.opp.set("한카리아스", dex.find_pokemon("한카리아스"))
    app.add_seen("지진")
    app.secs.set("2")
    app.ask()
    text = app.out.get("1.0", "end")
    if "=>" not in text:
        print("추천이 안 나왔습니다:\n%s" % text)
        return 1

    print("창 점검 끝 — 후보 고르기 · 능력치 · 노력치 규칙 · 추천까지 돌았습니다")
    print("  " + text.strip().splitlines()[-1])
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
