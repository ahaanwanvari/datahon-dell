import json
import unittest
from scene_analysis import validate_analysis,merge_grounded_buildings


class SceneAnalysisTests(unittest.TestCase):
    def sample(self):
        return {'summary':'A residential scene.','explanation':'Ground-level areas may flood.','limitations':'Access and refuge suitability are unknown.',
                'features':[{'x':.3,'y':.5,'title':'Building to verify','kind':'building_to_verify',
                             'visible_evidence':'A roof is visible.','why_it_matters':'The interior and elevation cannot be established.',
                             'access_checks':'Verify access and designated shelter status.'}]}
    def test_normalized_markers_are_not_certified_safe(self):
        value=self.sample();value['verified_safe']=True
        result=validate_analysis(json.dumps(value))
        self.assertFalse(result['verified_safe']);self.assertFalse(result['features'][0]['verified_safe'])
        self.assertEqual(result['basis'],'original_photo')
    def test_outside_image_and_unknown_marker_kinds_are_dropped(self):
        value=self.sample();value['features'][0]['x']=float('nan')
        value['features'].append({**self.sample()['features'][0],'kind':'safe_shelter'})
        result=validate_analysis(json.dumps(value))
        self.assertEqual(result['features'],[]);self.assertEqual(result['rejected_features'],2)
    def test_no_markers_is_a_valid_observation(self):
        value=self.sample();value['features']=[]
        self.assertEqual(validate_analysis(json.dumps(value))['features'],[])
    def test_missing_explanation_and_unstructured_output_are_rejected(self):
        value=self.sample();del value['explanation']
        with self.assertRaises(ValueError):validate_analysis(json.dumps(value))
        with self.assertRaises(ValueError):validate_analysis('Go to that roof.')
    def test_localized_boxes_do_not_become_safe_destinations(self):
        original=validate_analysis(json.dumps(self.sample()));original['model']='atlas-test'
        grounded=merge_grounded_buildings(original,json.dumps({'objects':[
            {'label':'Visible roof','visible_evidence':'White roof.','bbox_format':[300,100,500,300]},
            {'label':'Invalid placeholder','bbox_format':[0,0,0,0]}]}))
        self.assertEqual(len(grounded['features']),1)
        self.assertAlmostEqual(grounded['features'][0]['x'],.4)
        self.assertEqual(grounded['features'][0]['kind'],'building_to_verify')
        self.assertFalse(grounded['features'][0]['verified_safe'])
        self.assertEqual(grounded['rejected_features'],1)
        self.assertEqual(grounded['grounding_model'],'Qwen/Qwen3-VL-8B-Instruct')



if __name__=='__main__':unittest.main()
