#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import json
d=json.load(open('/tmp/pilot_demo_data.json',encoding='utf-8'))
payload=json.dumps(d,ensure_ascii=False,separators=(',',':'))
st=d['stats']

CSS=r"""
:root{--ground:#eceef1;--surface:#fff;--surface-2:#f5f7f9;--line:#d8dde3;--ink:#1a1d22;--muted:#646b76;--faint:#98a0aa;
--accent:#c05314;--accent-soft:#f4e3d7;--accent-ink:#8f3d0f;--steel:#2f4a63;--hi:#fff3d6;--hi-line:#e0a83c;--ok:#1a7d4f;
--mono:ui-monospace,"Consolas",monospace;--sans:system-ui,-apple-system,"Segoe UI","Noto Sans","Noto Sans SC",Arial,sans-serif;}
@media(prefers-color-scheme:dark){:root{--ground:#0f1215;--surface:#181c22;--surface-2:#1f242b;--line:#2b323b;--ink:#e6e9ee;--muted:#98a1ac;--faint:#69727e;--accent:#e8792f;--accent-soft:#3a2416;--accent-ink:#f0a06a;--steel:#8fb0cd;--hi:#3a3016;--hi-line:#7a5e1e;--ok:#57c98a;}}
*{box-sizing:border-box}html,body{margin:0;padding:0}
body{background:var(--ground);color:var(--ink);font-family:var(--sans);font-size:15px;line-height:1.45}
header{background:var(--steel);color:#fff;padding:14px 22px}
header h1{margin:0;font-size:18px;font-weight:800}
header .sub{font-size:13px;opacity:.9;margin-top:3px}
.banner{background:var(--accent-soft);color:var(--accent-ink);padding:9px 22px;font-size:13px;border-bottom:1px solid var(--line)}
.banner b{font-variant-numeric:tabular-nums}
.wrap{display:grid;grid-template-columns:250px 1fr;gap:0;height:calc(100vh - 96px)}
@media(max-width:820px){.wrap{grid-template-columns:1fr;height:auto}}
.plist{border-right:1px solid var(--line);overflow-y:auto;background:var(--surface)}
.pitem{padding:9px 14px;border-bottom:1px solid var(--line);cursor:pointer;font-size:13px}
.pitem:hover{background:var(--surface-2)}
.pitem.on{background:var(--accent-soft);border-left:3px solid var(--accent)}
.pitem .u{font-weight:600}
.pitem .m{color:var(--faint);font-size:11.5px;margin-top:2px;font-variant-numeric:tabular-nums}
.pitem .m.full{color:var(--ok)}
.main{overflow-y:auto;padding:16px 20px}
.plate{display:grid;grid-template-columns:1.15fr 1fr;gap:18px}
@media(max-width:1000px){.plate{grid-template-columns:1fr}}
.figwrap{position:relative;align-self:start;border:1px solid var(--line);border-radius:8px;overflow:hidden;background:#fff}
.figwrap img{width:100%;display:block}
.hot{position:absolute;width:26px;height:26px;margin:-13px 0 0 -13px;border:2px solid var(--accent);border-radius:50%;
background:rgba(192,83,20,.14);color:var(--accent-ink);font-size:11px;font-weight:800;display:flex;align-items:center;justify-content:center;
cursor:pointer;transition:transform .1s,background .1s;font-variant-numeric:tabular-nums;backdrop-filter:saturate(1.2)}
.hot:hover,.hot.on{background:var(--accent);color:#fff;transform:scale(1.25);z-index:5}
.tbl{align-self:start}
table{width:100%;border-collapse:collapse;font-size:13px}
th{background:var(--surface-2);text-align:left;font-size:10.5px;text-transform:uppercase;letter-spacing:.05em;color:var(--muted);font-weight:700;padding:8px 10px;border-bottom:1px solid var(--line)}
td{padding:7px 10px;border-bottom:1px solid var(--line);vertical-align:top}
tr[data-pos]{cursor:pointer}
tr:hover{background:var(--surface-2)}
tr.on{background:var(--hi);box-shadow:inset 3px 0 0 var(--hi-line)}
td.pos b{display:inline-block;min-width:22px;padding:1px 5px;border:1.5px solid var(--steel);border-radius:11px;font-size:12px;color:var(--steel);text-align:center}
td.pos.noloc b{border-style:dashed;opacity:.5}
td.num{font-family:var(--mono);font-size:12px;white-space:nowrap}
.warn{font-size:11.5px;color:var(--faint);margin:6px 0 0}
.phead{grid-column:1/-1;margin:0 0 4px}
.phead h2{margin:0;font-size:17px;font-weight:800}
.phead .eq{font-size:11px;text-transform:uppercase;letter-spacing:.1em;color:var(--muted);font-weight:700}
.phead .cnt{font-size:12.5px;color:var(--muted);margin-top:3px}
.hint{font-size:12px;color:var(--faint);margin:2px 0 12px}
"""

