# -*- coding: utf-8 -*-
"""
champs.pokedb.tokyo 구축기사 수집기 — **집 회선에서 돌리는 용도**.

    python fetch_champs.py --살펴보기            # 검색을 무엇으로 좁힐 수 있나
    python fetch_champs.py --구조 <기사주소>     # 기사 한 편의 구조를 본다
    python fetch_champs.py --전부 5000           # 색인을 통째로 훑어서 받는다
    python fetch_champs.py --목록 200            # 주소만 모아서 본다
    python fetch_champs.py --받기 <주소> [...]   # 받아서 data/samples.json 에 넣는다

## 왜 따로 있나

champs.pokedb.tokyo 는 **클라우드 IP 를 통째로 막는다.** robots.txt 까지 403 이다.
이 저장소가 도는 작업 환경(구글 클라우드)에서는 못 받는다. 집 회선에서는 열린다.
기기(아이패드/컴퓨터)나 와이파이와는 무관하고, **로컬 실행이냐 클라우드 실행이냐**
의 문제다.

## champs 는 기사를 갖고 있지 않다 — 색인일 뿐이다

집 회선에서 실제로 받아 보고 알게 된 것이다 (2026-09-18).

**champs 에는 기사 본문이 없다.** 목록의 카드마다 파티 6마리와 도구가
아이콘으로 박혀 있고, 본문 링크는 **외부 블로그로 나간다.** 60편을 세 보니
pokesol 17 · hatenablog 계열 26 · note 9 · 네이버 3 · 기타였다.
그래서 champs 안에는 기사 주소라는 것이 아예 없다 (`/article/search` 뿐이다).

여기서 얻을 수 있는 것이 둘로 갈린다.

  * **카드** — 이름·도구·테라스탈·순위·룰·트레이너가 구조적으로 박혀 있다.
    확실하지만 **기술·배분·성격·특성이 없다.**
    (그래서 카드만으로 만든 개체는 `samples.py` 의 `--맞추기`·`--쌍` 에
     기여를 못 하고 **동반 출현에만** 쓰인다.)
  * **외부 기사** — 기술·도구·성격·**배분이 글로 적혀 있다.**

    ! 이 줄은 한 번 틀리게 적혀 있었다. "배분은 거의 이미지다 / 노력치
      표기가 0건이었다" 고 써 뒀는데 **사실이 아니다.** 본문을 열어 보면
      대다수 기사가 숫자를 글로 적는다. 그때 못 찾은 이유는 정규식이
      **대시 주변 공백**과 **`x` 자리표시**를 안 받았기 때문이다.

          実数値(努力値)：205(32)-107-134(9)-x-132(15+)-97(10)
          メガ前：147(2)-162(32)-90- X -90- 156(32)
          177(32)-150(0)- 156(22) - x -112(12)-85
          基礎ポイント H16 A22 B2 S26

      H-A-B-C-D-S 순 6칸이고 괄호가 노력치다. 이 정규식이 위를 다 잡고
      날짜·레이팅 나열은 안 잡는다 (확인함).

          FIELD = r"(?:\d{1,3}\s*(?:[（(]\s*\d{1,2}\s*[+＋\-－]?\s*[）)])?|[xX×ｘ])"
          DASH  = r"\s*[-−ー–—]\s*"
          STATLINE = re.compile(FIELD + (DASH + FIELD) * 5)

      노력치가 괄호에 없어도 **실능만 있으면 역산된다.** calc.real_stat 이
      게임 화면과 6/6 일치 확인된 계산식이고 노력치는 0~32 뿐이라
      33개를 넣어 보면 된다 (왕복 시험 30/30). 성격을 모르면 25개를
      다 넣어 보고 6칸이 전부 맞는 것만 남긴다 — 하나로 안 좁혀지면
      그 개체는 배분을 비운다. `メガ前` 은 기본 폼, `メガ後` 는 메가 폼
      종족값으로 역산해야 한다. 합이 66 을 넘으면 버린다.

    다만 산문에서 **기술**을 줍는 것은 **해 봤지만 틀렸다** — 아래 (4) 참고.
    배분은 형식이 정해져 있어 되고, 기술은 안 된다. 둘을 구분할 것.

## 132편은 색인의 전부가 아니다

`--목록 200` 으로 돌려서 132편이 나왔는데, **그게 끝이 아니다.**
`collect_cards` 가 `?rule=0` **한 가지 필터만** 훑고, 한 쪽이 비면 바로
멈추게 돼 있었다. 그런데 받아 둔 132편에 룰이 **M-3·M-4·M-5**, 시즌이
**S4·S5** 로 섞여 있다. 즉 색인은 여러 룰·시즌을 담고 있고 `rule=0` 은
그중 하나를 고르는 값일 뿐이다.

그래서 셋을 고쳤다.

  * `--살펴보기` — 검색 페이지의 `select`·`option`·검색 링크·총 건수(`N件`)
    를 찍어 준다. **무엇으로 좁힐 수 있는지 모으기 전에 확인**하는 자리다.
  * `collect_cards` 가 한 쪽이 비었다고 바로 안 멈춘다 (세 쪽 연속 비어야
    끝으로 본다). 색인의 끝인지 일시적인 것인지 구분이 안 됐기 때문이다.
  * `--전부` / `collect_all` 이 `rule` 을 0부터 올려 가며 훑는다.
    몇 가지인지 모르므로 **세 번 연속 헛짚을 때까지** 올린다.
    `extra` 로 `&season=5` 처럼 다른 질의를 덧붙일 수도 있다
    (이름은 `--살펴보기` 로 먼저 확인할 것).

## champs 는 왜 pokesol 처럼 안 되나 — 사이트가 아니라 **글쓴이**가 갈랐다

"champs 기사도 링크를 따라가면 pokesol 처럼 샘플이 있을 텐데" 라는 물음에
직접 세 봤다. **갈림은 champs/pokesol 이 아니라 구조화 데이터/스크린샷이다.**

champs 가 가리키는 132편의 호스트를 세면 note.com 37 · pokesol 7 ·
yakkun 5 · 네이버 4 · 나머지는 하테나블로그 여럿으로 흩어진다.
하테나블로그·note 에는 팀빌더가 없으니 글쓴이가 스크린샷을 붙인다.

그런데 pokesol 로 나가는 7편조차 **6편이 카드 없는(스크린샷) 기사**였다.
pokesol 에 팀빌더가 있어도 **쓰는 사람만 쓴다.** (내가 사이트맵에서 받은
pokesol 기사도 약 17%는 카드가 없었다.)

그래서 champs 링크가 데이터를 덜 주는 것은 champs 탓이 아니고,
**높은 순위에 오른 사람들이 하테나블로그·note 를 즐겨 쓰기 때문**이다.

! 그 7편 중 카드가 있던 **1편을 실제로 놓쳤다.** pokesol 은 React 로 만든
  곳이라 HTML 안에 본문이 아예 없는데(주소 뒤 `.data` 를 붙여야 나온다)
  여기서 raw HTML 만 보고 있었다. `fetch_linked` 가 pokesol 주소는
  fetch_pokesol 으로 넘기도록 고쳤다 — 개체 6마리를 되살렸다.

## '질이 좋다' 는 두 가지 뜻이 섞였다

champs 기사를 3배로 보는 것은 **순위 검증** 때문이다 (132편 전부 순위가
붙어 있고, pokesol 사이트맵에서 온 기사는 28%만 순위가 있다).
**데이터 충실도는 반대다** — champs 카드는 이름·도구뿐이고, 구조화된 카드가
있는 쪽은 pokesol 이다. 두 축을 섞어 읽으면 안 된다.

그래서 카드로 파티를 잡고, 기사가 **구조화돼 있을 때만**(표·data-*)
기술을 주워 **이름으로 합친다**. 산문 기사는 카드 몫만 받는다.

## 배분이 없는 개체를 조용히 넣으면 안 된다

`forms.spread_class({})` 는 `"-"` 를 돌려준다. 이건 "무투자" 라는 **실재하는
형태**다. 배분을 못 읽은 개체를 그냥 넣으면 공격형이 전부 무투자로 분류돼
`samples.py --맞추기` 의 도구·메가 세기가 조용히 틀어진다.
그래서 배분을 못 읽은 개체는 `"evs": {}` 로 두고, samples.py 쪽에서
**맞추기에서만 빼고 기술 조합에는 쓴다** (`--쌍` 은 형태를 안 본다).

## 전략

`--구조` 로 한 편을 받아 보면 **무엇을 어떻게 파싱해야 하는지 찍어 준다.**
그걸 보고 `STRATEGIES` 에 전략을 넣는다. 지금 셋이 들어 있다.
  1. `data-*` 속성에 박힌 구조화 데이터 (pokesol 이 이 방식이었다)
  2. champs 카드 한 장 (카드만 따로 넘겼을 때)
  3. 표(table) — 포켓몬 한 줄에 기술·도구·배분
  4. 그냥 글 — **짜 봤다가 뺐다.** 왜 뺐는지는 STRATEGIES 바로 위에 적어 뒀다.

## 넣는 형식

`samples.py` 가 읽는 것과 같다. **`"source": "champs"` 가 들어간다** —
그게 있어야 표본 값어치를 3배로 본다 (samples.SOURCE_WEIGHT).
이름은 일본어 그대로 넣으면 된다.
"""

