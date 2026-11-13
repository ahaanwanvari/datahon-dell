"""Source-backed flood preparedness options. Generated imagery is never route evidence."""
from datetime import datetime, timezone
import json
import hashlib
import os
from pathlib import Path
import time
import math
import re
import requests
from concurrent.futures import ThreadPoolExecutor, wait

FEMA='https://gis.fema.gov/arcgis/rest/services/NSS/FEMA_NSS/MapServer'
ELEVATION='https://api.open-meteo.com/v1/elevation'
HEADERS={'User-Agent':'FloodAtlas/1.0 (local preparedness research)'}
_ROUTE_POOL=ThreadPoolExecutor(max_workers=3,thread_name_prefix='route-screen')


def cached_feed(url,params,ttl):
    """Cache source responses briefly; never replace a failed feed with invented data."""
    folder=Path(os.environ.get('FLOOD_STATE',str(Path(__file__).resolve().parent/'.state')))/'planning-cache'
    folder.mkdir(parents=True,exist_ok=True)
    key=hashlib.sha256((url+json.dumps(params,sort_keys=True)).encode()).hexdigest()
    path=folder/(key+'.json')
    try:
        saved=json.loads(path.read_text())
        if 0<=time.time()-saved['timestamp']<=ttl:
            return saved['payload'],saved['retrieved'],True
    except (OSError,ValueError,KeyError,TypeError):pass
    error=None
    for endpoint in dict.fromkeys([url,url.replace('/MapServer/','/FeatureServer/')]):
        try:
            r=requests.get(endpoint,params=params,headers=HEADERS,timeout=(2,4));r.raise_for_status()
            payload=r.json()
            if 'error' in payload:raise ValueError(payload['error'].get('message','Source returned an error.'))
            retrieved=datetime.now(timezone.utc).isoformat()
            temporary=folder/(key+'.tmp');temporary.write_text(json.dumps({'timestamp':time.time(),'retrieved':retrieved,'payload':payload}));temporary.replace(path)
            return payload,retrieved,False
        except Exception as exc:error=exc
    raise error


def geocode(query):
    query=str(query).strip()[:200]
    if not query:raise ValueError('Add the photo location: an address or latitude, longitude.')
    if re.fullmatch(r'\s*-?\d+(?:\.\d+)?\s*,\s*-?\d+(?:\.\d+)?\s*',query):
        lat,lon=map(float,query.split(','))
        if not (-85<=lat<=85 and -180<=lon<=180):raise ValueError('Invalid map coordinates.')
        return {'lat':lat,'lon':lon,'label':f'{lat:.5f}, {lon:.5f}','accuracy':'User-provided coordinates'}
    r=requests.get('https://nominatim.openstreetmap.org/search',params={'q':query,'format':'jsonv2','limit':1},headers=HEADERS,timeout=(4,20));r.raise_for_status()
    rows=r.json()
    if not rows:raise ValueError('Location not found. Try an exact address or coordinates.')
    p=rows[0]
    return {'lat':float(p['lat']),'lon':float(p['lon']),'label':p.get('display_name',query),'accuracy':'Geocoded location; confirm that this is where the photo was taken'}


def distance(a,b):
    lat1,lon1=a;lat2,lon2=b
    dlat=math.radians(lat2-lat1);dlon=math.radians(lon2-lon1)
    q=math.sin(dlat/2)**2+math.cos(math.radians(lat1))*math.cos(math.radians(lat2))*math.sin(dlon/2)**2
    return 6371*2*math.atan2(math.sqrt(q),math.sqrt(max(0,1-q)))


