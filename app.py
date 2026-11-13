"""Local Flood Change Explorer. No cloud account or browser dependencies."""
import base64
from bisect import bisect_left
import csv
import hashlib
import io
import json
import math
import os
import re
import sqlite3
import threading
import time
import uuid
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

import numpy as np
import requests
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent
STATE = Path(os.environ.get('FLOOD_STATE', str(ROOT / '.state'))).resolve()
STATE.mkdir(parents=True, exist_ok=True)
DB = STATE / 'explorer.sqlite'
BASE = os.environ.get('FLOOD_VLM_URL', 'http://127.0.0.1:8000/v1').rstrip('/')
MODEL = os.environ.get('FLOOD_MODEL', 'Qwen/Qwen3-VL-8B-Instruct')
KEY = os.environ.get('FLOOD_API_KEY', 'NONE')
LOCK = threading.Lock()
JOB = dict(running=False, done=0, total=0, message='Ready', errors=[])


def connect():
    c = sqlite3.connect(DB, timeout=30)
    c.row_factory = sqlite3.Row
    c.execute('PRAGMA foreign_keys=ON')
    return c


def init():
    with connect() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS images (
          id TEXT PRIMARY KEY, collection TEXT, location_id TEXT, name TEXT, date TEXT,
          lat REAL, lon REAL, path TEXT, source_url TEXT, sensor TEXT, aligned INTEGER,
          sha TEXT, UNIQUE(collection,location_id,date));
        CREATE TABLE IF NOT EXISTS image_provenance (
          image_id TEXT PRIMARY KEY REFERENCES images(id) ON DELETE CASCADE, metadata TEXT);
        CREATE TABLE IF NOT EXISTS events (
          id TEXT PRIMARY KEY, before_id TEXT REFERENCES images(id), after_id TEXT REFERENCES images(id),
          summary TEXT, kind TEXT, strength REAL, uncertainty TEXT, evidence TEXT,
          model TEXT, fingerprint TEXT, review TEXT DEFAULT 'automatic', note TEXT DEFAULT '',
          created TEXT DEFAULT CURRENT_TIMESTAMP);
        ''')


def digest(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1024*1024), b''):
            h.update(chunk)
    return h.hexdigest()


def import_manifest(path):
    path = Path(path).expanduser().resolve()
    with path.open(newline='') as stream:
        rows = list(csv.DictReader(stream))
    if not rows or len(rows) > 100000:
        raise ValueError('Manifest must contain 1–100,000 image rows.')
    required = {'location_id', 'acquisition_date', 'image_path', 'latitude', 'longitude'}
    if not required.issubset(rows[0]):
        raise ValueError('Required columns: ' + ', '.join(sorted(required)))
    collection = 'local'
    pending, seen, provenance = [], set(), []
    for n, r in enumerate(rows, 2):
        loc = r['location_id'].strip()
        when = date.fromisoformat(r['acquisition_date']).isoformat()
        if not loc or (loc, when) in seen:
            raise ValueError(f'Row {n}: empty location or duplicate location/date.')
        seen.add((loc, when))
        if not r['latitude'].strip() and not r['longitude'].strip() and r.get('georeferenced', '').lower() == 'false':
            lat = lon = None
        else:
            lat, lon = float(r['latitude']), float(r['longitude'])
            if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                raise ValueError(f'Row {n}: invalid coordinates.')
        p = (path.parent / r['image_path']).resolve()
        with Image.open(p) as im:
            im.verify()
        source = r.get('source_url', '')
        if source and urlparse(source).scheme not in ('http', 'https'):
            raise ValueError(f'Row {n}: source_url must use http or https.')
        ident = hashlib.sha256(f'{collection}:{loc}:{when}'.encode()).hexdigest()[:24]
        provenance.append((ident, json.dumps({k:v for k,v in r.items() if k not in {'image_path'}})))
        pending.append((ident, collection, loc, r.get('locality') or loc, when, lat, lon,
                        str(p), source, r.get('sensor', 'Unknown'),
                        int(r.get('aligned', '').lower() in ('true', '1', 'yes')), digest(p)))
    # Validate everything first; an invalid row cannot partially replace a collection.
    with connect() as c:
        c.execute("DELETE FROM events WHERE after_id IN (SELECT id FROM images WHERE collection='local')")
        c.execute("DELETE FROM images WHERE collection='local'")
        c.executemany('INSERT INTO images VALUES (?,?,?,?,?,?,?,?,?,?,?,?)', pending)
        c.executemany('INSERT INTO image_provenance VALUES (?,?)', provenance)
    return len(pending)


def encoded(path):
    with Image.open(path) as im:
        im = im.convert('RGB')
        im.thumbnail((768, 768))
        out = io.BytesIO()
        im.save(out, format='JPEG', quality=85)
    return 'data:image/jpeg;base64,' + base64.b64encode(out.getvalue()).decode()


PROMPT = '''Compare two satellite observations of the SAME location. Image 1 is BEFORE; image 2 AFTER.
Describe only visible evidence. Do not assume flooding, road damage, or alignment from appearance alone.
Clouds, shadows, seasonality, different viewpoints and sensors can mimic change.
Return ONLY JSON with keys: summary (concise visible change), kind (one of water_increase,
water_decrease, stable, uncertain), strength (0 to 1 apparent magnitude, NOT probability),
uncertainty (specific limitations), evidence (specific visible regions supporting the description).
Dates are observation dates, never assert the exact onset date. No markdown.'''


def analyze(a, b):
    prompt = f'{PROMPT}\nObservation dates: {a["date"]} and {b["date"]}. Sensors: {a["sensor"]}, {b["sensor"]}. Alignment declared by importer: {bool(a["aligned"] and b["aligned"])}.'
    r = requests.post(BASE + '/chat/completions', headers={'Authorization': 'Bearer ' + KEY},
        json={'model': MODEL, 'temperature': 0, 'max_tokens': 650,
              'chat_template_kwargs': {'enable_thinking': False},
              'response_format': {'type': 'json_schema', 'json_schema': {
                  'name': 'change_observation', 'strict': True, 'schema': {
                      'type': 'object', 'additionalProperties': False,
                      'properties': {
                          'summary': {'type': 'string'},
                          'kind': {'type': 'string', 'enum': ['water_increase','water_decrease','stable','uncertain']},
                          'strength': {'type': 'number', 'minimum': 0, 'maximum': 1},
                          'uncertainty': {'type': 'string'}, 'evidence': {'type': 'string'}},
                      'required': ['summary','kind','strength','uncertainty','evidence']}}},
              'messages': [{'role': 'user', 'content': [{'type': 'text', 'text': prompt},
                  {'type': 'image_url', 'image_url': {'url': encoded(a['path'])}},
                  {'type': 'image_url', 'image_url': {'url': encoded(b['path'])}}]}]}, timeout=(10, 180))
    r.raise_for_status()
    content = r.json()['choices'][0]['message']['content']
    match = re.search(r'\{.*\}', content, re.S)
    if not match:
        raise ValueError('Model did not return JSON')
    result = json.loads(match.group())
    for key in ('summary', 'uncertainty', 'evidence'):
        if not isinstance(result.get(key), str) or not result[key].strip():
            raise ValueError('Model response missing ' + key)
    if result.get('kind') not in {'water_increase', 'water_decrease', 'stable', 'uncertain'}:
        raise ValueError('Invalid model change type')
    strength = float(result['strength'])
    if not math.isfinite(strength) or not 0 <= strength <= 1:
        raise ValueError('Invalid model magnitude')
    result['strength'] = strength
    return result


def worker():
    try:
        with connect() as c:
            images = [dict(r) for r in c.execute("SELECT * FROM images WHERE collection='local' ORDER BY location_id,date")]
        pairs = [(a,b) for a,b in zip(images, images[1:]) if a['location_id'] == b['location_id']]
        JOB.update(total=len(pairs), done=0, errors=[])
        for a,b in pairs:
            JOB['message'] = f'Analyzing {b["name"]} · {b["date"]}'
            fingerprint = hashlib.sha256((a['sha']+b['sha']+MODEL+PROMPT+'schema-v1').encode()).hexdigest()
            ident = a['id'] + ':' + b['id']
            try:
                with connect() as c:
                    old = c.execute('SELECT fingerprint FROM events WHERE id=?', (ident,)).fetchone()
                if not old or old['fingerprint'] != fingerprint:
                    result = analyze(a,b)
                    with connect() as c:
                        c.execute('''INSERT INTO events (id,before_id,after_id,summary,kind,strength,
                            uncertainty,evidence,model,fingerprint) VALUES (?,?,?,?,?,?,?,?,?,?)
                            ON CONFLICT(id) DO UPDATE SET summary=excluded.summary,kind=excluded.kind,
                            strength=excluded.strength,uncertainty=excluded.uncertainty,evidence=excluded.evidence,
                            model=excluded.model,fingerprint=excluded.fingerprint,review='automatic',note='' ''',
                            (ident,a['id'],b['id'], result['summary'], result['kind'],result['strength'],
                             result['uncertainty'],result['evidence'],MODEL,fingerprint))
            except Exception as exc:
                JOB['errors'].append(f'{b["name"]} {b["date"]}: {str(exc)[:250]}')
            JOB['done'] += 1
        JOB['message'] = f'Finished: {len(pairs)-len(JOB["errors"])} pairs available; {len(JOB["errors"])} failed.'
    except Exception as exc:
        JOB['message'] = str(exc)
    finally:
        JOB['running'] = False
        LOCK.release()


def start_job():
    if not LOCK.acquire(blocking=False):
        raise ValueError('An indexing job is already running.')
    JOB.update(running=True, done=0, total=0, errors=[], message='Preparing image pairs')
    threading.Thread(target=worker, daemon=True).start()


def snapshot():
    with connect() as c:
        images = [dict(r) for r in c.execute('SELECT * FROM images ORDER BY date')]
        events = [dict(r) for r in c.execute('SELECT * FROM events')]
        provenance = {r['image_id']:json.loads(r['metadata']) for r in c.execute('SELECT * FROM image_provenance')}
    by_id = {i['id']: i for i in images}
    # Empirical magnitude percentile, within a collection. It is not flood probability.
    cohorts = {}
    for e in events:
        cohorts.setdefault(by_id[e['after_id']]['collection'], []).append(e['strength'])
    for cohort in cohorts.values():
        cohort.sort()
    for e in events:
        cohort = cohorts[by_id[e['after_id']]['collection']]
        e['rarity'] = round(100*bisect_left(cohort, e['strength'])/(len(cohort)-1)) if len(cohort)>1 else 0
    for i in images:
        i.pop('path')
        i['provenance'] = provenance.get(i['id'], {})
    return dict(images=images, events=events, job=JOB.copy(), model=MODEL, endpoint=BASE)


def demo():
    with connect() as c:
        if c.execute("SELECT 1 FROM images WHERE collection='demo'").fetchone():
            # Demo files move with the app; saved absolute paths may refer to its old home.
            for row in c.execute("SELECT id,path FROM images WHERE collection='demo'").fetchall():
                relocated = STATE / (row['id'] + '.png')
                if relocated.is_file():
                    c.execute('UPDATE images SET path=? WHERE id=?', (str(relocated), row['id']))
            return
    rng = np.random.default_rng(17)
    places = [('River bend',29.76,-95.37), ('East crossing',29.81,-95.29),
              ('South fields',29.68,-95.32), ('Reservoir edge',29.79,-95.48)]
    dates = ['2025-05-01','2025-05-08','2025-05-15','2025-05-22']
    magnitudes = [[0,.8,.5,.1],[0,.2,.85,.3],[0,.1,.05,.05],[0,.05,.05,.05]]
    for j,(name,lat,lon) in enumerate(places):
        noise = rng.integers(-13,14,(512,512,1))
        land = np.clip(np.array([87,112,68])[None,None,:]+noise,0,255).astype('uint8')
        previous = None
        for k,day in enumerate(dates):
            ident = f'demo-{j}-{k}'
            path = STATE / f'{ident}.png'
            im = Image.fromarray(land.copy()); d = ImageDraw.Draw(im)
            for x in range(0,512,90):
                d.rectangle((x,0,x+2,512), fill=(150,137,93))
            for y in range(0,512,110):
                d.line((0,y,512,y), fill=(139,129,95),width=3)
            width = int(18+magnitudes[j][k]*110)
            d.line([(int(245+45*math.sin(y/65)),y) for y in range(512)],fill=(50,91,116),width=width)
            d.line((0,300,512,220),fill=(191,184,162),width=10)
            d.text((12,12),'SYNTHETIC DEMO | '+day,fill='white')
            im.save(path)
            with connect() as c:
                c.execute('INSERT INTO images VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
                    (ident,'demo',f'demo-{j}',name,day,lat,lon,str(path),'','Synthetic',1,digest(path)))
                if previous:
                    delta = magnitudes[j][k]-magnitudes[j][k-1]
                    kind = 'water_increase' if delta>.1 else 'water_decrease' if delta<-.1 else 'stable'
                    summary = {'water_increase':'Water-like coverage expands from the central channel into adjacent fields.',
                               'water_decrease':'Water-like coverage recedes toward the central channel.',
                               'stable':'The central channel and surrounding fields show little change.'}[kind]
                    c.execute('INSERT INTO events (id,before_id,after_id,summary,kind,strength,uncertainty,evidence,model,fingerprint) VALUES (?,?,?,?,?,?,?,?,?,?)',
                        (previous+':'+ident,previous,ident,summary,kind,abs(delta),
                         'Synthetic demonstration. Not a real flood observation.',
                         'Central sinuous blue channel and neighboring field boundaries.',
                         'Demo fixture (not AI inference)','demo'))
            previous = ident


class Handler(BaseHTTPRequestHandler):
    def send_json(self, obj, status=200):
        self.send_response(status); self.send_header('Content-Type','application/json')
        self.end_headers(); self.wfile.write(json.dumps(obj).encode())

    def valid_host(self):
        return self.headers.get('Host', '').split(':')[0] in ('127.0.0.1', 'localhost')

    def do_GET(self):
        if not self.valid_host():
            return self.send_json({'error':'Local access only'},403)
        parsed = urlparse(self.path)
        if parsed.path in ('/api/state','/api/export'):
            return self.send_json(snapshot())
        if parsed.path == '/api/image':
            ident = parse_qs(parsed.query).get('id',[''])[0]
            with connect() as c:
                row = c.execute('SELECT path FROM images WHERE id=?',(ident,)).fetchone()
            if not row:
                return self.send_json({'error':'Unknown image'},404)
            try:
                with Image.open(row['path']) as im:
                    im = im.convert('RGB'); im.thumbnail((1400,1400)); data=io.BytesIO(); im.save(data,format='JPEG')
                self.send_response(200); self.send_header('Content-Type','image/jpeg'); self.end_headers()
                self.wfile.write(data.getvalue()); return
            except Exception:
                return self.send_json({'error':'Source image unavailable'},404)
        paths = {'/':'index.html','/app.js':'app.js','/style.css':'style.css'}
        if parsed.path not in paths:
            return self.send_json({'error':'Not found'},404)
        p = ROOT / 'static' / paths[parsed.path]
        try:
            content = p.read_bytes()
        except OSError:
            return self.send_json({'error': 'App assets are unavailable. Restart run.sh from the current app folder.'}, 503)
        self.send_response(200)
        self.send_header('Content-Type', {'html':'text/html; charset=utf-8','js':'text/javascript; charset=utf-8','css':'text/css; charset=utf-8'}[p.suffix[1:]])
        self.send_header('Content-Length', str(len(content)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers(); self.wfile.write(content)

    def do_POST(self):
        if not self.valid_host():
            return self.send_json({'error':'Local access only'},403)
        # Local app: reject cross-origin writes and unbounded request bodies.
        origin = self.headers.get('Origin')
        if origin and urlparse(origin).netloc != self.headers.get('Host'):
            return self.send_json({'error':'Cross-origin request rejected'},403)
        try:
            length = int(self.headers.get('Content-Length',0))
            if not 0 < length < 65536:
                raise ValueError('Invalid request size')
            body = json.loads(self.rfile.read(length))
            if self.path == '/api/import':
                if not LOCK.acquire(blocking=False):
                    raise ValueError('Wait for indexing to finish before replacing imagery.')
                try:
                    count = import_manifest(body['path'])
                finally:
                    LOCK.release()
                return self.send_json({'count':count})
            if self.path == '/api/index':
                start_job(); return self.send_json({'started':True})
            if self.path == '/api/review':
                if body['review'] not in ('automatic','confirmed','rejected','unsure'):
                    raise ValueError('Invalid review state')
                with connect() as c:
                    changed = c.execute('UPDATE events SET review=?,note=? WHERE id=?',
                        (body['review'],str(body.get('note',''))[:4000],body['id'])).rowcount
                if not changed:
                    raise ValueError('Unknown observation')
                return self.send_json({'saved':True})
            return self.send_json({'error':'Not found'},404)
        except Exception as exc:
            return self.send_json({'error':str(exc)},400)


if __name__ == '__main__':
    init(); demo()
    port = int(os.environ.get('FLOOD_PORT','8765'))
    print(f'Flood Change Explorer: http://127.0.0.1:{port}',flush=True)
    ThreadingHTTPServer(('127.0.0.1',port),Handler).serve_forever()