import gzip
import io as _io
import json
import os
import re
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "data", "samples.json")
BASE = "https://champs.pokedb.tokyo"

UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/125.0 Safari/537.36")
DELAY = 2.0

EV_KEYS = ("H", "A", "B", "C", "D", "S")


def get(url):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA, "Accept-Encoding": "gzip",
        "Accept-Language": "ja,en;q=0.8"})
    with urllib.request.urlopen(req, timeout=90) as r:
        raw = r.read()
        if (r.headers.get("Content-Encoding") or "").lower() == "gzip":
            raw = gzip.GzipFile(fileobj=_io.BytesIO(raw)).read()
    return raw.decode("utf-8", "replace")


# ---------------------------------------------------------------------------
# 1. 구조 보기 — 파싱을 채우기 전에 먼저 이걸 돌린다
# ---------------------------------------------------------------------------
def show_structure(url):
    """기사 한 편을 받아서 **무엇으로 파싱할 수 있는지** 찍어 준다."""
    html = get(url)
    path = os.path.join(HERE, "raw", "champs_sample.html")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)

    print("=" * 74)
    print("  champs 기사 구조 보기")
    print("=" * 74)
    print("  주소: %s" % url)
    print("  받은 크기: %d bytes  ->  %s 에 저장" % (len(html), path))
    print("-" * 74)

    # (1) data-* 속성
    attrs = {}
    for a in re.findall(r'(data-[a-z0-9-]+)=', html):
        attrs[a] = attrs.get(a, 0) + 1
    hot = sorted(attrs.items(), key=lambda x: -x[1])[:12]
    print("  [1] data-* 속성 %d종" % len(attrs))
    for a, c in hot:
        print("        %-28s %d회" % (a, c))
    if not attrs:
        print("        없음")

    # (2) 표
    tables = re.findall(r"<table[^>]*>(.*?)</table>", html, re.S)
    print("  [2] 표 %d개" % len(tables))
    for t in tables[:2]:
        rows = re.findall(r"<tr[^>]*>(.*?)</tr>", t, re.S)
        print("        %d줄, 첫 줄: %s"
              % (len(rows), _text(rows[0])[:60] if rows else ""))

    # (3) 페이지 안에 JSON 이 통째로 들어 있나
    for key in ("__NEXT_DATA__", "__NUXT__", "window.__", "application/json",
                "self.__next_f"):
        n = len(re.findall(re.escape(key), html))
        if n:
            print("  [3] %s %d회 — 페이지에 JSON 이 박혀 있을 수 있다" % (key, n))

    # (4) 일본어 포켓몬 이름이 몇 개나 보이나
    names = _known_names()
    found = [(n, html.count(n)) for n in names if n in html]
    found.sort(key=lambda x: -x[1])
    print("  [4] 아는 포켓몬 이름 %d종이 본문에 보인다" % len(found))
    for n, c in found[:8]:
        print("        %-14s %d회" % (n, c))

    # (5) 첫 포켓몬 이름 주변을 그대로 보여 준다 — 여기에 답이 있다
    if found:
        i = html.find(found[0][0])
        chunk = html[max(0, i - 900):i + 900]
        print("-" * 74)
        print("  [5] '%s' 주변 (여기 모양을 보고 파서를 쓴다)" % found[0][0])
        print(chunk.replace("><", ">\n<")[:2400])
    print("=" * 74)
    print("  다음: 위 [5] 모양을 보고 parse_article 의 전략 하나를 채운다.")
    print("  (이 파일 맨 아래 STRATEGIES 에 자리를 만들어 뒀다)")
    return html


