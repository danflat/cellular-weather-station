import hashlib, json, os, re, urllib.parse, urllib.request
from pathlib import Path

BASE='https://kgvgblcslhilhjfisacb.supabase.co'
ANON='eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImtndmdibGNzbGhpbGhqZmlzYWNiIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODY0OTM4MDUsImV4cCI6MjEwMjA2OTgwNX0.AGxTAzjqgnFcCXx3Wgb1UB3uyBcGvsSsu8nL9qNSFaA'
BUCKET='library-files'
CHUNK_COUNT=int(os.environ.get('CHUNK_COUNT','4'))
CHUNK_INDEX=int(os.environ.get('CHUNK_INDEX','0'))
headers={'apikey':ANON,'Authorization':'Bearer '+ANON,'Accept':'application/json','User-Agent':'Mozilla/5.0 (compatible; FreeBibleAccessIngest/1.0)'}

def request(url, accept=None):
    h=dict(headers)
    if accept: h['Accept']=accept
    req=urllib.request.Request(url,headers=h)
    with urllib.request.urlopen(req,timeout=180) as r:
        return r.read(), dict(r.headers)

select='id,uploader_id,name,description,size_bytes,mime_type,storage_path,download_count,approved,created_at'
q=urllib.parse.urlencode({'select':select,'approved':'eq.true','order':'created_at.asc','limit':'1000'},safe='*,():!')
body,_=request(BASE+'/rest/v1/files?'+q)
files=json.loads(body)
if len(files)!=116:
    raise RuntimeError(f'Expected 116 approved files, got {len(files)}')

# Greedy size balancing gives four roughly equal transfer artifacts.
bins=[[] for _ in range(CHUNK_COUNT)]; totals=[0]*CHUNK_COUNT
for f in sorted(files,key=lambda x:int(x.get('size_bytes') or 0),reverse=True):
    i=min(range(CHUNK_COUNT),key=lambda n:totals[n])
    bins[i].append(f); totals[i]+=int(f.get('size_bytes') or 0)
selected=sorted(bins[CHUNK_INDEX],key=lambda x:x['created_at'])

root=Path('freebibleaccess-download')/f'chunk-{CHUNK_INDEX}'
filedir=root/'files'; filedir.mkdir(parents=True,exist_ok=True)
manifest=[]
for n,f in enumerate(selected,1):
    original=f['name']
    # Avoid path traversal/path separators while otherwise preserving the name.
    safe_name=re.sub(r'[\\/]+','_',original).strip() or f['id']
    dest=filedir/safe_name
    quoted=urllib.parse.quote(f['storage_path'],safe='/')
    url=f'{BASE}/storage/v1/object/{BUCKET}/{quoted}'
    data,resp_headers=request(url,accept='application/octet-stream')
    expected=int(f.get('size_bytes') or 0)
    if expected and len(data)!=expected:
        raise RuntimeError(f'Size mismatch for {original}: expected {expected}, got {len(data)}')
    dest.write_bytes(data)
    sha=hashlib.sha256(data).hexdigest()
    detected='application/pdf' if data.startswith(b'%PDF-') else (resp_headers.get('Content-Type') or f.get('mime_type'))
    manifest.append({**f,'local_name':safe_name,'downloaded_bytes':len(data),'sha256':sha,'detected_type':detected})
    print(f'[{CHUNK_INDEX}] {n}/{len(selected)} OK {len(data)} {original}')

(root/'chunk_manifest.json').write_text(json.dumps({'chunk_index':CHUNK_INDEX,'chunk_count':CHUNK_COUNT,'planned_bytes':totals[CHUNK_INDEX],'downloaded_count':len(manifest),'files':manifest},indent=2,ensure_ascii=False),encoding='utf-8')
print(json.dumps({'chunk':CHUNK_INDEX,'count':len(manifest),'bytes':sum(x['downloaded_bytes'] for x in manifest),'planned_totals':totals}))
