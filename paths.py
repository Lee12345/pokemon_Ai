# -*- coding: utf-8 -*-
"""파일이 어디 있는지 한곳에서 정한다.

## 왜 필요한가

평소에는 `os.path.dirname(__file__)` 이면 충분하다. 그런데 **하나로 묶은
실행 파일(.exe)** 로 만들면 그게 안 통한다 —

  · 자료(data/)는 실행 파일 **안**에 들어간다. PyInstaller 는 그걸
    임시 폴더에 풀고 `sys._MEIPASS` 에 그 자리를 넣어 준다.
  · 반대로 **내가 만드는 것**(파티 파일·대전 기록)은 그 임시 폴더에
    쓰면 안 된다. 프로그램을 끄면 같이 지워진다.
    실행 파일이 **놓인 자리**에 써야 다음에도 남아 있다.

그래서 읽는 자리와 쓰는 자리를 갈라 둔다. 이걸 파일마다 따로 짜면
어느 하나가 조용히 임시 폴더를 가리키게 된다.
"""

import os
import sys


def frozen():
    """하나로 묶은 실행 파일로 도는 중인가."""
    return getattr(sys, "frozen", False)


def read_root():
    """**읽을 것**(data/)이 있는 자리."""
    if frozen():
        # PyInstaller 가 푼 임시 폴더. 없으면 실행 파일 옆.
        return getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def write_root():
    """**내가 남길 것**(파티·기록)을 쓸 자리.

    묶인 실행 파일이면 그 파일이 놓인 자리다. 임시 폴더에 쓰면
    프로그램을 끌 때 같이 지워져서, 다음에 켜면 파티를 또 물어본다.
    """
    if frozen():
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def data(*parts):
    return os.path.join(read_root(), "data", *parts)


def mine(*parts):
    """내가 남기는 파일 자리. 없으면 폴더를 만들어 준다."""
    path = os.path.join(write_root(), "내기록", *parts)
    folder = path if not parts or "." not in parts[-1] else os.path.dirname(path)
    try:
        os.makedirs(folder)
    except OSError:
        pass
    return path


def fix_console():
    """윈도우 콘솔에서 한글이 깨지지 않게 한다.

    윈도우는 콘솔 기본 인코딩이 cp949 라, UTF-8 로 적힌 글자가
    깨지거나 프로그램이 통째로 죽는 일이 있다. 파이썬 3.7 부터는
    `reconfigure` 로 바꿀 수 있다. 안 되면 조용히 넘어간다 —
    **여기서 죽으면 프로그램이 아예 안 켜진다.**
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError, OSError):
            pass
