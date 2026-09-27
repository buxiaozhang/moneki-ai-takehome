import json, urllib.request, io
def post(u, payload):
    r=urllib.request.Request(u, data=json.dumps(payload).encode('utf-8'),
        headers={'Content-Type':'application/json; charset=utf-8'})
    return json.loads(urllib.request.urlopen(r, timeout=40).read().decode('utf-8'))
def get(u):
    return json.loads(urllib.request.urlopen(u, timeout=20).read().decode('utf-8'))
# 用一条会同时触发"取数 + 引用"的问题，让夹具覆盖 hybrid 的全部中间态
q='S03 六月第二周营业额为什么这么低'
r=post('http://127.0.0.1:8000/api/chat', {'question':q,'session_id':'fixture'})
t=get('http://127.0.0.1:8000/api/trace/'+r['trace_id'])
out={'note':'由 tests/fixtures/make_trace_fixture.py 从真实服务抓取，勿手改','chat':r,'trace':t}
with io.open('tests/fixtures/trace_sample.json','w',encoding='utf-8') as fh:
    json.dump(out, fh, ensure_ascii=False, indent=1)
print('  trace_id =', t['trace_id'], ' steps =', len(t['steps']),
      ' hits =', len(next(s for s in t['steps'] if s['step']=='search')['detail']['hits']))
