# -*- coding: utf-8 -*-
"""
champs.pokedb.tokyo 구축기사 수집기 — **집 회선에서 돌리는 용도**.

    python fetch_champs.py --구조 <기사주소>     # 먼저 이걸로 구조를 본다
    python fetch_champs.py --목록 200            # 기사 주소를 모은다
    python fetch_champs.py --받기 <주소> [...]   # 받아서 data/samples.json 에 넣는다

## 왜 따로 있나

champs.pokedb.tokyo 는 **클라우드 IP 를 통째로 막는다.** robots.txt 까지 403 이다.
이 저장소가 도는 작업 환경(구글 클라우드)에서는 못 받는다. 집 회선에서는 열린다.
기기(아이패드/컴퓨터)나 와이파이와는 무관하고, **로컬 실행이냐 클라우드 실행이냐**
의 문제다.

## 그래서 이 파일은 반만 완성돼 있다

**HTML 구조를 못 봐서 파싱만 비어 있다.** 나머지는 다 돼 있다 —
주소 모으기, 일본어→한국어 잇기, 중복 거르기, 요청 간격, 중간 저장,
게시일 채우기, `samples.json` 형식 맞추기.

`--구조` 로 한 편을 받아 보면 **무엇을 어떻게 파싱해야 하는지 찍어 준다.**
그걸 보고 `parse_article` 안의 전략 하나만 채우면 된다.

일본 구축기사는 보통 셋 중 하나다. 셋 다 시도해 보고 되는 것을 쓴다.
  1. `data-*` 속성에 박힌 구조화 데이터 (pokesol 이 이 방식이었다)
  2. 표(table) — 포켓몬 한 줄에 기술·도구·배분
  3. 그냥 글 — 이러면 자동은 못 하고 사람이 봐야 한다

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


def _known_names():
    p = os.path.join(HERE, "data", "names_ja.json")
    if not os.path.exists(p):
        return []
    with open(p, encoding="utf-8") as f:
        return list((json.load(f).get("pokemon") or {}).keys())


# ---------------------------------------------------------------------------
# 2. 주소 모으기
# ---------------------------------------------------------------------------
def list_urls(limit=200):
    """기사 주소를 모은다. 사이트맵이 있으면 그쪽, 없으면 목록 페이지."""
    for path in ("/sitemap.xml", "/api/sitemap.xml", "/robots.txt"):
        try:
            body = get(BASE + path)
        except Exception:
            continue
        if path.endswith("robots.txt"):
            m = re.search(r"Sitemap:\s*(\S+)", body, re.I)
            if m:
                try:
                    body = get(m.group(1))
                except Exception:
                    continue
            else:
                continue
        urls = re.findall(r"<loc>([^<]*article[^<]*)</loc>", body)
        if urls:
            print("  사이트맵에서 기사 %d편" % len(urls))
            return urls[:limit]

    # 목록 페이지를 넘겨 가며 모은다
    seen, out = set(), []
    for page in range(1, 40):
        try:
            html = get("%s/article/search?rule=0&page=%d" % (BASE, page))
        except Exception as e:
            print("  목록 %d쪽 실패: %s" % (page, e))
            break
        got = re.findall(r'href="(/article/[^"?#]+)"', html)
        fresh = [BASE + u for u in got if u not in seen]
        for u in got:
            seen.add(u)
        if not fresh:
            break
        out += fresh
        print("  목록 %d쪽 — 기사 %d편 (누적 %d)" % (page, len(fresh), len(out)))
        if len(out) >= limit:
            break
        time.sleep(DELAY)
    return out[:limit]


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


# 되는 순서대로 시도한다. 새 전략을 쓰면 여기 넣으면 된다.
STRATEGIES = [
    ("data-* 속성", strategy_data_attrs),
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


def fetch_all(urls):
    doc = load_out()
    have = set((p.get("url") or "").rstrip("/") for p in doc["parties"])
    added = empty = 0
    how = {}
    for n, u in enumerate(urls):
        if u.rstrip("/") in have:
            continue
        if n:
            time.sleep(DELAY)
        try:
            party = parse_article(get(u), u)
        except Exception as e:
            print("  실패: %s — %s" % (u, e))
            continue
        if not party["members"]:
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
        if not urls:
            urls = list_urls(200)
        fetch_all(urls)
        return
    print(__doc__)


if __name__ == "__main__":
    main()