JS=r"""
var D=__PAYLOAD__, P=D.plates, cur=0;
var $=function(s,e){return (e||document).querySelector(s);};
function esc(s){return (s||'').replace(/[&<>]/g,function(c){return{'&':'&amp;','<':'&lt;','>':'&gt;'}[c];});}
function renderList(){
  var h='';P.forEach(function(p,i){
    var full=p.located===p.total;
    h+='<div class="pitem '+(i===cur?'on':'')+'" data-i="'+i+'"><div class="u">'+esc(p.unit)+'</div>'+
       '<div class="m '+(full?'full':'')+'">'+p.eq+' · '+p.located+'/'+p.total+' выносок'+(full?' ✓':'')+'</div></div>';});
  $('#plist').innerHTML=h;
  document.querySelectorAll('.pitem').forEach(function(el){el.onclick=function(){cur=+el.dataset.i;renderList();renderPlate();};});
}
function renderPlate(){
  var p=P[cur];
  var hots='';
  p.rows.forEach(function(r){
    if(r.x==null)return;
    hots+='<div class="hot" data-pos="'+esc(r.pos)+'" style="left:'+(r.x*100)+'%;top:'+(r.y*100)+'%">'+esc(r.pos)+'</div>';
  });
  var rows='';
  p.rows.forEach(function(r){
    var noloc=r.x==null;
    rows+='<tr data-pos="'+esc(r.pos)+'"><td class="pos'+(noloc?' noloc':'')+'"><b>'+esc(r.pos)+'</b></td>'+
      '<td class="num">'+esc(r.num)+'</td><td>'+(esc(r.name)||'—')+'</td></tr>';
  });
  var miss=p.total-p.located;
  $('#main').innerHTML=
    '<div class="plate"><div class="phead"><div class="eq">'+p.eq+' · '+esc(p.img)+'</div>'+
    '<h2>'+esc(p.unit)+'</h2><div class="cnt">Выносок на чертеже: <b>'+p.located+'</b> из '+p.total+
    (miss?' · <span style="color:var(--faint)">'+miss+' не локализовано (сложный лист)</span>':' · все найдены ✓')+'</div>'+
    '<div class="hint">Наведите/кликните точку на чертеже или строку таблицы — они подсветятся взаимно.</div></div>'+
    '<div class="figwrap" id="figwrap"><img src="'+p.src+'" alt="">'+hots+'</div>'+
    '<div class="tbl"><table><thead><tr><th>Поз.</th><th>Номер детали</th><th>Наименование</th></tr></thead><tbody>'+rows+'</tbody></table>'+
    (miss?'<div class="warn">Пунктирные позиции — выноска не размечена (на этом листе они тесно наложены на графику; в реальном прогоне такие правятся вручную).</div>':'')+
    '</div></div>';
  // взаимная подсветка
  function link(pos,on){
    document.querySelectorAll('.hot[data-pos="'+pos+'"]').forEach(function(h){h.classList.toggle('on',on);});
    document.querySelectorAll('tr[data-pos="'+pos+'"]').forEach(function(t){t.classList.toggle('on',on);});
  }
  document.querySelectorAll('#figwrap .hot').forEach(function(h){
    h.onmouseenter=function(){link(h.dataset.pos,true);};
    h.onmouseleave=function(){link(h.dataset.pos,false);};
    h.onclick=function(){var t=document.querySelector('tr[data-pos="'+h.dataset.pos+'"]');if(t)t.scrollIntoView({block:'center',behavior:'smooth'});};
  });
  document.querySelectorAll('tr[data-pos]').forEach(function(t){
    t.onmouseenter=function(){link(t.dataset.pos,true);};
    t.onmouseleave=function(){link(t.dataset.pos,false);};
    t.onclick=function(){var hh=document.querySelector('.hot[data-pos="'+t.dataset.pos+'"]');if(hh)hh.scrollIntoView({block:'center',behavior:'smooth'});};
  });
}
renderList();renderPlate();
"""

html=('<!DOCTYPE html><html lang="ru"><head><meta charset="utf-8">'
      '<meta name="viewport" content="width=device-width, initial-scale=1">'
      '<meta name="color-scheme" content="light dark"><title>Пилот: кликабельные выноски на чертеже</title>'
      f'<style>{CSS}</style></head><body>'
      '<header><h1>Пилот · кликабельные выноски на чертеже</h1>'
      '<div class="sub">Клик по номеру-выноске на чертеже ↔ подсветка строки в спецификации</div></header>'
      f'<div class="banner">Обработано листов: <b>{st["plates"]}</b> · выносок всего: <b>{st["total_callouts"]}</b> · '
      f'локализовано автоматически: <b>{st["located"]} ({st["pct"]}%)</b> — координаты определены vision-моделью, без OCR</div>'
      '<div class="wrap"><div class="plist" id="plist"></div><div class="main" id="main"></div></div>'
      f'<script>{JS.replace("__PAYLOAD__",payload)}</script></body></html>')
open('/tmp/pilot_callouts.html','w',encoding='utf-8').write(html)
import os
print('HTML:', round(os.path.getsize('/tmp/pilot_callouts.html')/1024/1024,1),'МБ')
