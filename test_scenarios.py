import base64
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from PIL import Image
from flood_plan import choose_model_result,geocode,build_plan
from scenarios import Scenarios


class PlanTests(unittest.TestCase):
    def test_model_cannot_invent_destination(self):
        with self.assertRaises(ValueError):
            choose_model_result('{"candidate_id":"imaginary tower","reason":"tall"}',[{'id':'fema:1'}])
        self.assertIsNone(choose_model_result('{"candidate_id":null,"reason":"insufficient data"}',[])['candidate_id'])
    def test_invalid_coordinates_rejected(self):
        with self.assertRaises(ValueError):geocode('100, 999')
    def test_unverified_shelters_do_not_become_recommendations(self):
        candidate={'id':'fema:1','name':'Closed shelter','lat':30,'lon':-95,'distance_km':2,'status':'unknown','listed_open':False,'recent_status':False,'floodplain_flag':'No','surge_flag':'No'}
        calls=[]
        def model(prompt):
            calls.append(prompt);return '{"candidate_id":"fema:1","reason":"Looks tall"}'
        with patch('flood_plan.shelter_candidates',return_value=([candidate],[],[])),patch('flood_plan.elevations',side_effect=RuntimeError('offline')):
            result=build_plan('30, -95',model,lambda *_:self.fail('No route should be requested'))
        self.assertIsNone(result['assessment']['candidate_id'])
        self.assertFalse(result['candidates'][0]['eligible_for_model_selection'])
        self.assertTrue(result['errors'])
        self.assertEqual(len(calls),0)


class ScenarioTests(unittest.TestCase):
    def test_failed_generation_has_no_fake_image(self):
        with tempfile.TemporaryDirectory() as folder:
            store=Scenarios(folder,'http://localhost:8001/v1','atlas-test',None)
            identity='a'*32;job=store.folder(identity);job.mkdir()
            Image.new('RGB',(32,32)).save(job/'original.png')
            store.write(identity,{'id':identity,'state':'queued','severity':'moderate'})
            store.busy.add(identity)
            with patch('scenarios.requests.post',side_effect=RuntimeError('editor unavailable')):
                store.generate(identity)
            record=store.read(identity)
            self.assertEqual(record['state'],'failed')
            self.assertNotIn('generated_url',record)
            self.assertFalse((job/'generated.png').exists())
            self.assertFalse(store.busy)
    def test_success_preserves_generated_provenance(self):
        from unittest.mock import Mock
        with tempfile.TemporaryDirectory() as folder:
            store=Scenarios(folder,'http://localhost:8001/v1','atlas-test',None)
            identity='c'*32;job=store.folder(identity);job.mkdir()
            Image.new('RGB',(32,32)).save(job/'original.png')
            buffer=io.BytesIO();Image.new('RGB',(32,32),(20,30,40)).save(buffer,format='PNG')
            store.write(identity,{'id':identity,'state':'queued','severity':'moderate'})
            store.busy.add(identity)
            response=Mock();response.json.return_value={'image':'data:image/png;base64,'+base64.b64encode(buffer.getvalue()).decode(),
                'generator':'test-editor','revision':'test-revision','synthetic':True,'forecast':False}
            with patch('scenarios.requests.post',return_value=response):store.generate(identity)
            record=store.read(identity)
            self.assertEqual(record['state'],'ready')
            self.assertTrue(record['synthetic']);self.assertFalse(record['forecast'])
            with Image.open(job/'generated.png') as image:
                self.assertIn('not an observation or forecast',image.info['Description'])
                self.assertEqual(image.info['Generator'],'test-editor @ test-revision')

    def test_automatic_review_and_grounding_receive_generated_image_after_edit(self):
        from unittest.mock import Mock
        with tempfile.TemporaryDirectory() as folder:
            store=Scenarios(folder,'http://localhost:8001/v1','atlas-test',None)
            identity='d'*32;job=store.folder(identity);job.mkdir()
            Image.new('RGB',(32,32),'red').save(job/'original.png')
            buffer=io.BytesIO();Image.new('RGB',(32,32),'blue').save(buffer,format='PNG')
            store.write(identity,{'id':identity,'state':'queued','severity':'moderate'})
            store.busy.add(identity);calls=[]
            def post(url,json,**kwargs):
                calls.append(url);response=Mock()
                if url.endswith('/flood-edits'):
                    image_url=json['image'];expected='red'
                    response.json.return_value={'image':'data:image/png;base64,'+base64.b64encode(buffer.getvalue()).decode(),
                        'generator':'test','revision':'test','synthetic':True,'forecast':False}
                else:
                    self.assertTrue((job/'generated.png').exists())
                    image_url=json['messages'][0]['content'][1]['image_url']['url'];expected='blue'
                    if json.get('use_base_model'):
                        response.json.return_value={'model':'Qwen/Qwen3-VL-8B-Instruct','adapter_applied':False,
                            'choices':[{'message':{'content':'{"objects":[]}'}}]}
                    else:
                        self.assertIn('GENERATED FLOOD IMAGE',json['messages'][0]['content'][0]['text'])
                        response.json.return_value={'model':'atlas-test','choices':[{'message':{'content':__import__('json').dumps({
                            'summary':'Water around buildings.','explanation':'The simulation shows flooded roads.',
                            'limitations':'Simulation only.','features':[]})}}]}
                with Image.open(io.BytesIO(base64.b64decode(image_url.split(',',1)[1]))) as image:
                    self.assertEqual(image.getpixel((0,0)),(255,0,0) if expected=='red' else (0,0,255))
                return response
            with patch('scenarios.requests.post',side_effect=post):store.generate(identity)
            record=store.read(identity)
            self.assertEqual(record['state'],'ready')
            self.assertEqual(record['photo_analysis']['basis'],'generated_flood_image')
            self.assertEqual(record['photo_analysis']['image_url'],record['generated_url'])
            self.assertTrue(calls[0].endswith('/flood-edits'));self.assertEqual(len(calls),3)

    def test_interrupted_job_and_path_traversal(self):
        with tempfile.TemporaryDirectory() as folder:
            store=Scenarios(folder,'http://localhost:8001/v1','atlas-test',None)
            with self.assertRaises(ValueError):store.folder('../original.png')
            identity='b'*32;store.folder(identity).mkdir()
            store.write(identity,{'id':identity,'state':'analyzing_and_generating'})
            self.assertEqual(store.read(identity)['state'],'interrupted')


if __name__=='__main__':unittest.main()
