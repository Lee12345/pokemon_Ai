# -*- coding: utf-8 -*-
"""
구축기사에서 파티를 꺼내 온다 (pokesol.app 전용).

    python fetch_pokesol.py <기사주소> [<기사주소> ...]
    python fetch_pokesol.py --파일 urls.txt

## 왜 pokesol 만 되는가

일본 구축기사는 대부분 **하테나블로그에 이미지로** 올린다. 본문에는
"H:8n-1", "S:ビビヨン抜き" 같은 **설명**만 있고 실제 배분 숫자는 스크린샷 안에 있다.
그건 글자로 긁을 수가 없다.

그런데 pokesol.app(ポケノート)은 파티 작성 전용 사이트라, 본문 HTML 안에
**기계가 읽을 수 있는 카드**가 그대로 박혀 있다.

    <div data-type="pokemon-card" data-pokemon-id="823" data-nature-id="6"
         data-ability-ids="[46]" data-item-id="59" data-move-ids="[413,339,164,355]"
         data-evs="{hp:32, attack:0, defense:25, specialAttack:0,
                    specialDefense:7, speed:2}">

노력치가 **정확한 숫자**로 들어 있다 (합 66). 사람이 옮겨 적을 필요가 없다.

## 어떻게 꺼내는가

본문은 서버에서 바로 안 오고 React Router 의 데이터 경로로 온다.
주소 뒤에 `.data` 를 붙이면 turbo-stream 형식으로 오는데, 이건 **값을 납작하게
펴 놓고 번호로 서로 가리키는** 형식이라 그대로는 못 읽는다. 풀어서 읽는다.

같은 응답에 이름표(masterData)도 들어 있어서 번호 -> 일본어 이름이 바로 된다.
거기서 우리 한국어 이름으로 잇는다 (`build_names.py` 가 만든 표).

## 주의

pokesol 의 이름표는 **본편까지 포함**한다 (기술 829개, 도구 328개 — 챔피언스는
512개, 166개). 그래서 챔피언스에 없는 이름이 섞여 나올 수 있고,
그건 samples.py 가 "못 알아들은 이름" 으로 보고한다. 조용히 안 버린다.
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
NAMES = os.path.join(HERE, "data", "names_ja.json")

UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/125.0 Safari/537.36")
DELAY = 2.0          # 사이트에 부담 안 가게 한 편마다 쉰다

# pokesol 의 노력치 키 -> 우리 표기
EV_KEY = {"hp": "H", "attack": "A", "defense": "B",
          "specialAttack": "C", "specialDefense": "D", "speed": "S"}


SITEMAP = "https://pokesol.app/api/sitemap.xml"


def get(url):
    """gzip 을 켜서 받는다. 남의 서버 대역폭을 5배 덜 쓴다."""
    req = urllib.request.Request(url, headers={
        "User-Agent": UA, "Accept-Encoding": "gzip"})
    with urllib.request.urlopen(req, timeout=90) as r:
        raw = r.read()
        if (r.headers.get("Content-Encoding") or "").lower() == "gzip":
            raw = gzip.GzipFile(fileobj=_io.BytesIO(raw)).read()
    return raw.decode("utf-8")


def sitemap_urls(limit=None):
    """사이트맵에서 기사 주소를 최신순으로.

    robots.txt 가 기사 페이지를 허용하면서 **사이트맵을 안내**한다.
    목록 페이지를 긁는 것보다 이쪽이 사이트가 의도한 방법이다.
    """
    xml = get(SITEMAP)
    rows = []
    for block in re.findall(r"<url>(.*?)</url>", xml, re.S):
        loc = re.search(r"<loc>([^<]+)</loc>", block)
        if not loc or "/articles/" not in loc.group(1):
            continue
        mod = re.search(r"<lastmod>([^<]+)</lastmod>", block)
        rows.append((mod.group(1) if mod else "", loc.group(1)))
    rows.sort(reverse=True)          # 최신 기사부터 — 시즌이 가까울수록 좋다
    urls = [u for _, u in rows]
    return urls[:limit] if limit else urls


def unflatten(flat):
    """turbo-stream 을 푼다.

    납작한 배열에 값이 다 들어 있고, 객체는 {"_7": 8} 처럼 **번호로** 서로를
    가리킨다 (7번 자리의 문자열이 키, 8번 자리가 값). 음수는 특수값이다.

    배열 중에는 **머리에 글자가 붙은 것**이 섞여 있다. 그게 진짜 목록이 아니라
    자료형 표시다 — 이걸 번호로 착각하면 통째로 터진다.

        ["M", 키번호, 값번호, ...]   Map
        ["D", 1789554238536]          Date (번호가 아니라 그냥 밀리초다)
        ["S", ...]                    Set
    """
    def res(i, depth=0):
        if isinstance(i, int) and i < 0:
            return None
        if not isinstance(i, int) or i >= len(flat):
            return None
        if depth > 18:
            return None
        v = flat[i]
        if isinstance(v, dict):
            out = {}
            for k, vi in v.items():
                key = (flat[int(k[1:])]
                       if isinstance(k, str) and k.startswith("_") else k)
                out[key] = res(vi, depth + 1)
            return out
        if isinstance(v, list):
            if v and isinstance(v[0], str):
                tag, rest = v[0], v[1:]
                if tag == "D":            # Date — 안쪽은 번호가 아니다
                    return rest[0] if rest else None
                if tag == "M":            # Map — 키·값이 번갈아 온다
                    return dict((res(rest[j], depth + 1),
                                 res(rest[j + 1], depth + 1))
                                for j in range(0, len(rest) - 1, 2))
                if tag == "S":            # Set
                    return [res(x, depth + 1) for x in rest]
                return None               # 모르는 자료형은 건드리지 않는다
            return [res(x, depth + 1) for x in v]
        return v
    return res(0)


def find_key(obj, want, depth=0):
    """깊이 어딘가에 있는 키를 찾아 준다."""
    if depth > 8 or not isinstance(obj, dict):
        return None
    if want in obj:
        return obj[want]
    for v in obj.values():
        got = find_key(v, want, depth + 1)
        if got is not None:
            return got
    return None


# 제목에서 시즌·룰·순위를 읽는다. 제목 표기가 제각각이라 넉넉하게 잡는다.
#   【S5最終1位】   【M-5:36位】   【シングルM-5 最終177位 】
#   【最終R1978/最高R2079】S5対戦記録   <- 괄호 밖에 있는 것도 있다
#
# S5 는 **시즌**, M-5 는 **룰(레귤레이션)** 이라 서로 다른 것이다. 따로 받는다.
# 둘 다 없는 기사도 많아서, 결국 제일 믿을 만한 것은 **게시일**이다.
_SEASON = re.compile(r"(?:^|[^A-Za-z])(?:S|Ｓ|シーズン|シ-ズン)\s*(\d{1,2})")
_RULE = re.compile(r"(M\s*-\s*[0-9A-Za-z])")
_RANK = re.compile(r"最終\s*(?:順位)?\s*(\d{1,5})\s*位")


def title_info(title):
    head = (title or "").replace("Ｍ", "M")
    season = _SEASON.search(head)
    rule = _RULE.search(head)
    rank = _RANK.search(head)
    return (int(season.group(1)) if season else None,
            int(rank.group(1)) if rank else None,
            rule.group(1).replace(" ", "") if rule else None)


def _table(rows):
    return dict((r["id"], r["name"]) for r in (rows or []) if isinstance(r, dict))


def parse_article(doc):
    """푼 데이터에서 파티 하나를 만든다."""
    art = find_key(doc, "article") or {}
    master = find_key(doc, "masterData") or {}
    body = art.get("body") or ""
    poke = _table(master.get("pokemons"))
    move = _table(master.get("moves"))
    item = _table(master.get("items"))
    nat = _table(master.get("natures"))
    abil = _table(master.get("abilities"))

    members = []
    for tag in re.findall(r'<div data-type="pokemon-card"[^>]*>', body):
        got = dict(re.findall(r'(data-[a-z-]+)="([^"]*)"', tag))

        def num(key):
            v = got.get(key)
            return int(v) if v and v.lstrip("-").isdigit() else None

        def lst(key):
            v = (got.get(key) or "").replace("&quot;", '"')
            try:
                return json.loads(v) if v else []
            except ValueError:
                return []

        pid = num("data-pokemon-id")
        if pid is None or pid not in poke:
            continue
        evs = {}
        raw = (got.get("data-evs") or "").replace("&quot;", '"')
        try:
            for k, v in (json.loads(raw) if raw else {}).items():
                if k in EV_KEY and int(v) > 0:
                    evs[EV_KEY[k]] = int(v)
        except ValueError:
            pass
        abils = lst("data-ability-ids")
        members.append({
            "name": poke[pid],
            "item": item.get(num("data-item-id")),
            "ability": abil.get(abils[0]) if abils else None,
            "nature": nat.get(num("data-nature-id")),
            "evs": evs,
            "moves": [move[m] for m in lst("data-move-ids") if m in move],
        })

    season, rank, rule = title_info(art.get("title"))
    published = art.get("publishedAt") or art.get("createdAt")
    if isinstance(published, (int, float)):
        # ["D", 1789554238536] 로 온 경우. 버리면 안 된다 —
        # 제목에 시즌이 없는 기사는 이게 **언제 것인지 아는 유일한 단서**다.
        published = time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                  time.gmtime(published / 1000.0))
    return {"season": season, "rule": rule, "rank": rank,
            "publishedAt": published, "title": art.get("title"),
            "url": None, "members": members}


def fetch_one(url):
    url = url.split("#")[0].rstrip("/")
    raw = get(url + ".data")
    party = parse_article(unflatten(json.loads(raw)))
    party["url"] = url
    return party


def load_out():
    if os.path.exists(OUT):
        with open(OUT, encoding="utf-8") as f:
            return json.load(f)
    return {"parties": []}


def save_out(doc):
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=1)


def main():
    args = sys.argv[1:]
    urls = []
    if "--파일" in args:
        i = args.index("--파일")
        with open(args[i + 1], encoding="utf-8") as f:
            urls = [x.strip() for x in f if x.strip()
                    and not x.startswith("#")]
        args = args[:i] + args[i + 2:]
    if "--목록" in args:
        i = args.index("--목록")
        want = int(args[i + 1])
        args = args[:i] + args[i + 2:]
        print("사이트맵에서 최신 기사 %d편을 고르는 중..." % want)
        urls += sitemap_urls(want)
    urls += [a for a in args if a.startswith("http")]
    urls = [u for u in urls if "pokesol." in u]
    if not urls:
        sys.exit("pokesol.app 기사 주소나 --목록 N 을 주세요.\n"
                 "(다른 사이트는 배분이 이미지 안이라 글자로는 못 읽습니다)")

    doc = load_out()
    have = set(p.get("url") for p in doc["parties"])
    added = 0
    skipped = [0]
    for n, u in enumerate(urls):
        if u.rstrip("/") in have:
            print("  건너뜀 (이미 있음): %s" % u)
            continue
        if n:
            time.sleep(DELAY)
        try:
            party = fetch_one(u)
        except Exception as e:
            print("  실패: %s — %s" % (u, e))
            continue
        if not party["members"]:
            skipped[0] += 1
            continue
        doc["parties"].append(party)
        added += 1
        # 중간중간 저장한다. 수백 편을 받다가 끊기면 통째로 날아가기 때문이다.
        if added % 10 == 0:
            save_out(doc)
        if added % 25 == 0 or added < 4:
            print("  %d편째: 시즌%s %s %s위  %d마리  %s"
                  % (added, party["season"], party.get("rule") or "-",
                     party["rank"], len(party["members"]),
                     (party["title"] or "")[:32]))
    # 게시일이 빈 것은 사이트맵의 lastmod 로 메운다 (요청 한 번이면 된다).
    missing = [p for p in doc["parties"] if not p.get("publishedAt")]
    if missing:
        try:
            xml = get(SITEMAP)
            mod = {}
            for block in re.findall(r"<url>(.*?)</url>", xml, re.S):
                loc = re.search(r"<loc>([^<]+)</loc>", block)
                lm = re.search(r"<lastmod>([^<]+)</lastmod>", block)
                if loc and lm:
                    mod[loc.group(1).rstrip("/")] = lm.group(1)
            filled = 0
            for party in missing:
                got = mod.get((party.get("url") or "").rstrip("/"))
                if got:
                    party["publishedAt"] = got
                    filled += 1
            print("  게시일 %d개를 사이트맵으로 메움" % filled)
        except Exception as e:
            print("  게시일 보완 실패: %s" % e)

    save_out(doc)
    print("\ndata/samples.json — 파티 %d개 (이번에 %d개 추가, 카드 없는 기사 %d개 건너뜀)"
          % (len(doc["parties"]), added, skipped[0]))


if __name__ == "__main__":
    main()
