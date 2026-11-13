"""Loopback vision API. One pinned adapter and one resident model per process."""
import base64
import hashlib
import io
import json
import os
from pathlib import Path
import signal
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'training'))
import atlas_runtime as runtime


class InvalidRequest(ValueError):
    pass


class Engine:
    def __init__(self):
        pointer = json.loads((runtime.ROOT / 'active_adapter.json').read_text())
        self.adapter = Path(pointer['path']).resolve()
        self.fingerprint = hashlib.file_digest((self.adapter / 'adapter_model.safetensors').open('rb'), 'sha256').hexdigest()
        if pointer.get('sha256') != self.fingerprint:
            raise RuntimeError('Active adapter fingerprint does not match its weights.')
        self.model_id = 'atlas-v2-' + self.fingerprint[:16]
        self.lock = threading.Lock()
        self.state = 'not_loaded'
        self.error = None
        self.model = self.processor = self.gpu = None
        self.loads = self.requests = 0
        self.editor = None

    def info(self):
        from inference.flood_edit import installation_status
        return dict(state=self.state, model=self.model_id, adapter=str(self.adapter),
                    adapter_sha256=self.fingerprint, model_loads=self.loads,
                    requests=self.requests, error=self.error,
                    image_editor={**installation_status(),**(dict(state='not_loaded',model_loads=0,generations=0) if self.editor is None else dict(state=self.editor.state,model_loads=self.editor.loads,generations=self.editor.generations))})

    def load(self):
        if self.model is not None:
            return
        self.state = 'waiting_for_gpu'
        self.gpu = runtime.GPUExclusive()
        self.gpu.__enter__()
        try:
            self.state = 'loading_model'
            model, processor = runtime.load_model(self.adapter)
            model.eval()
            self.model, self.processor = model, processor
            self.loads += 1
            self.state = 'ready'
        except Exception as exc:
            self.state, self.error = 'failed', str(exc)
            self.gpu.__exit__(None, None, None)
            self.gpu = None
            raise

    def generate(self, body):
        if body.get('model') != self.model_id:
            raise InvalidRequest('Requested model does not match ' + self.model_id)
        use_base=body.get('use_base_model',False)
        if type(use_base) is not bool:raise InvalidRequest('use_base_model must be a boolean.')
        messages = body.get('messages')
        if not isinstance(messages, list) or len(messages) != 1 or messages[0].get('role') != 'user':
            raise InvalidRequest('Provide exactly one user message.')
        content = messages[0].get('content')
        if not isinstance(content, list):
            raise InvalidRequest('Message content must be a list.')
        converted, images, texts = [], [], []
        for part in content:
            if part.get('type') == 'text':
                value = part.get('text', '')
                if not isinstance(value, str) or not value.strip() or len(value) > 20000:
                    raise InvalidRequest('Provide nonempty text up to 20000 characters.')
                texts.append(value)
                converted.append({'type': 'text', 'text': value})
            elif part.get('type') == 'image_url':
                url = part.get('image_url', {}).get('url', '')
                if not url.startswith(('data:image/png;base64,', 'data:image/jpeg;base64,')):
                    raise InvalidRequest('Images must be inline PNG/JPEG data URLs.')
                try:
                    data = base64.b64decode(url.split(',', 1)[1], validate=True)
                    with Image.open(io.BytesIO(data)) as im:
                        im = im.convert('RGB'); im.thumbnail((448, 448)); image = im.copy()
                except Exception as exc:
                    raise InvalidRequest('Invalid image data.') from exc
                images.append(image)
                converted.append({'type': 'image', 'image': image})
            else:
                raise InvalidRequest('Unsupported content type.')
        if not texts or not 1 <= len(images) <= 2:
            raise InvalidRequest('Provide text and one or two images.')
        tokens_limit = body.get('max_tokens', 650)
        if type(tokens_limit) is not int or not 1 <= tokens_limit <= 1024:
            raise InvalidRequest('max_tokens must be between 1 and 1024.')
        if body.get('temperature', 0) != 0:
            raise InvalidRequest('Only deterministic temperature=0 is supported.')
        # The app validates the generated JSON; this endpoint does not claim
        # grammar-constrained decoding support.
        with self.lock:
            if self.state == 'failed':
                raise RuntimeError(self.error)
            self.load()
            import torch
            inputs = self.processor.apply_chat_template(
                [{'role': 'user', 'content': converted}], tokenize=True,
                add_generation_prompt=True, return_dict=True, return_tensors='pt').to('cuda')
            try:
                from contextlib import nullcontext
                with self.model.disable_adapter() if use_base else nullcontext():
                    with torch.inference_mode():
                        tokens = self.model.generate(**inputs, max_new_tokens=tokens_limit, do_sample=False)
                answer = self.processor.batch_decode(
                    tokens[:, inputs['input_ids'].shape[1]:], skip_special_tokens=True)[0]
                self.requests += 1
                return answer
            finally:
                del inputs

    def flood_edit(self, body):
        from inference.flood_edit import FloodEditor, decode_image
        severity=body.get('severity','moderate')
        if severity not in ('minor','moderate','severe'):
            raise InvalidRequest('Choose minor, moderate or severe flooding.')
        image=decode_image(body.get('image'))
        buffer=io.BytesIO();image.save(buffer,format='PNG')
        url='data:image/png;base64,'+base64.b64encode(buffer.getvalue()).decode()
        description=self.generate({'model':self.model_id,'max_tokens':160,'messages':[{'role':'user','content':[
            {'type':'text','text':'Describe the visible scene, ground surfaces, buildings, vegetation and camera viewpoint in at most 80 words. Do not infer an address, water depth, flood safety or destinations.'},
            {'type':'image_url','image_url':{'url':url}}]}]})
        with self.lock:
            if self.editor is None:self.editor=FloodEditor()
            result=self.editor.generate(image,severity,description)
        result.update(scene_description=description,vision_model=self.model_id)
        return result

    def close(self):
        with self.lock:
            if self.model is not None:
                self.model = self.processor = None
                self.editor = None
                import gc
                import torch
                gc.collect(); torch.cuda.empty_cache()
            if self.gpu is not None:
                self.gpu.__exit__(None, None, None)
                self.gpu = None


