import json, re, urllib.parse, urllib.request
from datetime import datetime, timezone
from pathlib import Path

SITE = 'https://freebibleaccess.com'
UA = 'Mozilla/5.0 (compatible; FreeBibleAccessIngest/1.0)'

def get(url, headers=None):
    h = {'User-Agent': UA, 'Accept': '*/*'}
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, headers=h)
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()

html = None
page_url = None
for candidate in (SITE + '/', SITE + '/library'):
    try:
        text = get(candidate).decode('utf-8', 'replace')
        if '<script' in text:
            html, page_url = text, candidate
            break
    except Exception:
        pass
if not html:
    raise RuntimeError('Could not fetch site HTML')

script_src = None
for tag in re.findall(r'<script\b[^>]*>', html, flags=re.I):
    if re.search(r'type=["\']module["\']', tag, flags=re.I):
        m = re.search(r'src=["\']([^"\']+)["\']', tag, flags=re.I)
        if m:
            script_src = m.group(1)
            break
if not script_src:
    m = re.search(r'src=["\']([^"\']*/assets/[^"\']+\.js)["\']', html, flags=re.I)
    if m:
        script_src = m.group(1)
if not script_src:
    raise RuntimeError('Could not locate frontend bundle')

bundle_url = urllib.parse.urljoin(page_url, script_src)
js = get(bundle_url).decode('utf-8', 'replace')
pm = re.search(r'https://[a-z0-9]+\.supabase\.co', js)
if not pm:
    raise RuntimeError('Could not find Supabase project')
base = pm.group(0)
km = re.search(r'eyJ[\w-]+\.eyJ[\w-]+\.[\w-]+', js) or re.search(r'sb_publishable_[A-Za-z0-9._-]+', js)
if not km:
    raise RuntimeError('Could not find public Supabase key')
key = km.group(0)
headers = {'apikey': key}
if key.startswith('eyJ'):
    headers['Authorization'] = 'Bearer ' + key

def get_json(url):
    return json.loads(get(url, headers))

rest = base + '/rest/v1'
books_q = urllib.parse.urlencode({'select':'*,profiles:user_id(display_name)','status':'eq.approved','order':'created_at.asc','limit':'1000'}, safe='*,():.')
pages_q = urllib.parse.urlencode({'select':'id,bible_id,image_path,image_name,page_order','order':'page_order.asc','limit':'5000'}, safe='*,():.')
books = get_json(rest + '/bibles?' + books_q)
pages = get_json(rest + '/bible_pages?' + pages_q)
for b in books:
    p = b.get('profiles') or {}
    b['display_name'] = p.get('display_name') or 'Anonymous'

out = Path('freebibleaccess-output')
out.mkdir(exist_ok=True)
catalog = {'fetched_at':datetime.now(timezone.utc).isoformat(),'site':SITE,'page_url':page_url,'bundle_url':bundle_url,'supabase_base':base,'storage_base':base+'/storage/v1/object/public/bibles','books':books,'pages':pages}
(out/'live_catalog.json').write_text(json.dumps(catalog,indent=2,ensure_ascii=False),encoding='utf-8')
by_category={}
by_type={}
for b in books:
    c=b.get('category') or ''
    t=b.get('file_type') or ''
    by_category[c]=by_category.get(c,0)+1
    by_type[t]=by_type.get(t,0)+1
summary={'fetched_at':catalog['fetched_at'],'book_count':len(books),'page_record_count':len(pages),'by_category':dict(sorted(by_category.items())),'by_type':dict(sorted(by_type.items()))}
(out/'live_summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
print('FREEBIBLEACCESS_SUMMARY='+json.dumps(summary,separators=(',',':')))
