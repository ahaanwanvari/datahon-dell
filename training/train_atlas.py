"""Continue the local Qwen LoRA on labeled FloodNet VQA plus change replay."""
import json
import math
from pathlib import Path
import random
import re
import sys
import time
import traceback

HOME=Path.home()/'jupyterlab'
LEGACY=HOME/'flood_training'
RUN=LEGACY/'runs/atlas-v2'
import atlas_runtime as runtime


def status(stage,**fields):
    runtime.write_json(RUN/'status.json',{'state':stage,**fields})
    print(json.dumps({'state':stage,**fields}),flush=True)


def messages(row,target=False):
    from PIL import Image
    images=[]
    for path in row['images']:
        with Image.open(path) as im:
            im=im.convert('RGB');im.thumbnail((448,448));images.append(im.copy())
    result=[{'role':'user','content':[{'type':'text','text':row['prompt']},
                                    *[{'type':'image','image':im} for im in images]]}]
    if target:result.append({'role':'assistant','content':[{'type':'text','text':row['target']}]})
    return result


def encode(processor,row,target=False):
    return processor.apply_chat_template(messages(row,target),tokenize=True,add_generation_prompt=not target,
                                         return_dict=True,return_tensors='pt')


def normalize(text):
    text=text.lower().strip().strip('`\"\' .\n').replace('-',' ')
    text=' '.join(text.split())
    if text in ('flooded,non flooded','flooded, non flooded','non flooded,flooded','non flooded, flooded'):return 'mixed'
    return text


def classification_report(predictions):
    labels=sorted({r['answer'] for r in predictions})
    correct=sum(r['prediction']==r['answer'] for r in predictions)
    per={}
    for label in labels:
        tp=sum(r['answer']==label and r['prediction']==label for r in predictions)
        fp=sum(r['answer']!=label and r['prediction']==label for r in predictions)
        fn=sum(r['answer']==label and r['prediction']!=label for r in predictions)
        p=tp/(tp+fp) if tp+fp else 0.;r=tp/(tp+fn) if tp+fn else 0.
        per[label]={'precision':p,'recall':r,'f1':2*p*r/(p+r) if p+r else 0.,'support':tp+fn}
    return {'n':len(predictions),'exact_match_accuracy':correct/max(1,len(predictions)),
            'macro_f1':sum(v['f1'] for v in per.values())/max(1,len(per)),'per_answer':per,
            'invalid_answers':sum(r['prediction'] not in ('flooded','non flooded','mixed','yes','no') for r in predictions)}