def _text(fragment):
    t = re.sub(r"<[^>]+>", " ", fragment or "")
    return " ".join(t.split())


def _katakana(text):
    """가타카나가 섞인 이름인가.

    일본어 **포켓몬 이름은 가타카나**로 쓴다 (ガブリアス). 반면 폼 이름은
    히라가나인 것이 있다 (あおいはな = 푸른꽃, あまみずのすがた = 빗물의 모습).
    이름표에는 둘이 같이 들어 있어서, 안 거르면 기사 본문의 평범한 히라가나가
    포켓몬 이름으로 잘못 잡힌다. 표를 읽을 때 특히 위험하다.
    """
    return any(0x30A1 <= ord(c) <= 0x30FA for c in text or "")


def _known_names():
    p = os.path.join(HERE, "data", "names_ja.json")
    if not os.path.exists(p):
        return []
    with open(p, encoding="utf-8") as f:
        table = json.load(f).get("pokemon") or {}
    names = [n for n in table if len(n) >= 3 and _katakana(n)]
    # 긴 이름부터 본다 — 'メガボーマンダ' 를 'ボーマンダ' 로 잘못 잡지 않도록
    names.sort(key=lambda n: -len(n))
    return names


# ---------------------------------------------------------------------------
# 2. 주소 모으기
# ---------------------------------------------------------------------------
# 카드 한 장이 기사 한 편이다. 카드 안에 파티가 통째로 들어 있고,
# 푸터의 링크만 바깥(블로그)으로 나간다.
_CARD_RE = re.compile(r'<article[^>]*class="[^"]*article-card[^"]*"[^>]*>(.*?)</article>',
                      re.S)


