"""Prepare a provenance-preserving mix of labeled FloodNet VQA and UTSA replay."""
import ast
from collections import Counter,defaultdict
from concurrent.futures import ThreadPoolExecutor,as_completed
import hashlib
import json
from pathlib import Path
import random
import requests
import time

HOME=Path.home()/'jupyterlab'
LEGACY=HOME/'flood_training'
SOURCE=HOME/'FloodNet_VQA_source'
RUN=LEGACY/'runs/atlas-v2'
REV='9a2135a8d25b2cc471c9694b79107d1af4a64d8a'
REPO='takara-ai/FloodNet_2021-Track_2_Dataset_HF'


def dump(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(path.suffix+'.tmp');tmp.write_text(json.dumps(value,indent=2));tmp.replace(path)


def choose():
    rows=[]
    for path in sorted((SOURCE/'train_image/ann').glob('*.json')):
        stem=path.name.removesuffix('.json');number=int(Path(stem).stem)
        # Nearby numbered views remain in one group; leave a boundary buffer.
        if number%100<5 or number%100>94:continue
        for tag in json.loads(path.read_text())['tags']:
            if tag.get('name')!='question':continue
            q=ast.literal_eval(tag['value'])
            if 'Ground_Truth' not in q or q['Question_Type'] not in ('Condition_Recognition','Yes_No'):continue
            answer=str(q['Ground_Truth']).lower().strip()
            if answer=='flooded,non flooded':answer='mixed'
            if answer not in ('flooded','non flooded','mixed','yes','no'):continue
            rows.append({'id':f"floodnet:{q['Question_ID']}",'filename':stem,'question':q['Question'],
               'answer':answer,'question_type':q['Question_Type'],'group':str(number//100),
               'annotation_file':str(path),'label_source':'published_vqa_ground_truth',
               'dataset':REPO,'dataset_revision':REV})
    groups=sorted({r['group'] for r in rows});random.Random(3407).shuffle(groups)
    nv=max(1,round(len(groups)*.15));nt=max(1,round(len(groups)*.15))
    mapping={g:('validation' if i<nv else 'test' if i<nv+nt else 'train') for i,g in enumerate(groups)}
    selected=[]
    for split,cap in [('train',128),('validation',24),('test',24)]:
        buckets=defaultdict(list)
        for row in rows:
            if mapping[row['group']]==split:buckets[(row['question_type'],row['answer'])].append(row)
        per_image=Counter()
        for key,items in sorted(buckets.items()):
            random.Random(str(key)+split+'3407').shuffle(items)
            n=0
            for row in items:
                if per_image[row['filename']]>=2:continue
                row=dict(row,split=split);selected.append(row);per_image[row['filename']]+=1;n+=1
                if n>=cap:break
    return selected,mapping


def fetch_images(rows):
    paths=sorted({f"train_image/img/{r['filename']}" for r in rows})
    objects=[]
    for relative in paths:
        text=(SOURCE/relative).read_text()
        fields=dict(line.split(' ',1) for line in text.splitlines() if ' ' in line)
        objects.append({'oid':fields['oid'].split(':')[1],'size':int(fields['size']),'path':relative})
    output=HOME/'FloodNet_VQA_images';output.mkdir(exist_ok=True)
    pending=[o for o in objects if not (output/Path(o['path']).name).exists()]
    print(f'Downloading {len(pending)} labeled source images; {sum(o["size"] for o in pending)/1e9:.2f} GB.',flush=True)
    def fetch(obj):
        dest=output/Path(obj['path']).name
        for attempt in range(4):
            try:
                r=requests.get(obj['url'],headers=obj.get('headers',{}),timeout=(20,120),stream=True);r.raise_for_status()
                temp=dest.with_suffix('.partial');h=hashlib.sha256()
                with temp.open('wb') as f:
                    for chunk in r.iter_content(1024*1024):f.write(chunk);h.update(chunk)
                if h.hexdigest()!=obj['oid']:raise ValueError('Source image SHA-256 mismatch')
                temp.replace(dest);return obj['oid']
            except Exception:
                if attempt==3:raise
                time.sleep(2**attempt)
    for start in range(0,len(pending),100):
        chunk=pending[start:start+100]
        url=f'https://huggingface.co/datasets/{REPO}.git/info/lfs/objects/batch'
        response=requests.post(url,headers={'Accept':'application/vnd.git-lfs+json','Content-Type':'application/vnd.git-lfs+json'},
            json={'operation':'download','transfers':['basic'],'objects':[{'oid':o['oid'],'size':o['size']} for o in chunk]},timeout=60)
        response.raise_for_status();actions={o['oid']:o for o in response.json()['objects']}
        for obj in chunk:
            action=actions[obj['oid']]['actions']['download'];obj['url']=action['href'];obj['headers']=action.get('header',{})
        with ThreadPoolExecutor(max_workers=8) as pool:
            for i,job in enumerate(as_completed([pool.submit(fetch,o) for o in chunk]),1):
                job.result()
                if i%20==0:print(f'Downloaded {start+i}/{len(pending)} images',flush=True)
    # Preprocess once so training does not repeatedly decode 12 MP originals.
    from PIL import Image
    previews=RUN/'previews';previews.mkdir(parents=True,exist_ok=True)
    for obj in objects:
        source=output/Path(obj['path']).name
        assert hashlib.sha256(source.read_bytes()).hexdigest()==obj['oid']
        dest=previews/source.with_suffix('.png').name
        if not dest.exists():
            with Image.open(source) as im:
                im=im.convert('RGB');im.thumbnail((448,448));im.save(dest)
    hashes={Path(o['path']).name:o['oid'] for o in objects}
    for row in rows:
        row['images']=[str(previews/Path(row['filename']).with_suffix('.png').name)]
        row['source_image_sha256']=hashes[row['filename']]
        row['prompt']=row['question']+' Answer with only flooded, non flooded, mixed, yes, or no, as appropriate. Describe the image condition, not current road safety.'
        row['target']=row['answer'];row['task']='single_image_vqa'
    return rows


def add_replay(rows):
    manifest=json.loads((LEGACY/'pairs.json').read_text())
    labels={r['id']:r for r in (json.loads(x) for x in (LEGACY/'labels.jsonl').read_text().splitlines())}
    import ast
    # Preserve the exact earlier training prompt without importing its application code.
    tree=ast.parse((LEGACY/'workflow.py').read_text())
    old_prompt=next(ast.literal_eval(n.value) for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='PROMPT' for t in n.targets))
    def pair_prompt(pair):
        a,b=pair['before'],pair['after']
        return old_prompt + f"\nDates: {a['acquisition_date']} → {b['acquisition_date']}. Sensors: {a['source_agency']}, {b['source_agency']}."
    for split,cap in [('train',96),('validation',16)]:
        buckets=defaultdict(list)
        for pair in manifest['pairs']:
            if pair['split']==split and pair['id'] in labels:buckets[labels[pair['id']]['target']['kind']].append(pair)
        for kind,items in buckets.items():
            random.Random(split+kind).shuffle(items)
            for pair in items[:cap if kind=='water_increase' else 48 if split=='train' else 16]:
                rows.append({'id':'replay:'+pair['id'],'split':split,'task':'paired_change',
                  'images':[str(HOME/'Texas_Flood_Student_Data'/pair[k]['image_path']) for k in ['before','after']],
                  'prompt':pair_prompt(pair),'target':json.dumps(labels[pair['id']]['target']),
                  'label_source':'ai_generated_unverified','dataset':'UTSA','group':pair['id']})
    # Identical-image controls teach no-change, not no-flood.
    for split,count in [('train',64),('validation',16)]:
        candidates=[p for p in manifest['pairs'] if p['split']==split]
        random.Random('identity'+split).shuffle(candidates)
        for pair in candidates[:count]:
            image=str(HOME/'Texas_Flood_Student_Data'/pair['before']['image_path'])
            target={'summary':'The two supplied images are identical; no inter-image change is visible.',
               'kind':'stable','strength':0.0,'uncertainty':'This does not establish absence of flooding within the scene or conditions outside the images.',
               'evidence':'The same pixels and features appear in both images.'}
            rows.append({'id':'identity:'+pair['id'],'split':split,'task':'identity_control','images':[image,image],
              'prompt':old_prompt.replace('in chronological order','in the supplied order'),
              'target':json.dumps(target),'label_source':'deterministic_identical_input','dataset':'UTSA','group':pair['id']})
    return rows


def main():
    RUN.mkdir(parents=True,exist_ok=True)
    rows,groups=choose();dump(RUN/'selection.json',{'rows':rows,'groups':groups})
    rows=fetch_images(rows);rows=add_replay(rows)
    # Exact image identity must not cross splits, including images reused for QA variants.
    seen={}
    for row in rows:
        for image in row['images']:
            h=hashlib.sha256(Path(image).read_bytes()).hexdigest()
            if h in seen and seen[h]!=row['split']:raise RuntimeError('Image leak across splits')
            seen[h]=row['split']
    dump(RUN/'dataset.json',rows)
    summary={split:dict(Counter(r['task'] for r in rows if r['split']==split)) for split in ['train','validation','test']}
    dump(RUN/'data_report.json',{'counts':summary,'vqa_answer_counts':{s:dict(Counter(r['answer'] for r in rows if r['split']==s and r['task']=='single_image_vqa')) for s in ['train','validation','test']},
      'source':REPO,'revision':REV,'excluded':'Counts excluded because small objects are unreliable at 448 px; official validation/test answers are withheld.',
      'split_method':'Labeled original training pool regrouped by filename hundred-block, with 5-image boundary buffers; no group/image crosses splits. Same event; not verified geographic independence.',
      'limits':'VQA answers are published dataset ground truth, not new human reviews. UTSA replay remains AI-generated; identity controls only prove no inter-image change.'})
    print(json.dumps(summary,indent=2),flush=True)

if __name__=='__main__':main()
