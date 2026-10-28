"""Fetch only three reviewed attributed GLBs from an immutable catalogue commit.
Does not execute downloaded code. Fail closed on checksum or license mismatch.
"""
import hashlib, json, urllib.request
from pathlib import Path
ROOT = Path(__file__).resolve().parent
COMMIT = '2d18dfd9db96bbf0d9cffa949deaf7f571388cbf'
BASE = f'https://raw.githubusercontent.com/pedrosoandre/carros/{COMMIT}/'
MODELS = {
 'porsche-911-930.glb': ('8568d9d14a994b9cae59499f0dbed21e','917335eba55814cb25217b3823aa303d57b63779934162bf73eb931a6803b8c2'),
 'audi-r8.glb': ('e17e438f076f4427a58d93aa779edaed','627004f3b68fe3ab2917159d7798c22d125f32f1c6d5eb064c0f68947a02f20e'),
 'bmw-m3-e30.glb': ('ac3c7013434e403e8faff87948caf422','35cad98e89e6f1e54ccd238a3df049d29f20ecec3fc0aa2a85e0ad6c2663d330'),
}
def get(url):
    req=urllib.request.Request(url,headers={'User-Agent':'Check92-asset-review'})
    with urllib.request.urlopen(req,timeout=90) as response:
        return response.read()

def main():
    assets=ROOT/'assets'
    assets.mkdir(parents=True,exist_ok=True)
    catalog=json.loads(get(BASE+'cars.json'))
    records=[]
    for name,(source_id,expected) in MODELS.items():
        matches=[c for c in catalog['cars'] if c['file']==name and source_id in json.dumps(c.get('credit',{}))]
        if len(matches)!=1:
            raise ValueError('Missing or ambiguous provenance: '+name)
        record=matches[0]
        if record['credit'].get('license') not in ('CC Attribution','CC BY','CC BY 4.0'):
            raise ValueError('Unexpected license: '+name)
        raw=get(BASE+'assets/'+name)
        digest=hashlib.sha256(raw).hexdigest()
        if raw[:4]!=b'glTF' or digest!=expected:
            raise ValueError('GLB integrity check failed: '+name)
        (assets/name).write_bytes(raw)
        mobile=assets/(Path(name).stem+'-mobile.glb')
        if mobile.exists():
            mobile.unlink()
        records.append(dict(record,mirrorCommit=COMMIT,download=BASE+'assets/'+name,sha256=digest))
    (assets/'model-review.json').write_text(json.dumps(records,indent=2,ensure_ascii=False),encoding='utf-8')
    print('Downloaded three distinct attributed models; original hashes verified.')
if __name__=='__main__':
    main()
