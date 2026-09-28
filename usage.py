"""Explicit estimates and a metadata-only Sheets ledger. No inference calls."""
import math
import re
from datetime import datetime, timezone
from urllib.parse import quote

HEADERS = ['request_id', 'started_utc', 'finished_utc', 'title', 'status',
           'voice_a', 'voice_b', 'words', 'predicted_audio_seconds',
           'audio_seconds', 'worker_seconds', 'client_seconds',
           'estimated_compute_seconds', 'predicted_cost_usd', 'estimated_cost_usd',
           'gpu', 'gpu_usd_hour', 'cpu_usd_core_hour', 'memory_usd_gib_hour',
           'assumed_cpu_cores', 'assumed_memory_gib', 'cost_basis']

def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')

def number(config, key, default):
    value = float(config.get(key, default))
    if not math.isfinite(value) or value < 0:
        raise ValueError('Invalid cost setting: ' + key)
    return value

def estimate(config, words=0, report=None):
    gpu = number(config, 'GPU_USD_HOUR', .80)
    cpu = number(config, 'CPU_USD_CORE_HOUR', .0473)
    memory = number(config, 'MEMORY_USD_GIB_HOUR', .008)
    cores = number(config, 'ASSUMED_CPU_CORES', 1)
    gib = number(config, 'ASSUMED_MEMORY_GIB', 4)
    audio = min(30., words / 150 * 60)
    if report is None:
        seconds = 30 + audio * 2.13
        basis = 'Prediction: 150 words/min, 2.13 compute seconds/audio second, 30s overhead'
    else:
        audio = float(report['audio_seconds'])
        seconds = float(report['total_seconds']) + 8
        basis = 'Estimate: measured worker time + 8s startup; CPU/RAM assumed; excludes credits/storage/builds'
    return dict(audio_seconds=audio, seconds=seconds,
                cost=seconds / 3600 * (gpu + cpu * cores + memory * gib),
                gpu_rate=gpu, cpu_rate=cpu, memory_rate=memory,
                cores=cores, gib=gib, basis=basis)

def configured(config):
    return bool(config.get('USAGE_SCRIPT_URL') and config.get('USAGE_SCRIPT_SECRET'))

class UsageSheet:
    def __init__(self, config):
        self.url = str(config['USAGE_SCRIPT_URL']).strip()
        if not re.fullmatch(r'https://script\.google\.com/macros/s/[A-Za-z0-9_-]+/exec', self.url):
            raise ValueError('Use the Apps Script web app URL ending in /exec.')
        self.secret = str(config['USAGE_SCRIPT_SECRET'])

    def send(self, action, record=None):
        import requests
        # Secret is in the POST body, never the URL. Google redirects the response.
        response = requests.post(self.url, json={'secret': self.secret, 'action': action,
                                  'record': record}, timeout=(10, 30), allow_redirects=False)
        if response.status_code in (302, 303):
            from urllib.parse import urlparse
            destination = response.headers.get('Location', '')
            parsed = urlparse(destination)
            if parsed.scheme != 'https' or parsed.hostname != 'script.googleusercontent.com':
                raise RuntimeError('Apps Script deployment is not publicly callable. Check access settings.')
            # Retrieve response only; do not forward the secret to the redirected URL.
            response = requests.get(destination, timeout=(10, 30), allow_redirects=False)
        response.raise_for_status()
        result = response.json()
        if not isinstance(result, dict) or result.get('ok') is not True:
            raise RuntimeError('Apps Script rejected the tracking request. Check its setup and shared secret.')
        if action == 'upsert' and result.get('request_id') != record['request_id']:
            raise RuntimeError('Tracking acknowledgement did not match the request.')
        return result

    def check(self):
        return self.send('check')

    def upsert(self, record):
        return self.send('upsert', {key: record[key] for key in HEADERS if key in record})
