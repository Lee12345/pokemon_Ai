# -*- coding: utf-8 -*-
"""
게임 화면 사진 한 장 → 창의 칸에 넣을 것.

    python screenread.py 사진.png [사진2.jpg …]

- **선출 화면**이면 (상대 칸 6개가 보이면) 상대 6마리를 그림으로 알아본다 (`artmatch`).
- 아니면 **대전 화면**으로 보고, 화면 아래 문구 칸을 글자 인식(`tools/글자읽기.ps1`)으로
  읽어 일어난 일로 바꾼다 (`msgread`).

## 칸에 어떻게 넣나 (`apply`)

창과 똑같이 생긴 판(`Board`)에 넣는다 — 창(`gui.py`)은 자기 칸을 판으로 옮기고, 넣고,
다시 칸으로 옮긴다. 이렇게 나눠야 창 없이 검사할 수 있다.

넣은 것마다 **한 줄씩 적어 돌려준다** ("이렇게 읽었습니다"). 사용자가 보고 틀린 것을 고친다
— 잘못 읽으면 조용히 틀리기 때문이다 (사용자와 정한 것, 2026-09-21).
**창에 칸이 없어 계산에 못 넣는 것**(능력 하락·하품·앙코르 등)은 그렇다고 적는다. 버리지 않는다.

## 위치를 박지 않는다

문구 칸은 화면 비율로 찾는다: 왼쪽 35% 안, 위에서 70~90%. 잰 것 — 아이패드(4:3) 왼쪽 16%·
위 78~82%, 스위치(16:9) 16%·74~80% (docs/이어받기.md §10).
"""

import os
import re
import struct
import subprocess
import sys
import tempfile

import paths
import pngio

HERE = os.path.dirname(os.path.abspath(__file__))
OCR_SCRIPT = os.path.join(HERE, "tools", "글자읽기.ps1")
MSG_BOX = (0.0, 0.70, 0.35, 0.90)       # 왼쪽 · 위 · 오른쪽 · 아래 (화면에 대한 몫)


# ── 사진 ───────────────────────────────────────────────────────────────
def image_size(path):
    """PNG·JPG 의 (너비, 높이) — 머리만 읽는다."""
    with open(path, "rb") as f:
        head = f.read(32)
        if head.startswith(pngio.SIG):
            return struct.unpack(">II", head[16:24])
        if head[:2] != b"\xff\xd8":
            raise ValueError("PNG·JPG 가 아니다: %s" % path)
        f.seek(2)
        while True:
            m = f.read(2)
            if len(m) < 2 or m[0] != 0xFF:
                raise ValueError("JPG 크기를 못 찾았다: %s" % path)
            n = struct.unpack(">H", f.read(2))[0]
            if m[1] in (0xC0, 0xC1, 0xC2):
                h, w = struct.unpack(">xHH", f.read(5))
                return w, h
            f.seek(n - 2, 1)


def to_png(path):
    """PNG 가 아니면(스위치 스크린샷은 JPG) 윈도우 기본 기능으로 PNG 를 만들어 그 자리를 준다."""
    with open(path, "rb") as f:
        if f.read(8) == pngio.SIG:
            return path
    out = os.path.join(tempfile.gettempdir(), "screenread_%d.png" % os.getpid())
    cmd = ("Add-Type -AssemblyName System.Drawing; "
           "$b = [System.Drawing.Bitmap]::FromFile('%s'); $b.Save('%s', "
           "[System.Drawing.Imaging.ImageFormat]::Png); $b.Dispose()"
           % (os.path.abspath(path).replace("'", "''"), out.replace("'", "''")))
    subprocess.run(["powershell", "-NoProfile", "-Command", cmd], check=True,
                   capture_output=True)
    return out


SMALL_W = 1600          # 이보다 좁은 화면은 2배로 키워 읽는다
# 잰 것: 스위치 화면(1341x749)에서 문구 칸 두 줄 중 한 줄만 읽혔고, 2배로 키우니 두 줄 다 (2026-09-22).