def _icon_title(chunk, kind):
    """`<i class="... poke-icon ..." title="ガブリアス">` 에서 title 을 꺼낸다.

    class 와 title 사이에 줄바꿈이 들어 있어서 `\\s*` 가 꼭 필요하다.
    """
    m = re.search(r'<i[^>]*class="[^"]*%s[^"]*"\s*title="([^"]*)"' % kind, chunk)
    return m.group(1) if m else None


def _card_members(card):
    """카드 한 장에서 6마리를 꺼낸다. 이름과 도구는 확실하고, 나머지는 없다."""
    m = re.search(r'article-card-pokemons"[^>]*>(.*)$', card, re.S)
    blob = m.group(1) if m else card
    out = []
    for chunk in re.split(r'<div[^>]*class="article-card-pokemon"[^>]*>', blob)[1:]:
        name = _icon_title(chunk, "poke-icon")
        if not name:
            continue
        out.append({
            "name": name,
            "item": _icon_title(chunk, "item-icon"),
            "tera": _icon_title(chunk, "terastal-icon"),
            "ability": None, "nature": None,
            "evs": {}, "moves": [],
        })
    return out


def parse_card(card):
    """카드 한 장 -> 파티 하나. 본문 주소는 바깥 블로그를 가리킨다."""
    tag = re.search(r'<span[^>]*class="tag[^"]*"[^>]*>([^<]*)</span>', card)
    label = _text(tag.group(1)) if tag else ""
    season, _, rule = title_info(label)
    rank = re.search(r"<span>\s*(\d{1,5})\s*位\s*</span>", card)
    who = re.search(r'<p[^>]*class="title[^"]*"[^>]*>([^<]*)</p>', card)
    foot = re.search(r'<footer[^>]*class="card-footer"[^>]*>\s*<a[^>]*href="([^"]+)"',
                     card)
    title = re.search(r'card-footer.*?<span>(.*?)</span>', card, re.S)
    return {
        "url": foot.group(1) if foot else None,
        "title": _text(title.group(1)) if title else "",
        "season": season, "rule": rule,
        "rank": int(rank.group(1)) if rank else None,
        "trainer": _text(who.group(1)) if who else None,
        "members": _card_members(card),
    }


# 검색 페이지에 총 건수가 찍혀 있을 수 있다. 일본 사이트는 보통 'N件' 이다.
# 먼저 이걸 읽으면 **몇 편을 받아야 하는지 모으기 전에 안다.**
_TOTAL = re.compile(r"([\d,]{1,9})\s*(?:件|本|記事)")


def probe_search(rule=0, save=True):
    """검색 페이지를 한 번 받아서 **무엇으로 좁힐 수 있는지** 찍어 준다.

    앞서 `?rule=0` 하나만 훑어서 132편에서 멈췄다. 그런데 받아 놓은 자료에
    룰이 M-3·M-4·M-5, 시즌이 S4·S5 로 섞여 있다. 즉 **rule=0 은 여러 필터
    중 하나**이고, 색인에는 훨씬 많이 있다는 뜻이다. 그 필터를 찾는 자리다.
    """
    url = "%s/article/search?rule=%d" % (BASE, rule)
    html = get(url)
    if save:
        path = os.path.join(HERE, "raw", "champs_search.html")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(html)
    print("=" * 74)
    print("  champs 검색 페이지 살펴보기  (%s)" % url)
    print("=" * 74)
    cards = _CARD_RE.findall(html)
    print("  카드 %d장 · 받은 크기 %d bytes" % (len(cards), len(html)))
    got = _TOTAL.findall(html)
    if got:
        print("  ! 총 건수로 보이는 숫자: %s" % ", ".join(got[:6]))
        print("    -> 이게 색인 전체 편수라면 그만큼 받아야 한다.")
    else:
        print("  총 건수 표기를 못 찾았다. 마지막 쪽 번호로 대신 세야 한다.")

    print("-" * 74)
    print("  [좁히는 데 쓸 수 있는 것들]")
    for name, pat in (
            ("select 이름", r'<select[^>]*name="([^"]+)"'),
            ("select 값", r'<option[^>]*value="([^"]*)"[^>]*>([^<]{1,22})'),
            ("검색 링크", r'href="(/article/search\?[^"]+)"'),
            ("input 이름", r'<input[^>]*name="([^"]+)"'),
    ):
        hits = re.findall(pat, html)
        if not hits:
            continue
        flat = []
        for h in hits[:24]:
            flat.append(" ".join(h) if isinstance(h, tuple) else h)
        print("    %-12s %s" % (name, " | ".join(flat[:12])))
    print("-" * 74)
    print("  마지막 쪽으로 보이는 번호: %s"
          % (sorted(set(int(x) for x in re.findall(r"[?&]page=(\d+)", html)))
             [-6:] or "없음"))
    print("=" * 74)
    print("  다음: 위 [좁히는 데 쓸 수 있는 것들] 을 보고 rule 값이 몇 가지인지,")
    print("  시즌·룰 파라미터가 따로 있는지 확인한 뒤 collect_cards 를 그 값마다")
    print("  돌려라. `--전부` 가 rule 을 0..N 까지 훑는다.")
    return html


