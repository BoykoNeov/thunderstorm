import json, base64, sys

src, dst = sys.argv[1], sys.argv[2]
d = json.load(open(src))
rv = d.get('returnValue', d)
img = rv['image'] if 'image' in rv else rv
open(dst, 'wb').write(base64.b64decode(img['data']))
labels = rv.get('labeledActors', [])
print('saved', dst, 'cam', rv.get('cameraLocation'), rv.get('cameraRotation'), 'labels:', len(labels))
for l in labels[:20]:
    print(' ', l['name'], l.get('label'))
