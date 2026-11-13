"""Pinned Qwen loading and exclusive GB10 access for local training."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
ROOT = Path(os.environ.get('FLOOD_TRAINING_HOME', str(Path.home()/'jupyterlab/flood_training')))
MODEL = 'Qwen/Qwen3-VL-8B-Instruct'
REVISION = '0c351dd01ed87e9c1b53cbc748cba10e6187ff3b'
headers = ROOT.parent/'.flood-training-venv/headers/usr/include'
if headers.exists():
    os.environ['CPATH'] = str(headers/'python3.12') + ':' + str(headers) + (':' + os.environ['CPATH'] if os.environ.get('CPATH') else '')
def write_json(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix+'.tmp'); tmp.write_text(json.dumps(value,indent=2)); tmp.replace(path)

def docker_run(arguments, **kwargs):
    import grp, shlex
    command = ['docker', *arguments]
    docker_gid = grp.getgrnam('docker').gr_gid
    if docker_gid not in os.getgroups() and os.getegid() != docker_gid:
        command = ['sg', 'docker', '-c', shlex.join(command)]
    return subprocess.run(command, **kwargs)


class GPUExclusive:
    """Serialize GPU users and restore the inference server after model work."""
    def __enter__(self):
        import fcntl
        self.lock = (ROOT/'gpu.lock').open('w')
        fcntl.flock(self.lock, fcntl.LOCK_EX)
        r = docker_run(['inspect', '-f', '{{.State.Running}}', 'qwen-vl-server'], capture_output=True, text=True)
        if r.returncode:
            self.lock.close()
            raise RuntimeError('Cannot inspect the inference server: ' + r.stderr.strip())
        self.restore = r.stdout.strip() == 'true'
        if self.restore:
            print('Pausing inference server to free GPU memory.', flush=True)
            docker_run(['stop', '-t', '60', 'qwen-vl-server'], check=True)
        return self
    def __exit__(self, *args):
        try:
            if self.restore:
                print('Restoring inference server.', flush=True)
                docker_run(['start', 'qwen-vl-server'], check=True)
        finally:
            self.lock.close()

def load_model(adapter=None):
    import torch
    from transformers import AutoProcessor, Qwen3VLForConditionalGeneration
    processor = AutoProcessor.from_pretrained(MODEL, revision=REVISION, local_files_only=True,
                                            min_pixels=128*128, max_pixels=448*448)
    model = Qwen3VLForConditionalGeneration.from_pretrained(
        MODEL, revision=REVISION, local_files_only=True, dtype=torch.bfloat16,
        attn_implementation='sdpa', device_map='cuda')
    if adapter:
        from peft import PeftModel
        model = PeftModel.from_pretrained(model, adapter)
    return model, processor
