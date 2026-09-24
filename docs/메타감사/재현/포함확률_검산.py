import sys, itertools, random
sys.path.insert(0, sys.argv[1])
import scout
def brute(w, slots, mode):
    num=[0.0]*len(w); den=0.0
    for bits in itertools.product((0,1), repeat=len(w)):
        p=1.0
        for b,x in zip(bits,w): p*= x if b else 1-x
        k=sum(bits)
        ok = k<=slots if mode=="le" else k==slots
        if ok:
            den+=p
            for i,b in enumerate(bits):
                if b: num[i]+=p
    return [n/den for n in num]
rng=random.Random(0); worst=0
for t in range(300):
    n=rng.randint(2,8); slots=rng.randint(1,4)
    w=[rng.uniform(0.02,0.98) for _ in range(n)]
    worst=max(worst, max(abs(a-b) for a,b in zip(scout._inclusion(w,slots), brute(w,slots,"le"))))
print("300 random cases, max |code - brute(<=slots)| = %.2e" % worst)
w=[0.5,0.5,0.5]
print("example w=[.5,.5,.5] slots=1  code:", [round(x,4) for x in scout._inclusion(w,1)],
      " brute(<=1):", [round(x,4) for x in brute(w,1,"le")], " brute(==1):", [round(x,4) for x in brute(w,1,"eq")])
w=[0.5,0.5,0.5]
print("example slots=2  code:", [round(x,4) for x in scout._inclusion(w,2)], " brute(<=2):", [round(x,4) for x in brute(w,2,"le")], " brute(==2):",[round(x,4) for x in brute(w,2,"eq")])
# 실제 뽑기(sample_conditional)가 같은 조건을 쓰는지 — 20만 회
w=[0.9,0.8,0.7,0.6,0.5,0.4,0.3]; r=random.Random(0); N=200000; c=[0]*7
for _ in range(N):
    for i in scout.sample_conditional(r,w,4): c[i]+=1
print("뽑기 빈도   :", [round(x/N,3) for x in c]); print("_inclusion :", [round(x,3) for x in scout._inclusion(w,4)])
