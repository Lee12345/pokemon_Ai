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

## 왜 내 자리가 6개고 상대 자리도 6개인가

챔피언스는 **6마리를 데려가서 3마리를 낸다.** 그래서 —

  내 파티     자리 6개 (팀 프리뷰에 올리는 그대로)
  상대        자리 6개 (프리뷰에서 본 6마리, 대전 중에는 낸 3마리)

전에는 **내 자리가 3개, 상대 자리가 1개**였다. 사용자가 되물어서
잡혔다 (2026-09-18): *"왜 내 파티는 6인이 아니며 상대는 1인이지?"*
둘 다 맞는 지적이었고, 상대가 1마리였던 쪽은 답을 조용히 틀리게
만들고 있었다 — 상대 벤치가 계산에 아예 안 들어가서 '지금 이놈을
잡는 수' 를 '판을 이기는 수' 로 답했다. 같은 자리에서 '누리레느 로
교체' 가 상대 1마리일 때 94.6점(2등)이었는데 상대 3마리를 넣자
30.5점(꼴찌)이 됐다.

상대 칸에는 **노력치·성격을 안 묻는다.** 모르는 것이 맞고, 모르는
것은 사용률에서 뽑는 것이 이 프로그램이 하는 일이다 (`scout.py`).
칸을 만들어 두면 찍어서 채우게 되고, 그 찍은 값이 그대로 계산에 든다.

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
import pick
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
MAX_PARTY = live.MAX_PARTY     # 6마리를 데려간다


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
        # ! **눌렀을 때도 열려야 한다.** 전에는 글자를 쳐야만 열려서,
        #   이름을 모르는 칸(특성·성격·도구)은 아예 고를 수가 없었다.
        #   하마돈 특성이 '모래날림/모래의힘' 인 걸 모르면 칸을 눌러도
        #   아무 일도 안 일어났다. 사용자가 되물어서 잡혔다 (2026-09-19).
        self.entry.bind("<Button-1>", lambda _e: self.refresh(force=True))
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

    def refresh(self, force=False):
        """후보를 다시 그린다.

        force 면 **빈 칸이어도 전부 보여 준다** — 칸을 눌렀을 때다.
        이름을 모르는 칸은 이게 없으면 고를 방법이 없다.
        """
        typed = self.var.get().strip()
        # 정확히 같은 글이면 그걸로 고른 것으로 본다
        exact = [v for t, v in self.items if t == typed]
        self.value = exact[0] if exact else None
        self._mark()
        if not force and (not typed or exact):
            self.hide()
            return
        if not typed:
            hits = list(self.items)
        else:
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
        # 닫혀 있으면 **먼저 연다.** 전에는 닫혀 있을 때 아래키가
        # 아무 일도 안 했다 — 칸을 눌러도 안 열리니 열 방법이 없었다.
        if not self.pop.winfo_viewable():
            self.refresh(force=True)
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
        elif hits and self.var.get().strip():
            # 친 글자가 있을 때만 1등을 골라 준다.
            # ! 빈 칸에서 엔터를 쳤다고 목록 맨 위를 골라 버리면,
            #   고를 생각이 없었는데 231마리 중 첫 놈이 들어간다.
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


