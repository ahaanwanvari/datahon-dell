"""Verify the actual file-path helper on the active checkpoint and app JSON schema."""
import ast
import json
from pathlib import Path
import sys
ROOT=Path.home()/'jupyterlab/flood_training'
sys.path.insert(0,str(ROOT))
import predict
import workflow


def main():
    run=ROOT/'runs/atlas-v2'
    rows=json.loads((run/'dataset.json').read_text())
    example=next(r for r in rows if r['split']=='test' and r['task']=='single_image_vqa')
    pair=next(r for r in workflow.manifest()['pairs'] if r['split']=='test')
    # Use the exact application's prompt, dates, sources and schema.
    tree=ast.parse((Path(__file__).resolve().parents[1]/'app.py').read_text())
    prompt=next(ast.literal_eval(n.value) for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='PROMPT' for t in n.targets))
    a,b=pair['before'],pair['after']
    prompt+=f"\nObservation dates: {a['acquisition_date']} and {b['acquisition_date']}. Sensors: {a['source_agency']}, {b['source_agency']}. Alignment declared by importer: True."
    try:
        answer=predict.ask_image(example['images'][0],example['prompt'])
        paired=predict.ask_image(workflow.DATA/a['image_path'],prompt,second_image=workflow.DATA/b['image_path'])
        target=workflow.validate(json.loads(paired))
        workflow.write_json(run/'inference_check.json',{'active_adapter':str(workflow.active_adapter()),
          'single_image':{'id':example['id'],'expected':example['answer'],'actual':answer},
          'paired_image':{'id':pair['id'],'app_schema_valid':True,'response':target},
          'limits':'Interface/schema checks, not an independent validation of paired flood accuracy.'})
    finally:
        predict.close_model()
    print('File-path helper and paired app JSON schema verified.',flush=True)

if __name__=='__main__':main()
