# -*- coding: utf-8 -*-
"""**가짜 tkinter.** 그리지 않고 부르기만 받는다.

## 왜 이런 게 있나

이 창(`gui.py`)은 리눅스에서 만들어졌는데 **리눅스에서 볼 수가 없다.**
개발 컨테이너에 tkinter 도 화면도 없다. 그래서 지금까지 창 코드는
"문법이 맞나" 말고는 한 줄도 못 돌려 보고 윈도우로 보냈다.
윈도우에서만 나는 고장을 네 번 만났다 (CLAUDE.md §9).

이 파일을 `sys.path` 앞에 두면 `import tkinter` 가 이걸 집어서,
**창을 그리지 않고도 `gui.py` 가 통째로 돌아간다.** 위젯을 만들고,
칸을 채우고, 단추를 누르고, 추천이 나오는 데까지 간다.

## 이게 잡아 주는 것 / 못 잡는 것

잡는다 — 오타, 없는 메서드, 인자 개수, **그리고 칸에 넣은 값이
계산까지 가는가.** 실제로 여기에 붙이자마자 `gui.check` 의 엿보기가
너무 일찍 풀려서 두 번째 검사가 첫 번째 값을 다시 보던 것을 잡았다.

못 잡는다 — 진짜 창의 생김새, 글꼴, 단추가 눌리는 느낌, 윈도우의
인코딩. **그건 여전히 받아 봐야 안다.** 그래서 윈도우 빌드의
`gui.py --점검` 을 없애지 않는다. 이건 그 앞에 두는 그물이다.
"""


class _Var(object):
    def __init__(self, master=None, value=None):
        self._v = value if value is not None else self._zero
        self._cbs = []

    def get(self):
        return self._v

    def set(self, v):
        self._v = v
        for cb in list(self._cbs):
            cb()

    def trace_add(self, mode, cb):
        self._cbs.append(lambda *a: cb())


class StringVar(_Var):
    _zero = ""


class IntVar(_Var):
    _zero = 0


class DoubleVar(_Var):
    _zero = 0.0


class BooleanVar(_Var):
    _zero = False


class _W(object):
    def __init__(self, master=None, **kw):
        self._kw = dict(kw)
        self._children = []
        self._binds = {}
        self.master = master if isinstance(master, _W) else None
        if isinstance(master, _W):
            master._children.append(self)

    def pack(self, **kw): pass
    def grid(self, **kw): pass
    def place(self, **kw): pass
    def pack_forget(self): pass
    def configure(self, **kw): self._kw.update(kw)
    config = configure
    def cget(self, key): return self._kw.get(key, "")
    def bind(self, seq=None, fn=None, *a, **kw):
        # **무엇을 걸었는지는 기억한다.** 빈 함수로 두면 "목록을 한 번
        # 누르면 고른다" 가 걸려 있는지조차 시험할 수가 없다 (2026-09-21).
        if seq is None:
            return tuple(self._binds)
        if fn is not None:
            self._binds[seq] = fn
        return self._binds.get(seq)
    def bind_all(self, seq=None, fn=None, *a, **kw):
        return self.bind(seq, fn)
    def winfo_class(self): return type(self).__name__
    def winfo_children(self): return list(self._children)
    def winfo_containing(self, x, y): return None
    def winfo_pointerxy(self): return (0, 0)
    def winfo_reqwidth(self): return 100
    def winfo_reqheight(self): return 20
    def yview_scroll(self, n, what): pass
    def after(self, ms, fn=None, *a):
        if fn is not None:
            fn(*a)
    def winfo_viewable(self): return True
    def winfo_ismapped(self): return True
    def winfo_rootx(self): return 0
    def winfo_rooty(self): return 0
    def winfo_height(self): return 20
    def winfo_width(self): return 100
    def focus_set(self): pass
    def destroy(self): pass
    def update_idletasks(self): pass


class Frame(_W): pass
class Label(_W): pass
class Button(_W): pass
class Canvas(_W):
    def create_window(self, *a, **kw): return 1
    def create_rectangle(self, *a, **kw): return 1
    def create_text(self, *a, **kw): return 1
    def delete(self, *a): pass
    def bbox(self, *a): return (0, 0, 100, 100)
    def yview(self, *a): pass
    def yview_moveto(self, *a): pass
class Scrollbar(_W):
    def set(self, *a): pass
class Entry(_W):
    def __init__(self, master=None, **kw):
        _W.__init__(self, master, **kw)
        self.var = kw.get("textvariable")
    def icursor(self, *a): pass
    def selection_range(self, *a): pass
class Spinbox(_W): pass
class Radiobutton(_W): pass
class Checkbutton(_W): pass


class Listbox(_W):
    def __init__(self, master=None, **kw):
        _W.__init__(self, master, **kw)
        self._rows = []
    def delete(self, a, b=None): self._rows = []
    def insert(self, where, text): self._rows.append(text)
    def nearest(self, y): return 0 if self._rows else -1
    def size(self): return len(self._rows)
    def curselection(self): return (0,) if self._rows else ()
    def selection_clear(self, *a): pass
    def selection_set(self, *a): pass
    def activate(self, *a): pass
    def see(self, *a): pass
    def get(self, i, j=None):
        if j is None:
            return self._rows[i] if i < len(self._rows) else ""
        return self._rows[i:j]


class Text(_W):
    def __init__(self, master=None, **kw):
        _W.__init__(self, master, **kw)
        self._buf = []
    def insert(self, where, text): self._buf.append(text)
    def delete(self, a, b=None): self._buf = []
    def see(self, *a): pass
    def get(self, a, b=None): return "".join(self._buf)


class Toplevel(_W):
    """! **보이나 안 보이나를 실제로 들고 있어야 한다.**
    처음엔 withdraw/deiconify 를 빈 함수로 뒀는데, 그러면
    `winfo_viewable()` 이 없거나 늘 같은 값이라 "닫혀 있으면 먼저 연다"
    같은 코드를 시험할 수가 없다. 가짜가 너무 가짜면 안 잡힌다."""

    def __init__(self, master=None, **kw):
        _W.__init__(self, master, **kw)
        self._shown = False

    def withdraw(self): self._shown = False
    def deiconify(self): self._shown = True
    def winfo_viewable(self): return self._shown
    def winfo_ismapped(self): return self._shown
    def state(self, *a): return "normal" if self._shown else "withdrawn"
    def overrideredirect(self, *a): pass
    def geometry(self, *a): pass
    def lift(self): pass
    def attributes(self, *a): pass


class Tk(_W):
    _min = (0, 0)
    def title(self, *a): pass
    def minsize(self, w=None, h=None):
        if w is None:
            return self._min
        self._min = (w, h)
    def withdraw(self): pass
    def geometry(self, *a): pass
    def mainloop(self): pass
    def destroy(self): pass
