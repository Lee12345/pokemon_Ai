import sys, random, re, collections
sys.path.insert(0, sys.argv[1])
import calc, battle, search, scout, best
dex = calc.Dex()
P = lambda n: dex.find_pokemon(n)
garch = calc.Build(dex, P("한카리아스"), sp={"attack":32,"speed":32,"hp":2})
corv = calc.Build(dex, P("아머까오"), sp={"hp":32,"defense":32,"spDef":2})
party=[garch, corv]
mv=[dex.find_move(x) for x in ["지진","역린","스톤에지","칼춤"]]
opp_multi=0; my_multi=0; N=200; corv_moves=collections.Counter(); rng=random.Random(3)
for s in range(N):
    ob, om = scout.sample_opponent(dex, P("하마돈"), rng, None, lambda b: best.effective_speed(dex,b)[0])
    rows = best.rate_moves(dex, ob, garch, [(m,None) for m in om]); th=best.best_threat(rows)
    r = battle.run_once(dex, party, ob, [mv[3]], ([th["move"]] if th else [om[0]]), random.Random(s), log=True, my_moves=mv)
    o=set(); me=set()
    for l in r["log"]:
        m=re.match(r"\s*\d+턴\s+(\S+) 의 (\S+)", l)
        if not m: continue
        who, move = m.groups()
        try: dex.find_move(move)
        except LookupError: continue
        if who=="하마돈": o.add(move)
        elif who=="한카리아스": me.add(move)
        elif who=="아머까오": corv_moves[move]+=1
    opp_multi += len(o)>=2; my_multi += len(me - {"칼춤"})>=2
print("games=%d  opp used >=2 distinct moves: %d  |  my garchomp used >=2 distinct attacks after plan: %d" % (N, opp_multi, my_multi))
print("corviknight (bench) moves used:", dict(corv_moves))
# control: game length & how many games had >=2 opp move-turns
T=[];oppturns=0
for s in range(50):
    ob, om = scout.sample_opponent(dex, P("하마돈"), rng, None, lambda b: best.effective_speed(dex,b)[0])
    rows = best.rate_moves(dex, ob, garch, [(m,None) for m in om]); th=best.best_threat(rows)
    r = battle.run_once(dex, party, ob, [mv[3]], ([th["move"]] if th else [om[0]]), random.Random(s), log=True, my_moves=mv)
    T.append(r["turns"]); oppturns += sum(1 for l in r["log"] if re.match(r"\s*\d+턴\s+하마돈 의 ", l))>=3
print("avg turns %.1f, games with >=3 opp action lines: %d/50" % (sum(T)/50., oppturns))
