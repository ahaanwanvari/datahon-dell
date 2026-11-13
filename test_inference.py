"""HTTP contract checks without loading weights or touching the GPU."""
import base64
import io
import json
import threading
import unittest
from http.server import ThreadingHTTPServer
from unittest.mock import patch
import requests
from PIL import Image
from inference.server import Engine, InvalidRequest, make_handler


class FakeEngine:
    model_id = 'atlas-v2-test'
    fingerprint = 'test'
    def info(self):return {'model': self.model_id, 'state': 'ready'}
    def generate(self, body):
        if body['model'] != self.model_id:raise InvalidRequest('wrong model')
        return 'flooded'


class APIContractTests(unittest.TestCase):
    def setUp(self):
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(FakeEngine()))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = 'http://127.0.0.1:' + str(self.server.server_port)
    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join()
    def test_health_and_completion_identity(self):
        self.assertEqual(requests.get(self.url+'/health').json()['model'], 'atlas-v2-test')
        result = requests.post(self.url+'/v1/chat/completions',json={'model':'atlas-v2-test'})
        self.assertEqual(result.status_code,200)
        self.assertEqual(result.json()['model'],'atlas-v2-test')
        self.assertEqual(result.json()['choices'][0]['message']['content'],'flooded')
    def test_base_grounding_response_identifies_disabled_adapter(self):
        result=requests.post(self.url+'/v1/chat/completions',json={'model':'atlas-v2-test','use_base_model':True})
        self.assertEqual(result.status_code,200)
        value=result.json()
        self.assertEqual(value['model'],'Qwen/Qwen3-VL-8B-Instruct')
        self.assertFalse(value['adapter_applied'])
        self.assertEqual(value['resident_model'],'atlas-v2-test')

    def test_wrong_model_and_foreign_origin_rejected(self):
        self.assertEqual(requests.post(self.url+'/v1/chat/completions',json={'model':'base'}).status_code,400)
        self.assertEqual(requests.post(self.url+'/v1/chat/completions',json={},headers={'Origin':'https://example.com'}).status_code,403)
    def test_remote_image_is_rejected_before_loading(self):
        engine = object.__new__(Engine)
        engine.model_id='atlas-v2-test'
        with self.assertRaises(InvalidRequest):
            engine.generate({'model':engine.model_id,'messages':[{'role':'user','content':[
                {'type':'text','text':'Flooded?'},{'type':'image_url','image_url':{'url':'https://example.com/image.jpg'}}]}]})


class AppUploadTests(unittest.TestCase):
    def test_upload_uses_selected_checkpoint_and_rejects_identity_change(self):
        import app
        import urllib.request
        import urllib.error
        from unittest.mock import Mock
        server=ThreadingHTTPServer(('127.0.0.1',0),app.Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        body=json.dumps({'prompt':'Is flooding visible?','images':['data:image/png;base64,AAAA']}).encode()
        response=Mock()
        response.json.return_value={'model':'atlas-v2-test','choices':[{'message':{'content':'flooded'}}]}
        try:
            with patch.object(app,'LOCAL_ATLAS',True),patch.object(app,'MODEL','atlas-v2-test'),patch.object(app.requests,'post',return_value=response) as post:
                request=urllib.request.Request(f'http://127.0.0.1:{server.server_port}/api/ask',data=body,headers={'Content-Type':'application/json'})
                with urllib.request.urlopen(request) as result:
                    self.assertEqual(json.load(result),{'answer':'flooded','model':'atlas-v2-test'})
                self.assertEqual(post.call_args.kwargs['json']['model'],'atlas-v2-test')
                response.json.return_value={'model':'base','choices':[{'message':{'content':'flooded'}}]}
                with self.assertRaises(urllib.error.HTTPError) as error:
                    urllib.request.urlopen(request)
                self.assertEqual(error.exception.code,400)
                self.assertIn('checkpoint identity changed',error.exception.read().decode())
        finally:
            server.shutdown();server.server_close();thread.join()


if __name__ == '__main__':unittest.main()