def collect_cards(limit=200, rule=0, extra="", quiet=False):
    """목록 페이지를 넘겨 가며 카드를 모은다. 한 쪽에 30편이다.

    사이트맵은 안 본다 — champs 의 `<loc>` 에 걸리는 article 주소는
    `/article/search` 뿐이라 기사가 아니다. robots.txt 도 403 이다.

    extra 에 `&season=5` 처럼 덧붙일 질의를 줄 수 있다. 어떤 이름을 쓰는지는
    `probe_search` 로 먼저 확인할 것.

    ! 한 쪽이 비었다고 바로 멈추지 않는다. 앞서 132편에서 끊겼는데 그게
      색인의 끝인지 일시적인 것인지 구분이 안 됐다. 두 쪽까지 더 보고 판단한다.
    """
    seen, out = set(), []
    empty = 0
    for page in range(1, 200):
        try:
            html = get("%s/article/search?rule=%d&page=%d%s"
                       % (BASE, rule, page, extra))
        except Exception as e:
            print("  목록 %d쪽 실패: %s" % (page, e))
            break
        cards = [parse_card(c) for c in _CARD_RE.findall(html)]
        fresh = [c for c in cards if c["url"] and c["url"] not in seen]
        for c in cards:
            if c["url"]:
                seen.add(c["url"])
        if not fresh:
            empty += 1
            if empty >= 3:      # 세 쪽 연속 새것이 없으면 끝으로 본다
                if not quiet:
                    print("  목록 %d쪽 — 세 쪽 연속 새것이 없다. 끝으로 본다."
                          % page)
                break
            time.sleep(DELAY)
            continue
        empty = 0
        out += fresh
        if not quiet and (page <= 3 or page % 5 == 0):
            print("  목록 %d쪽 — 새 기사 %d편 (누적 %d)"
                  % (page, len(fresh), len(out)))
        if len(out) >= limit:
            if not quiet:
                print("  limit %d 에 닿아서 멈춘다 (더 있을 수 있다)" % limit)
            break
        time.sleep(DELAY)
    return out[:limit]


def collect_all(limit=5000, rules=None, extras=None):
    """rule(그리고 덧붙일 질의)을 바꿔 가며 **색인을 통째로** 훑는다.

    `rule=0` 하나만 보면 132편에서 끊겼다. 받아 둔 자료에 룰이 M-3~M-5,
    시즌이 S4~S5 로 섞여 있으니 색인에는 더 있다는 뜻이다.
    몇 가지인지 모르므로 **빈 결과가 세 번 연속 나올 때까지** 올려 본다.
    """
    rules = rules if rules is not None else range(0, 12)
    extras = extras or [""]
    seen, out = set(), []
    miss = 0
    for rule in rules:
        hit = 0
        for extra in extras:
            got = collect_cards(limit=limit, rule=rule, extra=extra, quiet=True)
            fresh = [c for c in got if c["url"] and c["url"] not in seen]
            for c in got:
                if c["url"]:
                    seen.add(c["url"])
            out += fresh
            hit += len(fresh)
        print("  rule=%-2s  새 기사 %4d편 (누적 %d)" % (rule, hit, len(out)))
        miss = miss + 1 if hit == 0 else 0
        if miss >= 3:
            print("  rule 을 세 번 연속 헛짚었다. 여기서 멈춘다.")
            break
        if len(out) >= limit:
            break
    return out[:limit]


def list_urls(limit=200):
    """기사 주소를 모은다. **바깥 블로그 주소가 나온다** — champs 것이 아니다."""
    return [c["url"] for c in collect_cards(limit) if c["url"]]


# ---------------------------------------------------------------------------
# 3. 파싱 — **여기만 비어 있다**
# ---------------------------------------------------------------------------
def _evs_from(text):
    """'H252 B156 D100' 같은 표기를 dict 로. 챔피언스는 한 칸 최대 32 다."""
    out = {}
    for k, v in re.findall(r"([HABCDS])\s*[:：]?\s*(\d{1,3})", text or ""):
        n = int(v)
        if k in EV_KEYS and 0 < n <= 32:
            out[k] = n
    return out


