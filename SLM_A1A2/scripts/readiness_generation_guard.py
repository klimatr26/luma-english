"""Fail-closed budget for synthetic readiness; never reads benchmark cases."""
import hashlib
import json
import os

REPEAT_IDS = frozenset(('qwen35_2b_f16', 'qwen35_2b_q8_0',
                        'qwen35_2b_q4_k_m', 'minicpm5_2b_f16'))
# Pins the exact record created from the human instruction on 2026-10-11,
# including the approved manifest and each historical request path/hash.
APPROVED_RECORD_SHA256 = '871f04d5d6fb8e4888001a18776431685d8f93eadec8cb8b3f28087dd871f66b'


def sha256(path):
    with open(path, 'rb') as stream:
        return hashlib.sha256(stream.read()).hexdigest()


def request_paths(lab, cid):
    return sorted(os.path.join(directory, cid + '.request.json')
                  for directory, _, files in os.walk(os.path.join(lab, 'logs'))
                  if cid + '.request.json' in files)


def load_authorization(path, manifest_sha, configs):
    if path is None:
        return None
    with open(path, 'rb') as stream:
        raw = stream.read()
    if hashlib.sha256(raw).hexdigest() != APPROVED_RECORD_SHA256:
        raise ValueError('repeat authorization differs from the exact approved record')
    record = json.loads(raw)
    if (record.get('scope') != 'four_nonthinking_readiness_repetitions'
            or record.get('manifest_sha256') != manifest_sha
            or record.get('human_authorized') is not True
            or not record.get('user_instruction')
            or record.get('main_benchmark_authorized') is not False):
        raise ValueError('repeat authorization scope, human evidence or manifest mismatch')
    entries = record.get('configurations', [])
    if len(entries) != 4 or {e['id'] for e in entries} != REPEAT_IDS:
        raise ValueError('repeat authorization must contain exactly the four approved configs')
    by_id = {c['id']: c for c in configs}
    for entry in entries:
        if (entry.get('model_sha256') != by_id[entry['id']]['model_sha256']
                or type(entry.get('additional_requests')) is not int
                or entry['additional_requests'] != 1
                or type(entry.get('prior_request_count')) is not int
                or entry['prior_request_count'] != 1):
            raise ValueError('repeat authorization must permit one addition to one historical request')
    return {'record': record, 'sha256': hashlib.sha256(raw).hexdigest(),
            'path': os.path.abspath(path), 'by_id': {e['id']: e for e in entries}}


def check_budget(lab, cid, authorization):
    claim_path = os.path.join(lab, 'logs', 'readiness_generation_claims', cid + '.claim.json')
    if os.path.exists(claim_path):
        raise ValueError(f'{cid}: generation budget already claimed; no retry')
    paths = request_paths(lab, cid)
    entry = authorization['by_id'].get(cid) if authorization else None
    if entry is None:
        if paths:
            raise ValueError(f'{cid}: synthetic request already recorded; repetition unauthorized')
    else:
        # The complete global history must be exactly the one pinned prior request.
        prior = os.path.normcase(os.path.abspath(os.path.join(lab, entry['prior_request_path'])))
        logs_root = os.path.normcase(os.path.abspath(os.path.join(lab, 'logs')))
        if os.path.commonpath([logs_root, prior]) != logs_root:
            raise ValueError(f'{cid}: prior request must remain under logs')
        if (len(paths) != 1 or os.path.normcase(os.path.abspath(paths[0])) != prior
                or sha256(paths[0]) != entry['prior_request_sha256']):
            raise ValueError(f'{cid}: historical request count, path or hash differs')
    return claim_path


def claim_generation(lab, cid, authorization, manifest_sha, out_dir):
    if authorization and manifest_sha != authorization['record']['manifest_sha256']:
        raise ValueError('generation manifest differs from approved manifest')
    path = check_budget(lab, cid, authorization)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    evidence = {'id': cid, 'manifest_sha256': manifest_sha,
                'authorization_sha256': authorization['sha256'] if authorization else None,
                'authorization_path': authorization['path'] if authorization else None,
                'request_path': os.path.join(out_dir, cid + '.request.json'),
                'purpose': 'one synthetic technical generation; no automatic retry',
                'repeat': bool(authorization and cid in authorization['by_id'])}
    # Exclusive creation serializes competing processes. Never remove a claim:
    # a crash after reservation means the request outcome may be unknown.
    with open(path, 'x', encoding='utf-8') as stream:
        json.dump(evidence, stream, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    return evidence
