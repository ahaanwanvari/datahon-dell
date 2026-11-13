"""Persisted asynchronous photo-to-flood illustration and preparedness jobs."""
import base64
from datetime import datetime,timezone
import io
import json
import math
from pathlib import Path
import re
import threading
import uuid
import requests
from PIL import Image,ImageOps
from PIL.PngImagePlugin import PngInfo
from flood_plan import build_plan, geocode
from photo_location import PhotoLocator
from scene_analysis import GENERATED_PROMPT as SCENE_PROMPT, GROUNDING_PROMPT, validate_analysis, merge_grounded_buildings


class Scenarios:
    def __init__(self,state,endpoint,model,route_call):
        self.root=Path(state)/'scenarios';self.root.mkdir(parents=True,exist_ok=True)
        self.endpoint=endpoint;self.model=model;self.route_call=route_call
        self.lock=threading.Lock();self.busy=set()
        self.locator=PhotoLocator(state)

    def folder(self,identity):
        if not re.fullmatch(r'[0-9a-f]{32}',identity):raise ValueError('Invalid scenario ID.')
        return self.root/identity

    def read(self,identity):
        record=json.loads((self.folder(identity)/'job.json').read_text())
        # Mark interrupted jobs honestly after an app process restart.
        if record['state']=='finding_destinations' and identity not in self.busy:
            record['state']='ready';record['plan_error']='Destination lookup was interrupted. Your preview is saved; choose Find nearby options to retry.'
        elif record['state'] in ('queued','analyzing_and_generating') and identity not in self.busy:
            record['state']='interrupted';record['error']='The app restarted during this job. Please generate a new scenario.'
        return record

    def write(self,identity,record):
        folder=self.folder(identity);temporary=folder/'job.tmp'
        temporary.write_text(json.dumps(record,indent=2));temporary.replace(folder/'job.json')

    def start(self,body):
        health=requests.get(self.endpoint.removesuffix('/v1')+'/health',timeout=10);health.raise_for_status()
        if not health.json().get('image_editor',{}).get('installed'):
            raise ValueError('The local image-editing model is still being installed. Please try again when setup finishes.')
        severity=body.get('severity','moderate')
        if severity not in ('minor','moderate','severe'):raise ValueError('Choose a flood scenario.')
        url=body.get('image')
        if not isinstance(url,str) or not url.startswith(('data:image/png;base64,','data:image/jpeg;base64,','data:image/webp;base64,')):
            raise ValueError('Upload a JPEG, PNG or WebP photo.')
        raw=base64.b64decode(url.split(',',1)[1],validate=True)
        gps=None
        with Image.open(io.BytesIO(raw)) as image:
            if image.width*image.height>40_000_000:raise ValueError('Use a photo below 40 megapixels.')
            try:
                data=image.getexif().get_ifd(34853)
                def degrees(value):return float(value[0])+float(value[1])/60+float(value[2])/3600
                lat_ref=data[1].decode() if isinstance(data[1],bytes) else str(data[1])
                lon_ref=data[3].decode() if isinstance(data[3],bytes) else str(data[3])
                lat=degrees(data[2])*(-1 if lat_ref=='S' else 1);lon=degrees(data[4])*(-1 if lon_ref=='W' else 1)
                if -85<=lat<=85 and -180<=lon<=180:gps={'lat':lat,'lon':lon}
            except (KeyError,TypeError,ValueError,ZeroDivisionError):pass
            image=ImageOps.exif_transpose(image).convert('RGB');image.thumbnail((1024,1024))
            identity=uuid.uuid4().hex;folder=self.folder(identity);folder.mkdir()
            image.save(folder/'original.png')
        location_match=self.locator.match(raw)
        if gps and not location_match.get('candidates'):
            location_match.update(method='photo_gps',suggested={**gps,'label':'Photo GPS metadata','location_precision':'GPS metadata supplied with the photo'},candidates=[{**gps,'label':'Photo GPS metadata'}],note='Confirm that the GPS metadata points to where this photo was taken.')
        record={'id':identity,'state':'queued','severity':severity,'gps':gps,'location_match':location_match,'synthetic':True,
                'created':datetime.now(timezone.utc).isoformat(),'original_url':f'/api/scenarios/{identity}/original.png'}
        with self.lock:
            if self.busy:raise ValueError('A scenario is already running. Wait for it to finish.')
            self.busy.add(identity)
        self.write(identity,record)
        threading.Thread(target=self.generate,args=(identity,),daemon=True).start()
        return record

    def image_url(self,identity,filename='original.png'):
        data=(self.folder(identity)/filename).read_bytes()
        return 'data:image/png;base64,'+base64.b64encode(data).decode()

    def analyze_photo(self,identity):
        response=requests.post(self.endpoint+'/chat/completions',json={
            'model':self.model,'temperature':0,'max_tokens':1000,
            'messages':[{'role':'user','content':[{'type':'text','text':SCENE_PROMPT},
                {'type':'image_url','image_url':{'url':self.image_url(identity,'generated.png')}}]}]},timeout=(10,900))
        response.raise_for_status();record=response.json()
        if record.get('model')!=self.model:raise ValueError('Photo-analysis checkpoint identity changed.')
        analysis=validate_analysis(record['choices'][0]['message']['content'],basis='generated_flood_image')
        analysis['model']=self.model
        if not analysis['features']:
            try:
                grounded=requests.post(self.endpoint+'/chat/completions',json={
                    'model':self.model,'temperature':0,'max_tokens':400,'use_base_model':True,
                    'messages':[{'role':'user','content':[{'type':'text','text':GROUNDING_PROMPT.replace('ORIGINAL image','supplied generated flood image')},
                        {'type':'image_url','image_url':{'url':self.image_url(identity,'generated.png')}}]}]},timeout=(10,900))
                grounded.raise_for_status();payload=grounded.json()
                if payload.get('model')!='Qwen/Qwen3-VL-8B-Instruct' or payload.get('adapter_applied') is not False:raise ValueError('Grounding checkpoint identity changed.')
                analysis=merge_grounded_buildings(analysis,payload['choices'][0]['message']['content'])
            except Exception as exc:analysis['annotation_error']=str(exc)[:1000]
        analysis.update(basis='generated_flood_image',image_url=f'/api/scenarios/{identity}/generated.png')
        return analysis

    def generate(self,identity):
        record=json.loads((self.folder(identity)/'job.json').read_text())
        try:
            record['state']='analyzing_and_generating';record['stage']='generating_flood_preview';self.write(identity,record)
            r=requests.post(self.endpoint+'/flood-edits',json={'image':self.image_url(identity),'severity':record['severity']},timeout=(10,1800))
            if not r.ok:
                try:message=r.json().get('error',r.text)
                except ValueError:message=r.text
                raise RuntimeError(str(message)[:2000])
            result=r.json();data=base64.b64decode(result.pop('image').split(',',1)[1],validate=True)
            metadata=PngInfo();metadata.add_text('Description','AI-generated hypothetical flood illustration; not an observation or forecast.')
            metadata.add_text('Generator',result['generator']+' @ '+result['revision'])
            with Image.open(io.BytesIO(data)) as generated:
                generated.save(self.folder(identity)/'generated.png',pnginfo=metadata)
            record.update(result,stage='reviewing_generated_photo',generated_url=f'/api/scenarios/{identity}/generated.png')
            self.write(identity,record)
            try:record['photo_analysis']=self.analyze_photo(identity)
            except Exception as exc:record['photo_analysis']={'status':'failed','error':str(exc)[:1500],'features':[],'verified_safe':False,'basis':'generated_flood_image'}
            record.update(state='ready',stage='complete')
        except Exception as exc:record.update(state='failed',error=str(exc))
        finally:
            self.write(identity,record)
            with self.lock:self.busy.discard(identity)

    def resolve_location(self,identity,query=None):
        if query:
            place=geocode(query)
            match={'method':'address_search','suggested':place,'candidates':[place],'requires_confirmation':True,
                   'note':'Search result; verify the map pin is the photo location.'}
        else:
            match=self.locator.match((self.folder(identity)/'original.png').read_bytes())
            record=self.read(identity)
            if record.get('gps') and not match.get('candidates'):
                place={**record['gps'],'label':'Photo GPS metadata'}
                match.update(method='photo_gps',suggested=place,candidates=[place],note='Verify the photo GPS position on the map.')
        with self.lock:
            if identity in self.busy:raise ValueError('Wait for this scenario job to finish before changing its location.')
            record=self.read(identity)
            record['location_match']=match;record.pop('confirmed_location',None);record.pop('plan',None)
            if record['state']=='planned':record['state']='ready'
            self.write(identity,record)
        return match

    def confirm_location(self,identity,lat,lon):
        lat,lon=float(lat),float(lon)
        if not (math.isfinite(lat) and math.isfinite(lon) and -85<=lat<=85 and -180<=lon<=180):
            raise ValueError('Invalid map coordinates.')
        place={'lat':lat,'lon':lon,'label':f'{lat:.6f}, {lon:.6f}','accuracy':'User-confirmed map pin'}
        with self.lock:
            if identity in self.busy:raise ValueError('Wait for this scenario job to finish before confirming a location.')
            record=self.read(identity)
            if record['state'] not in ('ready','planned'):raise ValueError('Generate the flood illustration before confirming its location.')
            place.update(confirmed_at=datetime.now(timezone.utc).isoformat(),method='user_confirmed_map_pin')
            record['confirmed_location']=place;record.pop('plan',None);record.pop('plan_error',None)
            if record['state']=='planned':record['state']='ready'
            self.write(identity,record)
        return place

    def start_plan(self,identity,location=None):
        with self.lock:
            record=self.read(identity)
            if record['state'] not in ('ready','planned'):raise ValueError('Finish generating the illustration first.')
            confirmed=record.get('confirmed_location')
            if not confirmed:raise ValueError('Confirm the photo location on the map before finding destinations.')
            # Only saved, explicitly confirmed coordinates become the navigation origin.
            location=f"{confirmed['lat']:.8f}, {confirmed['lon']:.8f}"
            if self.busy:raise ValueError('Another scenario job is still running.')
            self.busy.add(identity)
            record.pop('plan',None);record.pop('plan_error',None);record['plan_stage']='searching_shelters'
            record['state']='finding_destinations';self.write(identity,record)
        threading.Thread(target=self.plan,args=(identity,location),daemon=True).start()
        return record

    def plan(self,identity,location):
        record=json.loads((self.folder(identity)/'job.json').read_text())
        try:
            def model_call(prompt):
                r=requests.post(self.endpoint+'/chat/completions',json={'model':self.model,'max_tokens':300,
                    'messages':[{'role':'user','content':[{'type':'text','text':prompt},
                    {'type':'image_url','image_url':{'url':self.image_url(identity)}}]}]},timeout=(2,6))
                r.raise_for_status();return r.json()['choices'][0]['message']['content']
            def progress(stage,partial):
                record['plan_stage']=stage
                if partial is not None:record['plan']=partial
                self.write(identity,record)
            record['plan']=build_plan(location,model_call,self.route_call,progress=progress);record['state']='planned';record['plan_stage']='complete';record.pop('plan_error',None)
        except Exception as exc:record.update(state='ready',plan_error=str(exc))
        finally:
            self.write(identity,record)
            with self.lock:self.busy.discard(identity)
