"""Notebook/file-path client for the shared Atlas service; never loads model weights."""
import base64
import io
import os
from pathlib import Path
import requests
from PIL import Image


def ask_image(image_path, prompt='Describe visible water coverage and any possible flooding. State uncertainty.', second_image=None, endpoint=None):
    endpoint = (endpoint or os.environ.get('FLOOD_INFERENCE_URL', 'http://127.0.0.1:8001/v1')).rstrip('/')
    if not isinstance(prompt, str) or not prompt.strip():raise ValueError('Provide a nonempty prompt.')
    content = [{'type': 'text', 'text': prompt}]
    for name in [image_path] + ([] if second_image is None else [second_image]):
        with Image.open(Path(name).expanduser().resolve(strict=True)) as image:
            image = image.convert('RGB');image.thumbnail((448,448))
            buffer = io.BytesIO();image.save(buffer,format='PNG')
        content.append({'type':'image_url','image_url':{'url':'data:image/png;base64,' + base64.b64encode(buffer.getvalue()).decode()}})
    health = requests.get(endpoint.removesuffix('/v1')+'/health',timeout=10)
    health.raise_for_status();model = health.json()['model']
    result = requests.post(endpoint+'/chat/completions',json={
        'model':model,'temperature':0,'max_tokens':512,
        'messages':[{'role':'user','content':content}]},timeout=(10,900))
    if not result.ok:raise RuntimeError('Atlas inference failed: '+result.text)
    record=result.json()
    if record.get('model') != model:raise RuntimeError('Checkpoint identity changed during request.')
    return record['choices'][0]['message']['content']