class OppSlot(object):
    """상대 한 자리. 이름 · 남은 HP · 나와 있나, 셋만 받는다.

    ! 내 파티 자리처럼 노력치·성격 칸을 만들지 **않는다.** 상대 배분은
      모르는 것이 맞고, 모르는 것은 사용률에서 뽑는 것이 이 프로그램이
      하는 일이다. 칸이 있으면 찍어서 채우게 되고, 찍은 값이 그대로
      계산에 들어간다 — 조용히 틀어지는 자리가 하나 더 생긴다.
    """

    def __init__(self, app, parent, index):
        tk = app.tk
        self.app = app
        self.dex = app.dex
        self.index = index
        self.poke = None

        self.box = tk.Frame(parent, bg=CARD)
        self.box.pack(fill="x", pady=1)
        tk.Label(self.box, text="%d." % (index + 1), bg=CARD, fg=DIM,
                 font=FONT_S, width=2).pack(side="left")
        self.name = Picker(self.box, tk, "", width=12,
                           on_pick=self.on_poke, rows=5)
        self.name.pack(side="left")
        self.name.source([(p["name"], p)
                          for p in live.pickable_pokemon(self.dex)])
        tk.Label(self.box, text="HP", bg=CARD, fg=DIM,
                 font=FONT_S).pack(side="left", padx=(6, 1))
        self.hp = tk.StringVar(value="100")
        # 0 이면 쓰러진 것으로 본다. 칸을 따로 만들지 않는다.
        tk.Spinbox(self.box, from_=0, to=100, increment=5, width=4,
                   textvariable=self.hp, bg=FIELD, fg=TEXT,
                   insertbackground=TEXT, relief="flat",
                   buttonbackground=LINE, font=FONT_S).pack(side="left")
        tk.Radiobutton(self.box, text="나와 있음", variable=app.opp_active,
                       value=index, bg=CARD, fg=TEXT, selectcolor=FIELD,
                       activebackground=CARD, activeforeground=TEXT,
                       font=FONT_S,
                       command=app.draw_seen).pack(side="left", padx=(6, 0))
        self.seen_label = tk.Label(self.box, text="", bg=CARD, fg=DIM,
                                   font=FONT_S, anchor="w")
        self.seen_label.pack(side="left", padx=(6, 0))

    def on_poke(self, poke):
        self.poke = poke
        # '나와 있음' 이 **빈 자리에 놓여 있으면** 방금 고른 이 자리로
        # 옮긴다. 안 그러면 3번부터 채운 사람은 아무 데도 안 가리킨
        # 채로 물어보게 된다.
        mark = self.app.opp_active.get()
        if poke is not None and not (
                0 <= mark < len(self.app.opp_slots)
                and self.app.opp_slots[mark].poke):
            self.app.opp_active.set(self.index)
        self.app.draw_seen()

    def hp_pct(self):
        """남은 HP. **빈 칸은 만피로 본다.**

        ! `float("" or 0)` 은 0 이다. 그대로 두면 칸을 비웠을 때
          조용히 '쓰러졌다' 가 되어 그 상대가 계산에서 빠진다.
          모를 때는 빠뜨리는 쪽보다 성한 쪽으로 보는 것이 안전하다.
        """
        text = (self.hp.get() or "").strip()
        if not text:
            return 100.0
        try:
            return max(0.0, min(100.0, float(text)))
        except ValueError:
            return 100.0

    def draw_seen(self, moves):
        self.seen_label.config(text=("본 것: " + ", ".join(moves))
                               if moves else "")