def ocr(path, scale=1):
    """윈도우 기본 글자 인식 → [(x, y, 글)] (좌표는 **원래 사진** 기준). 결과는 임시 폴더에."""
    src = os.path.abspath(path)
    tmp = os.path.join(tempfile.gettempdir(), "screenread_%d_ocr%s"
                       % (os.getpid(), ".png" if scale != 1 else os.path.splitext(src)[1]))
    if scale == 1:          # 그대로 읽을 때는 바꾸지 않는다 (파워셸 한 번 = 약 0.5초)
        with open(src, "rb") as a, open(tmp, "wb") as b:
            b.write(a.read())
    else:
        _scaled(src, tmp, scale)
    return _ocr_file(tmp, scale)


def _scaled(src, tmp, scale):
    cmd = ("Add-Type -AssemblyName System.Drawing; "
           "$s = [System.Drawing.Bitmap]::FromFile('%s'); "
           "$b = New-Object System.Drawing.Bitmap ($s.Width * %d), ($s.Height * %d); "
           "$g = [System.Drawing.Graphics]::FromImage($b); "
           "$g.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic; "
           "$g.DrawImage($s, 0, 0, $b.Width, $b.Height); $g.Dispose(); $s.Dispose(); "
           "$b.Save('%s', [System.Drawing.Imaging.ImageFormat]::Png); $b.Dispose()"
           % (src.replace("'", "''"), scale, scale, tmp.replace("'", "''")))
    subprocess.run(["powershell", "-NoProfile", "-Command", cmd], check=True,
                   capture_output=True)


