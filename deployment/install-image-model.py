"""Download pinned image editor weights with hf. Does not start models or training."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import requests

root=Path(__file__).resolve().parents[1]
config=json.loads((root/'inference/flood_model.json').read_text())
metadata=requests.get(f"https://huggingface.co/api/models/{config['model']}/revision/{config['revision']}",timeout=30)
metadata.raise_for_status()
prefixes=('text_encoder/','tokenizer/','transformer/','scheduler/','vae/')
files=[p['rfilename'] for p in metadata.json()['siblings'] if p['rfilename'].startswith(prefixes) or p['rfilename'] in ('model_index.json','LICENSE.md')]
folder=Path(config['path']);folder.mkdir(parents=True,exist_ok=True)
cli=shutil.which('hf')
if not cli:raise SystemExit('Install the Hugging Face hf CLI before running this script.')
subprocess.run([cli,'download',config['model'],*files,'--revision',config['revision'],'--local-dir',str(folder),'--max-workers','4'],
               env={**os.environ,'HF_HOME':str(folder.parent/'hub'),'HF_XET_HIGH_PERFORMANCE':'1'},check=True)
print('Image model installed:',folder)
