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
import time

import battle
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
WHEEL_UNITS = 3          # 휠 한 칸에 몇 줄 (캔버스는 한 줄 20px)
MIN_OUT_H = 120          # 창을 줄여도 결과 칸은 이만큼 남긴다 (px)
FONT_S = ("Malgun Gothic", 9)
FONT_B = ("Malgun Gothic", 11, "bold")

STAT_ORDER = live.STAT_ORDER
MAX_PARTY = live.MAX_PARTY     # 6마리를 데려간다

# 실전 중간 상태 칸 (2026-09-23) — 이름은 battle 이 쓰는 그대로
NO_STATUS = "없음"
STATUS_CHOICES = (NO_STATUS,) + battle.Battle.START_STATUS
AUTO = "자동"
WEATHER_CHOICES = (AUTO, "없음", "쾌청", "비", "모래바람", "눈")
TERRAIN_CHOICES = (AUTO, "없음", "그래스필드", "일렉트릭필드", "사이코필드", "미스트필드")
RANK_KEYS = (("attack", "공"), ("defense", "방"), ("spAtk", "특공"), ("spDef", "특방"),
             ("speed", "스피"), ("accuracy", "명중"), ("evasion", "회피"))
HAZARD_KEYS = (("스텔스록", 1), ("압정뿌리기", 3), ("독압정", 2), ("끈적끈적네트", 1))


def _int(var, default=0):
    try:
        return int(float(var.get()))
    except (ValueError, TypeError, AttributeError):
        return default


def describe_mid(mid, my_names, opp_names):
    """넘긴 실전 중간 상태를 한 줄로 — 화면과 계산이 같은 값을 보게 (넘긴 것 그대로 적는다)."""
    bits = []
    for names, sts in ((my_names, mid.get("my_status")), (opp_names, mid.get("opp_status"))):
        bits += ["%s %s" % (n, s) for n, s in zip(names, sts or ()) if s]
    short = dict(RANK_KEYS)
    for who, key in (("내", "my_ranks"), ("상대", "opp_ranks")):
        r = mid.get(key) or {}
        if r:
            bits.append("%s 랭크 %s" % (who, " ".join("%s%+d" % (short[k], v) for k, v in r.items())))
    f = mid.get("field") or {}
    for key, word in (("weather", "날씨"), ("terrain", "필드")):
        if key in f:
            bits.append("%s %s" % (word, "%s %d턴" % (f[key], f[key + "_turns"]) if f[key] else "없음"))
    for who, key in (("내 쪽", "my_hazards"), ("상대 쪽", "opp_hazards")):
        h = mid.get(key) or {}
        if h:
            bits.append("%s %s" % (who, " ".join("%s%s" % (k, "" if v == 1 else "×%d" % v)
                                               for k, v in h.items())))
    return " · ".join(bits)