def strategy_data_attrs(html):
    """(1) data-* 속성에 박힌 구조화 데이터. pokesol 이 이 방식이었다."""
    members = []
    for tag in re.findall(r'<[a-z]+[^>]*data-pokemon[^>]*>', html):
        got = dict(re.findall(r'(data-[a-z0-9-]+)="([^"]*)"', tag))
        name = (got.get("data-pokemon-name") or got.get("data-pokemon")
                or got.get("data-name"))
        if not name or name.isdigit():
            continue
        members.append({
            "name": name,
            "item": got.get("data-item") or got.get("data-item-name"),
            "ability": got.get("data-ability") or got.get("data-ability-name"),
            "nature": got.get("data-nature") or got.get("data-nature-name"),
            "evs": _evs_from(got.get("data-evs") or got.get("data-ev") or ""),
            "moves": [x for x in re.split(r"[,/|]",
                                          got.get("data-moves") or "") if x],
        })
    return members


def strategy_tables(html):
    """(2) 표. 포켓몬 한 줄에 기술·도구·배분이 들어 있는 형태."""
    names = set(_known_names())
    members = []
    for table in re.findall(r"<table[^>]*>(.*?)</table>", html, re.S):
        for row in re.findall(r"<tr[^>]*>(.*?)</tr>", table, re.S):
            cells = [_text(c) for c in
                     re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, re.S)]
            if not cells:
                continue
            name = next((c for c in cells if c in names), None)
            if not name:
                continue
            blob = " ".join(cells)
            members.append({
                "name": name,
                "item": None, "ability": None, "nature": None,
                "evs": _evs_from(blob),
                "moves": [],
            })
    return members


def strategy_champs_card(html):
    """(2) champs 카드 한 장. 기사 본문이 아니라 목록의 카드다.

    카드가 딱 한 장일 때만 쓴다. 목록 페이지를 통째로 넘기면 서른 파티가
    한 덩어리로 섞이므로, 그쪽은 `collect_cards` 가 따로 맡는다.
    """
    cards = _CARD_RE.findall(html)
    if len(cards) != 1:
        return []
    return _card_members(cards[0])


# ---------------------------------------------------------------------------
# (4) 그냥 글 — **짜 봤다가 뺐다.** 기록으로 남긴다
# ---------------------------------------------------------------------------
#
# 외부 기사의 다수(hatenablog 계열 26/60)가 이 형태다. 그래서 이름 뒤 창을
# 훑어 기술을 줍는 전략을 짜서 돌려 봤는데, **그럴듯한데 틀린 값**이 나왔다.
# 한 편(reboiona, M-5 최종2위)을 손으로 대조한 결과다.
#
#   * 개체 구획은 있다. `・メガルカリオ` 처럼 가운뎃점 제목으로 나뉜다.
#     그런데 항목 표지(技構成·持ち物·性格·努力値)는 **한 개도 없다.**
#   * 구획을 정확히 잘라도 기술이 어긋난다 —
#       ・メガルカリオ  -> 인파이트/코메트펀치/칼춤/신속        (맞음)
#       ・ガブリアス    -> 본문이 **예전 구성과 최종 구성을 둘 다** 서술한다.
#                          앞에서 4개를 집으면 버린 구성을 집는다.
#       ・メガリザードンY -> 구획 안에 **상대 가브리아스의 기술**
#                          (바위사태·스톤에지…)이 먼저 나온다.
#   * 구획을 안 나누면 더 나쁘다. 구축경위에 적힌 가상적(메타그로스·플라엣테·
#     님피아)이 파티원으로 잡히고 셋이 같은 기술 4개를 나눠 가졌다.
#
# 기술 조합(samples.move_pairs)은 "어떤 기술끼리 같이 다니는가"를 세는 것이
# 전부다. 틀린 기술을 섞으면 그 표가 존재 이유를 잃는다. **없는 것이 낫다.**
# 그래서 산문 기사에서는 카드가 주는 것(이름·도구·순위)만 받는다.
# 이 파일 맨 위 설명에 적힌 "3. 그냥 글 — 자동은 못 한다" 가 맞았다.
#
# 다시 해 볼 사람에게: 구획 제목(`・`, `【】`, `◆`)으로 자르는 것까지는 된다.
# 막히는 곳은 **한 구획 안에서 자기 기술과 남의 기술을 가르는 것**이다.

# 되는 순서대로 시도한다. 새 전략을 쓰면 여기 넣으면 된다.
STRATEGIES = [
    ("data-* 속성", strategy_data_attrs),
    ("champs 카드", strategy_champs_card),
    ("표", strategy_tables),
]


