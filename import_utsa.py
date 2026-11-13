"""Convert the published UTSA metadata to an Explorer manifest without inventing pairs."""
import argparse
import csv
import json
from pathlib import Path

REPO = 'jennifer-fowler/UTSA-flood-images'
REVISION = 'ad98e681e7cf6af9ced145833b522c4f6c0acad1'
FIELDS = ['location_id','acquisition_date','image_path','latitude','longitude','locality',
          'sensor','source_url','aligned','georeferenced','original_image_id','original_pair_key',
          'dataset_repo','dataset_revision','source_agency','attribution','image_role',
          'time_precision','processing','west','south','east','north','native_resolution_note']


def build_manifest(folder):
    folder=Path(folder).expanduser().resolve()
    with (folder/'image_metadata.csv').open(newline='') as f:
        rows=list(csv.DictReader(f))
    by_id={r['image_id']:r for r in rows}
    if len(by_id)!=len(rows):raise ValueError('Duplicate source image IDs')
    manifest=[]
    pairs=set()
    for r in rows:
        companion=by_id.get(r['paired_image_id'])
        if r['paired_image_id'] and not companion:
            raise ValueError('Missing companion for '+r['image_id'])
        if companion:
            if companion['paired_image_id']!=r['image_id'] or companion['pair_key']!=r['pair_key']:
                raise ValueError('Inconsistent pair metadata: '+r['image_id'])
            location='utsa:'+r['pair_key']
            pairs.add(location)
        else:
            location='utsa:single:'+r['image_id']
        grid_fields=('west','south','east','north','width_px','height_px','output_crs')
        aligned=bool(companion and all(r[k] and r[k]==companion[k] for k in grid_fields))
        item={k:r.get(k,'') for k in FIELDS}
        item.update(location_id=location,
                    locality=f"{r['locality']} · {r['pair_id'] or r['image_id']}",
                    sensor=r['source_agency']+' / '+r['platform'],
                    aligned=str(aligned).lower(),original_image_id=r['image_id'],
                    original_pair_key=r['pair_key'],dataset_repo=REPO,dataset_revision=REVISION)
        manifest.append(item)
    path=folder/'explorer_manifest.csv'
    with path.open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=FIELDS);w.writeheader();w.writerows(manifest)
    summary={'dataset':REPO,'revision':REVISION,'manifest':str(path),'images':len(rows),
             'paired_locations':len(pairs),'standalone_images':sum(not r['paired_image_id'] for r in rows),
             'without_precise_coordinates':sum(r['georeferenced']!='true' for r in rows)}
    (folder/'explorer_install.json').write_text(json.dumps(summary,indent=2)+'\n')
    return summary

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('dataset_folder');args=parser.parse_args()
    print(json.dumps(build_manifest(args.dataset_folder),indent=2))
