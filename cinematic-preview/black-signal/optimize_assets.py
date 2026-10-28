"""Repack embedded GLB textures as WebP, preserving meshopt buffer references.
Only touches the isolated preview's three attributed vehicle models.
"""
from __future__ import annotations
import hashlib, io, json, struct
from pathlib import Path
from PIL import Image
ROOT = Path(__file__).resolve().parent

def optimize(path: Path, max_size: int = 1024) -> dict:
    raw = path.read_bytes()
    if raw[:4] != b'glTF':
        raise ValueError(f'Not GLB: {path}')
    json_len = struct.unpack_from('<I', raw, 12)[0]
    doc = json.loads(raw[20:20+json_len])
    bin_header = 20 + json_len
    bin_len, bin_type = struct.unpack_from('<II', raw, bin_header)
    if bin_type != 0x004E4942:
        raise ValueError('Expected embedded GLB binary chunk')
    source = raw[bin_header+8:bin_header+8+bin_len]
    image_views = {im['bufferView']: i for i, im in enumerate(doc.get('images', [])) if 'bufferView' in im}
    chunks = bytearray()
    converted = set()
    def append(data: bytes) -> int:
        while len(chunks) % 4:
            chunks.append(0)
        offset = len(chunks)
        chunks.extend(data)
        return offset
    for vi, view in enumerate(doc.get('bufferViews', [])):
        if view.get('buffer', 0) == 0:
            offset = view.get('byteOffset', 0)
            data = source[offset:offset+view['byteLength']]
            if vi in image_views:
                im_index = image_views[vi]
                image = Image.open(io.BytesIO(data))
                image = image.convert('RGBA' if ('A' in image.getbands() or 'transparency' in image.info) else 'RGB')
                image.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
                out = io.BytesIO()
                image.save(out, 'WEBP', quality=92, method=6)
                data = out.getvalue()
                doc['images'][im_index]['mimeType'] = 'image/webp'
                converted.add(im_index)
            view['byteOffset'] = append(data)
            view['byteLength'] = len(data)
        ext = view.get('extensions', {}).get('EXT_meshopt_compression')
        if ext and ext.get('buffer', 0) == 0:
            offset = ext.get('byteOffset', 0)
            ext['byteOffset'] = append(source[offset:offset+ext['byteLength']])
    for tex in doc.get('textures', []):
        if tex.get('source') in converted:
            tex.setdefault('extensions', {})['EXT_texture_webp'] = {'source': tex.pop('source')}
    if converted:
        for key in ('extensionsUsed', 'extensionsRequired'):
            if 'EXT_texture_webp' not in doc.setdefault(key, []):
                doc[key].append('EXT_texture_webp')
    while len(chunks) % 4:
        chunks.append(0)
    doc['buffers'][0]['byteLength'] = len(chunks)
    doc.setdefault('asset', {}).setdefault('extras', {})['check92Changes'] = f'Embedded textures converted to WebP quality 92, max {max_size}px. Geometry and author attribution retained.'
    text = json.dumps(doc, ensure_ascii=False, separators=(',', ':')).encode()
    text += b' ' * ((-len(text)) % 4)
    result = struct.pack('<III', 0x46546C67, 2, 28+len(text)+len(chunks)) + struct.pack('<II', len(text), 0x4E4F534A) + text + struct.pack('<II', len(chunks), 0x004E4942) + chunks
    path.write_bytes(result)
    return {'file':path.name,'before':len(raw),'after':len(result),'sha256':hashlib.sha256(result).hexdigest()}

if __name__ == '__main__':
    records=[]
    for name in ('porsche-911-930.glb','audi-r8.glb','bmw-m3-e30.glb'):
        path=ROOT/'assets'/name
        if not path.exists():
            raise FileNotFoundError(path)
        mobile = path.with_name(path.stem+'-mobile.glb')
        if not mobile.exists():
            mobile.write_bytes(path.read_bytes())
            records.append(optimize(mobile, 512))
        raw = path.read_bytes()
        jl = struct.unpack_from('<I', raw, 12)[0]
        already = json.loads(raw[20:20+jl]).get('asset',{}).get('extras',{}).get('check92Changes')
        if not already:
            records.append(optimize(path))
    (ROOT/'assets/optimization.json').write_text(json.dumps(records,indent=2))
    print(json.dumps(records,indent=2))
