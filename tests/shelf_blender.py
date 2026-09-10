import sys,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'blender'))
import daybreak_pipeline as P
folder=Path(sys.argv[sys.argv.index('--')+1]);manifest=folder/'range.json';data=json.loads(manifest.read_text())
for preset in ['vertical','horizontal','mixed']:
    data['shelf']['preset']=preset;manifest.write_text(json.dumps(data))
    cfg=dict(P.CONFIG,jobs_dir=str(folder),resolution=(960,640),samples=16,save=str(folder/('shelf-'+preset+'.blend')),render=False)
    scene=P.run(cfg)
    boxes=[o for o in scene.objects if o.get('shelf_row')]
    assert len(boxes)==36,len(boxes)
    for ob in boxes:
        assert ob.rotation_euler.z==0
        assert ob.location.z>=.12-1e-7
    front={(o['shelf_row'],o['facing']):o['flavour_key'] for o in boxes if o['stock_depth']==1}
    if preset=='vertical':assert front[1,1]==front[2,1]
    if preset=='horizontal':assert len({front[1,c] for c in range(1,7)})==1
    if preset=='mixed':assert front[1,1]!=front[2,1]
    if preset=='vertical':
        scene.render.filepath=str(folder/'shelf-preview.png')
        import bpy
        bpy.ops.render.render(write_still=True)
print('PASS: 3 planograms, 36 cartons each, placement and flavour rules')
