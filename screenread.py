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

import atexit
import os
import queue
import re
import struct
import subprocess
import sys
import tempfile
import threading

import paths
import pngio

HERE = os.path.dirname(os.path.abspath(__file__))
OCR_SCRIPT = os.path.join(HERE, "tools", "글자읽기.ps1")
WORKER_SCRIPT = os.path.join(HERE, "tools", "화면일꾼.ps1")
MSG_BOX = (0.0, 0.70, 0.35, 0.90)       # 왼쪽 · 위 · 오른쪽 · 아래 (화면에 대한 몫)


# ── 파워셸 일꾼 — 한 번 켜 두고 계속 시킨다 ─────────────────────────────
#
# 사진 한 장에 파워셸을 두 번 켰다 (그림 바꾸기 + 글자 읽기). 켜는 데만 장당 0.79초가
# 갔다 (2026-09-23 에 잼 — 장당 2.88초 중). 캡처보드 화면을 계속 읽으려면 이게 제일 크다.
#
# ★ **고장 나면 예전 방식(장마다 새로 켜기)으로 돌아간다.** 대전 중에 도구가 멈추면 안 된다.
#   돌아간 까닭은 `worker().fell_back` 에 남고, 창이 그걸 보여 준다. 조용히 죽지 않는다.
USE_WORKER = True
WORKER_WAIT = 20.0          # 한 번 시켜 놓고 이만큼까지 기다린다 (초)


