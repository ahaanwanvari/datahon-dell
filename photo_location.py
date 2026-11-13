"""Conservative matching to registered local imagery; not general image geolocation."""
import csv
import hashlib
import io
import json
import math
import os
from pathlib import Path
import threading
import numpy as np
from PIL import Image,ImageOps

VERSION='utsa-location-v1'


def pixel_digest(image):
    image=ImageOps.exif_transpose(image).convert('RGB')
    return hashlib.sha256(str(image.size).encode()+image.tobytes()).hexdigest()


def descriptors(image):
    image=ImageOps.exif_transpose(image).convert('RGB')
    rgb=np.asarray(image.resize((32,32),Image.Resampling.LANCZOS),dtype=np.float32)/255
    gray=rgb@np.array([.299,.587,.114],dtype=np.float32)
    x=np.arange(32,dtype=np.float32)
    basis=np.cos(np.pi*(2*x[None,:]+1)*np.arange(8,dtype=np.float32)[:,None]/64)
    coefficients=(basis@gray@basis.T).ravel()[1:]
    bits=coefficients>np.median(coefficients)
    return rgb.ravel(),bits


class PhotoLocator:
    def __init__(self,state,data_root=None):
        self.data_root=Path(data_root or os.environ.get('FLOOD_IMAGE_DATA',str(Path.home()/'jupyterlab/Texas_Flood_Student_Data'))).resolve()
        self.metadata=self.data_root/'image_metadata.csv'
        self.cache=Path(state)/'photo-locations.npz'
        self.lock=threading.RLock();self.rows=None

    def ensure(self):
        with self.lock:
            if self.rows is not None:return
            if not self.metadata.exists():
                self.rows=[];self.rgb=np.empty((0,3072),np.float32);self.bits=np.empty((0,63),bool);return
            signature=hashlib.sha256(VERSION.encode()+self.metadata.read_bytes()).hexdigest()
            try:
                with np.load(self.cache,allow_pickle=False) as saved:
                    if str(saved['signature'])!=signature:raise ValueError('Outdated location index.')
                    self.rows=json.loads(str(saved['rows']));self.rgb=saved['rgb'];self.bits=saved['bits']
                    return
            except (OSError,ValueError,KeyError):pass
            rows=[];features=[];hashes=[]
            with self.metadata.open() as stream:
                for row in csv.DictReader(stream):
                    try:
                        lat,lon=float(row['latitude']),float(row['longitude'])
                        if not(math.isfinite(lat) and math.isfinite(lon) and -85<=lat<=85 and -180<=lon<=180):continue
                        path=(self.data_root/row['image_path']).resolve()
                        if not path.is_relative_to(self.data_root):continue
                        raw=path.read_bytes();sha=hashlib.sha256(raw).hexdigest()
                        if row.get('sha256') and row['sha256']!=sha:continue
                        with Image.open(io.BytesIO(raw)) as image:
                            pixels=pixel_digest(image);rgb,bits=descriptors(image)
                        public={key:row.get(key,'') for key in ['image_id','image_path','acquisition_date','locality','source_url','location_precision']}
                        public.update(lat=lat,lon=lon,file_sha256=sha,pixel_sha256=pixels)
                        bounds={key:float(row[key]) for key in ['west','south','east','north'] if row.get(key)}
                        if len(bounds)==4:public['bounds']=bounds
                        rows.append(public);features.append(rgb);hashes.append(bits)
                    except (OSError,ValueError,KeyError):continue
            self.rows=rows;self.rgb=np.asarray(features,dtype=np.float32).reshape(-1,3072);self.bits=np.asarray(hashes,dtype=bool).reshape(-1,63)
            self.cache.parent.mkdir(parents=True,exist_ok=True)
            temporary=self.cache.with_suffix('.tmp')
            with temporary.open('wb') as output:
                np.savez_compressed(output,signature=np.array(signature),rows=np.array(json.dumps(rows)),rgb=self.rgb,bits=self.bits)
            temporary.replace(self.cache)

    def public(self,row):
        return {k:v for k,v in row.items() if k not in ('image_path','file_sha256','pixel_sha256')}

    def result(self,indices,method,metrics=None):
        rows=[self.rows[i] for i in indices]
        ambiguous=bool(rows) and any(abs(row['lat']-rows[0]['lat'])>.0001 or abs(row['lon']-rows[0]['lon'])>.0001 for row in rows[1:])
        candidates=[self.public(row) for row in rows[:3]]
        result={'method':method,'candidates':candidates,'requires_confirmation':True,
                'indexed_images':len(self.rows),'ambiguous':ambiguous,'suggested':None}
        if candidates and not ambiguous and method!='possible':result['suggested']=candidates[0]
        if metrics:result['similarity_metrics']=metrics
        result['note']='Dataset coordinates describe the aerial image footprint center, not a verified street address or your current position.' if candidates else 'No reliable match in the registered imagery. Enter the photo location or select it on the map.'
        return result

    def match(self,raw):
        self.ensure()
        with Image.open(io.BytesIO(raw)) as image:
            if image.width*image.height>40_000_000:raise ValueError('Use a photo below 40 megapixels.')
            sha=hashlib.sha256(raw).hexdigest()
            exact=[i for i,row in enumerate(self.rows) if row['file_sha256']==sha]
            if exact:return self.result(exact,'exact_file')
            pixels=pixel_digest(image)
            exact=[i for i,row in enumerate(self.rows) if row['pixel_sha256']==pixels]
            if exact:return self.result(exact,'exact_pixels')
            rgb,bits=descriptors(image)
        if not self.rows:return self.result([],'none')
        distances=np.count_nonzero(self.bits!=bits,axis=1)
        rmse=np.sqrt(np.mean((self.rgb-rgb)**2,axis=1))
        order=np.argsort(rmse)
        best=int(order[0]);runner=float(rmse[order[1]]) if len(order)>1 else 1
        metrics={'perceptual_hash_distance':int(distances[best]),'rgb_rmse':round(float(rmse[best]),5),'runner_up_rmse':round(runner,5),'calibrated_probability':False}
        close=[int(i) for i in order[:3] if rmse[i]<=rmse[best]+.025 and distances[i]<=8]
        if distances[best]<=6 and rmse[best]<=.045:
            return self.result(close or [best],'visual_copy',metrics)
        if distances[best]<=10 and rmse[best]<=.075:
            return self.result(close or [best],'possible',metrics)
        return self.result([],'none',metrics)

    def reference(self,image_id):
        self.ensure()
        row=next((r for r in self.rows if r['image_id']==image_id),None)
        if row is None:raise ValueError('Unknown reference image.')
        path=(self.data_root/row['image_path']).resolve()
        if not path.is_relative_to(self.data_root):raise ValueError('Invalid reference path.')
        return path


if __name__=='__main__':
    root=Path(__file__).resolve().parent/'.state'
    locator=PhotoLocator(root);locator.ensure()
    print('Indexed',len(locator.rows),'georeferenced photos:',locator.cache)
