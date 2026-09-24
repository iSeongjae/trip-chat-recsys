# 한국어 vs 영어 카테고리별 계절 곡선 겹쳐 그리기 (두 언어 모두 문서가 충분한 카테고리만)
# 사용: python3 plot_compare_langs.py   (KO_MIN/EN_MIN, MIN_VIEWS 환경변수로 기준 조정)
import os,io,contextlib,numpy as np,matplotlib
matplotlib.use('Agg'); import matplotlib.pyplot as plt
HERE=os.path.dirname(os.path.abspath(__file__)); OUT=os.path.join(HERE,'..','..','reports','figures','ko_vs_en'); os.makedirs(OUT,exist_ok=True)
def run(lang,mn):
    os.environ.update(LANGS=lang,MIN=str(mn),MIN_VIEWS=os.environ.get('MIN_VIEWS','240')); os.environ.pop('NORM',None)
    ns={'__file__':os.path.join(HERE,'season_clusters.py'),'__name__':'lib'}
    with contextlib.redirect_stdout(io.StringIO()): exec(open(ns['__file__']).read(),ns)
    return {c:p for c,p in zip(ns['cats'],ns['P'])},ns['prof'],ns['lvl'],ns['MON']
ko,kprof,klvl,MON=run('ko',int(os.environ.get('KO_MIN','10')))
en,eprof,elvl,_=run('en',int(os.environ.get('EN_MIN','15')))
both=sorted(set(ko)&set(en),key=lambda c:-np.corrcoef(ko[c],en[c])[0,1])
SURF,INK,INK2,MUTED,GRID,BASE='#fcfcfb','#0b0b0b','#52514e','#898781','#e1e0d9','#c3c2b7'
KO_C,EN_C='#2a78d6','#eb6834'
plt.rcParams.update({'font.family':'Apple SD Gothic Neo','axes.unicode_minus':False,'figure.facecolor':SURF,'axes.facecolor':SURF,
 'axes.edgecolor':BASE,'text.color':INK,'xtick.color':MUTED,'ytick.color':INK2,'font.size':10,'axes.spines.top':False,'axes.spines.right':False})
allv=np.array([ko[c] for c in both]+[en[c] for c in both]); ylo,yhi=allv.min()-0.04,allv.max()+0.22
ncol=min(5,len(both)); nrow=int(np.ceil(len(both)/ncol))
fig,axs=plt.subplots(nrow,ncol,figsize=(3.1*ncol,2.6*nrow+0.6),sharex=True,sharey=True,squeeze=False)
for ax in axs.flat[len(both):]: ax.set_visible(False)
for ax,c in zip(axs.flat,both):
    r=np.corrcoef(ko[c],en[c])[0,1]
    ax.axhline(1,color=BASE,lw=1); ax.yaxis.grid(True,color=GRID,lw=0.7); ax.set_axisbelow(True)
    ax.plot(range(12),en[c],color=EN_C,lw=2); ax.plot(range(12),ko[c],color=KO_C,lw=2)
    for p,col in ((ko[c],KO_C),(en[c],EN_C)):
        k=int(np.argmax(p)); ax.plot(k,p[k],'o',ms=5,color=col,mec=SURF,mew=1.2)
    ax.text(0.03,0.95,c,transform=ax.transAxes,va='top',fontsize=10.5,fontweight='bold')
    ax.text(0.03,0.80,f'상관 r={r:+.2f} · 최고 ko {MON[int(np.argmax(ko[c]))]} / en {MON[int(np.argmax(en[c]))]}',transform=ax.transAxes,va='top',fontsize=7.5,color=INK2)
    ax.text(0.97,0.04,f'문서 ko {len(kprof[c])} · en {len(eprof[c])}',transform=ax.transAxes,ha='right',va='bottom',fontsize=7,color=MUTED)
    ax.set_ylim(ylo,yhi); ax.set_xticks([0,3,6,9],['1월','4월','7월','10월']); ax.tick_params(length=0,labelsize=8)
for r_ in range(nrow): axs[r_,0].set_ylabel('평균 대비 배율',fontsize=8)
from matplotlib.lines import Line2D
fig.legend(handles=[Line2D([],[],color=KO_C,lw=2,label='한국어 위키백과'),Line2D([],[],color=EN_C,lw=2,label='영어 위키백과')],
           loc='upper right',ncol=2,frameon=False,fontsize=9.5)
fig.suptitle('한국어 vs 영어 — 카테고리별 계절 곡선 (36개월 월별 중간값, 일수·공통 추세 보정, 상관 높은 순)',x=0.01,ha='left',fontsize=12)
fig.tight_layout(rect=(0,0,1,0.95)); fig.savefig(f'{OUT}/ko_vs_en_by_category.png',dpi=160); plt.close(fig)
print('비교 카테고리',len(both)); [print(f'  {c:<10} r={np.corrcoef(ko[c],en[c])[0,1]:+.2f}  ko 최고 {MON[int(np.argmax(ko[c]))]} x{ko[c].max():.2f} | en 최고 {MON[int(np.argmax(en[c]))]} x{en[c].max():.2f}') for c in both]
print('saved',OUT)