def parse_article(html, url=None):
    """기사 하나에서 파티를 꺼낸다. 되는 전략을 찾아 쓴다."""
    title = ""
    m = re.search(r"<title[^>]*>(.*?)</title>", html, re.S)
    if m:
        title = _text(m.group(1))

    used, members = None, []
    for label, fn in STRATEGIES:
        try:
            got = fn(html)
        except Exception:
            continue
        if len(got) >= 3:          # 파티는 보통 6마리다
            used, members = label, got
            break

    season, rank, rule = title_info(title)
    return {"source": "champs", "url": url, "title": title,
            "season": season, "rule": rule, "rank": rank,
            "publishedAt": _published(html),
            "parsedBy": used, "members": members}


_SEASON = re.compile(r"(?:^|[^A-Za-z])(?:S|Ｓ|シーズン|シ-ズン)\s*(\d{1,2})")
_RULE = re.compile(r"(M\s*-\s*[0-9A-Za-z])")
_RANK = re.compile(r"最終\s*(?:順位)?\s*(\d{1,5})\s*位")


def title_info(title):
    head = (title or "").replace("Ｍ", "M")
    s, r, u = _SEASON.search(head), _RANK.search(head), _RULE.search(head)
    return (int(s.group(1)) if s else None,
            int(r.group(1)) if r else None,
            u.group(1).replace(" ", "") if u else None)


def _published(html):
    m = (re.search(r'"datePublished"\s*:\s*"([^"]+)"', html)
         or re.search(r'<time[^>]*datetime="([^"]+)"', html))
    return m.group(1) if m else None


# ---------------------------------------------------------------------------
# 4. 저장 — samples.py 가 읽는 형식 그대로
# ---------------------------------------------------------------------------
def load_out():
    if os.path.exists(OUT):
        with open(OUT, encoding="utf-8") as f:
            return json.load(f)
    return {"parties": []}


def save_out(doc):
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=1)


def _norm(text):
    """전각/반각을 맞춘다. 게임 파일은 'メガリザードンＹ', 기사는 'Y' 를 쓴다."""
    out = []
    for ch in text or "":
        o = ord(ch)
        if 0xFF01 <= o <= 0xFF5E:
            ch = chr(o - 0xFEE0)
        elif ch == "　":
            ch = " "
        out.append(ch)
    return "".join(out).replace(" ", "").lower()


def merge_card(party, card):
    """카드(이름·도구·순위)와 기사(기술·성격)를 **이름으로 합친다.**

    카드 쪽이 파티 명단의 기준이다 — 아이콘이라 틀릴 일이 없다. 파티는
    여섯이고 카드에 여섯이 다 있다. 기사에서 주운 기술·성격·특성·배분을
    그 위에 얹는다.

    **기사에만 있고 카드에 없는 이름은 파티에 넣지 않는다.** 구축경위에
    적힌 가상적이 파티원으로 섞여 들어와 파티가 열한 마리가 되는 일이
    있었다. 대신 버렸다는 사실을 `offRoster` 에 남긴다 — 폼 표기가
    어긋나서 못 이은 것인지 남의 포켓몬인지 나중에 봐야 하기 때문이다.
    """
    got = {}
    for m in (party or {}).get("members") or []:
        got.setdefault(_norm(m.get("name")), m)

    members = []
    for base in card["members"]:
        m = dict(base)
        art = got.pop(_norm(base["name"]), None)
        if art:
            m["moves"] = art.get("moves") or []
            m["nature"] = art.get("nature") or m.get("nature")
            m["ability"] = art.get("ability") or m.get("ability")
            m["evs"] = art.get("evs") or {}
            m["item"] = m.get("item") or art.get("item")
        members.append(m)
    off = [m.get("name") for m in got.values() if m.get("name")]

    title = (party or {}).get("title") or card["title"]
    season, rank, rule = title_info(title)
    return {
        "source": "champs",
        "url": card["url"],
        "title": card["title"] or title,
        "season": card["season"] or season,
        "rule": card["rule"] or rule,
        "rank": card["rank"] or rank,
        "trainer": card.get("trainer"),
        "publishedAt": (party or {}).get("publishedAt"),
        "parsedBy": "카드+%s" % ((party or {}).get("parsedBy") or "본문없음"),
        "offRoster": off,
        "members": members,
    }


def fetch_linked(url):
    """champs 카드가 가리키는 **외부 기사**를 받아서 파싱한다.

    pokesol 은 따로 다뤄야 한다. React 로 만든 곳이라 **HTML 안에 본문이
    아예 없다** — 주소 뒤에 `.data` 를 붙여야 나온다. 여기서 raw HTML 만
    보다가 champs 가 가리킨 pokesol 기사 7편 중 카드가 있던 1편을 놓쳤다.
    그쪽은 fetch_pokesol 이 이미 할 줄 아니 그대로 넘긴다.
    """
    if "pokesol." in url:
        try:
            import fetch_pokesol
            got = fetch_pokesol.fetch_one(url)
            if got.get("members"):
                got["source"] = "champs"      # champs 색인에서 온 것임을 남긴다
                return got
        except Exception:
            pass
    return parse_article(get(url), url)


