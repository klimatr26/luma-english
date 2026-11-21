"""Export committed sources to a NEW directory, without copying private Git history."""
import argparse
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import tarfile

ROOT = Path(__file__).resolve().parents[2]
EXCLUDED = {
    'PROJECT_CONTEXT_TITULACION_SLM_A1A2.md', 'opencode.jsonc',
    'PlanTrabajoTitulación_KevinLima-rev1.docx', 'PlanTrabajoTitulación_KevinLima-rev1.pdf',
    'respaldo_revision_2026-11-09T01-08-40-788Z.json',
    'SLM_A1A2/analysis_v2/human_review_20261109/clarified_v1/clarified_backup.json',
}
SECRETS = re.compile(rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|\bgh[pousr]_[A-Za-z0-9]{30,}|\bgithub_pat_[A-Za-z0-9_]{40,}|\bhf_[A-Za-z0-9]{25,}|\bsk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{32,}|\bAKIA[A-Z0-9]{16}')
FORBIDDEN = {'.gguf', '.safetensors', '.bin', '.pt', '.pth', '.exe', '.dll', '.so', '.apk', '.keystore', '.jks', '.db', '.pfx', '.pem', '.key'}

def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT)

def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    out = args.output.resolve()
    if out.exists():
        parser.error('Use a new output directory; existing exports are never overwritten.')
    if git('status', '--porcelain').strip():
        parser.error('Commit or otherwise preserve pending work before exporting.')
    source = git('rev-parse', 'HEAD').decode().strip()
    entries, skipped = [], []
    with tarfile.open(fileobj=io.BytesIO(git('archive', '--format=tar', 'HEAD'))) as archive:
        for member in archive:
            if member.isdir(): continue
            name = member.name; path = PurePosixPath(name)
            if not member.isfile() or path.is_absolute() or '..' in path.parts:
                raise ValueError('Unsupported archive entry: ' + name)
            if name in EXCLUDED or path.name == 'runner.lock':
                skipped.append(name); continue
            data = archive.extractfile(member).read()
            if len(data) > 10 * 1024**2 or path.suffix.lower() in FORBIDDEN:
                raise ValueError('Forbidden or oversized asset: ' + name)
            if path.suffix.lower() not in {'.png', '.jpg', '.jpeg', '.pdf', '.docx'} and SECRETS.search(data):
                raise ValueError('Possible secret; review locally: ' + name)
            entries.append((name, data))
    out.mkdir(parents=True)
    records = []
    for name, data in entries:
        p = out / name; p.parent.mkdir(parents=True, exist_ok=True); p.write_bytes(data)
        records.append({'path': name, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()})
    manifest = {'purpose': 'PRIVATE_THESIS_REPOSITORY_SOURCE_EXPORT', 'source_commit': source,
                'history': 'Independent publication history; original local Git history was not exported.',
                'excluded': sorted(skipped), 'files': records}
    (out / 'PUBLICATION_MANIFEST.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'output': str(out), 'source_commit': source, 'files': len(records), 'excluded': len(skipped)}))

if __name__ == '__main__': main()
