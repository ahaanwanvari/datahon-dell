"""Install per-user service definitions without starting models or training."""
import json
import os
from pathlib import Path
import subprocess
import sys

repo = Path(__file__).resolve().parents[1]
training = Path(os.environ.get('FLOOD_TRAINING_HOME', str(Path.home()/'jupyterlab/flood_training')))
model_python = Path(os.environ.get('FLOOD_MODEL_PYTHON', str(training.parent/'.flood-training-venv/bin/python')))
app_python = Path(os.environ.get('FLOOD_APP_PYTHON', str(training.parent/'.venv/bin/python')))
app_port = int(os.environ.get('FLOOD_PORT', '8766'))
api_port = int(os.environ.get('FLOOD_INFERENCE_PORT', '8001'))
quote = json.dumps
folder=Path.home()/'.config/systemd/user';folder.mkdir(parents=True,exist_ok=True)
(folder/'flood-atlas-inference.service').write_text(f'''[Unit]
Description=Resident Atlas v2 vision inference API

[Service]
WorkingDirectory={str(repo).replace(' ', r'\x20')}
Environment={quote('FLOOD_TRAINING_HOME='+str(training))}
Environment=FLOOD_INFERENCE_PORT={api_port}
ExecStart={quote(str(model_python))} -u inference/server.py
TimeoutStopSec=1000
Restart=no

[Install]
WantedBy=default.target
''')
health_code=f"import requests,time; time.sleep(1); requests.get('http://127.0.0.1:{api_port}/health',timeout=10).raise_for_status()"
(folder/'flood-atlas-app.service').write_text(f'''[Unit]
Description=Texas Flood Atlas integrated application
Requires=flood-atlas-inference.service
After=flood-atlas-inference.service

[Service]
WorkingDirectory={str(repo).replace(' ', r'\x20')}
Environment=FLOOD_VLM_URL=http://127.0.0.1:{api_port}/v1
Environment=FLOOD_LOCAL_ATLAS=1
Environment=FLOOD_PORT={app_port}
ExecStartPre={quote(str(app_python))} -c {quote(health_code)}
ExecStart={quote(str(app_python))} -u app.py
Restart=no

[Install]
WantedBy=default.target
''')
(training/'inference_service.json').write_text(json.dumps({'url':f'http://127.0.0.1:{api_port}/v1'},indent=2))
subprocess.run(['systemctl','--user','daemon-reload'],check=True)
print('Installed service definitions. Start with: systemctl --user start flood-atlas-app')
