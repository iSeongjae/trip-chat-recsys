# season_clusters.py 결과를 matplotlib 그림으로 (언어별 폴더): 히트맵 / 군집별 소형 다중 / 카테고리 수준 / 카테고리별 소형 다중
# 사용: LANGS=ko | en | ko+en  python3 plot_season_clusters.py
import os,sys,io,contextlib,numpy as np,matplotlib
matplotlib.use('Agg'); import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap,TwoSlopeNorm
HERE=os.path.dirname(os.path.abspath(__file__))
os.environ.setdefault('K','4')
ns={'__file__':os.path.join(HERE,'season_clusters.py')}
with contextlib.redirect_stdout(io.StringIO()): exec(open(ns['__file__']).read(),ns)  # 계산 재사용 (출력은 숨김)
cats,P,lab,lvl,prof,MON,TAG=ns['cats'],ns['P'],ns['lab'],ns['lvl'],ns['prof'],ns['MON'],ns['TAG']
if len(cats)<2: sys.exit(f'[{TAG}] 곡선을 그릴 카테고리가 {len(cats)}개뿐 — MIN을 낮춰 보세요')
OUT=os.path.join(HERE,'..','..','reports','figures',TAG); os.makedirs(OUT,exist_ok=True)
PERIOD=f'{TAG} 위키백과, 36개월 월별 중간값'
# ── 스타일: 참조 팔레트(라이트) ──
SURF,INK,INK2,MUTED,GRID,BASE='#fcfcfb','#0b0b0b','#52514e','#898781','#e1e0d9','#c3c2b7'
SERIES=['#2a78d6','#eb6834','#1baf7a','#4a3aa7']; MARK=['o','s','^','D']
plt.rcParams.update({'font.family':'Apple SD Gothic Neo','axes.unicode_minus':False,'figure.facecolor':SURF,'axes.facecolor':SURF,
 'axes.edgecolor':BASE,'axes.labelcolor':INK2,'xtick.color':MUTED,'ytick.color':INK2,'text.color':INK,'font.size':10,
 'axes.spines.top':False,'axes.spines.right':False,'axes.grid':False})
# 군집 순서 = 평균 곡선의 최고월 순 (1월 → 12월 흐름으로 읽히게), 이름 붙이기
groups={}
for c,g,p in zip(cats,lab,P): groups.setdefault(g,[]).append((c,p))
mean={g:np.mean([p for _,p in v],axis=0) for g,v in groups.items()}
order=sorted(groups,key=lambda g:int(np.argmax(mean[g])))
def name(g):  # 언어마다 패턴이 달라 활동 이름 대신 평균 곡선의 최고 계절로 명명
    pk=int(np.argmax(mean[g]))
    season={11:'겨울',0:'겨울',1:'겨울',2:'봄',3:'봄',4:'봄',5:'여름',6:'여름',7:'여름',8:'가을',9:'가을',10:'가을'}[pk]
    return f'{season}형({MON[pk]} 최고)'
color={g:SERIES[i] for i,g in enumerate(order)}; marker={g:MARK[i] for i,g in enumerate(order)}
med=lambda c:float(np.median(lvl[c]))
# ── 1) 히트맵 ──
rows=[]; seps=[]; glab=[]
for g in order:
    items=sorted(groups[g],key=lambda x:-x[1].max()); start=len(rows)
    rows+=items; seps.append(len(rows)); glab.append((g,start,len(rows)))
M=np.array([p for _,p in rows])
cmap=LinearSegmentedColormap.from_list('div',['#1c5cab','#6da7ec','#f0efec','#ec8a89','#c23a3a'])
vmax=float(np.ceil(M.max()*20)/20); vmin=2-vmax
fig,ax=plt.subplots(figsize=(10,0.34*len(rows)+1.6))
im=ax.imshow(M,aspect='auto',cmap=cmap,norm=TwoSlopeNorm(vcenter=1.0,vmin=min(vmin,M.min()),vmax=vmax))
for s in seps[:-1]: ax.axhline(s-0.5,color=SURF,lw=4)  # 군집 사이 표면색 간격
ax.set_xticks(range(12),MON); ax.set_yticks(range(len(rows)),[c for c,_ in rows])
ax.tick_params(length=0); [sp.set_visible(False) for sp in ax.spines.values()]
for g,s,e in glab:
    ax.annotate(name(g),xy=(-0.5,(s+e-1)/2),xytext=(-118,0),textcoords='offset points',ha='right',va='center',color=INK,fontsize=10,fontweight='bold',annotation_clip=False)
    ax.plot([-0.62,-0.62],[s-0.4,e-0.6],color=color[g],lw=3,clip_on=False,solid_capstyle='butt')
# 강한 칸만 값 표시 (선택적 라벨)
for i in range(M.shape[0]):
    for j in range(12):
        if M[i,j]>=1.2 or M[i,j]<=0.85: ax.text(j,i,f'{M[i,j]:.2f}',ha='center',va='center',fontsize=7.5,color='white' if abs(M[i,j]-1)>0.25 else INK)
