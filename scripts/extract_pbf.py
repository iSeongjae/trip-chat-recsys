import osmium,json,os
R=os.path.join(os.path.dirname(os.path.abspath(__file__)),'..','data')
F={'restaurant','fast_food','cafe','pub','bar','food_court','ice_cream'}
import glob
out={}
for path in sorted(glob.glob(f'{R}/raw/osm_pbf/*.osm.pbf')):
  fp=osmium.FileProcessor(path).with_locations().with_filter(osmium.filter.KeyFilter('amenity'))
  for o in fp:
      if o.tags.get('amenity') not in F: continue
      if o.is_node():
          lat,lon=o.location.lat,o.location.lon
      elif o.is_way():
          pts=[n.location for n in o.nodes if n.location.valid()]
          if not pts: continue
          lat=sum(p.lat for p in pts)/len(pts); lon=sum(p.lon for p in pts)/len(pts)
      else: continue
      out[(o.type_str(),o.id)]={'osm_id':f'{o.type_str()}{o.id}','name':{t.k:t.v for t in o.tags if t.k.startswith('name')},'amenity':o.tags.get('amenity'),'cuisine':o.tags.get('cuisine'),
                                 'tags':{k:o.tags[k] for k in ('amenity','cuisine','brand','brand:en','brand:wikidata','operator','takeaway','diet:vegetarian') if k in o.tags},'lat':lat,'lon':lon}
out=list(out.values())
json.dump(out,open(f'{R}/interim/osm_eateries_jp.json','w'),ensure_ascii=False)
print('OSM eateries',len(out))