def shelter_candidates(origin):
    errors=[];candidates={};sources=[]
    layers=[(0,'FEMA open shelter listing'),(5,'FEMA shelter location inventory')]
    lat,lon=round(origin['lat'],3),round(origin['lon'],3)
    params={'f':'json','where':'1=1','geometry':json.dumps({'x':lon,'y':lat,'spatialReference':{'wkid':4326}}),
            'geometryType':'esriGeometryPoint','inSR':4326,'distance':40500,'units':'esriSRUnit_Meter',
            'outFields':'shelter_id,shelter_name,address_1,city,state,latitude,longitude,shelter_status_code,reporting_period,in_100_yr_floodplain,in_surge_slosh_area,org_main_phone',
            'returnGeometry':'true','outSR':4326,'resultRecordCount':100}
    with ThreadPoolExecutor(max_workers=2) as pool:
        pending={layer:pool.submit(cached_feed,f'{FEMA}/{layer}/query',params,600 if layer==0 else 86400) for layer,_ in layers}
    for layer,label in layers:
        try:
            payload,retrieved,cached=pending[layer].result()
            lat,lon=origin['lat'],origin['lon']
            if 'error' in payload:raise ValueError(payload['error'].get('message','Shelter service failed.'))
            sources.append({'name':label,'url':f'{FEMA}/{layer}','retrieved':retrieved,'cached':cached})
            for feature in payload.get('features',[]):
                p=feature.get('attributes',{});g=feature.get('geometry',{})
                plat=p.get('latitude') or g.get('y');plon=p.get('longitude') or g.get('x')
                if plat is None or plon is None:continue
                km=distance((lat,lon),(float(plat),float(plon)))
                if km>40:continue
                identity='fema:'+str(p['shelter_id'])
                if identity in candidates:continue
                updated=p.get('reporting_period');fresh=isinstance(updated,(int,float)) and 0 <= datetime.now(timezone.utc).timestamp()-updated/1000 <= 86400
                candidates[identity]={'id':identity,'name':p.get('shelter_name') or 'Mapped shelter','lat':float(plat),'lon':float(plon),'distance_km':round(km,2),
                    'address':', '.join(str(p[k]) for k in ['address_1','city','state'] if p.get(k)),
                    'phone':p.get('org_main_phone'),'listed_open':layer==0,'recent_status':fresh,'status_timestamp':None,
                    'floodplain_flag':p.get('in_100_yr_floodplain'),'surge_flag':p.get('in_surge_slosh_area'),
                    'source':f'{FEMA}/{layer}','status':'Listed open by FEMA; confirm capacity and access' if layer==0 else 'Planning location only; current availability unverified'}
        except Exception as exc:errors.append(label+': '+str(exc)[:180])
    return sorted(candidates.values(),key=lambda p:(not p['listed_open'],p['distance_km']))[:12],sources,errors


def elevations(origin,candidates):
    coords=[origin]+candidates
    payload,_,_=cached_feed(ELEVATION,{'latitude':','.join(str(p['lat']) for p in coords),'longitude':','.join(str(p['lon']) for p in coords)},86400)
    values=payload.get('elevation')
    if not isinstance(values,list) or len(values)!=len(coords):raise ValueError('No complete terrain elevation response.')
    if any(not isinstance(v,(int,float)) or not math.isfinite(v) for v in values):raise ValueError('Terrain elevations unavailable.')
    origin['elevation_m']=values[0]
    for p,value in zip(candidates,values[1:]):
        p['elevation_m']=value;p['higher_by_m']=round(value-values[0],1)


def choose_model_result(text,eligible):
    """The model may select only from server-screened, source-backed IDs."""
    match=re.search(r'\{.*\}',text,re.S)
    if not match:raise ValueError('The planning model did not return a structured assessment.')
    result=json.loads(match.group());selected=result.get('candidate_id')
    ids={c['id'] for c in eligible}
    if selected is not None and selected not in ids:raise ValueError('The model selected an unsupported destination.')
    summary=result.get('reason')
    if not isinstance(summary,str) or not summary.strip():raise ValueError('The planning model omitted its reasoning.')
    return {'candidate_id':selected,'reason':summary[:1500]}