def _ocr_file(tmp, scale):
    subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                    "-File", OCR_SCRIPT, "-Path", tmp], check=True, capture_output=True)
    lines = []
    with open(tmp + ".txt", encoding="utf-8-sig") as f:
        for row in f:
            m = re.match(r"\s*(-?\d+),\s*(-?\d+)\s\s(.*)", row.rstrip("\n"))
            if m:
                lines.append((int(m.group(1)) // scale, int(m.group(2)) // scale, m.group(3)))
    for p in (tmp, tmp + ".txt"):
        try:
            os.remove(p)
        except OSError:
            pass
    return lines


def message_lines(lines, w, h):
    """글자 인식 줄들 → 문구 칸 줄만, 위에서부터."""
    x0, y0, x1, y1 = MSG_BOX
    # 문구는 한글이 있다 — 같은 자리에 걸리는 시계(「06:41」)·표시 조각(「b」)은 뺀다
    got = [(y, t) for x, y, t in lines
           if x0 <= x / float(w) < x1 and y0 <= y / float(h) < y1
           and len(re.findall(r"[가-힣]", t)) >= 2]
    return [t for _, t in sorted(got)]


def read_screen(path, dex, names):
    """사진 한 장 → {'kind': '선출', 'opp': [...]} 또는 {'kind': '대전', 'lines': [...], 'event': {...}}."""
    import artmatch
    import msgread
    png = to_png(path)
    w, h, px = pngio.read_png(png)
    try:
        found = artmatch.identify(w, h, px)
    except ValueError:
        found = None
    if found:
        opp = []
        for panel, gender, ranked in found:
            score, key = ranked[0]
            opp.append({"key": key, "gender": gender, "score": score,
                        "gap": score - ranked[1][0] if len(ranked) > 1 else score})
        return {"kind": "선출", "opp": opp}
    import hpread
    raw = ocr(path, 2 if w < SMALL_W else 1)
    lines = message_lines(raw, w, h)
    out = {"kind": "대전", "lines": lines,
           "event": msgread.read(lines, names) if lines else None,
           "opp_hp": hpread.measure(w, h, px),
           "opp_name": opp_name_line(raw, w, h, names),
           "my_hp": my_hp_numbers(raw, w, h)}
    return out


# 내 HP 는 「172/191」 처럼 숫자로 나온다 — 글자 인식이 잘 읽는다 (아이패드 145/215, 스위치 172/191).
# 자리: 왼쪽 아래 (아이패드 x 0.14·y 0.95, 스위치 x 0.13·y 0.94).
MY_HP_BOX = (0.0, 0.80, 0.40, 1.0)
# 상대 이름 칸: 오른쪽 위 (아이패드 x 0.83·y 0.04, 스위치 x 0.83·y 0.05)
OPP_NAME_BOX = (0.60, 0.0, 1.0, 0.15)


def _in(box, x, y, w, h):
    x0, y0, x1, y1 = box
    return x0 <= x / float(w) < x1 and y0 <= y / float(h) < y1


def my_hp_numbers(lines, w, h):
    """(지금, 최대) 또는 None."""
    for x, y, t in lines:
        m = re.search(r"(\d{1,3})\s*/\s*(\d{1,3})", t)
        if m and _in(MY_HP_BOX, x, y, w, h):
            cur, full = int(m.group(1)), int(m.group(2))
            if 0 < full and cur <= full:
                return cur, full
    return None


def opp_name_line(lines, w, h, names):
    """상대 이름 칸에서 읽힌 이름 → (이름, 점수, 읽힌 글) 또는 None. 이 판 포켓몬에서만 맞춘다."""
    import msgread
    pool = names.here or []
    best = None
    for x, y, t in lines:
        if not _in(OPP_NAME_BOX, x, y, w, h) or "%" in t:
            continue
        body = msgread.normalize(t)
        if len(body) < 2 or not pool:
            continue
        name, sc = names.best(body, pool)
        if best is None or sc > best[1]:
            best = (name, sc, t)
    return best if best and best[1] >= 0.5 else None


# ── 판 ────────────────────────────────────────────────────────────────
class Board(object):
    """창의 칸과 같은 것. my/opp 는 6자리: {'poke': 포켓몬 또는 None, 'hp': %, 'brought': 냈나}."""

    def __init__(self, my, opp, my_active=0, opp_active=0, my_fresh=False,
                 opp_fresh=False, seen=None, opp_items=None, opp_abilities=None):
        self.my = my
        self.opp = opp
        self.my_active = my_active
        self.opp_active = opp_active
        self.my_fresh = my_fresh
        self.opp_fresh = opp_fresh
        self.seen = seen if seen is not None else {}
        self.opp_items = opp_items if opp_items is not None else {}
        self.opp_abilities = opp_abilities if opp_abilities is not None else {}
        # 실전 중간 상태 (창의 칸과 같다). 자리마다의 상태이상은 my/opp 줄의 'status'.
        self.ranks = {"me": {}, "opp": {}}              # 나와 있는 놈의 랭크
        self.weather, self.weather_turns = None, 5      # None = 자동 (특성으로)
        self.terrain, self.terrain_turns = None, 5
        self.hazards = {"me": {}, "opp": {}}            # 그쪽 자리에 깔린 것 {"스텔스록": 1, …}

    def find(self, side, name):
        rows = self.my if side == "me" else self.opp
        for i, r in enumerate(rows):
            if r["poke"] is not None and r["poke"]["name"] == name:
                return i
        return None


# 읽었지만 창에 칸이 없어 계산에 못 넣는 것 — 그렇다고 적는다
_NO_FIELD = {
    "능력하락": "능력이 떨어짐", "하품": "하품(다음 턴 잠듦)", "앙코르": "앙코르",
    "이미졸림": "이미 졸린 상태", "잠듦": "잠듦", "자는중": "잠든 중", "깸": "깨어남",
    "길동무": "길동무", "모래바람시작": "모래바람 시작", "모래바람끝": "모래바람 끝",
    "모래바람데미지": "모래바람 데미지", "스텔스록깔림": "상대 쪽 스텔스록",
    "스텔스록데미지": "스텔스록 데미지", "메가진화": "메가진화", "효과굉장": "효과가 굉장했다",
    "실패": "기술이 실패", "들어감": "들어감", "타입바뀜": "타입이 바뀜",
}
REVIVE_HP = 50.0     # 회생의기도 설명: "기절한 지닌 포켓몬을 최대 HP의 1/2 상태로 부활시킨다"


def _who(side):
    return "내" if side == "me" else "상대"


def _switch_to(board, side, i):
    """그쪽의 나와 있는 놈을 i 로. 바뀌었으면 True — 막 나옴을 켜고, **랭크를 풀고**, 들어간 놈의
    졸음(하품)을 푼다 (게임 규칙: 교체하면 랭크·졸음이 사라진다)."""
    now = board.my_active if side == "me" else board.opp_active
    if now == i:
        return False
    rows = board.my if side == "me" else board.opp
    if 0 <= now < len(rows) and rows[now].get("status") == "졸음":
        rows[now]["status"] = None
    if side == "me":
        board.my_active, board.my_fresh = i, True
    else:
        board.opp_active, board.opp_fresh = i, True
    board.ranks[side] = {}
    return True


def apply(board, ev, dex):
    """일어난 일 하나를 판에 넣는다 → [(넣었나, 한 줄)]."""
    import live
    kind = ev.get("kind")
    side, name = ev.get("side"), ev.get("mon")
    out = []
    if kind == "못 읽음":
        return [(False, "못 읽음: 「%s」 — 칸을 직접 확인하세요" % ev.get("text", ""))]
    if kind == "나옴" or (kind == "기술" and name):
        i = board.find(side, name)
        if i is None and side == "opp":
            poke = live.pickable_for(dex, dex.find_pokemon(name)) if name else None
            empty = [j for j, r in enumerate(board.opp) if r["poke"] is None]
            if poke is not None and empty:
                i = empty[0]
                board.opp[i] = {"poke": poke, "hp": 100.0, "brought": True}
                out.append((True, "상대 %d번 칸: %s — 새로 적음 (프리뷰에 없던 이름)" % (i + 1, name)))
        if i is None:
            return out + [(False, "%s: %s 파티에 없음 — 칸을 확인하세요" % (name, _who(side)))]
        rows = board.my if side == "me" else board.opp
        changed = []
        if not rows[i]["brought"]:
            rows[i]["brought"] = True
            changed.append("냈다")
        if _switch_to(board, side, i):
            changed.append("나와 있음")
        if kind == "나옴":
            if side == "me":
                board.my_fresh = True
            else:
                board.opp_fresh = True
            out.append((True, "%s %s: 나옴%s" % (_who(side), name,
                                                " → " + "·".join(changed) if changed else "")))
        else:
            move = ev.get("move")
            if changed:
                out.append((True, "%s %s: 기술을 썼으니 나와 있음 → %s"
                            % (_who(side), name, "·".join(changed))))
            if side == "opp" and move:
                got = board.seen.setdefault(name, [])
                if move not in got:
                    got.append(move)
                    out.append((True, "상대 %s: 기술 %s → 본 기술에 넣음" % (name, move)))
                else:
                    out.append((True, "상대 %s: 기술 %s (이미 본 기술)" % (name, move)))
            elif move:
                out.append((True, "내 %s: 기술 %s" % (name, move)))
        return out
    if kind in ("쓰러짐", "되살아남"):
        i = board.find(side, name)
        if i is None:
            return [(False, "%s: %s 파티에 없음 — 칸을 확인하세요" % (name, _who(side)))]
        rows = board.my if side == "me" else board.opp
        hp = 0.0 if kind == "쓰러짐" else REVIVE_HP
        rows[i]["hp"] = hp
        rows[i]["brought"] = True
        return [(True, "%s %s: %s → HP %d" % (_who(side), name,
                                              "쓰러짐" if kind == "쓰러짐" else "되살아남", hp))]
    if kind in ("풍선", "메가반응") and side == "opp":
        item = ev.get("item")
        board.opp_items[name] = item
        return [(True, "상대 %s: 도구 %s → 계산에 넣음" % (name, item))]
    if kind == "통찰" and side == "opp":
        board.opp_abilities[name] = "통찰"
        return [(True, "상대 %s: 특성 통찰 → 계산에 넣음 (본 것: 내 %s · %s)"
                 % (name, ev.get("other"), ev.get("item")))]
    if kind == "풍선터짐" and side == "opp":
        return [(False, "상대 %s: 풍선이 터짐 — 도구가 없어진 것은 아직 계산에 못 넣음" % name)]
    if kind in ("풍선", "메가반응", "풍선터짐", "통찰"):
        return [(True, "내 %s: %s (내 쪽이라 칸은 그대로)" % (name, kind))]
    if kind == "이김":
        return [(True, "승부에서 이겼다")]
    got = _apply_mid(board, ev, kind, side, name)
    if got is not None:
        return got
    what = _NO_FIELD.get(kind, kind)
    if ev.get("stat"):
        what += " (%s)" % ev["stat"]
    if ev.get("type"):
        what += " (%s)" % ev["type"]
    who = ("%s %s: " % (_who(side), name)) if name else ""
    return [(False, "%s%s — 창에 칸이 없어 계산엔 안 들어감" % (who, what))]


def _apply_mid(board, ev, kind, side, name):
    """랭크 · 상태이상 · 날씨 · 압정 칸에 넣는 일 (2026-09-23). 해당 없으면 None."""
    import battle
    if kind == "능력하락":
        key = battle.STAT_WORD.get(ev.get("stat"))
        i = board.find(side, name)
        active = board.my_active if side == "me" else board.opp_active
        if key is None or i is None:
            return [(False, "%s %s: %s 하락 — 누구인지·무엇인지 못 맞춤" % (_who(side), name, ev.get("stat")))]
        if i != active:
            return [(False, "%s %s: %s 하락 — 나와 있는 놈이 아니라 안 넣음" % (_who(side), name, ev.get("stat")))]
        r = board.ranks.setdefault(side, {})
        r[key] = max(-6, r.get(key, 0) - 1)
        return [(True, "%s %s: %s 랭크 %+d" % (_who(side), name, ev["stat"], r[key]))]
    if kind in ("하품", "잠듦", "자는중", "깸"):
        i = board.find(side, name)
        if i is None:
            return [(False, "%s: %s 파티에 없음 — 칸을 확인하세요" % (name, _who(side)))]
        row = (board.my if side == "me" else board.opp)[i]
        before = row.get("status")
        if kind == "하품":
            if before and before not in ("없음", "졸음"):
                return [(True, "%s %s: 하품 — 이미 %s 라 안 바꿈" % (_who(side), name, before))]
            row["status"] = "졸음"
        elif kind == "깸":
            row["status"] = None
        else:
            row["status"] = "잠듦"
        now = row["status"] or "없음"
        return [(True, "%s %s: 상태 %s" % (_who(side), name, now))]
    if kind == "모래바람시작":
        board.weather, board.weather_turns = "모래바람", 5
        return [(True, "날씨 모래바람 5턴 (보송보송바위면 8턴 — 남은 턴은 확인하세요)")]
    if kind == "모래바람끝":
        board.weather = "없음"
        return [(True, "날씨 없음 (모래바람이 가라앉음)")]
    if kind == "모래바람데미지":
        if board.weather != "모래바람":
            board.weather = "모래바람"
            return [(True, "모래바람이 불고 있음 → 날씨 모래바람 (남은 턴은 몰라 %d 로 둠)"
                     % board.weather_turns)]
        return [(True, "모래바람 데미지 (날씨는 이미 모래바람)")]
    if kind in ("스텔스록깔림", "스텔스록데미지"):
        where = "opp" if kind == "스텔스록깔림" else side     # 「상대의 주변에」 만 봤다
        board.hazards.setdefault(where, {})["스텔스록"] = 1
        return [(True, "%s 쪽에 스텔스록" % ("상대" if where == "opp" else "내"))]
    return None


def apply_hp(board, res):
    """대전 화면의 HP 를 판에 넣는다 → [(넣었나, 한 줄)].

    상대 HP 는 **나와 있는 상대 칸**에 넣는다. 이름 칸이 읽혔고 다른 칸의 이름이면 그 칸으로
    (그리고 그놈이 나와 있는 것으로). 내 HP 는 나와 있는 내 칸에.
    """
    out = []
    m = res.get("opp_hp")
    if m:
        i = board.opp_active
        named = res.get("opp_name")
        if named:
            j = board.find("opp", named[0])
            if j is not None and j != i:
                _switch_to(board, "opp", j)
                i = j
                out.append((True, "상대 이름 칸이 %s — 나와 있는 상대를 그쪽으로" % named[0]))
        row = board.opp[i] if 0 <= i < len(board.opp) else None
        if row is None or row["poke"] is None:
            out.append((False, "상대 HP %.0f%% 를 쟀지만 나와 있는 상대 칸이 비어 있음" % m["hp"]))
        else:
            row["hp"] = round(m["hp"], 1)
            row["brought"] = True
            out.append((True, "상대 %s: HP %.0f%% (막대로 잼)" % (row["poke"]["name"], m["hp"])))
        if m.get("warn"):
            out.append((False, "상대 HP: " + m["warn"]))
    mine = res.get("my_hp")
    if mine:
        cur, full = mine
        i = board.my_active
        # 최대 HP 는 그 포켓몬의 HP 능력치다 — 딱 한 칸만 맞으면 그놈이 나와 있는 것이다
        same = [j for j, r in enumerate(board.my) if r.get("maxhp") == full]
        if len(same) == 1 and same[0] != i:
            i = same[0]
            _switch_to(board, "me", i)
            out.append((True, "최대 HP %d 가 내 %s 와 같다 — 나와 있는 내 포켓몬을 그쪽으로"
                        % (full, board.my[i]["poke"]["name"])))
        elif 0 <= i < len(board.my):
            have = board.my[i].get("maxhp")
            if have and have != full:
                out.append((False, "내 HP 최대치 %d 가 나와 있는 칸(%s, HP %d)과 다름 — 칸을 확인하세요"
                            % (full, board.my[i]["poke"]["name"], have)))
        row = board.my[i] if 0 <= i < len(board.my) else None
        if row is None or row["poke"] is None:
            out.append((False, "내 HP %d/%d 를 읽었지만 나와 있는 내 칸이 비어 있음" % mine))
        else:
            row["hp"] = round(cur * 100.0 / full, 1)
            out.append((True, "내 %s: HP %d/%d = %.0f%%" % (row["poke"]["name"], cur, full, row["hp"])))
    return out


def apply_preview(board, found, dex):
    """선출 화면에서 알아본 6마리를 상대 칸에 넣는다 (있던 상대 칸은 비운다)."""
    import live
    out = []
    board.opp = []
    for i, f in enumerate(found):
        poke = live.pickable_for(dex, dex.find_pokemon(f["key"]))
        board.opp.append({"poke": poke, "hp": 100.0, "brought": False})
        warn = "  ← 2등과 차이가 작음, 확인하세요" if f["gap"] < 0.05 else ""
        out.append((True, "상대 %d. %s  (%s, 점수 %.2f)%s"
                    % (i + 1, live.poke_label(poke), f["gender"] or "성별 표시 없음",
                       f["score"], warn)))
    board.opp_active, board.opp_fresh = 0, True
    board.seen.clear()
    board.opp_items.clear()
    board.opp_abilities.clear()
    return out


def main(argv):
    paths.fix_console()
    import calc
    import msgread
    dex = calc.Dex()
    names = msgread.Names(dex)
    for path in argv:
        got = read_screen(path, dex, names)
        print("==", path, got["kind"])
        if got["kind"] == "선출":
            for f in got["opp"]:
                p = dex.find_pokemon(f["key"])
                print("  ", p["name"], p["formName"], f["gender"], round(f["score"], 2))
        else:
            print("   읽은 글:", " / ".join(got["lines"]))
            print("   일어난 일:", got["event"])


if __name__ == "__main__":
    main(sys.argv[1:])
