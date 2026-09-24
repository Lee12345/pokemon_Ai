# OpenCode-A8 — 노력치가 다른 파티에 같은 표가 돌아오는가
import sys; sys.path.insert(0, sys.argv[1] if len(sys.argv) > 1 else ".")
import calc, battle
dex=calc.Dex();P=dex.find_pokemon
a1=[calc.Build(dex,P('한카리아스'),sp={'attack':32,'speed':32}),calc.Build(dex,P('아머까오'),sp={'hp':32,'defense':32})]
a2=[calc.Build(dex,P('한카리아스'),sp={'hp':32,'defense':32}),calc.Build(dex,P('아머까오'),sp={'attack':32})]
o=[calc.Build(dex,P('하마돈')),calc.Build(dex,P('드래펄트'))]
t1=battle.matchup_table(dex,a1,o,trials=20); t2=battle.matchup_table(dex,a2,o,trials=20)
print('다른 파티인데 같은 표 객체:', t1 is t2)
battle._MATCHUP_CACHE.clear(); t3=battle.matchup_table(dex,a2,o,trials=20)
print('캐시 값 vs 새로 잰 값:', {k:(round(t2[k],2),round(t3[k],2)) for k in t3 if t2[k]!=t3[k]})
