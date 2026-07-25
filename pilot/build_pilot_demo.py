#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Собрать демо кликабельных выносок для пилотных листов."""
import json, os, base64

ROOT='/home/user/KMZ-Parts_book'
IMGDIR=os.path.join(ROOT,'catalog_book','img')
coords=json.load(open('/tmp/pilot_coords.json',encoding='utf-8'))
pick=json.load(open('/tmp/pilot_plates.json',encoding='utf-8'))

# карта img -> позиции (num,name) из выбранных листов;
# для листа "Ключ" реальные выноски на p124, поэтому добавим его позиции к p124
def positions_for(img, plate):
    return {p:(num,name) for p,num,name in plate['positions']}

demo=[]
# сопоставим каждому листу изображение с выносками
img_override={'bs230_p123.jpg':'bs230_p124.jpg','bs215_p053.jpg':'bs215_p054.jpg'}  # общий вид -> детальный
seen=set()
for pl in pick:
    img=pl['img']
    real_img=img_override.get(img,img)
    if real_img in seen: continue
    seen.add(real_img)
    pos_map=positions_for(real_img, pl)
    cmap=coords.get(real_img,{})
    # база64 картинки
    fp=os.path.join(IMGDIR,real_img)
    b64=base64.b64encode(open(fp,'rb').read()).decode('ascii')
    rows=[]
    for p,(num,name) in sorted(pos_map.items(), key=lambda kv:(len(kv[0]),kv[0])):
        xy=cmap.get(p)
        rows.append({'pos':p,'num':num,'name':name,
                     'x':xy[0] if xy else None,'y':xy[1] if xy else None})
    located=sum(1 for r in rows if r['x'] is not None)
    demo.append({'img':real_img,'src':'data:image/jpeg;base64,'+b64,
                 'eq':pl['eq'],'unit':pl['unit'],'total':len(rows),'located':located,'rows':rows})

# статистика точности
tot=sum(d['total'] for d in demo); loc=sum(d['located'] for d in demo)
stats={'plates':len(demo),'total_callouts':tot,'located':loc,'pct':round(loc*100/tot)}
json.dump({'stats':stats,'plates':demo}, open('/tmp/pilot_demo_data.json','w',encoding='utf-8'),ensure_ascii=False)
print('Листов:',len(demo),'| выносок всего:',tot,'| локализовано:',loc,f'({stats["pct"]}%)')
for d in demo:
    print(f"  {d['img']:16} {d['located']:2}/{d['total']:2}  {d['unit'][:34]}")
