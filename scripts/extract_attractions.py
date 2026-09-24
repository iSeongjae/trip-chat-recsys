# Geofabrik pbf → 관광지 POI (구경/신사·사찰/산책·자연/휴식/쇼핑)
import osmium,json,os,glob
R=os.path.join(os.path.dirname(os.path.abspath(__file__)),'..','data')
import re
# 쇼핑: 한국인 여행자가 많이 찾는 유형 (잡화 할인점·드럭스토어·전자제품·애니/취미)
SHOP={'department_store','mall','gift','variety_store','chemist','electronics','anime','hobby','games','video_games'}
DONKI=re.compile('ドン・?キホーテ|MEGAドン|Don Quijote',re.I)
TOUR={'attraction','museum','gallery','viewpoint','zoo','aquarium','theme_park','artwork'}
def category(t):
    if t.get('tourism') in TOUR: return '구경'
    if 'historic' in t: return '구경'
    if t.get('amenity')=='place_of_worship': return '신사·사찰'
    if t.get('leisure') in ('park','garden','nature_reserve') or t.get('natural') in ('beach','peak','hot_spring') or t.get('waterway')=='waterfall': return '산책·자연'
    if t.get('amenity')=='public_bath' or t.get('leisure')=='sauna': return '휴식'
    if t.get('shop') in SHOP: return '쇼핑'
    if t.get('shop')=='supermarket' and DONKI.search(t.get('name','')+t.get('brand','')): return '쇼핑'  # MEGA 돈키호테 등
KEEP=('brand','tourism','historic','amenity','religion','leisure','natural','waterway','shop','bath:type','wikidata','wikipedia','opening_hours','website','fee')
def rec(t,lat,lon):
    return {'category':category(t),'name':{k:v for k,v in t.items() if k.startswith('name')},**{k:t[k] for k in KEEP if k in t},'lat':lat,'lon':lon}
out={}
for path in sorted(glob.glob(f'{R}/raw/osm_pbf/*.osm.pbf')):
    fp=(osmium.FileProcessor(path).with_locations().with_areas()
        .with_filter(osmium.filter.KeyFilter('tourism','historic','amenity','leisure','natural','waterway','shop','type')))
    for o in fp:
        t=dict(o.tags)
        if o.is_area():
            if o.from_way(): continue  # 닫힌 way는 아래 way 분기에서 처리
            if not category(t): continue
            pts=[n for ring in o.outer_rings() for n in ring if n.location.valid()]
            if not pts: continue
            out[('r',o.orig_id())]=rec(t,sum(p.lat for p in pts)/len(pts),sum(p.lon for p in pts)/len(pts))
            continue
        if not category(t): continue
        if o.is_node(): out[('n',o.id)]=rec(t,o.location.lat,o.location.lon)
        elif o.is_way():
            pts=[n.location for n in o.nodes if n.location.valid()]
            if pts: out[('w',o.id)]=rec(t,sum(p.lat for p in pts)/len(pts),sum(p.lon for p in pts)/len(pts))
    print(os.path.basename(path),len(out),flush=True)
res=[{'osm_id':f'{k[0]}{k[1]}',**v} for k,v in out.items()]
json.dump(res,open(f'{R}/interim/osm_attractions_jp.json','w'),ensure_ascii=False)
print('관광지 POI',len(res))
