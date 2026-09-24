import sys, random
sys.path.insert(0, sys.argv[1])
import calc, battle
dex = calc.Dex(); P=dex.find_pokemon; M=dex.find_move
def B(n, **k): return calc.Build(dex, P(n), **k)
# 공격기 추가 효과 (Claude-A4) — 기대: 용성군 뒤 특공 -2, 인파이트 뒤 방어·특방 -1
b = battle.Battle(dex, B("한카리아스", sp={"spAtk":32}), B("잠만보", sp={"hp":32,"spDef":32}), rng=random.Random(0), log=True)
b.step(M("용성군"), M("철벽")); print("용성군 뒤 내 특공 랭크:", b.me.ranks.get("spAtk"), "(기대 -2)")
b = battle.Battle(dex, B("한카리아스", sp={"attack":32}), B("잠만보", sp={"hp":32}), rng=random.Random(0), log=True)
b.step(M("인파이트"), M("철벽")); print("인파이트 뒤 내 방어/특방:", b.me.ranks.get("defense"), b.me.ranks.get("spDef"), "(기대 -1 -1)")
# tailwind: pick pair where slow < fast < 2*slow
slow = B("한카리아스"); fast = B("드래펄트", sp={"speed":32})
print("speeds: slow", slow.stat("speed"), "x2=", slow.stat("speed")*2, " fast", fast.stat("speed"))
for tw in (False, True):
    b = battle.Battle(dex, slow, fast, rng=random.Random(0), log=True)
    b.step(M("순풍") if tw else M("칼춤"), M("용의춤"))
    b.step(M("지진"), M("섀도볼"))
    t2 = [l for l in b.log if l.startswith(" 2턴") and " 의 " in l]
    print("tailwind=%s  2턴 첫 행동: %s" % (tw, t2[0][:30] if t2 else None))
# berry: damage per hit with and without 플카열매
for item in (None, "플카열매"):
    me = B("한카리아스", item=item, sp={"hp":32})
    b = battle.Battle(dex, me, B("글레이시아", sp={"spAtk":32}), rng=random.Random(1), log=True)
    b.me.max_hp = b.me.hp = 5000
    for i in range(3): b.step(M("칼춤"), M("냉동빔"))
    dm=[l.split("에게 ")[1].split(" ")[0] for l in b.log if "냉동빔 →" in l]
    print("item=%s 냉동빔 데미지 %s item_used=%s" % (item, dm, b.me.item_used))
# trick room vs sand
b = battle.Battle(dex, B("하마돈"), B("잠만보"), rng=random.Random(0), log=True)
print("시작 날씨:", b.field.weather); b.step(M("트릭룸"), M("철벽")); print("트릭룸 뒤 날씨:", b.field.weather)
