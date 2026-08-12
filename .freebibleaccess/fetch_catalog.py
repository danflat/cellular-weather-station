import json, urllib.parse, urllib.request
from datetime import datetime, timezone
from pathlib import Path

SITE='https://freebibleaccess.com'
BASE='https://kgvgblcslhilhjfisacb.supabase.co'
# Public anon client key captured from the current site's public JS bundle.
ANON='eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImtndmdibGNzbGhpbGhqZmlzYWNiIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODY0OTM4MDUsImV4cCI6MjEwMjA2OTgwNX0.AGxTAzjqgnFcCXx3Wgb1UB3uyBcGvsSsu8nL9qNSFaA'
BUCKET='library-files'
out=Path('freebibleaccess-output'); out.mkdir(exist_ok=True)
headers={'apikey':ANON,'Authorization':'Bearer '+ANON,'Accept':'application/json','User-Agent':'Mozilla/5.0 (compatible; FreeBibleAccessIngest/1.0)'}

def get(url):
    req=urllib.request.Request(url,headers=headers)
    with urllib.request.urlopen(req,timeout=60) as r:
        return r.read()

select='id,uploader_id,name,description,size_bytes,mime_type,storage_path,download_count,approved,created_at'
q=urllib.parse.urlencode({'select':select,'order':'created_at.asc','limit':'1000'},safe='*,():!')
files=json.loads(get(BASE+'/rest/v1/files?'+q))
if not isinstance(files,list): raise RuntimeError('Unexpected files response')
approved=sum(1 for f in files if f.get('approved'))
pending=len(files)-approved
total_bytes=sum(int(f.get('size_bytes') or 0) for f in files)
by_mime={}
for f in files:
    m=f.get('mime_type') or 'unknown'; by_mime[m]=by_mime.get(m,0)+1
summary={'fetched_at':datetime.now(timezone.utc).isoformat(),'site':SITE,'supabase_base':BASE,'bucket':BUCKET,'file_count':len(files),'approved_count':approved,'pending_count':pending,'total_bytes':total_bytes,'total_gib':round(total_bytes/1024**3,3),'by_mime':dict(sorted(by_mime.items()))}
(out/'live_catalog.json').write_text(json.dumps({'summary':summary,'files':files},indent=2,ensure_ascii=False),encoding='utf-8')
(out/'live_summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
print('FREEBIBLEACCESS_SUMMARY='+json.dumps(summary,separators=(',',':')))
