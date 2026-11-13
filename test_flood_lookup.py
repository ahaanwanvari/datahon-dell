import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from flood_plan import shelter_candidates,build_plan
from scenarios import Scenarios


class LookupTests(unittest.TestCase):
    def test_shelter_feeds_run_concurrently(self):
        barrier=threading.Barrier(2)
        def fetch(*args):
            barrier.wait(timeout=2)
            return {'features':[]},'2026-11-13T00:00:00Z',False
        with patch('flood_plan.cached_feed',side_effect=fetch):
            candidates,sources,errors=shelter_candidates({'lat':30,'lon':-95})
        self.assertEqual(len(sources),2);self.assertEqual(errors,[])
    def test_partial_results_publish_before_terrain_and_no_empty_model_call(self):
        candidate={'id':'fema:1','name':'Site','lat':30,'lon':-95,'distance_km':1,'listed_open':False,'status':'unverified','floodplain_flag':None,'surge_flag':None}
        events=[]
        def progress(stage,partial):events.append((stage,partial))
        def terrain(*args):
            self.assertEqual(events[-1][0],'checking_terrain')
            self.assertEqual(events[-1][1]['candidates'][0]['id'],'fema:1')
            raise RuntimeError('Unavailable')
        with patch('flood_plan.shelter_candidates',return_value=([candidate],[],[])),patch('flood_plan.elevations',side_effect=terrain):
            plan=build_plan('30, -95',lambda _:self.fail('No eligible candidates: do not queue Qwen.'),lambda *_:self.fail('No verified access data.'),progress)
        self.assertIsNone(plan['assessment']['candidate_id']);self.assertFalse(plan['candidates'][0]['route_usable'])
    def test_interrupted_lookup_keeps_saved_preview(self):
        with tempfile.TemporaryDirectory() as folder:
            store=Scenarios(folder,'http://localhost','model',None);identity='a'*32;store.folder(identity).mkdir()
            store.write(identity,{'id':identity,'state':'finding_destinations','generated_url':'/saved.png'})
            result=store.read(identity)
            self.assertEqual(result['state'],'ready');self.assertEqual(result['generated_url'],'/saved.png')
            self.assertIn('retry',result['plan_error'])


if __name__=='__main__':unittest.main()
