"""Local reference-image editing; synthetic illustrations, never inundation forecasts."""
import base64
import io
import json
from pathlib import Path
import re
from PIL import Image, ImageOps

CONFIG = json.loads(Path(__file__).with_name('flood_model.json').read_text())


def installation_status():
    root=Path(CONFIG['path'])
    required=['transformer/diffusion_pytorch_model.safetensors','text_encoder/model-00001-of-00002.safetensors',
              'text_encoder/model-00002-of-00002.safetensors','vae/diffusion_pytorch_model.safetensors']
    present=[name for name in required if (root/name).is_file()]
    return {'installed':len(present)==len(required),'files_ready':len(present),'files_total':len(required),
            'model':CONFIG['model'],'revision':CONFIG['revision']}


def decode_image(url):
    if not isinstance(url,str) or not url.startswith(('data:image/png;base64,','data:image/jpeg;base64,','data:image/webp;base64,')):
        raise ValueError('Upload a JPEG, PNG or WebP photo.')
    data=base64.b64decode(url.split(',',1)[1],validate=True)
    with Image.open(io.BytesIO(data)) as image:
        if image.width*image.height>40_000_000:raise ValueError('Use a photo smaller than 40 megapixels.')
        image=ImageOps.exif_transpose(image).convert('RGB');image.thumbnail((1024,1024))
        return image.copy()


class FloodEditor:
    def __init__(self):
        self.pipeline=None
        self.loads=0
        self.generations=0
        self.state='not_loaded'

    def generate(self, image, severity, description):
        import torch
        if not installation_status()['installed']:raise RuntimeError('The local image-editing model is still downloading. Try again when installation finishes.')
        if self.pipeline is None:
            self.state='loading_model'
            from diffusers import Flux2KleinPipeline
            self.pipeline=Flux2KleinPipeline.from_pretrained(CONFIG['path'],torch_dtype=torch.bfloat16,local_files_only=True).to('cuda')
            self.pipeline.set_progress_bar_config(disable=True)
            self.loads+=1
        self.state='generating'
        water={
            'minor':'Shallow floodwater pools over the visible ground or floor, with small ripples and realistic reflections.',
            'moderate':'Floodwater covers streets, paths, gardens or the indoor floor and the lower portions of objects. Keep upper building features visible.',
            'severe':'Extensive floodwater submerges the visible ground and reaches the lower parts of buildings and vehicles. Retain recognizable roofs, upper walls and tree canopies.'}[severity]
        prompt=('Edit this exact reference photo to illustrate a hypothetical flood at the same place. '+water+
                ' Preserve the original camera angle, framing, perspective, buildings, hills, vegetation and recognizable landmarks. '
                'Water should follow the scene perspective, occlude lower surfaces and reflect the surrounding structures. '
                'Keep the original lighting and photographic style. Do not add arrows, labels, evacuation routes, new buildings or rescue vehicles. '
                'This is a visual illustration, not a prediction or a map. Scene reference: '+description[:1200])
        scale=min(1,CONFIG['max_side']/max(image.size))
        width=max(64,int(image.width*scale)//16*16);height=max(64,int(image.height*scale)//16*16)
        try:
            with torch.inference_mode():
                result=self.pipeline(image=image,prompt=prompt,width=width,height=height,
                    guidance_scale=CONFIG['guidance_scale'],num_inference_steps=CONFIG['steps'],
                    generator=torch.Generator(device='cuda').manual_seed(3407)).images[0]
            output=io.BytesIO();result.save(output,format='PNG')
            self.generations+=1
            return {'image':'data:image/png;base64,'+base64.b64encode(output.getvalue()).decode(),
                    'generator':CONFIG['model'],'revision':CONFIG['revision'],'prompt':prompt,
                    'severity':severity,'synthetic':True,'forecast':False}
        finally:self.state='ready'
