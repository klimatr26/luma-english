"""Acquire only the pinned official LFM2.5-2.6B Q8_0/Q4_K_M assets; no inference."""
import hashlib
import json
import shutil
from pathlib import Path

from huggingface_hub import hf_hub_download


def main():
    lab = Path(__file__).resolve().parents[1]
    snapshot = json.loads((lab / 'manifests/lfm26_upstream_snapshot_120.json').read_text(encoding='utf-8'))
    target = lab / 'models/lfm25_26b'
    target.mkdir(parents=True, exist_ok=True)
    needed = sum(f['size'] for f in snapshot['files'].values())
    if shutil.disk_usage(target).free < needed * 2 + 5 * 1024**3:
        raise RuntimeError('Insufficient free space for pinned downloads and safety margin')
    tree = {'repo': snapshot['repo'], 'revision': snapshot['revision'], 'files': {
        name: {'size': meta['size'], 'lfs_size': meta['size'], 'lfs_sha256': meta['lfs']['sha256']}
        for name, meta in snapshot['files'].items()}}
    cache = target / '.cache/huggingface/trees'
    cache.mkdir(parents=True, exist_ok=True)
    (cache / (snapshot['revision'] + '.json')).write_text(json.dumps(tree, indent=2) + '\n', encoding='utf-8')
    records = []
    for name, meta in snapshot['files'].items():
        print('Acquiring pinned asset: ' + name, flush=True)
        path = Path(hf_hub_download(snapshot['repo'], name, revision=snapshot['revision'], local_dir=target))
        digest = hashlib.sha256()
        before = path.stat()
        with path.open('rb') as stream:
            for block in iter(lambda: stream.read(8 * 1024**2), b''):
                digest.update(block)
        after = path.stat()
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise RuntimeError('Asset changed while hashing: ' + name)
        if after.st_size != meta['size'] or digest.hexdigest() != meta['lfs']['sha256']:
            raise RuntimeError('Upstream hash or size mismatch: ' + name)
        records.append({'file': name, 'bytes': after.st_size, 'sha256': digest.hexdigest()})
        print('Verified: ' + name, flush=True)
    record = {'repo': snapshot['repo'], 'revision': snapshot['revision'], 'license': 'lfm1.0',
              'license_source': 'pinned model card license_name', 'outputs': records,
              'execution_approved': False}
    (lab / 'manifests/lfm26_acquisition_record_120.json').write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