def _choice_box(tk, parent, var, values, width):
    """고르는 칸 — 가짜 tkinter 에도 있는 Spinbox 에 값 목록을 준다 (드롭다운은 가짜에 없다)."""
    box = tk.Spinbox(parent, values=values, textvariable=var, width=width, state="readonly",
                     bg=FIELD, fg=TEXT, readonlybackground=FIELD, relief="flat",
                     buttonbackground=LINE, font=FONT_S, wrap=True)
    var.set(values[0])
    return box


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
        # ✓ 자리를 **처음부터 잡아 둔다.** 비어 있다가 ✓ 가 붙는 순간 줄이
        # 넓어져서 왼쪽 목록 오른쪽 끝(비우기 단추 등)이 잘렸다 (2026-09-21).
        self.mark = tk.Label(self.box, text="", bg=CARD, fg=DIM,
                             font=FONT_S, width=2)
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
        # ! **목록을 마우스로 누르는 순간에도 칸은 초점을 잃는다.** 전에는
        #   그때 무조건 0.15초 뒤 목록을 닫았고, 목록은 **두 번** 눌러야
        #   골라졌다. 첫 번 누르면 닫혀서 두 번째가 닿지 않았다 — 마우스로는
        #   아예 못 골랐다 (엔터만 됐다). 윈도우에서 창을 처음 실제로 써 본
        #   사용자가 잡았다 (2026-09-21). 가짜 tkinter 로는 못 보는 종류다.
        #   -> 한 번 누르면 고르고, 마우스가 목록 위에 있으면 닫지 않는다.
        self.entry.bind("<FocusOut>", lambda _e: self.box.after(
            150, self._maybe_hide))
        self.list.bind("<ButtonRelease-1>", self._click)
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

    def _pointer_in_pop(self):
        """마우스가 후보 목록 위에 있나."""
        try:
            x, y = self.pop.winfo_pointerxy()
            w = self.pop.winfo_containing(x, y)
        except Exception:
            return False
        return w is not None and str(w).startswith(str(self.pop))

    def _maybe_hide(self):
        # 목록을 누르러 가는 중이면 닫지 않는다 — 닫으면 못 고른다
        if self._pointer_in_pop():
            return
        self.hide()

    def _click(self, e):
        """한 번 눌러서 고른다. 누른 줄을 직접 찾는다 (선택이 늦게 잡힐 수 있다)."""
        if not getattr(self, "_hits", None):
            return "break"
        i = self.list.nearest(e.y)
        if i < 0 or i >= len(self._hits):
            return "break"
        self.list.selection_clear(0, "end")
        self.list.selection_set(i)
        return self._enter()

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

    def hp_pct(self):
        return _hp_from(self.hp)

    def on_active(self):
        """'나와 있음' 이면 **당연히 낸 것이다** (상대 칸과 같은 규칙)."""
        if self.poke is not None:
            self.brought.set(True)

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
        self.name.source([(live.poke_label(p), p)
                          for p in live.pickable_pokemon(self.dex)])
        self.title = tk.Label(top, text="", bg=CARD, fg=TEXT, font=FONT_B)
        self.title.pack(side="left", padx=(8, 0))
        tk.Button(top, text="비우기", command=self.clear, bg=LINE, fg=TEXT,
                  relief="flat", font=FONT_S).pack(side="right")

        # -- 이번 판: HP · 냈다 · 나와 있음 ---------------------------------
        # ! **상대 칸과 똑같이 만든다.** 이게 없어서 창이 내 6마리 전부를
        #   HP 100% 로 계산했다 (2026-09-21). 규칙은 live.my_turn_state.
        bt = tk.Frame(self.box, bg=CARD)
        bt.pack(fill="x", pady=(3, 0))
        tk.Label(bt, text="이번 판", bg=CARD, fg=DIM, font=FONT_S,
                 width=6, anchor="w").pack(side="left")
        tk.Label(bt, text="HP", bg=CARD, fg=DIM,
                 font=FONT_S).pack(side="left", padx=(0, 1))
        self.hp = tk.StringVar(value="100")
        tk.Spinbox(bt, from_=0, to=100, increment=5, width=4,
                   textvariable=self.hp, bg=FIELD, fg=TEXT,
                   insertbackground=TEXT, relief="flat",
                   buttonbackground=LINE, font=FONT_S).pack(side="left")
        tk.Label(bt, text="% (0=쓰러짐)", bg=CARD, fg=DIM,
                 font=FONT_S).pack(side="left", padx=(1, 0))
        self.brought = tk.BooleanVar(value=False)
        tk.Checkbutton(bt, text="냈다", variable=self.brought,
                       bg=CARD, fg=TEXT, selectcolor=FIELD,
                       activebackground=CARD, activeforeground=TEXT,
                       font=FONT_S).pack(side="left", padx=(8, 0))
        tk.Radiobutton(bt, text="나와 있음", variable=app.my_active,
                       value=index, bg=CARD, fg=TEXT, selectcolor=FIELD,
                       activebackground=CARD, activeforeground=TEXT,
                       font=FONT_S, command=self.on_active
                       ).pack(side="left", padx=(8, 0))
        # 상태이상 — 물러나도 남는다 (그래서 자리마다)
        self.status = tk.StringVar()
        _choice_box(tk, bt, self.status, STATUS_CHOICES, 5).pack(side="left", padx=(8, 0))

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
            # 폭은 '0' 글자 기준이라 한글 네 글자(특수공격)가 6칸에 안
            # 들어갔다 — 화면에서 「특수공ㅈ」 로 잘려 보였다 (2026-09-21,
            # 윈도우에서 창을 처음 실제로 띄워서 잡음). --점검 의
            # clipped_labels 가 이걸 다시 잡는다.
            tk.Label(r, text=ko, width=8, anchor="w", bg=CARD, fg=DIM,
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
        self.status.set(NO_STATUS)
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
        else:
            base = live.pickable_for(self.dex, base) or base
        self.name.set(live.poke_label(base), base)
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


def _hp_from(var):
    """HP 칸 -> 숫자. **빈 칸은 만피.** 이상한 글자도 만피로 본다.
    (float("" or 0) 은 0 이라, 그대로 두면 칸을 비웠을 때 조용히 '쓰러짐' 이 된다)"""
    text = (var.get() or "").strip()
    if not text:
        return 100.0
    try:
        return max(0.0, min(100.0, float(text)))
    except ValueError:
        return 100.0


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
        self.name.source([(live.poke_label(p), p)
                          for p in live.pickable_pokemon(self.dex)])
        tk.Label(self.box, text="HP", bg=CARD, fg=DIM,
                 font=FONT_S).pack(side="left", padx=(6, 1))
        self.hp = tk.StringVar(value="100")
        # 0 이면 쓰러진 것으로 본다. 칸을 따로 만들지 않는다.
        tk.Spinbox(self.box, from_=0, to=100, increment=5, width=4,
                   textvariable=self.hp, bg=FIELD, fg=TEXT,
                   insertbackground=TEXT, relief="flat",
                   buttonbackground=LINE, font=FONT_S).pack(side="left")
        # **밝혀졌나.** 프리뷰에서 본 6마리와, 실제로 낸 것이 확인된 놈은
        # 다른 것이다. 상대 선출은 모르지만 **밝혀진 만큼은 알고 있고**,
        # 그게 눈에 보여야 한다 (사용자 요청, 2026-09-19).
        self.brought = tk.BooleanVar(value=False)
        tk.Checkbutton(self.box, text="냈다", variable=self.brought,
                       bg=CARD, fg=TEXT, selectcolor=FIELD,
                       activebackground=CARD, activeforeground=TEXT,
                       font=FONT_S, command=self.redraw_state
                       ).pack(side="left", padx=(6, 0))
        tk.Radiobutton(self.box, text="나와 있음", variable=app.opp_active,
                       value=index, bg=CARD, fg=TEXT, selectcolor=FIELD,
                       activebackground=CARD, activeforeground=TEXT,
                       font=FONT_S,
                       command=self.on_active).pack(side="left", padx=(6, 0))
        self.status = tk.StringVar()
        _choice_box(tk, self.box, self.status, STATUS_CHOICES, 5).pack(side="left", padx=(6, 0))
        # 한눈에 보이는 표시 — ● 밝혀짐 / ○ 아직 모름
        self.state_label = tk.Label(self.box, text="", bg=CARD, fg=DIM,
                                    font=FONT_S, width=8, anchor="w")
        self.state_label.pack(side="left", padx=(6, 0))
        self.seen_label = tk.Label(self.box, text="", bg=CARD, fg=DIM,
                                   font=FONT_S, anchor="w")
        self.seen_label.pack(side="left", padx=(6, 0))

    def on_active(self):
        """'나와 있음' 으로 고르면 **그놈은 당연히 낸 것이다.**
        따로 체크하게 만들면 잊어버리고, 그러면 계산에서 빠진다."""
        if self.poke is not None:
            self.brought.set(True)
        self.app.draw_seen()
        self.app.redraw_opp_states()

    def revealed(self):
        """밝혀진 놈인가 (낸 것이 확인됐나)."""
        return bool(self.poke) and bool(self.brought.get())

    def redraw_state(self):
        if self.poke is None:
            self.state_label.config(text="", fg=DIM)
        elif self.brought.get():
            self.state_label.config(text="● 밝혀짐", fg=GOOD)
        else:
            self.state_label.config(text="○ 모름", fg=DIM)
        self.app.redraw_opp_states()

    def on_poke(self, poke):
        self.poke = poke
        self.redraw_state()
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
        self.watcher = None         # 따라가기 (watch.Watcher) — 처음 켤 때 만든다
        self.follow_said = None     # 같은 알림을 되풀이하지 않으려고
        self.overlay = self.overlay_text = None   # 추천만 띄우는 작은 창
        self.last_short = None                    # 거기 띄울 몇 줄
        self.slots = []
        self.opp_slots = []
        # 상대 이름 -> 본 기술 목록. **상대마다 따로 쌓는다** —
        # 지진을 쓴 것은 그때 나와 있던 놈이지 상대 셋 전부가 아니다.
        self.seen = {}
        # 화면 문구로 드러난 상대 도구·특성 (screenread) — 이름 -> 값
        self.opp_items = {}
        self.opp_abilities = {}

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
        canvas = tk.Canvas(left, bg=BG, highlightthickness=0, width=500,
                           yscrollincrement=20)
        bar = tk.Scrollbar(left, orient="vertical", command=canvas.yview)
        self.party_box = tk.Frame(canvas, bg=BG)
        # ! **보이는 폭이 내용 폭을 따라가게 한다.** 폭 500 으로 못 박아 두니
        #   빈 칸일 때 이미 딱 500 이었고, 성격·특성·도구를 채우면 536 이 돼서
        #   **모든 칸**의 오른쪽 끝(비우기 · 능력 포인트 · 도구 칸)이 잘렸다.
        #   (2026-09-21, 창을 실제로 띄워서 잡음) --점검 이 다시 잰다.
        def _fit(_e=None):
            canvas.configure(scrollregion=canvas.bbox("all"))
            need = self.party_box.winfo_reqwidth()
            if need > int(float(canvas.cget("width"))):
                canvas.configure(width=need)
        self.party_box.bind("<Configure>", _fit)
        self._fit_party = _fit
        canvas.create_window((0, 0), window=self.party_box, anchor="nw")
        canvas.configure(yscrollcommand=bar.set)
        canvas.pack(side="left", fill="y", expand=False)
        bar.pack(side="left", fill="y")
        self.canvas = canvas

        self.my_active = tk.IntVar(value=0)
        # 「이번 턴에 막 나옴」 — 속이기·만나자마자는 나온 뒤 첫 기술일 때만 된다
        # (2026-09-22). 손이 덜 가게: 처음엔 켜져 있고(첫 턴은 둘 다 막 나옴),
        # 계산하고 나면 꺼지고, '나와 있음' 을 바꾸면 그쪽이 다시 켜진다.
        self.my_fresh = tk.BooleanVar(value=True)
        self.my_active.trace_add("write", lambda *_a: self.my_fresh.set(True))
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

        # ! **휠이 아예 연결돼 있지 않았다.** 왼쪽 파티는 여섯 자리라
        #   길어서 스크롤이 필수인데, 막대를 잡아 끌어야만 내려갔다.
        #   (2026-09-21, 사용자가 창을 처음 실제로 써 보고 잡음)
        #   윈도우 Tk 8.6 은 휠을 **초점 가진 칸**에 보낸다 — 마우스 밑이
        #   아니다. 그래서 전체에 걸고, 마우스 밑이 어디인지 직접 본다.
        self.root.bind_all("<MouseWheel>", self._on_wheel)
        self.root.bind_all("<Button-4>", self._on_wheel)     # 리눅스
        self.root.bind_all("<Button-5>", self._on_wheel)

        # ! **창을 줄이면 오른쪽이 잘렸다.** 왼쪽을 폭 500 으로 못 박았는데
        #   최소 크기를 안 정해서, 좁히면 오른쪽 패널이 창 밖으로 밀려났다.
        #   -> 가로는 내용물보다 못 줄이게 한다. 세로는 결과 칸만 줄어들게
        #   남겨 둔다 (왼쪽은 스크롤, 결과 칸은 늘었다 줄었다 한다).
        self.root.update_idletasks()
        min_h = (self.root.winfo_reqheight() - self.out.winfo_reqheight()
                 + MIN_OUT_H)
        self.root.minsize(self.root.winfo_reqwidth(), min_h)
        self.min_size = (self.root.winfo_reqwidth(), min_h)

    def wheel_target(self, w):
        """마우스 밑 위젯 -> 굴릴 것. 파티 칸 어디든 왼쪽 캔버스를 굴린다.

        결과 칸(Text)·후보 목록(Listbox) 위면 그것을 굴린다.
        아무것도 아니면 None.
        """
        node = w
        while node is not None:
            if node is self.canvas:
                return self.canvas
            try:
                cls = node.winfo_class()
            except Exception:
                cls = ""
            if cls in ("Text", "Listbox"):
                return node
            node = getattr(node, "master", None)
        return None

    def _on_wheel(self, e):
        try:
            w = self.root.winfo_containing(e.x_root, e.y_root)
        except Exception:
            w = None
        target = self.wheel_target(w)
        if target is None:
            return None
        if target is not self.canvas and target is getattr(e, "widget", None):
            return None           # 그 칸이 제 휠을 이미 처리했다 — 두 번 굴리지 않는다
        num = getattr(e, "num", None)
        if num == 4:
            step = -1
        elif num == 5:
            step = 1
        else:
            step = -1 if (e.delta or 0) > 0 else 1
        target.yview_scroll(step * WHEEL_UNITS, "units")
        return "break"

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
        tk.Label(box, text="「냈다」 를 켜면 ● 밝혀짐 — 이번 턴 계산에 들어갑니다. "
                           "안 켠 것은 프리뷰에서 본 것뿐입니다.",
                 bg=CARD, fg=DIM, font=FONT_S).pack(anchor="w")
        tk.Label(box, text="HP 0 이면 쓰러진 것으로 봅니다. "
                           "배분·성격은 안 묻습니다 (사용률에서 뽑습니다).",
                 bg=CARD, fg=DIM, font=FONT_S).pack(anchor="w")
        self.opp_active = tk.IntVar(value=0)
        self.opp_fresh = tk.BooleanVar(value=True)
        self.opp_active.trace_add("write", lambda *_a: self.opp_fresh.set(True))
        self.opp_state = tk.Label(box, text="", bg=CARD, fg=DIM,
                                  font=FONT_S, anchor="w")
        self.opp_state.pack(anchor="w")
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

        # ! 여기 있던 「나와 있는 내 포켓몬(번호)」「내 HP%」 는 **없앴다.**
        #   왼쪽 각 자리의 「이번 판」 줄로 옮겼다 (2026-09-21). 같은 값을
        #   두 군데서 받으면 둘이 어긋나도 모른다.
        tk.Label(box, text="내 쪽은 왼쪽 각 자리의 「이번 판」 줄에서 "
                 "HP · 냈다 · 나와 있음을 고릅니다.",
                 bg=CARD, fg=DIM, font=FONT_S).pack(anchor="w", pady=(4, 0))

        rf = tk.Frame(box, bg=CARD)
        rf.pack(fill="x", pady=(6, 0))
        tk.Label(rf, text="이번 턴에 막 나옴", bg=CARD, fg=DIM,
                 font=FONT_S).pack(side="left")
        for text, var in (("내 쪽", self.my_fresh), ("상대", self.opp_fresh)):
            tk.Checkbutton(rf, text=text, variable=var, bg=CARD, fg=TEXT,
                           selectcolor=FIELD, activebackground=CARD,
                           activeforeground=TEXT,
                           font=FONT_S).pack(side="left", padx=(6, 0))
        tk.Label(box, text="(속이기·만나자마자가 되는 턴인가. 계산하면 꺼지고, "
                 "'나와 있음' 을 바꾸면 켜집니다)",
                 bg=CARD, fg=DIM, font=FONT_S).pack(anchor="w")

        # -- 실전 중간 상태: 날씨·필드 · 압정 · 랭크 (2026-09-23) ---------------------
        # 전엔 칸이 없어 계산이 매번 '날씨는 특성으로, 랭크 0, 압정 없음' 으로 돌았다.
        rw = tk.Frame(box, bg=CARD)
        rw.pack(fill="x", pady=(6, 0))
        self.weather, self.weather_turns = tk.StringVar(), tk.StringVar(value="5")
        self.terrain, self.terrain_turns = tk.StringVar(), tk.StringVar(value="5")
        for label, var, turns, values in (("날씨", self.weather, self.weather_turns, WEATHER_CHOICES),
                                          ("필드", self.terrain, self.terrain_turns, TERRAIN_CHOICES)):
            tk.Label(rw, text=label, bg=CARD, fg=DIM, font=FONT_S).pack(side="left", padx=(0, 2))
            _choice_box(tk, rw, var, values, 9).pack(side="left")
            tk.Label(rw, text="남은", bg=CARD, fg=DIM, font=FONT_S).pack(side="left", padx=(4, 1))
            tk.Spinbox(rw, from_=1, to=8, width=2, textvariable=turns, bg=FIELD, fg=TEXT,
                       insertbackground=TEXT, relief="flat", buttonbackground=LINE,
                       font=FONT_S).pack(side="left")
            tk.Label(rw, text="턴", bg=CARD, fg=DIM, font=FONT_S).pack(side="left", padx=(1, 10))
        tk.Label(box, text="(자동 = 나와 있는 포켓몬의 특성으로. 모래날림 하마돈이 나와 있으면 모래바람)",
                 bg=CARD, fg=DIM, font=FONT_S).pack(anchor="w")

        self.hazards, self.ranks = {}, {}
        for side, who in (("me", "내 쪽"), ("opp", "상대 쪽")):
            rh = tk.Frame(box, bg=CARD)
            rh.pack(fill="x", pady=(4, 0))
            tk.Label(rh, text="%s 압정" % who, bg=CARD, fg=DIM, font=FONT_S,
                     width=11, anchor="w").pack(side="left")
            self.hazards[side] = {}
            for name, most in HAZARD_KEYS:
                if most == 1:
                    var = tk.BooleanVar(value=False)
                    tk.Checkbutton(rh, text=name, variable=var, bg=CARD, fg=TEXT,
                                   selectcolor=FIELD, activebackground=CARD,
                                   activeforeground=TEXT, font=FONT_S).pack(side="left", padx=(0, 4))
                else:
                    var = tk.StringVar(value="0")
                    tk.Label(rh, text=name, bg=CARD, fg=TEXT, font=FONT_S).pack(side="left")
                    tk.Spinbox(rh, from_=0, to=most, width=2, textvariable=var, bg=FIELD, fg=TEXT,
                               insertbackground=TEXT, relief="flat", buttonbackground=LINE,
                               font=FONT_S).pack(side="left", padx=(1, 6))
                self.hazards[side][name] = var
        for side, who in (("me", "내 랭크"), ("opp", "상대 랭크")):
            rr = tk.Frame(box, bg=CARD)
            rr.pack(fill="x", pady=(4, 0))
            tk.Label(rr, text=who, bg=CARD, fg=DIM, font=FONT_S, width=11,
                     anchor="w").pack(side="left")
            self.ranks[side] = {}
            for key, short in RANK_KEYS:
                var = tk.StringVar(value="0")
                tk.Label(rr, text=short, bg=CARD, fg=TEXT, font=FONT_S).pack(side="left")
                tk.Spinbox(rr, from_=-6, to=6, width=2, textvariable=var, bg=FIELD, fg=TEXT,
                           insertbackground=TEXT, relief="flat", buttonbackground=LINE,
                           font=FONT_S).pack(side="left", padx=(1, 5))
                self.ranks[side][key] = var
        tk.Label(box, text="(랭크는 나와 있는 포켓몬 것 — 바꾸면 0 으로. 위협 등으로 떨어진 것도 "
                 "여기 적어야 계산에 들어갑니다)", bg=CARD, fg=DIM, font=FONT_S).pack(anchor="w")
        # 나와 있는 놈이 바뀌면 그쪽 랭크는 풀린다 (게임 규칙)
        self._last_active = {"me": self.my_active.get(), "opp": self.opp_active.get()}
        self.my_active.trace_add("write", lambda *_a: self.reset_ranks("me"))
        self.opp_active.trace_add("write", lambda *_a: self.reset_ranks("opp"))

        # 화면 사진 넣기 — 선출 화면이면 상대 6마리, 대전 화면이면 문구 칸의 일 (screenread)
        rs = tk.Frame(box, bg=CARD)
        rs.pack(fill="x", pady=(6, 0))
        self.go_screen = tk.Button(rs, text="화면 사진 넣기", command=self.load_screens,
                                   bg=LINE, fg=TEXT, relief="flat", font=FONT_B)
        self.go_screen.pack(side="left")
        # 따라가기 — OBS 창 프로젝터를 계속 읽어 칸을 채우고 둘 수를 다시 알려 준다 (watch.py)
        self.following = False
        self.go_follow = tk.Button(rs, text="따라가기 시작", command=self.toggle_follow,
                                   bg=LINE, fg=TEXT, relief="flat", font=FONT_B)
        self.go_follow.pack(side="left", padx=(6, 0))
        # ★ **창 프로젝터를 전체화면으로 두면 이 창이 뒤에 깔려 왔다갔다해야 한다**
        #   (사용자, 2026-09-23). 처음엔 이 창을 통째로 위에 올렸는데 **게임 화면을 가려서
        #   더 나빠졌다** (사용자: "문제가 해결되기는커녕 오히려 악화되었어").
        #   → **추천만 담은 작은 창**을 위에 띄운다. 게임은 그대로 보이고 답만 구석에 뜬다.
        self.on_top = tk.IntVar(value=0)
        tk.Checkbutton(rs, text="추천 작은 창", variable=self.on_top, command=self.apply_on_top,
                       bg=CARD, fg=TEXT, selectcolor=FIELD, activebackground=CARD,
                       activeforeground=TEXT, font=FONT_S).pack(side="left", padx=(6, 0))
        tk.Label(rs, text="사진: 선출 화면 → 상대 6마리 · 대전 화면 → 문구 칸 (여러 장은 순서대로) /"
                 " 따라가기: OBS 「창 프로젝터」 를 계속 읽습니다",
                 bg=CARD, fg=DIM, font=FONT_S).pack(side="left", padx=(6, 0))

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
    def reset_ranks(self, side):
        """나와 있는 놈이 **실제로 바뀌었을 때만** 그쪽 랭크를 0 으로.
        (tkinter 는 같은 값을 다시 넣어도 '바뀜' 으로 알린다 — 같은 자리를 다시 눌러도 지워질 뻔했다.)"""
        now = (self.my_active if side == "me" else self.opp_active).get()
        last = getattr(self, "_last_active", {})
        if last.get(side) == now:
            return
        last[side] = now
        self._last_active = last
        for var in getattr(self, "ranks", {}).get(side, {}).values():
            var.set("0")

    def mid_state(self, my_slots, opp_slots):
        """창의 실전 중간 상태 칸 -> 계산에 넘길 것 (battle.Battle 의 이름 그대로).

        my_slots / opp_slots — 넘기는 목록의 각 자리가 원래 몇 번 자리였나. 상태이상은 자리마다다.
        """
        st = lambda sl: None if sl.status.get() in ("", NO_STATUS) else sl.status.get()
        field = {}
        for key, var, turns in (("weather", self.weather, self.weather_turns),
                                ("terrain", self.terrain, self.terrain_turns)):
            v = var.get()
            if v and v != AUTO:
                field[key] = None if v == "없음" else v
                field[key + "_turns"] = max(1, _int(turns, 5))
        hz = {}
        for side in ("me", "opp"):
            got = {}
            for name, most in HAZARD_KEYS:
                var = self.hazards[side][name]
                n = (1 if var.get() else 0) if most == 1 else max(0, min(most, _int(var)))
                if n:
                    got[name] = n
            hz[side] = got or None
        ranks = {side: {k: max(-6, min(6, _int(v))) for k, v in self.ranks[side].items()
                        if _int(v)} for side in ("me", "opp")}
        return {"my_status": [st(self.slots[i]) for i in my_slots],
                "opp_status": [st(self.opp_slots[i]) for i in opp_slots],
                "my_ranks": ranks["me"], "opp_ranks": ranks["opp"], "field": field,
                "my_hazards": hz["me"], "opp_hazards": hz["opp"]}

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
            for d in (self.seen, self.opp_items, self.opp_abilities):
                d.pop(sl.poke["name"], None)
        self.draw_seen()

    def draw_seen(self):
        for sl in self.opp_slots:
            name = (sl.poke or {}).get("name")
            got = list(self.seen.get(name) or [])
            if self.opp_items.get(name):
                got.append("도구 " + self.opp_items[name])
            if self.opp_abilities.get(name):
                got.append("특성 " + self.opp_abilities[name])
            sl.draw_seen(got)

    def redraw_opp_states(self):
        """상대 쪽 한 줄 요약. '6마리 중 2마리 밝혀짐' 처럼."""
        filled = [sl for sl in self.opp_slots if sl.poke]
        shown = [sl for sl in filled if sl.revealed()]
        if not filled:
            self.opp_state.config(text="상대를 아직 안 적었습니다.", fg=DIM)
            return
        self.opp_state.config(
            text="프리뷰 %d마리 적음 · 그중 %d마리가 밝혀짐 (%s)"
                 % (len(filled), len(shown),
                    ", ".join(sl.poke["name"] for sl in shown) or "아직 없음"),
            fg=(GOOD if shown else DIM))

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
        notes = []
        saved = live.load_party(self.dex, notes=notes)
        if notes:
            # 콘솔이 아니라 **창에** 보여 준다 — 콘솔은 창을 쓰는 사람에게 안 보인다
            self.say("저장된 파티를 읽다가 고친 것:\n  " + "\n  ".join(notes)
                     + "\n→ 칸을 확인하세요. 고치면 자동으로 다시 저장됩니다.")
        if not saved:
            return
        while len(self.slots) < len(saved):
            self.add_slot()
        for slot, row in zip(self.slots, saved):
            slot.fill_from(row[0], row[1])

    def ask(self, clear=True):
        """탐색은 **다른 갈래에서 돌린다.** 안 그러면 창이 10초 동안 언다.

        `clear=False` 는 따라가기에서 쓴다 — **방금 보여 준 「읽었습니다」 를 지우면 안 된다.**
        (계산 전에 읽은 것을 먼저 보여 주기로 사용자와 정했다, 2026-09-21.)
        """
        if self.busy:
            return
        party = self.party()
        if not party:
            self.say("먼저 왼쪽에 파티를 채우세요.", clear=clear)
            return
        def num(var, default):
            try:
                return float(var.get())
            except (ValueError, AttributeError):
                return default

        # 내 쪽 — **이번 판에 낸 놈만, 각자의 HP 로.** (live.my_turn_state)
        mine_rows = []
        for sl in self.slots:
            b, bad = sl.build()
            ok = b is not None and not bad
            mine_rows.append((b if ok else None,
                              sl.move_names() if ok else [],
                              sl.hp_pct(), bool(sl.brought.get())))
        mine = live.my_turn_state(mine_rows, self.my_active.get())
        if mine["why"]:
            self.say("%s — 왼쪽 「이번 판」 줄을 확인하세요." % mine["why"],
                     clear=clear)
            return
        party = mine["party"]
        idx = mine["my_active"]
        my_hp = mine["my_hp"]
        self.guessed_mine = mine["guessed"]

        # 쓰러진 상대(HP 0)는 빼고 넘긴다. 빼면 번호가 밀리므로
        # **나와 있는 놈의 새 번호를 다시 찾는다.** 여기서 어긋나면
        # 상대가 엉뚱한 놈을 겨냥한 채 계산이 돈다.
        # ★ **이번 턴은 '밝혀진 놈' 으로만 센다.** 프리뷰에서 본 6마리를
        #    전부 넣으면 상대가 6마리를 낸 판을 재게 된다 — 실제로는
        #    3마리만 나온다. 하나도 안 켰으면 적은 것 전부로 본다.
        shown = [sl for sl in self.opp_slots if sl.revealed()]
        use = shown if shown else [sl for sl in self.opp_slots if sl.poke]
        self.guessed_opp = not shown
        rows = [(sl.poke if sl in use else None, sl.hp_pct())
                for sl in self.opp_slots]
        opp_pokes, state, why = live.turn_state(
            my_hp, idx, rows, self.opp_active.get())
        if why:
            self.say("%s — 상대를 고르세요 (HP 0 은 쓰러진 것으로 봅니다)."
                     % why, clear=clear)
            return
        secs = max(1.0, num(self.secs, 10))
        ev = live.evidence_map(self.seen, opp_pokes, self.opp_items, self.opp_abilities)
        oi = state["opp_active"]
        # 막 나왔나 — 계산에 넘기고, 넘긴 뒤엔 끈다 (다음 턴엔 이미 나와 있던 것이다).
        # 안 넘기면 대전이 '모름' 으로 보고 막 나온 것으로 가정한다 (경고만 남긴다).
        state = dict(state, my_fresh=bool(self.my_fresh.get()),
                     opp_fresh=bool(self.opp_fresh.get()))
        # 상태이상 · 랭크 · 날씨·필드 · 압정 — 자리 번호는 넘기는 목록에 맞춘다
        mid = self.mid_state(mine["slots"], live.alive_slots(rows))
        state.update(mid)
        self.my_fresh.set(False)
        self.opp_fresh.set(False)

        self.busy = True
        self.go.config(text="생각하는 중...", state="disabled")
        # 화면에 찍는 것도 **넘긴 값 그대로** 쓴다. 따로 다시 세면
        # 화면과 계산이 갈라진다 — 이 저장소가 늘 고장 나는 방식이다.
        said = ", ".join("%s %.0f%%" % (p["name"], hp)
                         for p, hp in zip(opp_pokes, state["opp_hp"]))
        self.say("상대 %s 를 놓고 %.0f초 생각합니다...\n(나와 있는 상대: %s)"
                 % (said, secs, opp_pokes[oi]["name"]), clear=clear)
        extra = describe_mid(mid, [b.poke["name"] for b, _m in party],
                             [p["name"] for p in opp_pokes])
        if extra:
            self.say("넘긴 판 상태: " + extra)

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
            text = self._format(got, len(opp_pokes),
                                guessed_opp=self.guessed_opp)
        except Exception:
            import traceback
            text = "문제가 생겼습니다:\n%s" % traceback.format_exc()
        if self.headless:
            self._show(text)
        else:
            self.root.after(0, lambda: self._show(text))

    # -- 화면 사진 --------------------------------------------------------
    def board(self):
        """창의 칸 -> screenread.Board."""
        import screenread
        my = []
        for sl in self.slots:
            b, bad = sl.build()
            # 최대 HP(능력치) — 화면의 「145/215」 로 누가 나와 있는지 맞춰 볼 때 쓴다
            my.append({"poke": sl.poke, "hp": sl.hp_pct(), "brought": bool(sl.brought.get()),
                       "maxhp": b.stat("hp") if b is not None and not bad else None,
                       "status": sl.status.get()})
        opp = [{"poke": sl.poke, "hp": sl.hp_pct(), "brought": bool(sl.brought.get()),
                "status": sl.status.get()}
               for sl in self.opp_slots]
        bd = screenread.Board(my, opp, self.my_active.get(), self.opp_active.get(),
                              bool(self.my_fresh.get()), bool(self.opp_fresh.get()),
                              self.seen, self.opp_items, self.opp_abilities)
        bd.ranks = {side: {k: _int(v) for k, v in self.ranks[side].items()} for side in ("me", "opp")}
        # 판에서는 '자동' 을 None 으로 둔다
        auto = lambda v: None if v in ("", AUTO) else v
        bd.weather, bd.weather_turns = auto(self.weather.get()), _int(self.weather_turns, 5)
        bd.terrain, bd.terrain_turns = auto(self.terrain.get()), _int(self.terrain_turns, 5)
        bd.hazards = {}
        for side in ("me", "opp"):
            got = {}
            for name, most in HAZARD_KEYS:
                var = self.hazards[side][name]
                got[name] = (1 if var.get() else 0) if most == 1 else _int(var)
            bd.hazards[side] = got
        return bd

    def set_board(self, bd):
        """screenread.Board -> 창의 칸. '나와 있음' 을 바꾸면 '막 나옴' 이 켜지므로
        (trace) 나와 있음을 먼저 넣고 막 나옴을 나중에 넣는다."""
        for sl, row in zip(self.slots, bd.my):
            sl.hp.set("%g" % row["hp"])
            sl.brought.set(bool(row["brought"]))
            sl.status.set(row.get("status") or NO_STATUS)
        for sl, row in zip(self.opp_slots, bd.opp + [None] * len(self.opp_slots)):
            poke = row["poke"] if row else None
            if poke is not sl.poke:
                sl.name.set(live.poke_label(poke) if poke else "", poke)
                sl.poke = poke
            sl.hp.set("%g" % (row["hp"] if row else 100.0))
            sl.brought.set(bool(row and row["brought"]))
            sl.status.set((row and row.get("status")) or NO_STATUS)
            sl.redraw_state()
        # 나와 있음 → (바뀌었으면 랭크 0) → 판의 랭크 → 막 나옴 순서
        self.my_active.set(bd.my_active)
        self.opp_active.set(bd.opp_active)
        for side in ("me", "opp"):
            for k, var in self.ranks[side].items():
                var.set(str(bd.ranks.get(side, {}).get(k, 0)))
            for name, var in self.hazards[side].items():
                n = bd.hazards.get(side, {}).get(name, 0)
                var.set(bool(n) if isinstance(var, self.tk.BooleanVar) else str(n))
        self.weather.set(bd.weather or AUTO)
        self.weather_turns.set(str(bd.weather_turns))
        self.terrain.set(bd.terrain or AUTO)
        self.terrain_turns.set(str(bd.terrain_turns))
        self.my_fresh.set(bool(bd.my_fresh))
        self.opp_fresh.set(bool(bd.opp_fresh))
        self.seen, self.opp_items, self.opp_abilities = bd.seen, bd.opp_items, bd.opp_abilities
        self.draw_seen()
        self.redraw_opp_states()

    def load_screens(self, files=None):
        """사진 고르기 -> 읽기(다른 갈래) -> 칸에 넣기 + '이렇게 읽었습니다'."""
        if self.busy:
            return
        if files is None:
            from tkinter import filedialog
            files = filedialog.askopenfilenames(
                title="게임 화면 사진 (여러 장이면 찍은 순서대로)",
                filetypes=[("사진", "*.png *.jpg *.jpeg"), ("모든 파일", "*.*")])
        files = list(files or [])
        if not files:
            return
        import msgread
        here = [sl.poke["name"] for sl in self.slots + self.opp_slots if sl.poke]
        names = msgread.Names(self.dex, here)
        self.busy = True
        self.go_screen.config(text="읽는 중...", state="disabled")
        self.say("사진 %d장을 읽습니다..." % len(files), clear=True)

        def work():
            import screenread
            got = []
            for f in files:
                try:
                    got.append((f, screenread.read_screen(f, self.dex, names), None))
                except Exception as e:
                    got.append((f, None, "%s: %s" % (type(e).__name__, e)))
            if self.headless:
                self._apply_screens(got)
            else:
                self.root.after(0, lambda: self._apply_screens(got))

        if self.headless:
            work()
        else:
            threading.Thread(target=work, daemon=True).start()

    # -- 따라가기 ---------------------------------------------------------
    #
    # OBS 창 프로젝터를 계속 읽어 (watch.Watcher) 칸을 채우고, **판이 바뀌면 둘 수를 다시
    # 물어본다.** 사용자가 게임하면서 칸을 손으로 채우기 힘들다고 해서 시작한 일이다.
    # ★ 읽은 것은 **언제나 먼저 보여 준다** — 잘못 읽으면 조용히 틀리기 때문이다.
    FOLLOW_REST = 0.2       # 한 바퀴 돌고 쉬는 시간 (읽는 데 0.5초쯤 걸린다)

    # -- 추천 작은 창 -----------------------------------------------------
    #
    # 게임 화면(OBS 창 프로젝터)을 전체화면으로 두면 이 창이 뒤에 깔린다. 그렇다고 이 창을
    # 통째로 위에 올리면 **게임이 안 보인다.** 그래서 **추천만 담은 작은 창**을 구석에 띄운다.
    OVERLAY_SIZE = (460, 210)

    def apply_on_top(self):
        """작은 창을 켜고 끈다. 가짜 tkinter 에는 Toplevel·attributes 가 없을 수 있으니 조용히 넘어간다."""
        want = bool(self.on_top.get())
        if not want:
            if self.overlay is not None:
                try:
                    self.overlay.destroy()
                except Exception:
                    pass
                self.overlay = self.overlay_text = None
            return False
        if self.overlay is not None:
            return True
        tk = self.tk
        try:
            top = tk.Toplevel(self.root)
            top.title("지금 둘 수")
            top.configure(bg=BG)
            top.attributes("-topmost", True)
            w, h = self.OVERLAY_SIZE
            # 오른쪽 위 구석에 — 게임 화면에서 문구 칸(왼쪽 아래)과 제일 안 겹치는 자리다
            try:
                sw = self.root.winfo_screenwidth()
            except Exception:
                sw = 1920
            top.geometry("%dx%d+%d+%d" % (w, h, max(0, sw - w - 40), 40))
            body = tk.Text(top, bg=BG, fg=TEXT, relief="flat", padx=10, pady=8,
                           wrap="word", font=("Malgun Gothic", 13, "bold"))
            body.pack(fill="both", expand=True)
            top.protocol("WM_DELETE_WINDOW", lambda: (self.on_top.set(0), self.apply_on_top()))
        except Exception:
            self.on_top.set(0)
            return False
        self.overlay, self.overlay_text = top, body
        self.show_overlay(self.last_short or "판이 바뀌면 여기에 둘 수를 띄웁니다.")
        return True

    def show_overlay(self, text):
        """작은 창에 글을 띄운다. 꺼져 있으면 아무것도 안 한다."""
        if self.overlay_text is None:
            return False
        try:
            self.overlay_text.delete("1.0", "end")
            self.overlay_text.insert("end", text)
        except Exception:
            return False
        return True

    @staticmethod
    def short_advice(text):
        """긴 보고에서 **답과 경고만** 뽑는다 — 작은 창에 넣을 몇 줄."""
        # 한 턴의 답은 「=> 지진 …」, 선출의 답은 「▶ 선봉 …」 · 「벤치 …」 로 나온다.
        # 경고(「!」)도 같이 띄운다 — 답만 보고 믿으면 안 되는 자리가 있다.
        want = [ln.strip() for ln in (text or "").splitlines()
                if ln.lstrip().startswith(("=>", "!", "▶", "벤치"))]
        if not want:
            want = [ln for ln in (text or "").splitlines() if ln.strip()][:4]
        return "\n".join(want[:6])

    def toggle_follow(self):
        if self.following:
            self.following = False
            self.go_follow.config(text="따라가기 시작")
            self.say("따라가기를 멈췄습니다.")
            return
        if self.watcher is None:
            import watch
            # 읽은 것을 파일에도 남긴다 — 창은 글이 밀려 올라가서 판이 끝나면 앞부분을 못 본다
            log = paths.mine("대전기록", "따라간기록_%s.txt" % time.strftime("%m%d_%H%M"))
            try:
                self.watcher = watch.Watcher(log=log)
            except Exception as e:
                self.say("따라가기를 못 켰습니다 — %s" % e, clear=True)
                return
        self.following = True
        self.go_follow.config(text="따라가기 멈춤")
        self.say("따라갑니다 — OBS 「창 프로젝터(미리 보기)」 를 띄워 두세요.\n"
                 "읽은 것을 그때그때 보여 드리고, 판이 바뀌면 둘 수를 다시 알려 드립니다.\n"
                 "(읽은 것은 %s 에도 남습니다)" % (self.watcher.log or "(기록 없음)"),
                 clear=True)
        if self.headless:
            self.follow_once()
        else:
            threading.Thread(target=self._follow_loop, daemon=True).start()

    def _follow_loop(self):
        while self.following:
            self.follow_once()
            time.sleep(self.FOLLOW_REST)

    def follow_once(self):
        """한 장 읽어 칸에 넣는다. 판이 바뀌었으면 둘 수를 다시 묻는다."""
        import msgread
        here = [sl.poke["name"] for sl in self.slots + self.opp_slots if sl.poke]
        names = msgread.Names(self.dex, here)
        bd = self.board()
        got = self.watcher.step(bd, self.dex, names)
        if self.headless:
            self._after_follow(bd, got)
        else:
            self.root.after(0, lambda: self._after_follow(bd, got))
        return got

    def _after_follow(self, bd, got):
        if got["trouble"]:
            if got["trouble"] != self.follow_said:
                self.say("! " + got["trouble"])
                self.follow_said = got["trouble"]
            return
        self.follow_said = None
        if not got["changed"]:
            return
        self.set_board(bd)
        self.say("─ 읽었습니다 (%s 화면)" % got["kind"])
        for ok, text in got["notes"]:
            self.say("   %s %s" % ("✓" if ok else "○", text))
        # 칸이 바뀌었으니 다시 묻는다. 이미 생각하는 중이면 다음 바퀴에 묻는다.
        # ★ **선출 화면이면 「어떤 3마리」 를, 대전 화면이면 「무엇을 둘까」 를** 묻는다.
        #   선출 화면에서 둘 수를 물으면 아무 쓸모가 없다 — 그때 둘 수는 '어떤 3마리' 다.
        if self.busy:
            return
        if got["kind"] == "선출":
            self.ask_pick(clear=False)
        else:
            self.ask(clear=False)

    def _apply_screens(self, got):
        import screenread
        bd = self.board()
        lines = ["이렇게 읽었습니다 — 틀린 칸은 직접 고치세요.", ""]
        for f, res, err in got:
            lines.append("■ %s" % os.path.basename(f))
            if err:
                lines.append("   ! 못 읽음: %s" % err)
                continue
            if res["kind"] == "선출":
                notes = screenread.apply_preview(bd, res["opp"], self.dex)
            else:
                if res["lines"]:
                    lines.append("   문구: 「%s」" % " / ".join(res["lines"]))
                # 문구의 일을 먼저 (누가 나왔나가 바뀔 수 있다), 그 다음 HP
                notes = screenread.apply(bd, res["event"], self.dex) if res.get("event") else []
                notes += screenread.apply_hp(bd, res)
                if not notes:
                    notes = [(False, "문구도 HP 도 못 찾음 — 대전 화면이 맞나요?")]
            for ok, text in notes:
                lines.append("   %s %s" % ("✓" if ok else "○", text))
        self.set_board(bd)
        self.busy = False
        self.go_screen.config(text="화면 사진 넣기", state="normal")
        lines.append("")
        lines.append("✓ = 칸에 넣음   ○ = 읽었지만 칸이 없어 계산에 안 들어감 (또는 못 읽음)")
        # 빠른 읽기가 안 되면 **말해 준다** — 조용히 느려지기만 하면 왜 느린지 알 수가 없다.
        fell = screenread.worker().fell_back
        if fell:
            lines.append("! 빠르게 읽는 장치가 안 돌아 예전 방식으로 읽었습니다 (더 느립니다) — %s" % fell)
        self.say("\n".join(lines), clear=True)

    # -- 선출 -------------------------------------------------------------
    def ask_pick(self, clear=True):
        """팀 프리뷰 — 내 6마리 중 어떤 3마리를 낼까.

        `clear=False` 는 따라가기에서 쓴다 — 방금 보여 준 「읽었습니다」 를 지우면 안 된다.
        """
        if self.busy:
            return
        party = self.party()
        foes = self.opp_party()
        if len(party) < pick.PICK:
            self.say("내 파티를 %d마리 이상 채우세요 (지금 %d)."
                     % (pick.PICK, len(party)), clear=clear)
            return
        if len(foes) < pick.PICK:
            self.say("상대를 %d마리 이상 적으세요 (지금 %d). 팀 프리뷰에서"
                     " 본 6마리를 다 적으면 제일 정확합니다."
                     % (pick.PICK, len(foes)), clear=clear)
            return
        try:
            secs = max(10.0, float(self.pick_secs.get()))
        except (ValueError, AttributeError):
            secs = 45.0
        self.busy = True
        self.go_pick.config(text="고르는 중...", state="disabled")
        self.say("선출을 고릅니다 (%.0f초)..." % secs, clear=clear)
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
            text = pick.short_report(self.dex, my_builds, opp_builds, got)
        except Exception:
            import traceback
            text = "문제가 생겼습니다:\n%s" % traceback.format_exc()
        if self.headless:
            self._show_pick(text)
        else:
            self.root.after(0, lambda: self._show_pick(text))

    def _show_pick(self, text):
        self.last_short = self.short_advice(text)
        self.show_overlay(self.last_short)
        self.say(text)
        self.busy = False
        self.go_pick.config(text="선출 — 어떤 3마리?", state="normal")

    def _show(self, text):
        self.last_short = self.short_advice(text)
        self.show_overlay(self.last_short)
        self.say(text)
        self.busy = False
        self.go.config(text="무엇을 둘까?", state="normal")

    def _format(self, got, n_foes=1, guessed_opp=False):
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
        if guessed_opp:
            L.append("! 「냈다」 를 하나도 안 켜서 **적은 것 전부**를 상대로")
            L.append("  봤습니다. 실제로 나온 놈만 켜면 더 정확합니다")
        if getattr(self, "guessed_mine", False):
            L.append("! 내 쪽 「냈다」 를 하나도 안 켜서 **채운 자리 전부**를 내")
            L.append("  팀으로 봤습니다. 실제로는 3마리만 나갑니다 — 그대로 두면")
            L.append("  이기는 쪽으로 크게 틀어집니다 (한 대면에서 약 80점 대 40점)")
        # 대전이 띄운 경고 — 전에는 창에 한 줄도 안 보였다 (2026-09-22)
        L.extend(search.warning_lines(got))
        return "\n".join(L)

    def run(self):
        self.root.mainloop()


def clipped_labels(root):
    """글자가 칸보다 넓어서 잘리는 이름표를 찾는다. [(글자, 필요 px, 있는 px)].

    폭을 글자 수로 못 박은 칸(width=N)만 본다 — tkinter 의 폭은 '0' 한 글자
    기준이라 한글처럼 넓은 글자는 조용히 잘린다. 터지지 않고 화면에서만
    틀어지는 종류라, **진짜 tkinter 일 때만** 잴 수 있다.
    가짜 tkinter 에서는 None 을 돌려준다 (못 쟀다는 뜻 — 통과가 아니다).
    """
    try:
        import tkinter.font as tkfont
        root.update_idletasks()
    except Exception:
        return None
    out = []
    stack = [root]
    while stack:
        w = stack.pop()
        try:
            stack.extend(w.winfo_children())
            if w.winfo_class() != "Label":
                continue
            width = int(w.cget("width") or 0)
            text = w.cget("text")
        except Exception:
            return None
        if width <= 0 or not text:
            continue
        f = tkfont.Font(root=root, font=w.cget("font"))
        need = max(f.measure(line) for line in str(text).splitlines() or [""])
        pad = 2 * (int(float(w.cget("padx"))) + int(float(w.cget("bd")))
                   + int(float(w.cget("highlightthickness"))))
        have = w.winfo_reqwidth() - pad
        if need > have:
            out.append((text, need, have))
    return out


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
    # ★ **저장해 둔 파티를 먼저 비운다.** 창은 켤 때 `내기록/내파티.txt` 를 읽는데, 점검이 그걸
    #   그대로 두면 **사용자가 무엇을 저장해 뒀느냐에 따라 점검이 통과했다 실패했다** 한다
    #   (2026-09-23: 사용자가 6마리를 저장하자 「파티가 두 마리로 안 잡힙니다: 5」 로 깨졌다).
    #   점검은 남의 파일에 기대면 안 된다.
    for sl in app.slots:
        sl.clear()
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
    # ★ 밝혀진 놈만 이번 턴 계산에 들어가야 한다
    if app.opp_slots[0].revealed():
        print("아무것도 안 켰는데 밝혀진 것으로 돼 있습니다")
        return 1
    app.opp_slots[0].brought.set(True)
    app.opp_slots[0].redraw_state()
    app.opp_slots[1].brought.set(True)
    app.opp_slots[1].redraw_state()
    if app.opp_slots[0].state_label.cget("text") != "● 밝혀짐":
        print("밝혀진 표시가 안 뜹니다: %r"
              % app.opp_slots[0].state_label.cget("text"))
        return 1
    if app.opp_slots[2].state_label.cget("text") != "○ 모름":
        print("안 밝혀진 표시가 틀립니다: %r"
              % app.opp_slots[2].state_label.cget("text"))
        return 1
    if "2마리가 밝혀짐" not in app.opp_state.cget("text"):
        print("상대 요약이 틀립니다: %r" % app.opp_state.cget("text"))
        return 1
    app.opp_active.set(0)
    app.opp_slots[0].on_active()
    app.add_seen("지진")
    if app.seen.get("한카리아스") != ["지진"]:
        print("본 기술이 나와 있는 놈 것으로 안 들어갑니다: %r" % app.seen)
        return 1

    seen_args = {}
    real = search.best_action

    def spy(dex_, my_party, opp_pokes, **kw):
        seen_args["opp"] = [p["name"] for p in opp_pokes]
        # 내 쪽도 본다 — 전엔 상대만 봐서 "내 6마리가 전부 넘어간다" 를 못 봤다
        seen_args["mine"] = [b.poke["name"] for b in my_party]
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
        # 「이번 턴에 막 나옴」 — 첫 계산은 둘 다 켜진 채로 넘어가고, 넘긴 뒤엔 꺼진다
        fresh1 = ((first.get("state") or {}).get("my_fresh"),
                  (first.get("state") or {}).get("opp_fresh"))
        after1 = (app.my_fresh.get(), app.opp_fresh.get())

        # ⑦ 나와 있는 상대를 2번으로 바꾸면 번호가 따라가는가
        app.opp_active.set(1)
        app.ask()
        moved = (seen_args.get("state") or {}).get("opp_active")
        # 상대만 바꿨으니 상대만 '막 나옴' 이어야 한다
        fresh2 = ((seen_args.get("state") or {}).get("my_fresh"),
                  (seen_args.get("state") or {}).get("opp_fresh"))

        # ★ 안 밝혀진 놈은 이번 턴 계산에서 빠져야 한다
        kil2 = dex.find_pokemon("킬가르도")
        app.opp_slots[3].name.set(kil2["name"], kil2)
        app.opp_slots[3].on_poke(kil2)     # 켜지 않았다 = 프리뷰에서만 봄
        app.opp_slots[3].brought.set(False)
        app.opp_slots[3].redraw_state()
        app.opp_active.set(0)
        app.opp_slots[0].on_active()
        app.ask()
        hidden_in = "킬가르도" in (seen_args.get("opp") or [])
        seen_args = first
    finally:
        search.best_action = real
    if hidden_in:
        print("안 밝혀진 놈이 계산에 들어갔습니다")
        return 1
    if moved != 1:
        print("'나와 있음' 을 바꿨는데 안 따라갑니다: %r" % (moved,))
        return 1
    if fresh1 != (True, True):
        print("첫 계산이 '막 나옴' 으로 안 넘어갔습니다: %r" % (fresh1,))
        return 1
    if after1 != (False, False):
        print("계산한 뒤 '막 나옴' 이 안 꺼졌습니다: %r" % (after1,))
        return 1
    if fresh2 != (False, True):
        print("상대 '나와 있음' 을 바꿨는데 '막 나옴' 이 안 따라갑니다: %r" % (fresh2,))
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
    if "실제로 나온 놈만" in text:
        print("밝혀진 놈을 켰는데도 추측했다고 합니다:\n%s" % text[-300:])
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

    # ★ 내 쪽도 '낸 놈만, 각자의 HP 로' 계산에 가는가 (2026-09-21)
    #   전엔 채운 6자리를 전부 HP 100% 로 넘겼다. 같은 대면이 약 80점 대 40점.
    for sl in app.slots:
        sl.brought.set(False)
        sl.hp.set("100")
    app.slots[0].brought.set(True)            # 하마돈
    app.slots[1].brought.set(True)            # 아머까오
    app.slots[1].hp.set("40")
    app.my_active.set(1)
    app.slots[1].on_active()
    mine_args = {}

    def spy2(dex_, my_party, opp_pokes, **kw):
        mine_args["mine"] = [b.poke["name"] for b in my_party]
        mine_args["state"] = kw.get("state")
        return real(dex_, my_party, opp_pokes, **kw)

    search.best_action = spy2
    try:
        app.secs.set("1")
        mine_args.clear()
        app.ask()
        got1 = dict(mine_args)
        app.slots[0].hp.set("0")               # 하마돈 쓰러짐
        mine_args.clear()
        app.ask()
        got2 = dict(mine_args)
        app.my_active.set(0)                   # 쓰러진 놈을 '나와 있음' 으로
        mine_args.clear()
        app.ask()
        got3 = dict(mine_args)
        said3 = app.out.get("1.0", "end")
    finally:
        search.best_action = real
    st1 = got1.get("state") or {}
    if got1.get("mine") != ["하마돈", "아머까오"]:
        print("'냈다' 로 고른 둘만 넘어가야 하는데: %r" % got1.get("mine"))
        return 1
    if st1.get("my_hp") != [100.0, 40.0] or st1.get("my_active") != 1:
        print("내 HP·나와 있는 번호가 칸과 다릅니다: %r" % st1)
        return 1
    st2 = got2.get("state") or {}
    if got2.get("mine") != ["아머까오"] or st2.get("my_active") != 0:
        print("쓰러진 내 포켓몬이 안 빠지거나 번호가 안 맞습니다: %r %r"
              % (got2.get("mine"), st2))
        return 1
    if got3 or "쓰러졌습니다" not in said3:
        print("쓰러진 놈을 나와 있음으로 골랐는데 그냥 계산했습니다: %r" % got3)
        return 1
    app.slots[0].hp.set("100")
    app.my_active.set(0)

    # ★ 마우스로 쓸 수 있는가 (2026-09-21, 사용자가 창을 처음 써 보고 잡음)
    #   ① 후보를 **한 번** 눌러 고른다 — 전엔 두 번 눌러야 했는데 첫 번에 닫혔다
    #   ② 목록을 누르러 가는 동안 칸이 초점을 잃어도 목록이 안 닫힌다
    #   ③ 파티 칸 위에서 휠을 굴리면 왼쪽이 내려간다 — 휠이 아예 안 걸려 있었다
    #   ④ 창을 내용물보다 좁게 못 줄인다 — 줄이면 오른쪽이 잘렸다
    pk = app.slots[MAX_PARTY - 1].name
    if "<ButtonRelease-1>" not in (pk.list.bind() or ()):
        print("후보 목록에 '한 번 누르기' 가 안 걸려 있습니다")
        return 1
    pk.var.set("한카")
    pk.refresh(force=True)

    class _Ev(object):
        x = y = x_root = y_root = 0
        delta = -120
        num = None
        widget = None

    pk._pointer_in_pop = lambda: True
    pk._maybe_hide()
    kept = pk.pop.winfo_viewable()
    pk._pointer_in_pop = lambda: False
    pk._maybe_hide()
    closed = not pk.pop.winfo_viewable()
    del pk._pointer_in_pop
    if not (kept and closed):
        print("목록 위에 마우스가 있어도 닫힙니다 (남음 %s / 밖이면 닫힘 %s)"
              % (kept, closed))
        return 1
    pk.refresh(force=True)
    pk._click(_Ev())
    got = pk.get()
    if not got or got.get("name") != "한카리아스":
        print("후보를 한 번 눌렀는데 안 들어갑니다: %r" % (got,))
        return 1

    if not app.root.bind_all("<MouseWheel>"):
        print("창에 휠이 안 걸려 있습니다")
        return 1
    inside = app.slots[MAX_PARTY - 1].box
    if app.wheel_target(inside) is not app.canvas:
        print("파티 칸 위의 휠이 왼쪽 목록을 안 굴립니다")
        return 1
    if app.wheel_target(app.out) is not app.out:
        print("결과 칸 위의 휠이 결과 칸을 안 굴립니다")
        return 1
    app.root.update_idletasks()
    app.canvas.yview_moveto(0)
    before = app.canvas.yview()
    real_containing = app.root.winfo_containing
    app.root.winfo_containing = lambda x, y: inside
    app._on_wheel(_Ev())
    app.root.winfo_containing = real_containing
    after = app.canvas.yview()
    if before and after and tuple(before) != (0.0, 1.0):
        if not after[0] > before[0]:
            print("휠을 굴렸는데 왼쪽이 안 내려갑니다: %s -> %s"
                  % (before, after))
            return 1
    else:
        print("  (휠로 실제로 내려가는지는 못 쟀다 — 창이 안 보이는 상태라서)")
    # ! 처음엔 'mw > 0' 으로 봤는데, 최소 크기를 안 정해도 tkinter 가 기본값
    #   1x1 을 돌려줘서 통과해 버렸다 — 일부러 줄을 지워 보고 알았다.
    mw, _mh = app.root.minsize()
    if not mw or mw < app.min_size[0]:
        print("창의 최소 크기가 안 정해져 있습니다 (줄이면 오른쪽이 잘린다)")
        return 1

    # ★ 칸을 다 채워도 왼쪽 목록 오른쪽 끝이 안 잘리는가 (2026-09-21)
    #   채우면 536 > 500 이 돼서 비우기 단추 등이 잘렸다.
    try:
        app.root.update_idletasks()
        app._fit_party()
        need = app.party_box.winfo_reqwidth()
        have = int(float(app.canvas.cget("width")))
    except Exception:
        need = have = None
    if isinstance(need, int) and need > 1 and have and need > have:
        print("칸을 채우니 왼쪽 목록이 보이는 폭보다 넓습니다 (%d > %d) — "
              "오른쪽 끝이 잘립니다" % (need, have))
        return 1

    # ★ 글자가 칸에 들어가는가 — 진짜 창에서만 잴 수 있다.
    #   「특수공격」 이 「특수공ㅈ」 로 잘려 있었는데 가짜 tkinter 점검은
    #   통과했다. 생김새는 가짜로는 안 보인다.
    clipped = clipped_labels(app.root)
    if clipped is None:
        print("  (글자 잘림은 못 쟀다 — 가짜 tkinter 라서. 윈도우 빌드에서 잰다)")
    elif clipped:
        print("글자가 칸보다 넓어서 잘립니다: %s"
              % ", ".join("%s(%d>%dpx)" % c for c in clipped[:8]))
        return 1

    # ★ 모습이 다른 포켓몬을 고를 수 있는가 (2026-09-22) — 예전엔 이름마다 하나만 있어서
    #   워시로토무를 고를 수 없었고 로토무(전기/고스트)로 계산됐다.
    labels = [t for t, _v in app.opp_slots[0].name.items]
    for want in ("로토무(워시로토무)", "라이츄(알로라의모습)", "대쓰여너(암컷의모습)"):
        if want not in labels:
            print("상대 칸 후보에 %s 가 없습니다 — 모습을 못 고릅니다" % want)
            return 1

    # ★ 화면 사진에서 읽은 것이 칸에 들어가는가 (screenread, 2026-09-22).
    #   사진 읽기(글자 인식)는 윈도우 것이라 여기선 **읽은 결과를 바로 넣어** 본다.
    wash = dex.find_pokemon("0479-02")
    fake = [("선출.png", {"kind": "선출", "opp": [
        {"key": "0479-02", "gender": None, "score": 0.9, "gap": 0.3},
        {"key": dex.find_pokemon("하마돈")["key"], "gender": "수컷", "score": 0.9, "gap": 0.3},
        {"key": dex.find_pokemon("타부자고")["key"], "gender": "암컷", "score": 0.9, "gap": 0.3}]}, None),
        ("나옴.png", {"kind": "대전", "lines": ["x"], "event": {
            "kind": "나옴", "mon": "하마돈", "side": "opp"}}, None),
        ("기술.png", {"kind": "대전", "lines": ["x"], "event": {
            "kind": "기술", "mon": "하마돈", "side": "opp", "move": "지진"}}, None),
        ("풍선.png", {"kind": "대전", "lines": ["x"], "event": {
            "kind": "풍선", "mon": "타부자고", "side": "opp", "item": "풍선"}}, None),
        ("쓰러짐.png", {"kind": "대전", "lines": ["x"], "event": {
            "kind": "쓰러짐", "mon": "로토무", "side": "opp"}}, None),
        ("하품.png", {"kind": "대전", "lines": ["x"], "event": {
            "kind": "하품", "mon": "하마돈", "side": "opp"}}, None),
        ("하락.png", {"kind": "대전", "lines": ["x"], "event": {
            "kind": "능력하락", "mon": "하마돈", "side": "opp", "stat": "공격"}}, None),
        ("모래.png", {"kind": "대전", "lines": ["x"], "event": {"kind": "모래바람시작"}}, None),
        ("록.png", {"kind": "대전", "lines": ["x"], "event": {"kind": "스텔스록깔림"}}, None),
        ("앙코르.png", {"kind": "대전", "lines": ["x"], "event": {
            "kind": "앙코르", "mon": "하마돈", "side": "opp"}}, None)]
    app._apply_screens(fake)
    shown = app.out.get("1.0", "end")
    o = app.opp_slots
    bad = []
    if (o[0].poke is not wash or o[0].name.get() is not wash
            or o[0].name.var.get() != "로토무(워시로토무)"):
        bad.append("선출 화면의 워시로토무가 1번 칸에 없음")
    if app.opp_active.get() != 1 or not o[1].brought.get() or not app.opp_fresh.get():
        bad.append("하마돈이 나왔는데 나와 있음·냈다·막 나옴이 안 켜짐")
    if app.seen.get("하마돈") != ["지진"]:
        bad.append("본 기술에 지진이 안 들어감 (%s)" % app.seen)
    if app.opp_items.get("타부자고") != "풍선" or "도구 풍선" not in o[2].seen_label.cget("text"):
        bad.append("타부자고의 풍선이 안 들어감")
    if o[0].hp_pct() != 0:
        bad.append("쓰러진 로토무 HP 가 0 이 아님")
    if "○ 상대 하마돈: 앙코르" not in shown or "이렇게 읽었습니다" not in shown:
        bad.append("칸이 없는 일(앙코르)을 '계산에 안 들어감' 으로 안 알림")
    # 새 칸 (2026-09-23): 하품 → 졸음 · 공격 하락 → 랭크 −1 · 모래바람 · 상대 쪽 스텔스록
    if o[1].status.get() != "졸음":
        bad.append("하품을 맞은 하마돈 상태가 졸음이 아님 (%s)" % o[1].status.get())
    if app.ranks["opp"]["attack"].get() != "-1":
        bad.append("상대 공격 랭크가 −1 이 아님 (%s)" % app.ranks["opp"]["attack"].get())
    if app.weather.get() != "모래바람" or not app.hazards["opp"]["스텔스록"].get():
        bad.append("날씨·스텔스록이 칸에 안 들어감")
    # 그리고 그 칸들이 **계산에 넘어가는가** — 넘길 목록 번호에 맞춰서
    mid = app.mid_state([0], [1, 2])
    if (mid["opp_status"] != ["졸음", None] or mid["opp_ranks"] != {"attack": -1}
            or mid["field"].get("weather") != "모래바람" or mid["opp_hazards"] != {"스텔스록": 1}
            or "terrain" in mid["field"]):
        bad.append("새 칸이 계산에 넘어가는 모양이 틀림 (%s)" % mid)
    # 나와 있는 상대가 바뀌면 상대 랭크는 0 으로 (같은 자리를 다시 넣을 땐 그대로)
    app.opp_active.set(1)
    kept = app.ranks["opp"]["attack"].get()
    app.opp_active.set(2)
    if kept != "-1" or app.ranks["opp"]["attack"].get() != "0":
        bad.append("나와 있는 상대가 바뀔 때 랭크 처리가 틀림 (%s → %s)"
                   % (kept, app.ranks["opp"]["attack"].get()))
    ev = live.evidence_map(app.seen, [p for p in (o[1].poke, o[2].poke)],
                           app.opp_items, app.opp_abilities)
    if not ev or ev["타부자고"].item != "풍선" or "지진" not in ev["하마돈"].seen_moves:
        bad.append("본 기술·도구가 계산에 넘어가지 않음 (%s)" % ev)
    # ★ 따라가기 — 화면을 계속 읽어 칸을 채우고 **둘 수를 다시 묻는가** (2026-09-23).
    #   진짜 OBS 창 대신 저장해 둔 화면을 차례로 내놓는 가짜를 끼운다.
    import tempfile
    import watch as watchmod
    import pngio as pngiomod
    import screenread as srmod
    here = os.path.dirname(os.path.abspath(__file__))

    class _Replay(object):
        def __init__(self, files):
            self.files, self.i = files, 0

        def grab(self):
            f = self.files[min(self.i, len(self.files) - 1)]
            self.i += 1
            w, h, px = pngiomod.read_png(srmod.to_png(f))
            return f, w, h, px

    shots = os.path.join(here, "data", "screens")
    # 같은 화면을 두 번씩 — **두 장 연속 같아야** 믿는다
    seq = [os.path.join(shots, "선출_실전OBS.jpg")] * 2
    app.watcher = watchmod.Watcher(_Replay(seq))
    app.follow_once()
    app.follow_once()
    got6 = [sl.poke["name"] if sl.poke else None for sl in app.opp_slots]
    if got6 != ["갸라도스", "팬텀", "조로아크", "초염몽", "엘레이드", "루카리오"]:
        bad.append("따라가기가 선출 화면의 상대 6마리를 칸에 안 넣음 (%s)" % got6)
    if "읽었습니다" not in app.out.get("1.0", "end"):
        bad.append("따라가기가 '읽었습니다' 를 안 보여 줌")
    # 한 장만 본 것은 **아직 안 믿는다**
    app.watcher = watchmod.Watcher(_Replay([os.path.join(shots, "대전_아이패드_풍선.jpg")] * 2))
    first = app.follow_once()
    second = app.follow_once()
    if first["changed"] or not second["changed"]:
        bad.append("두 장 연속 같아야 믿는 규칙이 안 돎 (첫 장 %s, 둘째 장 %s)"
                   % (first["changed"], second["changed"]))
    # 신호 없음 — 까만 화면
    black = os.path.join(tempfile.gettempdir(), "gui_점검_까망.png")
    pngiomod.write_png(black, 64, 36, bytearray([0, 0, 0, 255] * (64 * 36)))
    app.watcher = watchmod.Watcher(_Replay([black]))
    app.follow_once()
    if "신호가 없습니다" not in app.out.get("1.0", "end"):
        bad.append("신호 없음(까만 화면)을 안 알림")
    try:
        os.remove(black)
    except OSError:
        pass

    # ★ 추천 작은 창 — 게임을 가리지 않고 **답만** 구석에 띄운다 (2026-09-23).
    #   처음엔 이 창을 통째로 「항상 위에」 로 올렸는데 게임 화면을 덮어서 더 나빠졌다.
    turn_text = ("\n%-18s %6s\n----\n지진  78.0\n=> 지진   (78.0점 ±1.2, 900판)\n"
                 "! 겹치는 수: 하품 — 확실하지 않습니다\n" % ("수", "점수"))
    pick_text = "  [선출]  이 3마리를 이 순서로 내세요\n\n    ▶ 선봉   하마돈\n      벤치   마폭시 · 고릴타\n"
    short = app.short_advice(turn_text)
    if "=> 지진" not in short or "겹치는 수" not in short or "78.0\n" in short:
        bad.append("작은 창에 넣을 몇 줄이 답·경고만 뽑지 않음 (%r)" % short)
    short = app.short_advice(pick_text)
    # ! 처음엔 "선봉 이 들어갔나" 만 봤는데, 못 뽑았을 때 쓰는 되돌림(앞 네 줄)에 그 줄이
    #   섞여 들어와 **일부러 고장 내도 안 잡혔다.** 그래서 「[선출]」 머리글이 없는 것까지 본다.
    if short.splitlines() != ["▶ 선봉   하마돈", "벤치   마폭시 · 고릴타"]:
        bad.append("선출 답(선봉·벤치)만 뽑아야 하는데 다름 (%r)" % short)
    app.on_top.set(1)
    made = app.apply_on_top()
    if made:
        app.show_overlay("시험")
        if app.overlay is None or app.overlay_text is None:
            bad.append("추천 작은 창이 안 만들어짐")
        app.on_top.set(0)
        app.apply_on_top()
        if app.overlay is not None:
            bad.append("추천 작은 창이 안 닫힘")

    # 빠르게 읽는 장치(파워셸 일꾼)가 안 돌면 **창에 그렇게 적히는가** (2026-09-23).
    # 조용히 느려지기만 하면 왜 느린지 알 길이 없다.
    import screenread
    screenread.worker().fell_back = "일부러 고장 낸 것"
    try:
        app._apply_screens([("없음.png", None, "시험")])
        if "일부러 고장 낸 것" not in app.out.get("1.0", "end"):
            bad.append("빠르게 읽는 장치가 안 된다는 말이 창에 안 나옴")
    finally:
        screenread.worker().fell_back = None
    if bad:
        print("화면 사진 넣기: " + " / ".join(bad))
        return 1

    print("창 점검 끝 — 후보 고르기 · 능력치 · 노력치 규칙 · 6자리 ·"
          " 상대 파티가 계산까지 가는지 · 추천 · 선출 · 마우스(한 번 누르기·휠)"
          " · 최소 크기 · 글자 잘림 · 모습 고르기 · 화면 사진 넣기까지 돌았습니다")
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