class App(object):
    """창 하나. 왼쪽은 내 파티 6자리, 오른쪽은 상대 6자리와 이번 턴."""

    def __init__(self, dex, headless=False):
        import tkinter as tk

        self.tk = tk
        self.dex = dex
        self.headless = headless
        self.busy = False
        self.slots = []
        self.opp_slots = []
        # 상대 이름 -> 본 기술 목록. **상대마다 따로 쌓는다** —
        # 지진을 쓴 것은 그때 나와 있던 놈이지 상대 셋 전부가 아니다.
        self.seen = {}

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

        # **6자리로 연다.** 챔피언스는 6마리를 데려가서 3마리를 낸다.
        for i in range(MAX_PARTY):
            self.slots.append(Slot(self, self.party_box, i))
        add = tk.Frame(self.party_box, bg=BG)
        add.pack(fill="x", pady=(0, 8))
        self.save_msg = tk.Label(add, text="", bg=BG, fg=GOOD, font=FONT_S)
        self.save_msg.pack(side="left", padx=(8, 0))

        # 오른쪽 — 이번 턴
        right = tk.Frame(body, bg=BG)
        right.pack(side="left", fill="both", expand=True, padx=(10, 0))
        self._build_opp(right)
        self._build_turn(right)

    def add_slot(self):
        """남은 자리 — 이제 처음부터 6자리를 열어 두므로 쓸 일이 없다.
        옛 저장 파일을 읽을 때 자리가 모자라면 여기서 늘린다."""
        if len(self.slots) >= MAX_PARTY:
            return
        self.slots.append(Slot(self, self.party_box, len(self.slots)))

    def _build_opp(self, parent):
        tk = self.tk
        box = tk.Frame(parent, bg=CARD, highlightbackground=LINE,
                       highlightthickness=1, padx=10, pady=8)
        box.pack(fill="x")
        tk.Label(box, text="상대 — 프리뷰에서 본 6마리, 대전 중에는 낸 3마리",
                 bg=CARD, fg=DIM, font=FONT_S).pack(anchor="w")
        tk.Label(box, text="HP 0 이면 쓰러진 것으로 봅니다. "
                           "배분·성격은 안 묻습니다 (사용률에서 뽑습니다).",
                 bg=CARD, fg=DIM, font=FONT_S).pack(anchor="w")
        self.opp_active = tk.IntVar(value=0)
        holder = tk.Frame(box, bg=CARD)
        holder.pack(fill="x", pady=(4, 0))
        for i in range(MAX_PARTY):
            self.opp_slots.append(OppSlot(self, holder, i))

        r = tk.Frame(box, bg=CARD)
        r.pack(fill="x", pady=(6, 0))
        tk.Label(r, text="상대에게서 본 기술", bg=CARD, fg=DIM,
                 font=FONT_S).pack(side="left")
        self.seen_pick = Picker(r, tk, "", width=13, on_pick=self.add_seen)
        self.seen_pick.pack(side="left", padx=(6, 0))
        self.seen_pick.source([(m["name"], m["name"]) for m in self.dex.moves])
        tk.Button(r, text="본 것 지우기", command=self.clear_seen, bg=LINE,
                  fg=TEXT, relief="flat", font=FONT_S).pack(side="left",
                                                            padx=(6, 0))
        tk.Label(r, text="← '나와 있음' 인 놈 것으로 들어갑니다",
                 bg=CARD, fg=DIM, font=FONT_S).pack(side="left", padx=(6, 0))

        r2 = tk.Frame(box, bg=CARD)
        r2.pack(fill="x", pady=(6, 0))
        tk.Label(r2, text="선출에 쓸 시간(초)", bg=CARD, fg=DIM,
                 font=FONT_S).pack(side="left")
        self.pick_secs = tk.StringVar(value="45")
        tk.Spinbox(r2, from_=10, to=300, increment=15, width=5,
                   textvariable=self.pick_secs, bg=FIELD, fg=TEXT,
                   insertbackground=TEXT, relief="flat",
                   buttonbackground=LINE, font=FONT_S).pack(side="left",
                                                            padx=4)
        self.go_pick = tk.Button(r2, text="선출 — 어떤 3마리?",
                                 command=self.ask_pick, bg=LINE, fg=TEXT,
                                 relief="flat", font=FONT_B)
        self.go_pick.pack(side="right")

    def _build_turn(self, parent):
        tk = self.tk
        box = tk.Frame(parent, bg=CARD, highlightbackground=LINE,
                       highlightthickness=1, padx=10, pady=8)
        box.pack(fill="x", pady=(8, 0))
        tk.Label(box, text="이번 턴", bg=CARD, fg=DIM,
                 font=FONT_S).pack(anchor="w")

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

    def active_opp(self):
        """지금 '나와 있음' 인 상대 자리. 안 골랐으면 채워진 첫 자리."""
        i = self.opp_active.get()
        if 0 <= i < len(self.opp_slots) and self.opp_slots[i].poke:
            return self.opp_slots[i]
        for sl in self.opp_slots:
            if sl.poke:
                return sl
        return None

    def add_seen(self, name):
        """본 기술을 **나와 있는 놈 것으로** 넣는다."""
        sl = self.active_opp()
        if sl is None:
            self.say("상대를 먼저 고르세요.", clear=True)
        elif name:
            got = self.seen.setdefault(sl.poke["name"], [])
            if name not in got:
                got.append(name)
        self.seen_pick.set("", None)
        self.draw_seen()

    def clear_seen(self):
        sl = self.active_opp()
        if sl is not None:
            self.seen.pop(sl.poke["name"], None)
        self.draw_seen()

    def draw_seen(self):
        for sl in self.opp_slots:
            sl.draw_seen(self.seen.get((sl.poke or {}).get("name")) or [])

    def opp_party(self):
        """칸이 채워진 상대 자리들. [(포켓몬, HP%)] — 쓰러진 놈도 들어 있다."""
        return [(sl.poke, sl.hp_pct()) for sl in self.opp_slots if sl.poke]

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
        def num(var, default):
            try:
                return float(var.get())
            except (ValueError, AttributeError):
                return default

        idx = int(max(1, min(len(party), num(self.active, 1)))) - 1
        my_hp = [100.0] * len(party)
        my_hp[idx] = max(1.0, min(100.0, num(self.my_hp, 100)))

        # 쓰러진 상대(HP 0)는 빼고 넘긴다. 빼면 번호가 밀리므로
        # **나와 있는 놈의 새 번호를 다시 찾는다.** 여기서 어긋나면
        # 상대가 엉뚱한 놈을 겨냥한 채 계산이 돈다.
        # 규칙은 live.py 에 있고 거기서 시험한다 — 창은 값만 모아 준다.
        rows = [(sl.poke, sl.hp_pct()) for sl in self.opp_slots]
        opp_pokes, state, why = live.turn_state(
            my_hp, idx, rows, self.opp_active.get())
        if why:
            self.say("%s — 상대를 고르세요 (HP 0 은 쓰러진 것으로 봅니다)."
                     % why, clear=True)
            return
        secs = max(1.0, num(self.secs, 10))
        ev = live.evidence_map(self.seen, opp_pokes)
        oi = state["opp_active"]

        self.busy = True
        self.go.config(text="생각하는 중...", state="disabled")
        # 화면에 찍는 것도 **넘긴 값 그대로** 쓴다. 따로 다시 세면
        # 화면과 계산이 갈라진다 — 이 저장소가 늘 고장 나는 방식이다.
        said = ", ".join("%s %.0f%%" % (p["name"], hp)
                         for p, hp in zip(opp_pokes, state["opp_hp"]))
        self.say("상대 %s 를 놓고 %.0f초 생각합니다...\n(나와 있는 상대: %s)"
                 % (said, secs, opp_pokes[oi]["name"]), clear=True)

        args = (party, opp_pokes, ev, secs, state, idx)
        if self.headless:
            self._work(*args)
        else:
            threading.Thread(target=self._work, args=args,
                             daemon=True).start()

    def _work(self, party, opp_pokes, ev, secs, state, idx):
        try:
            got = search.best_action(
                self.dex, [b for b, _m in party], opp_pokes,
                my_moves=party[idx][1] or None, evidence=ev,
                seconds=secs, state=state)
            text = self._format(got, len(opp_pokes))
        except Exception:
            import traceback
            text = "문제가 생겼습니다:\n%s" % traceback.format_exc()
        if self.headless:
            self._show(text)
        else:
            self.root.after(0, lambda: self._show(text))

    # -- 선출 -------------------------------------------------------------
    def ask_pick(self):
        """팀 프리뷰 — 내 6마리 중 어떤 3마리를 낼까."""
        if self.busy:
            return
        party = self.party()
        foes = self.opp_party()
        if len(party) < pick.PICK:
            self.say("내 파티를 %d마리 이상 채우세요 (지금 %d)."
                     % (pick.PICK, len(party)), clear=True)
            return
        if len(foes) < pick.PICK:
            self.say("상대를 %d마리 이상 적으세요 (지금 %d). 팀 프리뷰에서"
                     " 본 6마리를 다 적으면 제일 정확합니다."
                     % (pick.PICK, len(foes)), clear=True)
            return
        try:
            secs = max(10.0, float(self.pick_secs.get()))
        except (ValueError, AttributeError):
            secs = 45.0
        self.busy = True
        self.go_pick.config(text="고르는 중...", state="disabled")
        self.say("선출을 고릅니다 (%.0f초)..." % secs, clear=True)
        args = ([b for b, _m in party], [p for p, _hp in foes], secs)
        if self.headless:
            self._work_pick(*args)
        else:
            threading.Thread(target=self._work_pick, args=args,
                             daemon=True).start()

    def _work_pick(self, my_builds, foes, secs):
        try:
            opp_builds = [calc.popular_build(self.dex, p)[0] for p in foes]
            got = pick.choose(self.dex, my_builds, opp_builds, seconds=secs)
            text = pick.short_report(my_builds, opp_builds, got)
        except Exception:
            import traceback
            text = "문제가 생겼습니다:\n%s" % traceback.format_exc()
        if self.headless:
            self._show_pick(text)
        else:
            self.root.after(0, lambda: self._show_pick(text))

    def _show_pick(self, text):
        self.say(text)
        self.busy = False
        self.go_pick.config(text="선출 — 어떤 3마리?", state="normal")

    def _show(self, text):
        self.say(text)
        self.busy = False
        self.go.config(text="무엇을 둘까?", state="normal")

    def _format(self, got, n_foes=1):
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
        if n_foes < 2:
            L.append("! 상대를 한 마리만 넣었습니다. 벤치를 아는 만큼")
            L.append("  적으면 답이 달라집니다 (한 수에서 64%p 움직였습니다)")
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

    # ★ **칸을 눌렀을 때 후보가 뜨는가.**
    #    안 뜨면 이름을 모르는 칸(특성·성격·도구)은 고를 방법이 아예 없다.
    #    하마돈 특성이 '모래날림/모래의힘' 인 걸 모르면 칸을 눌러도
    #    아무 일도 안 일어났다. 사용자가 되물어서 잡혔다 (2026-09-19).
    for label, pk in (("특성", slot.ability), ("성격", slot.nature),
                      ("도구", slot.item), ("기술", slot.move_pickers[0]),
                      ("포켓몬", slot.name)):
        pk.set("", None)
        pk.refresh(force=True)
        if not pk.list.size():
            print("%s 칸을 눌러도 후보가 안 뜹니다" % label)
            return 1
        # 아래키로도 열려야 한다 (닫혀 있으면 먼저 열고 고른다)
        pk.hide()
        pk._down(None)
        if not pk.pop.winfo_viewable():
            print("%s 칸에서 아래키를 눌러도 안 열립니다" % label)
            return 1
        pk.hide()
    # 빈 칸에서 엔터를 쳤다고 멋대로 1등을 고르면 안 된다
    slot.ability.set("", None)
    slot.ability._hits = []
    slot.ability.list.delete(0, "end")
    slot.ability._enter()
    if slot.ability.get() is not None:
        print("빈 칸에서 엔터를 쳤는데 멋대로 골랐습니다: %r"
              % slot.ability.get())
        return 1
    slot.ability.set("모래날림", "모래날림")

    # ⑤ 자리가 6개로 열리는가 (챔피언스는 6마리를 데려간다)
    if len(app.slots) != 6 or len(app.opp_slots) != 6:
        print("자리가 6개가 아닙니다: 내 %d / 상대 %d"
              % (len(app.slots), len(app.opp_slots)))
        return 1

    # ⑥ 상대를 세 마리 적고, **그 셋이 정말로 계산까지 가는지** 본다.
    #    창에 찍히는 것과 계산이 쓰는 것이 다르면 조용히 틀어진다 —
    #    이 저장소가 고장 나는 방식은 늘 그것 하나다 (CLAUDE.md §1).
    for i, name in enumerate(["한카리아스", "타부자고", "킬가르도"]):
        poke = dex.find_pokemon(name)
        sl = app.opp_slots[i]
        sl.name.set(poke["name"], poke)
        sl.on_poke(poke)
    app.opp_slots[1].hp.set("40")
    app.opp_slots[2].hp.set("0")          # 쓰러진 놈은 빠져야 한다
    app.opp_active.set(0)
    app.add_seen("지진")
    if app.seen.get("한카리아스") != ["지진"]:
        print("본 기술이 나와 있는 놈 것으로 안 들어갑니다: %r" % app.seen)
        return 1

    seen_args = {}
    real = search.best_action

    def spy(dex_, my_party, opp_pokes, **kw):
        seen_args["opp"] = [p["name"] for p in opp_pokes]
        seen_args["state"] = kw.get("state")
        seen_args["ev"] = kw.get("evidence")
        return real(dex_, my_party, opp_pokes, **kw)

    # ! 엿보기는 **두 번째 물음까지** 걸어 둔다. 한 번만 걸고 떼면
    #   두 번째 검사가 첫 번째 값을 다시 보게 되어, 안 따라가도 따라간
    #   것처럼(또는 그 반대로) 보인다. 실제로 그렇게 헛짚었다.
    search.best_action = spy
    try:
        app.secs.set("2")
        app.ask()
        text = app.out.get("1.0", "end")
        if "=>" not in text:
            print("추천이 안 나왔습니다:\n%s" % text)
            return 1
        first = dict(seen_args)

        # ⑦ 나와 있는 상대를 2번으로 바꾸면 번호가 따라가는가
        app.opp_active.set(1)
        app.ask()
        moved = (seen_args.get("state") or {}).get("opp_active")
    finally:
        search.best_action = real
    seen_args = first
    if moved != 1:
        print("'나와 있음' 을 바꿨는데 안 따라갑니다: %r" % (moved,))
        return 1
    if seen_args.get("opp") != ["한카리아스", "타부자고"]:
        print("상대 파티가 계산까지 안 갔습니다: %r" % (seen_args.get("opp"),))
        return 1
    st = seen_args.get("state") or {}
    if st.get("opp_hp") != [100.0, 40.0]:
        print("상대 HP 가 계산까지 안 갔습니다: %r" % (st.get("opp_hp"),))
        return 1
    if st.get("opp_active") != 0:
        print("나와 있는 상대 번호가 틀렸습니다: %r" % (st.get("opp_active"),))
        return 1
    ev = seen_args.get("ev") or {}
    if sorted(ev) != ["한카리아스"]:
        print("본 기술이 그놈에게만 안 붙었습니다: %r" % (sorted(ev),))
        return 1

    # ⑧ 선출 단추도 한 번 눌러 본다 (내 3마리 x 상대 3마리 = 1가지씩)
    nuri = dex.find_pokemon("누리레느")
    s3 = app.slots[2]
    s3.name.set("누리레느", nuri)
    s3.on_poke(nuri)
    s3.nature.set(live.nature_label(dex, "조심"), "조심")
    for i, name in enumerate(["문포스", "냉동빔", "아쿠아제트", "하품"]):
        s3.move_pickers[i].set(name, name)
    s3.redraw()
    app.opp_slots[2].hp.set("100")      # 쓰러뜨려 뒀던 놈을 되살린다
    app.pick_secs.set("10")
    app.ask_pick()
    out = app.out.get("1.0", "end")
    if "최악 기준" not in out:
        print("선출이 안 나왔습니다:\n%s" % out[-600:])
        return 1

    print("창 점검 끝 — 후보 고르기 · 능력치 · 노력치 규칙 · 6자리 ·"
          " 상대 파티가 계산까지 가는지 · 추천 · 선출까지 돌았습니다")
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
