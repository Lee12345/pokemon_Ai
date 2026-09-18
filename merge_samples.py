# -*- coding: utf-8 -*-
"""표본 파일 둘을 **하나로 합친다**.

    python3 merge_samples.py 파일A.json 파일B.json [-o 나올파일.json]

## 왜 이게 따로 필요한가

`data/samples.json` 은 1MB 가 넘는 JSON 한 덩어리다. 두 사람이(또는
두 컴퓨터가) 각자 기사를 모으면 git 은 이 파일을 **줄 단위로** 합치려
든다. 그러면 남의 파티 한복판에 내 파티가 끼어들어 **문법은 맞는데
내용이 뒤섞인 파일**이 나온다. 이 프로젝트에서 제일 무서운 고장 방식,
곧 **조용히 틀어지는 것**이다.

그래서 git 에게 맡기지 않는다. **주소(url)를 열쇠로 삼아 합친다.**

## 같은 주소가 양쪽에 있으면 어느 쪽을 남기나

**더 많이 채워진 쪽**을 남긴다. 값어치를 이렇게 센다:

    개체 한 마리당  기술이 있으면 +2, 배분이 있으면 +2,
                    도구 +1, 성격 +1, 특성 +1

champs 카드만으로 만든 파티(이름과 도구뿐)와 같은 기사를 pokesol
쪽에서 제대로 읽은 파티가 둘 다 있을 때, 제대로 읽은 쪽이 남는다.
값어치가 같으면 **먼저 준 파일(A)** 을 남긴다.

## 하는 김에 같이 봐 주는 것

 · 주소가 없는 파티 — 열쇠가 없으니 합칠 수가 없다. 그대로 다 넣고
   몇 개인지 보고한다.
 · 한 파일 안에 같은 주소가 두 번 — 수집기가 두 번 돈 흔적이다.
 · 합치고 나서 **파티 수·개체 수·채워진 칸** 을 양쪽과 비교해 보여 준다.
   숫자가 안 맞으면 여기서 보인다.

합친 결과를 덮어쓰기 전에 **원본을 먼저 복사해 두는 것**을 권한다.
"""

import io
import json
import os
import sys


def worth(party):
    """이 파티가 얼마나 채워져 있는가."""
    n = 0
    for m in (party or {}).get("members") or []:
        if m.get("moves"):
            n += 2
        if m.get("evs"):
            n += 2
        if m.get("item"):
            n += 1
        if m.get("nature"):
            n += 1
        if m.get("ability"):
            n += 1
    return n


def counts(parties):
    """(파티, 개체, 기술 있는 개체, 배분 있는 개체)."""
    mem = mv = ev = 0
    for p in parties:
        for m in p.get("members") or []:
            mem += 1
            if m.get("moves"):
                mv += 1
            if m.get("evs"):
                ev += 1
    return len(parties), mem, mv, ev


def read(path):
    with io.open(path, encoding="utf-8") as f:
        doc = json.load(f)
    if isinstance(doc, list):
        doc = {"parties": doc}
    return doc.get("parties") or []


def merge(a, b, log=None):
    """A 와 B 를 주소로 합친다. (합친 목록, 설명줄들)."""
    say = log if log is not None else []
    out = []
    where = {}          # url -> out 안의 자리
    nourl = 0
    self_dup = [0, 0]   # **한 파일 안에서** 주소가 두 번 나온 것
    overlap = 0         # 양쪽에 다 있는 기사
    kept_b = replaced = 0
    seen = [set(), set()]

    for which, parties in ((0, a), (1, b)):
        for p in parties:
            url = (p.get("url") or "").strip()
            if not url:
                nourl += 1
                out.append(p)
                continue
            if url in seen[which]:
                self_dup[which] += 1
            elif which == 1 and url in seen[0]:
                overlap += 1
            seen[which].add(url)
            if url not in where:
                where[url] = len(out)
                out.append(p)
                if which == 1:
                    kept_b += 1
                continue
            old = out[where[url]]
            if worth(p) > worth(old):
                out[where[url]] = p
                if which == 1:
                    replaced += 1

    say.append("  양쪽에 다 있는 기사 %d편" % overlap)
    say.append("  B 에서 새로 들어온 기사 %d편" % kept_b)
    say.append("  그중 B 쪽이 더 채워져 있어서 A 것을 바꾼 기사 %d편"
               % replaced)
    if self_dup[0] or self_dup[1]:
        say.append("  ! 한 파일 안에서 주소가 겹친 것: A %d편 · B %d편 "
                   "(수집기가 두 번 돈 흔적이다)"
                   % (self_dup[0], self_dup[1]))
    if nourl:
        say.append("  ! 주소가 없는 파티 %d편 — 합칠 열쇠가 없어서 "
                   "그대로 다 넣었다. 같은 기사가 두 번 들어갔을 수 있다."
                   % nourl)
    return out, say


def main():
    args = [x for x in sys.argv[1:]]
    out_path = None
    if "-o" in args:
        i = args.index("-o")
        out_path = args[i + 1]
        del args[i:i + 2]
    if len(args) != 2:
        print(__doc__)
        return 1
    pa, pb = args
    for p in (pa, pb):
        if not os.path.exists(p):
            print("파일이 없다: %s" % p)
            return 1

    a, b = read(pa), read(pb)
    print("=" * 74)
    print("  표본 합치기")
    print("=" * 74)
    print("  A  %-40s 파티 %5d · 개체 %5d" % ((pa,) + counts(a)[:2]))
    print("  B  %-40s 파티 %5d · 개체 %5d" % ((pb,) + counts(b)[:2]))
    print("-" * 74)
    merged, say = merge(a, b)
    for line in say:
        print(line)
    print("-" * 74)
    ca, cb, cm = counts(a), counts(b), counts(merged)
    print("  %-12s %8s %8s %8s" % ("", "A", "B", "합친 것"))
    for i, nm in enumerate(("파티", "개체", "기술 있음", "배분 있음")):
        print("  %-12s %8d %8d %8d" % (nm, ca[i], cb[i], cm[i]))
    print("-" * 74)
    # 합친 결과는 양쪽보다 적을 수 없다. 적으면 뭔가 잘못된 것이다.
    bad = [nm for i, nm in enumerate(("파티", "개체", "기술 있음", "배분 있음"))
           if cm[i] < max(ca[i], cb[i])]
    if bad:
        print("  !! 합친 결과가 한쪽보다 줄었다: %s" % ", ".join(bad))
        print("     합치기는 무엇도 버리지 않아야 한다. 멈춘다.")
        return 1
    print("  합친 결과는 양쪽 어느 쪽보다도 줄지 않았다.")

    if out_path:
        with io.open(out_path, "w", encoding="utf-8") as f:
            f.write(json.dumps({"parties": merged},
                               ensure_ascii=False, indent=1))
        print("  저장함: %s" % out_path)
    else:
        print("  (-o 를 안 줘서 저장하지 않았다. 세어 보기만 했다)")
    print("=" * 74)
    return 0


if __name__ == "__main__":
    sys.exit(main())
