import zipfile, pathlib

root = pathlib.Path('citation-truth-auditor')
out = pathlib.Path('Meteorain_C4_citation-truth-auditor.skill')
files = sorted(p for p in root.rglob('*')
               if p.is_file() and '__pycache__' not in p.parts)
with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z:
    for p in files:
        z.write(p, p.as_posix())
print('packed', len(files), 'files ->', out, out.stat().st_size, 'bytes')
for p in files:
    print('  ', p.as_posix(), p.stat().st_size)