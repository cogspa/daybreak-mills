"""Simple shelf bay and deterministic planograms, using shared carton meshes."""
import json
import math
from pathlib import Path
import bpy
from mathutils import Vector


def build_shelf(scene, boxes, settings):
    if not isinstance(settings,dict):raise ValueError('Invalid shelf settings')
    # A neutral environment makes shelf comparisons independent of the product HDRI.
    nodes=scene.world.node_tree.nodes;nodes.clear()
    bg=nodes.new('ShaderNodeBackground');bg.inputs['Color'].default_value=(.22,.22,.22,1);bg.inputs['Strength'].default_value=.6
    out=nodes.new('ShaderNodeOutputWorld');scene.world.node_tree.links.new(bg.outputs[0],out.inputs[0])
    for ob in list(scene.objects):
        if ob.type=='LIGHT':bpy.data.objects.remove(ob,do_unlink=True)
    for name,pos,power in [('Shelf key',(0,-3,3.5),650),('Shelf fill',(-2,-2,1.8),250)]:
        light=bpy.data.lights.new(name,'AREA');light.energy=power;light.shape='DISK';light.size=4
        ob=bpy.data.objects.new(name,light);scene.collection.objects.link(ob);ob.location=pos
        ob.rotation_euler=(Vector((0,0,1))-ob.location).to_track_quat('-Z','Y').to_euler()
    preset = settings.get('preset', 'vertical')
    if preset not in ('vertical', 'horizontal', 'mixed'):
        raise ValueError('Unknown shelf planogram')
    counts = []
    for key, default, maximum in [('rows', 3, 5), ('facings', 6, 12), ('depth', 2, 3)]:
        value = settings.get(key, default)
        if type(value) is not int or not 1 <= value <= maximum:
            raise ValueError('Invalid shelf ' + key)
        counts.append(value)
    rows, facings, stock = counts
    dims = [(max(v.co.x for v in o.data.vertices)*2, max(v.co.y for v in o.data.vertices)*2,
             max(v.co.z for v in o.data.vertices)) for o in boxes]
    w, d, h = [max(v[i] for v in dims) for i in range(3)]
    spec=json.loads((Path(__file__).resolve().parents[1]/'spec/boxes.json').read_text())['shelf_scene']
    gap,board,base,clearance=[spec[k] for k in ['gap_m','board_m','base_m','clearance_m']]
    width = facings*(w+gap)+.06
    depth = stock*(d+gap)+.08
    pitch = h+clearance+board
    height = base+rows*pitch
    coll = bpy.data.collections.new('Shelf geometry');scene.collection.children.link(coll)
    mat = bpy.data.materials.new('Shelf warm grey');mat.diffuse_color=(.52,.55,.57,1)
    def slab(name, location, dimensions):
        bpy.ops.mesh.primitive_cube_add(size=1, location=location)
        ob=bpy.context.object;ob.name=name;ob.dimensions=dimensions
        bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
        for c in list(ob.users_collection):c.objects.unlink(ob)
        coll.objects.link(ob);ob.data.materials.append(mat)
        bevel=ob.modifiers.new('Shelf edge','BEVEL');bevel.width=.003;bevel.segments=2
        return ob
    for r in range(rows+1):
        z=base+r*pitch
        slab('Shelf deck %02d'%r,(0,depth/2-.04,z-board/2),(width,depth,board))
        slab('Shelf front rail %02d'%r,(0,-.04,z-.018),(width,.016,.036))
    slab('Shelf back',(0,depth-.025,height/2),(width,.025,height))
    for x in [-width/2,width/2]:slab('Shelf upright',(x,depth/2-.04,height/2),(.025,depth,height))
    placed=[]
    for r in range(rows):
        for c in range(facings):
            index=(c if preset=='vertical' else r if preset=='horizontal' else c+r)%len(boxes)
            source=boxes[index]
            for k in range(stock):
                ob=source.copy();ob.data=source.data;source.users_collection[0].objects.link(ob)
                ob.name='Shelf_R%d_F%d_D%d_%s'%(r+1,c+1,k+1,source.name)
                ob.rotation_euler=(0,0,0)
                ob.location=((c-(facings-1)/2)*(w+gap),dims[index][1]/2+k*(d+gap),base+r*pitch)
                ob['shelf_row']=r+1;ob['facing']=c+1;ob['stock_depth']=k+1
                placed.append(ob)
    for ob in boxes:bpy.data.objects.remove(ob,do_unlink=True)
    scene['planogram']=json.dumps(dict(settings,box_count=len(placed),width_m=width,depth_m=depth,height_m=height))
    target=bpy.data.objects.new('Shelf camera target',None);scene.collection.objects.link(target)
    target.location=(0,depth*.25,height*.5)
    data=bpy.data.cameras.new('Shelf camera');data.lens=45;data.dof.use_dof=False
    cam=bpy.data.objects.new('Shelf camera',data);scene.collection.objects.link(cam)
    aspect=scene.render.resolution_x/scene.render.resolution_y
    dist=max(width,height*aspect)*data.lens/36*1.4
    cam.location=(width*.18,-dist,height*.62)
    cam.rotation_euler=(Vector(target.location)-cam.location).to_track_quat('-Z','Y').to_euler()
    scene.camera=cam
    print('Shelf planogram: %s, %d shelves, %d facings, %d deep, %d boxes'%(preset,rows,facings,stock,len(placed)))
    return placed
