"""CSV/DataFrame 묶음 → 단일 HTML 데이터 뷰어 (외부 라이브러리 없음, 오프라인 동작).
기능: 데이터셋 선택, 정렬, 열별 필터(>=2, 2..5, !단어, (빈값)), 전체 검색, 열 선택, 요약 통계, CSV 내보내기.
    from sciharness.viewer import build_viewer
    build_viewer({"결과": df, "원자료": "data/raw.csv"}, "outputs/viewer.html", title="데이터 뷰어")
"""
from __future__ import annotations
import html, json
from pathlib import Path
import pandas as pd

_JS = r"""
const DS=__DATA__;let cur=Object.keys(DS)[0],sortC=null,sortD=1,filt={},hidden={},q='';
const $=s=>document.querySelector(s);
function num(v){if(v===null||v===''||v===undefined)return NaN;const x=Number(v);return isNaN(x)?NaN:x}
function pass(v,f){f=f.trim();if(!f)return true;if(f==='(빈값)')return v===null||v==='';
 let m;if(m=f.match(/^(>=|<=|>|<|=)\s*(-?[\d.eE+-]+)$/)){const x=num(v),y=Number(m[2]);if(isNaN(x))return false;
  return {'>=':x>=y,'<=':x<=y,'>':x>y,'<':x<y,'=':x==y}[m[1]]}
 if(m=f.match(/^(-?[\d.eE+-]+)\s*\.\.\s*(-?[\d.eE+-]+)$/)){const x=num(v);return !isNaN(x)&&x>=Number(m[1])&&x<=Number(m[2])}
 const s=String(v??'').toLowerCase();if(f.startsWith('!'))return !s.includes(f.slice(1).toLowerCase());return s.includes(f.toLowerCase())}
function rows(){const d=DS[cur];let r=d.rows.filter(row=>d.cols.every((c,i)=>pass(row[i],filt[c]||''))&&
 (!q||row.some(v=>String(v??'').toLowerCase().includes(q))));
 if(sortC!==null){const i=d.cols.indexOf(sortC);r=[...r].sort((a,b)=>{const x=num(a[i]),y=num(b[i]);
  if(!isNaN(x)&&!isNaN(y))return (x-y)*sortD;return String(a[i]??'').localeCompare(String(b[i]??''),'ko')*sortD})}return r}
function render(){const d=DS[cur],r=rows(),vis=d.cols.map((c,i)=>[c,i]).filter(([c])=>!hidden[cur+c]);
 let h='<thead><tr>'+vis.map(([c])=>`<th onclick="srt('${c.replace(/'/g,"\\'")}')">${c}${sortC===c?(sortD>0?' ▲':' ▼'):''}</th>`).join('')+'</tr><tr>'+
 vis.map(([c])=>`<th><input data-c="${c}" value="${(filt[c]||'').replace(/"/g,'&quot;')}" placeholder="필터" oninput="flt(this)"></th>`).join('')+'</tr></thead><tbody>';
 h+=r.slice(0,3000).map(row=>'<tr>'+vis.map(([c,i])=>`<td>${row[i]??''}</td>`).join('')+'</tr>').join('')+'</tbody>';
 $('#t').innerHTML=h;$('#n').textContent=`${r.length.toLocaleString()} / ${d.rows.length.toLocaleString()} 행`+(r.length>3000?' (상위 3000행 표시)':'');
 $('#cols').innerHTML=d.cols.map(c=>`<label><input type="checkbox" ${hidden[cur+c]?'':'checked'} onchange="hid('${c.replace(/'/g,"\\'")}',this)">${c}</label>`).join(' ');
 $('#note').textContent=d.note||'';stats(r)}
function stats(r){const d=DS[cur];let h='<tr><th>열</th><th>n</th><th>평균</th><th>최소</th><th>최대</th></tr>';
 d.cols.forEach((c,i)=>{const v=r.map(x=>num(x[i])).filter(x=>!isNaN(x));if(v.length){const m=v.reduce((a,b)=>a+b,0)/v.length;
 h+=`<tr><td>${c}</td><td>${v.length}</td><td>${m.toPrecision(4)}</td><td>${Math.min(...v).toPrecision(4)}</td><td>${Math.max(...v).toPrecision(4)}</td></tr>`}});$('#s').innerHTML=h}
function srt(c){if(sortC===c)sortD=-sortD;else{sortC=c;sortD=1}render()}
function flt(el){filt[el.dataset.c]=el.value;const p=el.selectionStart;render();const n=document.querySelector(`input[data-c="${el.dataset.c}"]`);if(n){n.focus();n.setSelectionRange(p,p)}}
function hid(c,el){hidden[cur+c]=!el.checked;render()}
function sel(k){cur=k;sortC=null;filt={};render()}
function csv(){const d=DS[cur],r=rows();const e=v=>{v=String(v??'');return /[",\n]/.test(v)?'"'+v.replace(/"/g,'""')+'"':v};
 const t='\ufeff'+[d.cols.map(e).join(','),...r.map(x=>x.map(e).join(','))].join('\n');const a=document.createElement('a');
 a.href=URL.createObjectURL(new Blob([t],{type:'text/csv'}));a.download=cur+'.csv';a.click()}
window.onload=()=>{$('#ds').innerHTML=Object.keys(DS).map(k=>`<option>${k}</option>`).join('');render()};
"""

def build_viewer(datasets: dict, out_html: str | Path, title: str = "데이터 뷰어", notes: dict | None = None) -> Path:
    data = {}
    for name, src in datasets.items():
        df = src if isinstance(src, pd.DataFrame) else pd.read_csv(src)
        df = df.astype(object).where(pd.notna(df), None)
        data[name] = {"cols": [str(c) for c in df.columns], "rows": df.values.tolist(),
                      "note": (notes or {}).get(name, "")}
    js = _JS.replace("__DATA__", json.dumps(data, ensure_ascii=False, default=str))
    css = ("body{font-family:'Malgun Gothic',sans-serif;margin:16px;color:#222}table{border-collapse:collapse;font-size:12.5px}"
           "th,td{border:1px solid #D0D7E2;padding:3px 6px;vertical-align:top}th{background:#E8EEF6;cursor:pointer;position:sticky;top:0}"
           "input{width:100%;box-sizing:border-box;font-size:11px}#wrap{max-height:70vh;overflow:auto;border:1px solid #ccc}"
           "#cols label{margin-right:8px;font-size:12px}.bar{margin:8px 0}")
    doc = (f'<!DOCTYPE html><html lang="ko"><head><meta charset="utf-8"><title>{html.escape(title)}</title><style>{css}</style></head><body>'
           f'<h2>{html.escape(title)}</h2><div class="bar">데이터셋 <select id="ds" onchange="sel(this.value)"></select> '
           f'검색 <input style="width:200px" oninput="q=this.value.toLowerCase();render()"> <button onclick="csv()">CSV 내보내기</button> '
           f'<span id="n"></span></div><div class="bar" id="note" style="color:#555;font-size:12px"></div>'
           f'<details class="bar"><summary>열 선택</summary><div id="cols"></div></details>'
           f'<div class="bar" style="font-size:12px;color:#555">필터 문법: <code>&gt;=2</code>, <code>2..5</code>, <code>!단어</code>(제외), <code>(빈값)</code></div>'
           f'<div id="wrap"><table id="t"></table></div><h3>요약 통계(필터 적용 후)</h3><table id="s"></table><script>{js}</script></body></html>')
    out_html = Path(out_html); out_html.parent.mkdir(parents=True, exist_ok=True)
    out_html.write_text(doc, encoding="utf-8")
    return out_html