def make_handler(engine):
    class Handler(BaseHTTPRequestHandler):
        def reply(self, value, status=200):
            data = json.dumps(value).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers(); self.wfile.write(data)

        def allowed(self):
            host = self.headers.get('Host', '').split(':')[0]
            return host in ('127.0.0.1', 'localhost') and not self.headers.get('Origin')

        def do_GET(self):
            if not self.allowed():return self.reply({'error': 'Loopback clients only'}, 403)
            if self.path == '/health':return self.reply(engine.info())
            if self.path == '/v1/models':
                return self.reply({'object': 'list', 'data': [{'id': engine.model_id, 'object': 'model',
                    'adapter_sha256': engine.fingerprint}]})
            self.reply({'error': 'Not found'}, 404)

        def do_POST(self):
            if not self.allowed():return self.reply({'error': 'Loopback clients only'}, 403)
            if self.path not in ('/v1/chat/completions','/v1/flood-edits'):return self.reply({'error': 'Not found'}, 404)
            try:
                length = int(self.headers.get('Content-Length', 0))
                if not 0 < length <= 24 * 1024 * 1024:
                    raise InvalidRequest('Request size must be between 1 byte and 24 MiB.')
                body = json.loads(self.rfile.read(length))
                if not isinstance(body, dict):raise InvalidRequest('Expected a JSON object.')
                if self.path == '/v1/flood-edits':return self.reply(engine.flood_edit(body))
                answer = engine.generate(body)
                return self.reply({'model': runtime.MODEL if body.get('use_base_model') else engine.model_id,
                    'adapter_applied':not body.get('use_base_model',False),'resident_model':engine.model_id,'adapter_sha256': engine.fingerprint,
                    'choices': [{'index': 0, 'message': {'role': 'assistant', 'content': answer},
                                 'finish_reason': 'stop'}]})
            except (ValueError, KeyError, TypeError) as exc:
                self.reply({'error': str(exc)}, 400)
            except Exception as exc:
                self.reply({'error': str(exc)}, 503)
    return Handler


def main():
    engine = Engine()
    server = ThreadingHTTPServer(('127.0.0.1', int(os.environ.get('FLOOD_INFERENCE_PORT', '8001'))), make_handler(engine))
    def stop(*_):
        threading.Thread(target=server.shutdown, daemon=True).start()
    signal.signal(signal.SIGTERM, stop); signal.signal(signal.SIGINT, stop)
    print(json.dumps(engine.info()), flush=True)
    try:server.serve_forever()
    finally:
        server.server_close(); engine.close()


if __name__ == '__main__':main()