cb=fig.colorbar(im,ax=ax,fraction=0.025,pad=0.02); cb.outline.set_visible(False); cb.ax.tick_params(colors=MUTED,length=0)
cb.set_label('전체 평균 대비 배율 (1.0 = 평소)',color=INK2)
ax.set_title(f'카테고리별 월간 조회수 계절 패턴 ({PERIOD}, 일수·공통 추세 보정)',loc='left',fontsize=12,color=INK,pad=12)
fig.tight_layout(); fig.savefig(f'{OUT}/season_heatmap.png',dpi=160); plt.close(fig)
# ── 2) 군집별 소형 다중 ──
fig,axs=plt.subplots(1,len(order),figsize=(3.3*len(order),3.4),sharey=True,squeeze=False); axs=axs[0]
ylo=min(P.min(),0.8); yhi=P.max()*1.03
for ax,g in zip(axs,order):
    ax.axhline(1,color=BASE,lw=1)
    for c,p in groups[g]: ax.plot(range(12),p,color=BASE,lw=1)
    ax.plot(range(12),mean[g],color=color[g],lw=2.2)
    top=max(groups[g],key=lambda x:x[1].max()); k=int(np.argmax(top[1]))
    ax.annotate(f'{top[0]} {top[1][k]:.2f}',(k,top[1][k]),xytext=(0,6),textcoords='offset points',ha='center',fontsize=8.5,color=INK2)
    ax.set_title(f'{name(g)}  ({len(groups[g])}개)',loc='left',fontsize=10.5,color=INK)
    ax.set_xticks([0,3,6,9],['1월','4월','7월','10월']); ax.set_ylim(ylo,yhi); ax.tick_params(length=0)
    ax.yaxis.grid(True,color=GRID,lw=0.8); ax.set_axisbelow(True)
axs[0].set_ylabel('평균 대비 배율')
fig.suptitle(f'계절 군집별 곡선 — 색: 군집 평균, 회색: 소속 카테고리  ({PERIOD})',x=0.01,ha='left',fontsize=12)
fig.tight_layout(); fig.savefig(f'{OUT}/season_clusters_small_multiples.png',dpi=160); plt.close(fig)
# ── 3) 카테고리 수준 점 그래프 ──
cs=sorted(cats,key=med); gof={c:g for g in groups for c,_ in groups[g]}
fig,ax=plt.subplots(figsize=(8,0.3*len(cs)+1.4))
for i,c in enumerate(cs):
    q1,q3=np.percentile(lvl[c],[25,75]); g=gof[c]
    ax.plot([q1,q3],[i,i],color=BASE,lw=2,solid_capstyle='round')
    ax.plot(med(c),i,marker=marker[g],ms=8,color=color[g],mec=SURF,mew=1.5,ls='')
    ax.text(q3*1.12,i,f'{int(med(c)):,}',va='center',fontsize=8,color=MUTED)
ax.set_xscale('log'); ax.set_yticks(range(len(cs)),cs); ax.tick_params(length=0)
ax.xaxis.grid(True,color=GRID,lw=0.8); ax.set_axisbelow(True); ax.spines['left'].set_visible(False)
ax.set_xlabel('연간 조회수 (log) — 점: 중간값, 막대: 25~75%')
for g in order: ax.plot([],[],marker=marker[g],color=color[g],ls='',ms=8,label=name(g))
ax.legend(loc='lower right',frameon=False,fontsize=9,labelcolor=INK2)
ax.set_title(f'카테고리별 연간 조회수 수준 ({PERIOD})',loc='left',fontsize=12)
fig.tight_layout(); fig.savefig(f'{OUT}/category_level_by_cluster.png',dpi=160); plt.close(fig)
print('saved',OUT)
# ── 4) 카테고리별 소형 다중 (전 카테고리) ──
seq=[(c,p,g) for g in order for c,p in sorted(groups[g],key=lambda x:-(x[1].max()-x[1].min()))]
ncol=6; nrow=int(np.ceil(len(seq)/ncol))
fig,axs=plt.subplots(nrow,ncol,figsize=(2.6*ncol,2.25*nrow),sharex=True,sharey=True,squeeze=False)
for ax in axs.flat[len(seq):]: ax.set_visible(False)
for ax,(c,p,g) in zip(axs.flat,seq):
    ax.axhline(1,color=BASE,lw=1)
    ax.plot(range(12),mean[g],color=BASE,lw=1.2)  # 군집 평균(회색)
    ax.plot(range(12),p,color=color[g],lw=2)
    k=int(np.argmax(p)); ax.plot(k,p[k],'o',ms=5,color=color[g],mec=SURF,mew=1.2)
    ax.text(0.03,0.95,c,transform=ax.transAxes,ha='left',va='top',fontsize=10,fontweight='bold',color=INK)
    ax.text(0.03,0.80,f'{name(g)} · 최고 {MON[k]} ×{p[k]:.2f}',transform=ax.transAxes,ha='left',va='top',fontsize=7.5,color=INK2)
    ax.text(0.97,0.04,f'문서 {len(prof[c])}',transform=ax.transAxes,ha='right',va='bottom',fontsize=7,color=MUTED)
    ax.set_ylim(ylo-0.04,yhi+0.28); ax.yaxis.grid(True,color=GRID,lw=0.7); ax.set_axisbelow(True); ax.tick_params(length=0,labelsize=8)
    ax.set_xticks([0,3,6,9],['1월','4월','7월','10월'])
for r in range(nrow): axs[r,0].set_ylabel('평균 대비 배율',fontsize=8)
fig.suptitle(f'카테고리별 월간 조회수 계절 곡선 — 색: 해당 카테고리(군집 색), 회색: 소속 군집 평균  ({PERIOD})',x=0.01,ha='left',fontsize=12)
fig.tight_layout(rect=(0,0,1,0.97)); fig.savefig(f'{OUT}/season_by_category_small_multiples.png',dpi=160); plt.close(fig)
print('saved category grid')
