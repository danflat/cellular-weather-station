import json, re, urllib.parse, urllib.request, urllib.error
from datetime import datetime, timezone
from pathlib import Path

SITE='https://freebibleaccess.com'
UA='Mozilla/5.0 (compatible; FreeBibleAccessIngest/1.0)'
out=Path('freebibleaccess-output'); out.mkdir(exist_ok=True)

def get(url, headers=None):
    h={'User-Agent':UA,'Accept':'*/*'}
    if headers: h.update(headers)
    req=urllib.request.Request(url,headers=h)
    with urllib.request.urlopen(req,timeout=60) as r:
        return r.status,dict(r.headers),r.read()

html=None; page_url=None
for candidate in (SITE+'/',SITE+'/library'):
    try:
        st,hd,b=get(candidate)
        text=b.decode('utf-8','replace')
        if st<400 and '<script' in text:
            html=text; page_url=candidate; break
    except Exception:
        pass
if not html: raise RuntimeError('Could not fetch site HTML')
srcs=re.findall(r'<script\b[^>]*?src=["\']([^"\']+)["\']',html,flags=re.I)
script_src=next((s for s in srcs if '/assets/' in s and s.endswith('.js')),srcs[-1])
bundle_url=urllib.parse.urljoin(page_url,script_src)
st,hd,b=get(bundle_url); js=b.decode('utf-8','replace')
base=re.search(r'https://[a-z0-9]+\.supabase\.co',js).group(0)
km=re.search(r'eyJ[\w-]+\.eyJ[\w-]+\.[\w-]+',js) or re.search(r'sb_publishable_[A-Za-z0-9._-]+',js)
if not km: raise RuntimeError('Public Supabase key not found')
key=km.group(0)
headers={'apikey':key,'Authorization':'Bearer '+key,'Accept':'application/json'}

select='id,uploader_id,name,description,size_bytes,mime_type,storage_path,download_count,approved,created_at'
q=urllib.parse.urlencode({'select':select,'order':'created_at.asc','limit':'1000'},safe='*,():!')
st,hd,body=get(base+'/rest/v1/files?'+q,headers)
files=json.loads(body)
if not isinstance(files,list): raise RuntimeError('Unexpected files response: '+body[:500].decode('utf-8','replace'))

approved=sum(1 for f in files if f.get('approved'))
pending=len(files)-approved
total_bytes=sum(int(f.get('size_bytes') or 0) for f in files)
by_mime={}
for f in files:
    m=f.get('mime_type') or 'unknown'; by_mime[m]=by_mime.get(m,0)+1
summary={
 'fetched_at':datetime.now(timezone.utc).isoformat(),
 'site':SITE,'bundle_url':bundle_url,'supabase_base':base,'bucket':'library-files',
 'file_count':len(files),'approved_count':approved,'pending_count':pending,
 'total_bytes':total_bytes,'total_gib':round(total_bytes/1024**3,3),
 'by_mime':dict(sorted(by_mime.items()))
}
(out/'live_catalog.json').write_text(json.dumps({'summary':summary,'files':files},indent=2,ensure_ascii=False),encoding='utf-8')
(out/'live_summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
print('FREEBIBLEACCESS_SUMMARY='+json.dumps(summary,separators=(',',':')))
