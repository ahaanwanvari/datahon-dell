"""Pipeline regression checks; no model download or server required."""
import csv
import os
import tempfile
import unittest
import threading
import requests
from pathlib import Path
from unittest.mock import patch

TEMP = tempfile.TemporaryDirectory()
os.environ['FLOOD_STATE'] = TEMP.name
import app
from PIL import Image


class PipelineTests(unittest.TestCase):
    def setUp(self):
        app.init()
        with app.connect() as c:
            c.execute('DELETE FROM events'); c.execute('DELETE FROM images')
        self.manifest = Path(TEMP.name) / 'manifest.csv'
        for n in range(4):
            Image.new('RGB',(64,64),(20,n*30,70)).save(Path(TEMP.name)/f'{n}.png')

    def write_manifest(self, bad=False):
        with self.manifest.open('w',newline='') as f:
            w=csv.writer(f)
            w.writerow(['location_id','acquisition_date','image_path','latitude','longitude'])
            for n in range(4):
                w.writerow(['a' if n<3 else 'b',f'2025-01-0{n+1}',
                            'missing.png' if bad and n==3 else f'{n}.png',29,-95])

    def test_invalid_import_is_atomic(self):
        self.write_manifest(); self.assertEqual(app.import_manifest(self.manifest),4)
        self.write_manifest(bad=True)
        with self.assertRaises(FileNotFoundError):app.import_manifest(self.manifest)
        self.assertEqual(len(app.snapshot()['images']),4)

    def test_pairs_cache_and_annotations(self):
        self.write_manifest(); app.import_manifest(self.manifest)
        result=dict(summary='Water expands',kind='water_increase',strength=.7,
                    uncertainty='Cloud shadows possible',evidence='Central channel')
        with patch.object(app,'analyze',return_value=result) as model:
            app.LOCK.acquire(); app.worker()
            self.assertEqual(model.call_count,2)  # Do not pair different locations.
            snapshot=app.snapshot(); self.assertEqual(len(snapshot['events']),2)
            self.assertNotIn('path',snapshot['images'][0])
            with app.connect() as c:
                c.execute("UPDATE events SET review='confirmed',note='Keep this'")
            app.LOCK.acquire(); app.worker()
            self.assertEqual(model.call_count,2)
            self.assertTrue(all(e['note']=='Keep this' for e in app.snapshot()['events']))
            self.assertFalse(app.JOB['running'])

    def test_failed_pair_continues_and_retries(self):
        self.write_manifest();app.import_manifest(self.manifest)
        result=dict(summary='Stable',kind='stable',strength=.1,uncertainty='No calibration',evidence='Channel')
        with patch.object(app,'analyze',side_effect=[ValueError('bad model JSON'),result]):
            app.LOCK.acquire();app.worker()
        self.assertEqual(len(app.snapshot()['events']),1)
        self.assertEqual(len(app.JOB['errors']),1)
        with patch.object(app,'analyze',return_value=result) as model:
            app.LOCK.acquire();app.worker()
            self.assertEqual(model.call_count,1)
        self.assertEqual(len(app.snapshot()['events']),2)

    def test_demo_paths_repair_after_move(self):
        app.demo()
        with app.connect() as c:
            c.execute("UPDATE images SET path='/old/moved/folder/image.png' WHERE collection='demo'")
        app.demo()
        with app.connect() as c:
            rows = c.execute("SELECT path FROM images WHERE collection='demo'").fetchall()
        self.assertTrue(all(Path(row['path']).is_file() for row in rows))

    def test_static_assets_never_return_empty_success(self):
        server = app.ThreadingHTTPServer(('127.0.0.1', 0), app.Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f'http://127.0.0.1:{server.server_port}'
        try:
            with patch.object(app.Handler, 'log_message'):
                for route in ('/', '/style.css', '/app.js'):
                    response = requests.get(base + route, timeout=5)
                    self.assertEqual(response.status_code, 200)
                    self.assertGreater(len(response.content), 100)
                    self.assertEqual(int(response.headers['Content-Length']), len(response.content))
                with patch.object(app, 'ROOT', Path(TEMP.name) / 'missing-assets'):
                    response = requests.get(base + '/', timeout=5)
                    self.assertEqual(response.status_code, 503)
                    self.assertIn('Restart', response.json()['error'])
        finally:
            server.shutdown(); server.server_close(); thread.join()

    def test_caption_only_image_keeps_missing_coordinates(self):
        with self.manifest.open('w', newline='') as f:
            w=csv.writer(f)
            w.writerow(['location_id','acquisition_date','image_path','latitude','longitude','georeferenced','original_image_id'])
            w.writerow(['caption-only','2025-07-04','0.png','','','false','AF001'])
        app.import_manifest(self.manifest)
        image=app.snapshot()['images'][0]
        self.assertIsNone(image['lat']); self.assertIsNone(image['lon'])
        self.assertEqual(image['provenance']['original_image_id'],'AF001')
        with self.manifest.open('w', newline='') as f:
            w=csv.writer(f)
            w.writerow(['location_id','acquisition_date','image_path','latitude','longitude'])
            w.writerow(['missing-without-declaration','2025-07-04','0.png','',''])
        with self.assertRaises(ValueError):app.import_manifest(self.manifest)

    def test_utsa_adapter_preserves_explicit_pairing(self):
        import import_utsa
        folder=Path(TEMP.name)/'adapter'
        folder.mkdir(exist_ok=True)
        fields=['image_id','image_path','paired_image_id','pair_key','pair_id','locality','source_agency','platform',
                'acquisition_date','latitude','longitude','georeferenced','west','south','east','north',
                'width_px','height_px','output_crs']
        common=dict(locality='Test place',source_agency='NOAA',platform='aircraft',latitude='29',longitude='-95',
                    georeferenced='true',west='-96',south='28',east='-94',north='30',width_px='1024',height_px='1024',output_crs='EPSG:3857')
        rows=[dict(common,image_id='before',image_path='0.png',paired_image_id='after',pair_key='source/pair1',pair_id='pair1',acquisition_date='2016-09-28'),
              dict(common,image_id='after',image_path='1.png',paired_image_id='before',pair_key='source/pair1',pair_id='pair1',acquisition_date='2017-08-30'),
              dict(common,image_id='single',image_path='2.png',paired_image_id='',pair_key='',pair_id='',acquisition_date='2025-07-11')]
        with (folder/'image_metadata.csv').open('w',newline='') as f:
            w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
        result=import_utsa.build_manifest(folder)
        self.assertEqual(result['paired_locations'],1);self.assertEqual(result['standalone_images'],1)
        with (folder/'explorer_manifest.csv').open(newline='') as f:converted=list(csv.DictReader(f))
        self.assertEqual(converted[0]['location_id'],converted[1]['location_id'])
        self.assertNotEqual(converted[0]['location_id'],converted[2]['location_id'])
        self.assertEqual(converted[0]['aligned'],'true')

    def test_demo_provenance(self):
        app.demo(); s=app.snapshot()
        self.assertEqual(len(s['images']),16)
        self.assertEqual(len(s['events']),12)
        self.assertTrue(all('Demo' in e['model'] for e in s['events']))

    def test_texas_route_returns_unscreened_alternatives(self):
        class Response:
            def raise_for_status(self): pass
            def json(self):
                return {'code':'Ok','routes':[{'distance':4200,'duration':360,'geometry':{'coordinates':[[-95.37,29.76],[-95.35,29.78]]},'legs':[{'steps':[{'name':'Main Street'}]}]}]}
        with patch.object(app.requests,'get',return_value=Response()):
            result=app.route_options((29.76,-95.37),(29.78,-95.35))
        self.assertEqual(result['options'][0]['distance_km'],4.2)
        self.assertIn('INCOMPLETE COVERAGE',result['options'][0]['risk_level'])
        self.assertEqual(result['options'][0]['roads'],['Main Street'])
        with self.assertRaises(ValueError): app.route_options((40,-95),(29.78,-95.35))

if __name__=='__main__':unittest.main()