def fetch_all(urls, cards=None):
    doc = load_out()
    have = set((p.get("url") or "").rstrip("/") for p in doc["parties"])
    index = dict((c["url"].rstrip("/"), c) for c in (cards or []) if c["url"])
    added = empty = 0
    how = {}
    for n, u in enumerate(urls):
        if u.rstrip("/") in have:
            continue
        if n:
            time.sleep(DELAY)
        card = index.get(u.rstrip("/"))
        try:
            party = fetch_linked(u)
        except Exception as e:
            # 본문을 못 받아도 카드가 있으면 명단과 도구는 건진다.
            print("  본문 실패: %s — %s" % (u, e))
            party = None
            if not card:
                continue
        if card:
            party = merge_card(party, card)
        if not party or not party["members"]:
            empty += 1
            continue
        how[party["parsedBy"]] = how.get(party["parsedBy"], 0) + 1
        doc["parties"].append(party)
        added += 1
        if added % 20 == 0 or added < 4:
            print("  %d편째: 시즌%s %s %s위  %d마리  %s"
                  % (added, party["season"], party.get("rule") or "-",
                     party["rank"], len(party["members"]),
                     (party["title"] or "")[:30]))
        if added % 10 == 0:
            save_out(doc)
    save_out(doc)
    print("\ndata/samples.json — 파티 %d개 (이번에 %d개 추가, 못 읽은 기사 %d개)"
          % (len(doc["parties"]), added, empty))
    if how:
        print("  쓴 전략: " + ", ".join("%s %d편" % (k, v) for k, v in how.items()))

    # 배분과 기술이 얼마나 채워졌는지 **반드시 같이 알린다.** 카드만으로도
    # 개체는 만들어지므로, 숫자만 보면 다 받은 것처럼 착각하기 쉽다.
    mem = [m for p in doc["parties"] for m in p["members"]]
    if mem:
        ev = sum(1 for m in mem if m.get("evs"))
        mv = sum(1 for m in mem if m.get("moves"))
        print("  개체 %d마리 — 기술 있음 %d (%.0f%%), 배분 있음 %d (%.0f%%)"
              % (len(mem), mv, mv * 100.0 / len(mem), ev, ev * 100.0 / len(mem)))
        if ev * 2 < len(mem):
            print("  ! 배분이 없는 개체가 많다. 구축기사는 배분을 이미지로 올린다.")
            print("    samples.py 는 배분 없는 개체를 --맞추기 에서 빼고")
            print("    --쌍(기술 조합) 에만 쓴다. 조용히 무투자로 세지 않는다.")
    if empty and not added:
        print("\n  ! 한 편도 못 읽었다. `--구조 <기사주소>` 로 모양을 먼저 보고")
        print("    STRATEGIES 에 전략을 하나 더 넣어야 한다.")
    print("\n  확인: python samples.py        (못 알아들은 이름을 다 찍어 준다)")
    print("        python samples.py --맞추기")


def main():
    args = sys.argv[1:]
    if "--구조" in args:
        i = args.index("--구조")
        show_structure(args[i + 1])
        return
    if "--살펴보기" in args:
        i = args.index("--살펴보기")
        rule = int(args[i + 1]) if i + 1 < len(args) and args[i + 1].isdigit() else 0
        probe_search(rule)
        return
    if "--전부" in args:
        i = args.index("--전부")
        want = int(args[i + 1]) if i + 1 < len(args) and args[i + 1].isdigit() else 5000
        cards = collect_all(limit=want)
        print("\n색인에서 기사 %d편을 찾았다." % len(cards))
        fetch_all([c["url"] for c in cards if c["url"]], cards)
        return
    if "--목록" in args:
        i = args.index("--목록")
        want = int(args[i + 1]) if i + 1 < len(args) else 200
        urls = list_urls(want)
        print("\n".join(urls))
        print("\n기사 %d편. 받으려면: python fetch_champs.py --받기 <주소들>"
              % len(urls))
        return
    if "--받기" in args:
        i = args.index("--받기")
        urls = [a for a in args[i + 1:] if a.startswith("http")]
        cards = None
        if not urls:
            # 주소를 안 주면 목록부터 본다. 이때 카드도 같이 쥐고 있어야
            # 도구·순위를 잃지 않는다 — 기사 본문에는 그게 없을 때가 많다.
            cards = collect_cards(200)
            urls = [c["url"] for c in cards if c["url"]]
        fetch_all(urls, cards)
        return
    print(__doc__)


if __name__ == "__main__":
    main()