class Worker(object):
    """파워셸 하나를 켜 두고 `tools/화면일꾼.ps1` 에게 시킨다."""

    def __init__(self):
        self.proc = None
        self.lines = None
        self.fell_back = None
        self.used = 0
        self.reply = None       # 마지막으로 받은 「OK …」 줄 (창 크기 등이 붙어 온다)

    def start(self):
        """켜져 있으면 True. 한 번 못 켠 뒤로는 다시 안 해 본다 (대전 중에 매번 1초를 버리면 안 된다)."""
        if self.proc is not None and self.proc.poll() is None:
            return True
        if self.fell_back is not None:
            return False
        self.proc = None
        try:
            p = subprocess.Popen(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", WORKER_SCRIPT],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                encoding="utf-8", errors="replace", bufsize=1)
        except OSError as e:
            self.fell_back = "파워셸을 못 켰다: %s" % e
            return False
        q = queue.Queue()

        def read():
            try:
                for row in p.stdout:
                    q.put(row.rstrip("\r\n"))
            except (OSError, ValueError):
                pass
            q.put(None)

        threading.Thread(target=read, daemon=True).start()
        self.proc, self.lines = p, q
        try:
            first = q.get(timeout=WORKER_WAIT)
        except queue.Empty:
            first = None
        if first != "READY":
            self._die("일꾼이 시작을 안 알렸다 (%r)" % (first,))
            return False
        return True

    def _die(self, why):
        self.fell_back = why
        p, self.proc, self.lines = self.proc, None, None
        if p is not None:
            try:
                p.kill()
            except OSError:
                pass

    def ask(self, cmd):
        """시킨다. 됐으면 True. 고장 나면 False 로 돌려주고 그 뒤로는 예전 방식을 쓴다."""
        if not self.start():
            return False
        try:
            self.proc.stdin.write(cmd + "\n")
            self.proc.stdin.flush()
        except (OSError, ValueError) as e:
            self._die("일꾼에게 말을 못 걸었다: %s" % e)
            return False
        ok = None
        while True:
            try:
                row = self.lines.get(timeout=WORKER_WAIT)
            except queue.Empty:
                self._die("일꾼이 %.0f초 안에 답을 안 했다: %s" % (WORKER_WAIT, cmd))
                return False
            if row is None:
                self._die("일꾼이 도중에 꺼졌다: %s" % cmd)
                return False
            if row == "<<END>>":
                break
            if ok is None:
                ok = row
        self.reply = ok
        if ok is None or not ok.startswith("OK"):
            # 그 한 번만 실패한 것일 수도 있다 (사진이 깨졌다든가) → 일꾼은 살려 두고 예전 방식으로 해 본다.
            return False
        self.used += 1
        return True

    def stop(self):
        p = self.proc
        self.proc, self.lines = None, None
        if p is None:
            return
        try:
            p.stdin.write("bye\n")
            p.stdin.flush()
            p.wait(timeout=3)
        except Exception:
            try:
                p.kill()
            except OSError:
                pass


_WORKER = Worker()


def worker():
    return _WORKER


def stop_worker():
    _WORKER.stop()


atexit.register(stop_worker)


def _bar(path):
    """세로줄은 주고받는 말의 구분자다 — 경로에 들어 있으면 일꾼에게 못 맡긴다."""
    return "|" in path


# ── 창 찍기 (OBS 창 프로젝터) ───────────────────────────────────────────
#
# 사용자는 캡처보드 화면을 **OBS** 로 본다 (2026-09-23). OBS 미리보기 위에서 우클릭 →
# 「창 프로젝터(미리 보기)」 를 띄우면 **그 창 속이 곧 게임 화면**이다. 그 창만 찍으면
# OBS 의 단추·목록이 안 섞이므로 자리를 찾을 필요가 없다.
#
# 잰 것 (2026-09-23, OBS 30.1.2 본 창 1923x1233): PrintWindow 한 번 **19ms**, PNG 저장까지 35ms.
# ★ 창을 앞으로 끌어올리지 않는다 (`tools/창사진.ps1` 과 다른 점) — 실전 중에 초점을 뺏으면 안 된다.
#   가려져 있어도 그려진다. OBS 미리보기가 그래픽카드로 그려져서 새까맣게 나올까 걱정했는데
#   **멀쩡히 나온다** (실제로 찍어서 확인함).
PROJECTOR = "프로젝터"          # 창 프로젝터 제목에 들어가는 말


def shot(title, out=None, box=None):
    """창 하나를 찍어 (PNG 자리, 창 속 크기) 를 돌려준다 (제목줄·테두리 뺀 속만).

    `box` 를 주면 **파워셸에서** 그 자리만 잘라 저장한다. 파이썬에서 자르고 PNG 를 다시 쓰면
    2448x1377 한 장에 0.36초가 더 든다 (2026-09-23 에 잼) — 찍는 것보다 비싸다.
    못 찍으면 RuntimeError.
    """
    if out is None:
        out = os.path.join(tempfile.gettempdir(), "screenshot_%d.png" % os.getpid())
    if _bar(title) or _bar(out):
        raise RuntimeError("창 제목이나 저장 자리에 '|' 가 있으면 못 찍는다")
    cmd = "shot|%s|%s" % (title, out)
    if box is not None:
        cmd += "|%d|%d|%d|%d" % tuple(box)
    if not (USE_WORKER and _WORKER.ask(cmd)):
        raise RuntimeError("창을 못 찍었다 (%s) — %s"
                           % (title, _WORKER.reply or _WORKER.fell_back or "그런 창이 없거나 최소화됨"))
    part = (_WORKER.reply or "").split()
    size = (int(part[1]), int(part[2])) if len(part) >= 3 else None
    return out, size


class Window(object):
    """창 하나를 계속 찍어 읽는다 (OBS 창 프로젝터).

    창 프로젝터는 창 비율이 영상 비율과 다르면 **까만 띠**를 넣는다. 그대로 두면 문구 칸 자리를
    화면 비율로 찾는 것이 통째로 어긋난다 → 잘라 낸다. 잘라 낼 자리는 **창 크기가 그대로면
    한 번만** 찾는다 (찾는 데 0.03초, 창을 다시 찍는 데 0.16초). 창 크기가 바뀌면 다시 찾는다.
    """

    def __init__(self, title=PROJECTOR, out=None):
        self.title = title
        self.out = out or os.path.join(tempfile.gettempdir(), "screenshot_%d.png" % os.getpid())
        self.box = None         # 창 속에서 잘라 낼 자리
        self.raw_size = None    # 그때의 창 속 크기
        self.size = None        # 잘라 낸 뒤 크기

    def grab(self):
        """한 장 찍어 (PNG 자리, 너비, 높이, 점들)."""
        if self.box is not None:
            path, raw = shot(self.title, self.out, self.box)
            if raw == self.raw_size:
                w, h, px = pngio.read_png(path)
                self.size = (w, h)
                return path, w, h, px
            self.box = None     # 창 크기가 바뀌었다 → 다시 찾는다
        path, raw = shot(self.title, self.out)
        w, h, px = pngio.read_png(path)
        box = pngio.trim_black(w, h, px)
        self.raw_size = raw
        if box == (0, 0, w, h):
            self.box, self.size = None, (w, h)
            return path, w, h, px
        self.box = box
        path, _ = shot(self.title, self.out, box)
        w, h, px = pngio.read_png(path)
        self.size = (w, h)
        return path, w, h, px

    def read(self, dex, names):
        """한 장 찍어 바로 읽는다 → `read_screen` 과 같은 모양 + 'shot'·'size'·'trimmed'."""
        path, w, h, _px = self.grab()
        got = read_screen(path, dex, names)
        got["shot"] = path
        got["size"] = (w, h)
        got["trimmed"] = self.box
        return got


def read_window(title, dex, names, out=None):
    """창 하나를 찍어 바로 읽는다 (한 번만 쓸 때. 계속 읽으려면 `Window` 를 쓴다)."""
    return Window(title, out).read(dex, names)


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
    src = os.path.abspath(path)
    if USE_WORKER and not _bar(src) and not _bar(out) and _WORKER.ask("png|%s|%s" % (src, out)):
        return out
    cmd = ("Add-Type -AssemblyName System.Drawing; "
           "$b = [System.Drawing.Bitmap]::FromFile('%s'); $b.Save('%s', "
           "[System.Drawing.Imaging.ImageFormat]::Png); $b.Dispose()"
           % (src.replace("'", "''"), out.replace("'", "''")))
    subprocess.run(["powershell", "-NoProfile", "-Command", cmd], check=True,
                   capture_output=True)
    return out


# 고른 빨간 띠가 이만큼 쌓여 있으면 대전 화면이 아니다 (선출 화면 · 「상태 확인」 화면)
STACK_MIN = 3

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
    if USE_WORKER and not _bar(src) and not _bar(tmp) and \
            _WORKER.ask("scale|%s|%s|%d" % (src, tmp, scale)):
        return
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
    if not (USE_WORKER and not _bar(tmp) and _WORKER.ask("ocr|%s" % tmp)):
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


def crop_lines(w, h, px, box, scale=1):
    """화면의 한 칸만 잘라서 글자를 읽는다 → [줄]. 좌표는 안 돌려준다 (그 칸 안이 전부다).

    ★ **통째로 읽으면 엔진이 화면 전체를 보느라 문구를 놓친다.** 저장해 둔 실전 화면으로
      재 봤다 (2026-09-23) — 「상대 개굴닌자는 / 악타입이 됐다!」 가 통째로는 아랫줄만
      읽혀 **못 읽음**, 문구 칸만 잘라 읽으니 두 줄이 다 나와 **0.92 로 맞았다.**
    ★ 값: OBS 한 장(2448x1377)에서 잘라내기 0.001 + 저장 0.020 + 읽기 0.013 = **0.035초.**
      (통째로 읽는 데 0.144초 드는 것과 견주면 4분의 1이다.)
    """
    x0, y0, x1, y1 = box
    cw, ch, cpx = pngio.crop(w, h, px, int(w * x0), int(h * y0), int(w * x1), int(h * y1))
    if cw <= 0 or ch <= 0:
        return []
    tmp = os.path.join(tempfile.gettempdir(), "screenread_%d_cut.png" % os.getpid())
    pngio.write_png(tmp, cw, ch, cpx)
    try:
        got = ocr(tmp, scale)
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass
    # 한글이 두 자 이상인 줄만 (시계·표시 조각을 뺀다 — message_lines 와 같은 규칙)
    return [t for _x, _y, t in sorted(got, key=lambda r: r[1])
            if len(re.findall(r"[가-힣]", t)) >= 2]


def message_lines(lines, w, h):
    """글자 인식 줄들 → 문구 칸 줄만, 위에서부터."""
    x0, y0, x1, y1 = MSG_BOX
    # 문구는 한글이 있다 — 같은 자리에 걸리는 시계(「06:41」)·표시 조각(「b」)은 뺀다
    got = [(y, t) for x, y, t in lines
           if x0 <= x / float(w) < x1 and y0 <= y / float(h) < y1
           and len(re.findall(r"[가-힣]", t)) >= 2]
    return [t for _, t in sorted(got)]


def read_screen(path, dex, names, img=None):
    """사진 한 장 → {'kind': '선출', 'opp': [...]} 또는 {'kind': '대전', 'lines': [...], 'event': {...}}.

    `img` 로 (너비, 높이, 점들) 을 미리 주면 다시 안 읽는다 (계속 읽을 때 장당 0.06초를 아낀다).
    """
    import artmatch
    import msgread
    png = to_png(path)
    w, h, px = img if img is not None else pngio.read_png(png)
    bands = artmatch.panel_bands(w, h, px)
    try:
        found = artmatch.identify(w, h, px, bands=bands) if artmatch.pick_six(bands) else None
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
    # ★ **지금 대전 화면인가를 먼저 가린다.** 선출 화면과 「상태 확인」 화면은 상대 여섯 칸을
    #   세로로 쌓아 보여 주는데, 그 분홍 칸을 HP 막대로 잘못 읽었다 (2026-09-23 실전 한 판에서
    #   막대가 잡힌 240프레임 중 절반 가까이가 거짓이었다). 잰 것 — **대전 화면은 고른 띠가
    #   0~1개, 선출·상태확인 화면은 3~6개.** 그래서 3개 이상이면 HP 를 아예 안 잰다.
    stack = artmatch.stack_size(bands)
    battle_like = stack < STACK_MIN
    if not battle_like and is_status(raw, w, h):
        # 글자가 작아 2배로 키워야 읽힌다 — 이 화면일 때만 한 번 더 읽는다
        big = ocr(path, STATUS_SCALE)
        out = {"kind": "상태확인", "lines": lines, "event": None, "stack": stack, "raw": big}
        out.update(status_screen(big, w, h, names))
        return out
    # ★ **못 읽었을 때만** 문구 칸을 잘라 2배로 키워 한 번 더 읽는다.
    #
    #   글자가 보이는데 틀에 안 맞은 장이 그 대상이다. 큰 화면(OBS 2448)은 통째로 1배로
    #   읽으므로 문구 글자가 작다 — 「패리퍼를 내보냈다」 가 「때라퍼를 내보했다」 로 깨진 적이
    #   있다 (2026-09-23). 작은 화면(SMALL_W 아래)은 이미 통째로 2배로 읽으므로 그대로 둔다.
    #   드는 값: 문구 칸 2배 읽기 **0.131초** (통째 0.331초의 40%). 못 읽은 장에만 낸다.
    #   ★ 둘 중 **더 닮은 쪽**을 고르므로 나빠질 수는 없다.
    event = msgread.read(lines, names) if lines else None
    if (battle_like and lines and w >= SMALL_W
            and (event is None or event.get("kind") == "못 읽음")):
        cut = crop_lines(w, h, px, MSG_BOX, 2)
        if cut and cut != lines:
            ev2 = msgread.read(cut, names)
            if event is None or ev2.get("score", 0.0) > event.get("score", 0.0):
                lines, event = cut, ev2
    out = {"kind": "대전", "lines": lines,
           "event": event,
           "opp_hp": hpread.measure(w, h, px) if battle_like else None,
           "opp_hp_text": opp_hp_text(raw, w, h) if battle_like else None,
           "stack": stack,
           "opp_name": opp_name_line(raw, w, h, names),
           "my_hp": my_hp_numbers(raw, w, h),
           # 글자 인식이 읽은 줄 **전부** — 문구 칸 밖(상대 HP %·기술 PP 등)을 보려면 필요하다
           "raw": raw}
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


# 상대 HP % 글자 자리: 오른쪽 위 (OBS 캡처 2448x1377 에서 x 0.91 · y 0.25).
# 아이패드 녹화에서는 여기 글자가 읽혔고 유튜브 스위치 화면(1341x749)에서는 못 읽었다 — 화면이
# 커지면 읽힌다. **막대와 맞대 보는 데 쓴다.** 어느 한쪽만 믿지 않는다.
OPP_PCT_BOX = (0.65, 0.0, 1.0, 0.50)


def opp_hp_text(lines, w, h):
    """상대 HP 를 글자로 읽은 % 또는 None. 100 을 넘으면 버린다 (실전에서 109·199·799 가 나왔다)."""
    for x, y, t in lines:
        if not _in(OPP_PCT_BOX, x, y, w, h):
            continue
        m = re.search(r"(\d{1,3})\s*%", t)
        if m:
            v = int(m.group(1))
            if 0 < v <= 100:
                return v
    return None


# 막대와 글자가 이만큼까지 다른 것은 봐준다 (실전 83번 비교에서 맞는 짝은 전부 ±1 안이었다)
HP_AGREE = 5


def combine_hp(bar, text):
    """막대와 글자를 맞대 본다 → (HP% 또는 None, 알림 또는 None).

    실전 한 판(903프레임, 2026-09-23)에서 잰 것:
    - 둘 다 읽힌 83프레임 중 **진짜 대전 화면에서는 ±1** 로 붙었다 (86.3/86 · 67.8/68 · 55.9/56 …).
    - **글자는 9번 100% 를 넘었다** (109 · 199 · 799) 그리고 47% 를 「7」 로 읽었다.
    - **막대는 100% 를 한 번도 안 넘었다.** 대신 대전 화면이 아닌 곳에서 헛것을 봤다.
    → 어느 한쪽이 나은 게 아니라 **서로의 잘못을 잡아 준다.** 크게 다르면 **고르지 않고 말한다.**

    ★ **둘이 맞으면 글자 쪽을 쓴다** (2026-09-23, 사용자: "1~2%정도 오차가 있는데 이건
      생각보다 큰 문제이다"). 글자 % 는 **게임이 직접 띄운 수**라 오차가 없다. 막대는 잘 맞아도
      1~2% 어긋난다 (86.3/86 · 73.4/74 · 67.8/68 · 55.9/56 …). 1~2% 는 「한 대 더 버티나」 를
      뒤집을 수 있다. 글자를 못 읽었을 때만 막대를 쓴다.
    """
    b = bar["hp"] if bar else None
    if b is None and text is None:
        return None, None
    if text is None:
        return b, None
    if b is None:
        return float(text), None        # 게임이 띄운 수 — 막대보다 낫다
    if abs(b - text) <= HP_AGREE:
        return float(text), None        # 둘이 맞는다 → 정확한 쪽(글자)을 쓴다
    return None, ("상대 HP 가 막대로는 %.0f%%, 글자로는 %d%% 입니다 — 달라서 안 넣었습니다"
                  % (b, text))


# ── 「상태 확인」 화면 ──────────────────────────────────────────────────
#
# 게임에서 X 를 누르면 뜨는 화면이다. 한 장에 이게 다 있다 (2026-09-23 실전에서 봄) —
# 상대 6마리 전부 · 나와 있는 놈 · 상대 상태이상(Zz) · 상대 HP % ·
# **내가 이번 판에 낸 3마리** · 나와 있는 내 포켓몬의 기술 4개 + PP + 특성 + 도구.
#
# 글자가 작아서 **2배로 키워야** 읽힌다 (원본 크기로는 네 줄밖에 안 읽혔다).
# 그래서 이 화면일 때만 한 번 더 읽는다 (0.3초 더) — 대전 화면은 그대로다.
#
# ★ **지금 읽는 것은 「낸 3마리」 와 「상대 HP」 뿐이다.** 이 화면 표본이 **한 판, 한 순간뿐**이라
#   (27프레임이지만 전부 같은 15초) 자리를 더 박으면 또 '한 장에 맞춘 문턱' 이 된다 (§10 의 그 실수).
#   기술·특성·도구·상태이상도 읽히긴 하지만, 다른 판 화면을 더 보고 나서 붙인다.
STATUS_BOX = (0.60, 0.0, 1.0, 0.12)     # 오른쪽 위 「상태 확인」 글자
MY_LIST_BOX = (0.0, 0.12, 0.35, 0.92)   # 왼쪽 — 이번 판에 낸 내 포켓몬 이름들
STATUS_SCALE = 2
NAME_MIN = 0.72                         # 이만큼 닮아야 그 포켓몬 이름으로 본다
BROUGHT = 3                             # 챔피언스 싱글 — 6마리에서 3마리를 낸다


def is_status(lines, w, h):
    """「상태 확인」 화면인가. 실전 프레임에서 27/27 맞고 대전·선출 화면에서는 한 번도 안 걸렸다."""
    import msgread
    for x, y, t in lines:
        if _in(STATUS_BOX, x, y, w, h) and msgread.sim(msgread.normalize(t), "상태확인") > 0.7:
            return True
    return False


def status_screen(lines, w, h, names):
    """상태 확인 화면 → {'mine': [이름 …], 'opp_hp': % 또는 None}.

    이름은 **이 판에 있는 포켓몬**(`names.here`) 에서만 찾는다 — 깨진 글자가 엉뚱한 포켓몬이
    되지 않게. 위에서 아래 순서 그대로 돌려준다.
    ★ **누가 나와 있는지는 안 본다.** 이 화면에서 나와 있는 놈은 테두리가 밝지만, 목록 순서가
      '나와 있는 놈이 맨 위' 인지 '파티 순서 그대로' 인지 **표본이 한 순간뿐이라 모른다.**
    """
    import msgread
    pool = names.here or []
    got = []
    for x, y, t in sorted(lines, key=lambda r: r[1]):
        if not _in(MY_LIST_BOX, x, y, w, h) or not pool:
            continue
        body = msgread.normalize(t)
        if len(body) < 2:
            continue
        name, sc = names.best(body, pool)
        if sc >= NAME_MIN and name not in got:
            got.append(name)
    return {"mine": got, "opp_hp": opp_hp_text(lines, w, h)}


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
        # ★ **누가 나와 있는지 아는가.** 선출 화면을 읽으면 6칸이 채워지지만 **누가 먼저
        #   나올지는 모른다.** 그런데 `opp_active` 가 0(1번 칸)이라 실전에서 상대가 6번
        #   다크펫을 냈는데 **1번 망나뇽의 HP 로 넣고 있었다** (2026-09-23, 사용자가 잡음).
        #   조용히 엉뚱한 놈에게 HP 를 붙이느니 **모른다고 말하고 안 넣는다.**
        self.opp_active_known = True
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
        board.opp_active_known = True
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
    # ★ **이름 칸을 먼저 본다 — HP 가 있든 없든.** 예전에는 HP 를 넣을 때만 봐서, 문구를
    #   못 읽은 판에서는 상대가 누구인지 영영 모른 채 1번 칸에 HP 를 쌓았다 (2026-09-23).
    named = res.get("opp_name")
    if named:
        j = board.find("opp", named[0])
        if j is not None:
            if _switch_to(board, "opp", j):
                out.append((True, "상대 이름 칸이 %s — 나와 있는 상대를 그쪽으로" % named[0]))
            elif not board.opp_active_known:
                board.opp_active_known = True
                out.append((True, "상대 이름 칸이 %s — 나와 있는 상대로 확인" % named[0]))
    m = res.get("opp_hp")
    hp, why_hp = combine_hp(m, res.get("opp_hp_text"))
    if why_hp and hp is None:
        out.append((False, why_hp))
    if hp is not None:
        i = board.opp_active
        row = board.opp[i] if 0 <= i < len(board.opp) else None
        if not board.opp_active_known:
            # 누가 나와 있는지 모르면 **안 넣는다.** 엉뚱한 놈에게 붙이면 계산이 통째로 틀린다.
            out.append((False, "상대 HP %.0f%% 를 읽었지만 **누가 나와 있는지 몰라** 안 넣었습니다"
                        " — 상대 칸에서 나와 있는 놈을 골라 주세요" % hp))
        elif row is None or row["poke"] is None:
            out.append((False, "상대 HP %.0f%% 를 쟀지만 나와 있는 상대 칸이 비어 있음" % hp))
        else:
            row["hp"] = round(hp, 1)
            row["brought"] = True
            txt = res.get("opp_hp_text")
            how = ("글자 %d%% (막대 %.0f%% 와 맞음)" % (txt, m["hp"])) if (m and txt) else (
                "막대로 잼 — 글자를 못 읽어 1~2%% 오차가 있을 수 있음" if m else "글자로 읽음")
            out.append((True, "상대 %s: HP %.0f%% (%s)" % (row["poke"]["name"], hp, how)))
        if why_hp:
            out.append((False, "상대 HP: " + why_hp))
        if m and m.get("warn"):
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
                # ★ **안 맞으면 안 넣는다.** 전에는 경고만 하고 그대로 넣었다. 실전에서
                #   「0/3」 으로 잘못 읽은 것이 하마돈(215)에 들어가 **HP 0% = 쓰러짐**
                #   이 되었고, 그 판 내내 내 파티가 두 마리로 계산됐다 (2026-09-23 기록).
                #   경고를 띄우면서 틀린 값을 넣는 것은 안 띄우는 것보다 나쁘다.
                out.append((False, "내 HP 최대치 %d 가 나와 있는 칸(%s, HP %d)과 달라 "
                                   "안 넣었습니다 — 잘못 읽었거나 칸의 HP 능력치가 틀립니다"
                            % (full, board.my[i]["poke"]["name"], have)))
                return out
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
    board.opp_active_known = False      # 6마리는 알지만 **누가 먼저 나오는지는 아직 모른다**
    out.append((False, "누가 먼저 나오는지는 아직 모릅니다 — 문구나 상대 이름 칸을 읽으면 정합니다"))
    board.seen.clear()
    board.opp_items.clear()
    board.opp_abilities.clear()
    return out


def apply_status(board, res, dex):
    """「상태 확인」 화면에서 읽은 것을 판에 넣는다 → [(넣었나, 한 줄)].

    - **내가 이번 판에 낸 3마리** → 그 칸의 「냈다」 를 켜고, 나머지는 끈다.
      (이 화면에 이름이 있다는 것이 곧 '냈다' 다 — 안 낸 놈은 여기 안 나온다.)
    - **상대 HP %** → 나와 있는 상대 칸.
    """
    out = []
    mine = res.get("mine") or []
    if mine:
        found = []
        for name in mine:
            j = board.find("me", name)
            if j is None:
                out.append((False, "상태 확인 화면의 %s 가 내 파티에 없습니다 — 칸을 확인하세요" % name))
            else:
                found.append(j)
        # ★ **셋을 다 읽었을 때만 넣는다.** 챔피언스 싱글은 6마리에서 **3마리**를 낸다.
        #   실전 27프레임 중 11프레임은 한둘만 읽혔는데, 그걸로 나머지의 「냈다」 를 끄면
        #   **낸 포켓몬을 안 낸 것으로 만들어 버린다.** 조용히 틀리는 자리라 아예 안 넣는다.
        if len(found) == BROUGHT:
            for j, row in enumerate(board.my):
                if row.get("poke"):
                    row["brought"] = j in found
            out.append((True, "이번 판에 낸 내 포켓몬: %s (나머지는 「냈다」 를 껐습니다)"
                        % ", ".join(board.my[j]["poke"]["name"] for j in found)))
        else:
            out.append((False, "낸 포켓몬을 %d마리만 읽어서 안 넣었습니다 (읽힌 것: %s)"
                        % (len(found), ", ".join(board.my[j]["poke"]["name"] for j in found) or "없음")))
    hp = res.get("opp_hp")
    if hp is not None:
        i = board.opp_active
        row = board.opp[i] if 0 <= i < len(board.opp) else None
        if row is None or row["poke"] is None:
            out.append((False, "상대 HP %d%% 를 읽었지만 나와 있는 상대 칸이 비어 있음" % hp))
        else:
            row["hp"] = float(hp)
            row["brought"] = True
            out.append((True, "상대 %s: HP %d%% (상태 확인 화면의 글자)"
                        % (row["poke"]["name"], hp)))
    if not out:
        out.append((False, "상태 확인 화면인데 읽을 것을 못 찾았습니다"))
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