def train():
    import torch
    from peft import PeftModel
    rows=json.loads((RUN/'dataset.json').read_text())
    train_rows=[r for r in rows if r['split']=='train']
    val_rows=[r for r in rows if r['split']=='validation']
    test_rows=[r for r in rows if r['split']=='test' and r['task']=='single_image_vqa']
    output=RUN/'adapter'
    if (output/'adapter_config.json').exists():raise RuntimeError('V2 adapter exists; refusing to overwrite it.')
    random.seed(3407);torch.manual_seed(3407)
    status('loading_model',training_examples=len(train_rows),validation_examples=len(val_rows),test_questions=len(test_rows))
    started=time.time()
    with runtime.GPUExclusive():
        base,processor=runtime.load_model()
        model=PeftModel.from_pretrained(base,LEGACY/'adapter',is_trainable=True)
        model.load_adapter(LEGACY/'adapter',adapter_name='previous',is_trainable=False)
        model.set_adapter('default')
        model.config.use_cache=False
        model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={'use_reentrant':False})
        model.enable_input_require_grads()
        def loss(row):
            inputs=encode(processor,row,True).to('cuda')
            prefix=encode(processor,row)['input_ids'].to('cuda')
            if not torch.equal(inputs['input_ids'][:,:prefix.shape[1]],prefix):raise RuntimeError('Assistant token prefix mismatch')
            labels=inputs['input_ids'].clone();labels[:,:prefix.shape[1]]=-100
            if not (labels!=-100).any():raise RuntimeError('No assistant target tokens')
            value=model(**inputs,labels=labels).loss
            if not torch.isfinite(value):raise RuntimeError('Nonfinite loss')
            return value
        def validate(stage):
            model.eval();sums={};counts={}
            with torch.inference_mode():
                for i,row in enumerate(val_rows):
                    if i%10==0:status(stage,done=i,total=len(val_rows))
                    value=loss(row).item();key=row['task']
                    sums[key]=sums.get(key,0)+value;counts[key]=counts.get(key,0)+1
            result={k:sums[k]/counts[k] for k in sums};result['overall']=sum(sums.values())/sum(counts.values())
            return result
        baseline=validate('baseline_validation')
        print('Previous adapter validation:',baseline,flush=True)
        model.set_adapter('default');model.train()
        parameters=[p for p in model.parameters() if p.requires_grad]
        assert parameters and all('lora_' in name and '.previous.' not in name for name,p in model.named_parameters() if p.requires_grad), 'Only the new LoRA may train'
        optimizer=torch.optim.AdamW(parameters,lr=2e-5,weight_decay=.01)
        random.shuffle(train_rows);optimizer.zero_grad();steps=0
        for i,row in enumerate(train_rows):
            value=loss(row);group_size=min(4,len(train_rows)-(i//4)*4)
            (value/group_size).backward()
            if (i+1)%4==0 or i+1==len(train_rows):
                torch.nn.utils.clip_grad_norm_(parameters,1.)
                optimizer.step();optimizer.zero_grad();steps+=1
            record={'example':i+1,'total':len(train_rows),'task':row['task'],'loss':value.item(),'optimizer_step':steps}
            with (RUN/'metrics.jsonl').open('a') as f:f.write(json.dumps(record)+'\n')
            if i%10==0:status('training',**record)
        final=validate('validation')
        model.save_pretrained(output,selected_adapters=['default']);processor.save_pretrained(output)
        # Published answer evaluation, performed only after training is fixed.
        model.gradient_checkpointing_disable();model.config.use_cache=True
        model.generation_config.use_cache=True
        def generate(row,tokens=12):
            inputs=encode(processor,row).to('cuda')
            with torch.inference_mode():
                ids=model.generate(**inputs,max_new_tokens=tokens,do_sample=False)
            return processor.batch_decode(ids[:,inputs['input_ids'].shape[1]:],skip_special_tokens=True)[0]
        evaluations={}
        for adapter,label in [('previous','previous_utsa_adapter'),('default','atlas_v2')]:
            model.set_adapter(adapter);model.eval();predictions=[]
            for i,row in enumerate(test_rows):
                if i%10==0:status('held_out_evaluation',model=label,done=i,total=len(test_rows))
                response=generate(row)
                predictions.append({'id':row['id'],'group':row['group'],'answer':row['answer'],
                  'prediction':normalize(response),'raw_response':response,'question':row['question']})
            runtime.write_json(RUN/(label+'_predictions.json'),predictions)
            evaluations[label]=classification_report(predictions)
        model.set_adapter('default');model.eval()
        # Reload is checked separately so the saved adapter is not assumed usable merely because training ran.
        sample=next(r for r in test_rows)
        sample_response=generate(sample)
        accepted=final['overall']<baseline['overall'] and final.get('paired_change',0)<=baseline.get('paired_change',float('inf'))*1.5
        report={'base_model':runtime.MODEL,'base_revision':runtime.REVISION,'initialized_from':str(LEGACY/'adapter'),
            'repo_commit':'d6724a272778631c2b114badbd2b83f0ee854e46','train_examples':len(train_rows),
            'validation_examples':len(val_rows),'test_questions':len(test_rows),'epochs':1,'learning_rate':2e-5,
            'optimizer_steps':steps,'baseline_validation_loss':baseline,'trained_validation_loss':final,
            'held_out_vqa':evaluations,'accepted_by_validation':accepted,'elapsed_seconds':time.time()-started,
            'sample':{'question':sample['question'],'expected':sample['answer'],'response':sample_response},
            'limits':'Filename-group holdout from published labeled training pool, same Harvey event. Not official hidden test or geographic/event-independent accuracy. UTSA replay uses unverified AI labels; identity controls prove no inter-image change, not no flooding.'}
        runtime.write_json(RUN/'training_report.json',report)
        del value,optimizer,parameters,base,model,processor
        import gc;gc.collect();torch.cuda.empty_cache()
        status('checkpoint_reload',adapter=str(output))
        model,processor=runtime.load_model(output)
        model.eval()
        response=generate(sample)
        import hashlib
        fingerprint=hashlib.sha256((output/'adapter_model.safetensors').read_bytes()).hexdigest()
        runtime.write_json(RUN/'reload_check.json',{'adapter':str(output),'sha256':fingerprint,'question':sample['question'],'answer':response,'expected':sample['answer']})
        del model,processor
        gc.collect();torch.cuda.empty_cache()
    if accepted:
        runtime.write_json(LEGACY/'active_adapter.json',{'path':str(output),'sha256':fingerprint,'training_report':str(RUN/'training_report.json'),'label_sources':['published_vqa_ground_truth','ai_generated_unverified','deterministic_identical_input']})
    result={'state':'completed','trained':True,'accepted_by_validation':accepted,'adapter':str(output),'training_report':str(RUN/'training_report.json'),'reload_verified':True}
    runtime.write_json(RUN/'status.json',result)
    runtime.write_json(LEGACY/'status.json',result)
    print(json.dumps(result),flush=True)


if __name__=='__main__':
    RUN.mkdir(parents=True,exist_ok=True)
    try:train()
    except Exception as exc:
        status('failed',error=str(exc));traceback.print_exc();raise
