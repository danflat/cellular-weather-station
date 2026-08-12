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
    try:
        with urllib.request.urlopen(req,timeout=60) as r:
            return r.status,dict(r.headers),r.read()
    except urllib.error.HTTPError as e:
        return e.code,dict(e.headers),e.read()

html=None; page_url=None
for candidate in (SITE+'/',SITE+'/library'):
    st,hd,b=get(candidate)
    text=b.decode('utf-8','replace')
    if st<400 and '<script' in text:
        html=text; page_url=candidate; break
if not html: raise RuntimeError('Could not fetch site HTML')
(out/'index.html').write_text(html,encoding='utf-8')

srcs=re.findall(r'<script\b[^>]*?src=["\']([^"\']+)["\']',html,flags=re.I)
if not srcs: raise RuntimeError('No script src found')
# choose module/assets JS first
script_src=next((s for s in srcs if '/assets/' in s and s.endswith('.js')),srcs[-1])
bundle_url=urllib.parse.urljoin(page_url,script_src)
st,hd,b=get(bundle_url)
if st>=400: raise RuntimeError(f'Bundle fetch failed {st}')
js=b.decode('utf-8','replace')
(out/'bundle.js').write_text(js,encoding='utf-8')

projects=sorted(set(re.findall(r'https://[a-z0-9]+\.supabase\.co',js)))
keys=re.findall(r'eyJ[\w-]+\.eyJ[\w-]+\.[\w-]+',js)+re.findall(r'sb_publishable_[A-Za-z0-9._-]+',js)
# public keys are intentionally not written to artifact/log
interesting=[]
for term in ['bibles','bible_pages','files','documents','library','storage/v1','rest/v1','supabase','approved','file_path','file_name','download']:
    positions=[m.start() for m in re.finditer(re.escape(term),js,flags=re.I)]
    interesting.append({'term':term,'count':len(positions),'positions':positions[:20]})

url_candidates=sorted(set(re.findall(r'https://[^"\'`\\\s]+',js)))
# keep only host/path discovery, strip query/fragments and redact JWT-like strings
safe_urls=[]
for u in url_candidates:
    u=re.sub(r'eyJ[\w-]+\.eyJ[\w-]+\.[\w-]+','<redacted-public-key>',u)
    if any(x in u for x in ['supabase','freebibleaccess','storage','rest','api']): safe_urls.append(u[:500])

endpoint_tests=[]
for base in projects:
    for p in ['/rest/v1/','/rest/v1/bibles?select=id&limit=1','/rest/v1/bible_pages?select=id&limit=1','/storage/v1/bucket']:
        headers={}
        if keys:
            headers['apikey']=keys[0]
            if keys[0].startswith('eyJ'): headers['Authorization']='Bearer '+keys[0]
        st,resp_h,body=get(base+p,headers)
        endpoint_tests.append({'url':base+p.split('?')[0],'status':st,'body_prefix':body[:300].decode('utf-8','replace')})

summary={
 'fetched_at':datetime.now(timezone.utc).isoformat(),
 'page_url':page_url,'bundle_url':bundle_url,'bundle_bytes':len(b),
 'supabase_projects':projects,'public_key_found':bool(keys),
 'script_srcs':srcs,'interesting_terms':interesting,
 'safe_url_candidates':safe_urls[:200],
 'endpoint_tests':endpoint_tests
}
(out/'diagnostic.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
print('DIAGNOSTIC='+json.dumps(summary,separators=(',',':')))