def build_plan(location,model_call,route_call,progress=None):
    origin=geocode(location)
    notify=progress or (lambda *_:None)
    notify('searching_shelters',None)
    candidates,sources,errors=shelter_candidates(origin)
    def partial():
        return {'origin':origin.copy(),'candidates':[dict(p) for p in candidates[:5]],
                'assessment':{'candidate_id':None,'reason':('Nearby source records found; terrain and access checks are still in progress.' if candidates else 'No nearby shelter records returned yet; checking available terrain and source information.')},
                'sources':list(sources),'errors':list(errors),'scope':'Planning candidates; current safety and access are not established.',
                'terrain_limit':'Terrain elevations are approximate; not building heights or flood depths.',
                'official_guidance':'https://www.weather.gov/safety/flood-during',
                'shelter_directory':'https://www.redcross.org/get-help/disaster-relief-and-recovery-services/find-an-open-shelter.html',
                'checked_at':datetime.now(timezone.utc).isoformat(),'partial':True}
    notify('checking_terrain',partial())
    try:
        elevations(origin,candidates)
        sources.append({'name':'Open-Meteo / Copernicus 90 m terrain elevation','url':'https://open-meteo.com/en/docs/elevation-api'})
    except Exception as exc:errors.append('Elevation: '+str(exc)[:180])
    candidates.sort(key=lambda p:(not(p.get('higher_by_m',-999)>=3),not p['listed_open'],p['distance_km']))
    candidates=candidates[:5]
    notify('checking_access',partial())
    route_jobs={}
    for candidate in candidates:
        # Planning candidates are places to contact, never instructions to travel.
        candidate['eligible_for_model_selection']=candidate.get('higher_by_m',-999)>=3 and str(candidate['floodplain_flag']).strip().lower() not in ('yes','y','true','1') and str(candidate['surge_flag']).strip().lower() not in ('yes','y','true','1')
        candidate['route_usable']=False
        # Unknown terrain or floodplain data cannot become positive safety evidence.
        outside_floodplain=str(candidate['floodplain_flag']).lower() in ('no','n','false','0')
        outside_surge=str(candidate['surge_flag']).lower() in ('no','n','false','0')
        if not (candidate['eligible_for_model_selection'] and outside_floodplain and outside_surge):
            candidate['route_note']='No route recommendation: flood-zone or terrain screening is missing, unfavorable or incomplete.'
            continue
        route_jobs[_ROUTE_POOL.submit(route_call,(origin['lat'],origin['lon']),(candidate['lat'],candidate['lon']),1)]=candidate
    if route_jobs:
        # Route screening is supplementary. Keep the coordinate lookup responsive
        # when public routing or hazard feeds are slow; incomplete checks remain
        # explicitly unavailable and never become a safety clearance.
        done,pending=wait(route_jobs,timeout=4)
        for future in pending:
            future.cancel();route_jobs[future]['route_error']='Route screening exceeded its time limit. No passability claim is made.'
        for future in done:
            candidate=route_jobs[future]
            try:
                routes=future.result();candidate['routes']=routes['options']
                usable=[r for r in routes['options'] if r.get('risk_score') is not None and not r.get('txdot_hazards') and r.get('fema_zone_sample_fraction')==0]
                candidate['route_usable']=bool(usable)
                if usable:candidate['route']=usable[0]
            except Exception as exc:candidate['route_error']=str(exc)[:160]
    eligible=[p for p in candidates if p['eligible_for_model_selection']]
    facts={'origin':origin,'candidates':[{k:p[k] for k in ['id','name','distance_km','status','higher_by_m','route_usable'] if k in p} for p in eligible]}
    assessment=None
    if eligible:
        notify('reviewing_options',partial())
        prompt=('For a hypothetical future flood preparedness plan, compare ONLY the supplied source-backed higher-terrain planning sites. '
                'These are places to contact and verify before a disaster, NOT instructions to travel or confirmed open shelters. '
                'Return JSON {"candidate_id": one supplied ID or null, "reason": short explanation}. '
                'Do not invent coordinates, open status, building heights or directions. No route is guaranteed safe. '
                'If no eligible candidates are supplied, candidate_id must be null and explain that a verified destination cannot be established. '
                'Never recommend entering floodwater, an arbitrary tall building or an unverified road. '
                'Do not use a generated flood image as map evidence. Facts: '+json.dumps(facts))
        try:assessment=choose_model_result(model_call(prompt),eligible)
        except Exception as exc:errors.append('Model assessment: '+str(exc)[:180])
    if assessment is None:
        assessment={'candidate_id':None,'reason':'No suitable higher-terrain planning site could be established from the available records. Contact local emergency management to identify designated shelters and evacuation routes; the listed sites are unverified planning references.'}
    return {'origin':origin,'candidates':candidates,'assessment':assessment,'sources':sources,'errors':errors,
            'scope':'Preparedness planning, not live evacuation directions. Shelter listing coverage is U.S.-focused; route screening is currently available in Texas.',
            'terrain_limit':'Terrain elevations use a 90 m grid, not building heights or flood depths.',
            'official_guidance':'https://www.weather.gov/safety/flood-during','shelter_directory':'https://www.redcross.org/get-help/disaster-relief-and-recovery-services/find-an-open-shelter.html',
            'checked_at':datetime.now(timezone.utc).isoformat()}
