"""Shared-password frontend. Generation remains disabled during budget testing."""
import hashlib
import hmac
import time
import uuid
import json

import streamlit as st

from settings import settings, check_connection, modal_client
from script_parser import parse_script
from usage import estimate, configured, UsageSheet, utc_now

st.set_page_config(page_title='Caribbean Podcast Studio', page_icon='🎙️', layout='centered')
try:
    secrets = dict(st.secrets)
except FileNotFoundError:
    secrets = {}
config = settings(secrets)
st.title('Caribbean Podcast Studio')
st.caption('Two voices. Your script. A short podcast preview.')

password = config.get('APP_PASSWORD', '')
if not password:
    st.error('The organiser needs to configure the shared access password.')
    st.stop()
# Rotation invalidates existing authenticated sessions on their next interaction.
fingerprint = hashlib.sha256(password.encode()).hexdigest()
if st.session_state.get('auth') != fingerprint:
    with st.form('login'):
        entered = st.text_input('Access password', type='password')
        submitted = st.form_submit_button('Enter studio')
    if submitted:
        if time.time() < st.session_state.get('retry_after', 0):
            st.error('Please wait a few seconds before trying again.')
        elif hmac.compare_digest(entered.encode(), password.encode()):
            st.session_state.auth = fingerprint
            st.rerun()
        else:
            st.session_state.retry_after = time.time() + 3
            st.error('That password was not recognised.')
    st.stop()

if st.button('Sign out'):
    st.session_state.clear()
    st.rerun()

enabled = str(config.get('ENABLE_GENERATION', 'false')).lower() == 'true'
if not enabled:
    st.info('Setup mode · Audio generation is paused to preserve the available credit. You can prepare a script and check the connection.')

with st.expander('Connection'):
    if configured(config) and st.button('Check usage tracker'):
        try:
            UsageSheet(config).check()
            st.success('Connected to the usage sheet. No audio generated and no usage row added.')
        except Exception:
            st.error('Could not reach the tracker. Check its web app URL, shared secret, and deployment access.')
    st.write('This check contacts Modal without starting a GPU or sending your script.')
    if st.button('Check Modal connection'):
        try:
            check_connection(config)
            st.success('Connected to Modal. No GPU started and no audio generated.')
        except Exception:
            st.error('Could not connect. Ask the organiser to check the server credentials.')

names = {'Shontelle · preview': 'shontelle-preview', 'Kiomi · preview': 'kiomi-preview'}
left, right = st.columns(2)
a = left.selectbox('Speaker A', list(names), index=0)
b = right.selectbox('Speaker B', list(names), index=1)
title = st.text_input('Podcast title', max_chars=160, placeholder='Give this preview a title')
uploaded = st.file_uploader('Upload a script', type=['txt'])
if uploaded is not None:
    raw = uploaded.getvalue()
    if len(raw) > 1_000_000:
        st.error('Please use a text file smaller than 1 MB.')
        st.stop()
    digest = hashlib.sha256(raw).hexdigest()
    if st.session_state.get('upload_digest') != digest:
        try:
            st.session_state.script = raw.decode('utf-8-sig')
            st.session_state.upload_digest = digest
        except UnicodeDecodeError:
            st.error('Please save the script as UTF-8 text.')
            st.stop()
if 'script' not in st.session_state:
    st.session_state.script = 'A: Welcome to our podcast. Today we are exploring Caribbean voices.\nB: Let us start with a short preview and hear how it sounds.'
script = st.text_area('Podcast script', key='script', height=250, help='Start each speaker turn with A: or B:.')
valid = False
try:
    if len(script.split()) > 60:
        raise ValueError('Short tests allow up to 60 words, including speaker labels. Please shorten the script.')
    chunks, limited = parse_script(script)
    words = sum(len(c['text'].split()) for c in chunks)
    st.caption(f'{words} words prepared · maximum 30 seconds per preview')
    prediction = estimate(config, words=words)
    st.info(f"Estimated cost: US${prediction['cost']:.4f} · about {prediction['audio_seconds']:.0f} seconds of audio")
    with st.expander('How the estimate works'):
        st.write(f"L4: US${prediction['gpu_rate']:.2f}/hour. Assumes {prediction['cores']:g} CPU core(s) and {prediction['gib']:g} GiB RAM, plus startup time. Calibrated from one short test; actual usage may differ.")
        st.caption('Gross compute estimate before credits. Includes assumed CPU/RAM; excludes storage, deployment builds and regeneration. This is not a spending cap or a bill.')
    valid = True
except ValueError as exc:
    st.warning(str(exc))

tracking_ready = configured(config)
if not tracking_ready:
    st.warning('Usage tracking needs the organiser’s Google Sheets settings before generation can start.')

# Logging retries never invoke the GPU again.
if st.session_state.get('pending_usage'):
    st.warning('A usage record has not yet been saved. Retry saving before another generation. Any audio already returned remains available below.')
    if st.button('Retry saving usage record'):
        try:
            UsageSheet(config).upsert(st.session_state.pending_usage)
            st.session_state.pop('pending_usage')
            st.rerun()
        except Exception:
            st.error('Could not save the usage record. Check the sheet settings and access.')
    st.download_button('Download unsaved usage record', json.dumps(st.session_state.pending_usage, indent=2), 'usage-record.json', mime='application/json')

if st.button('Generate preview', disabled=not enabled or not valid or not title.strip() or not tracking_ready or bool(st.session_state.get('pending_usage')), type='primary'):
    st.session_state.pop('result', None)
    record = dict(request_id=str(uuid.uuid4()), started_utc=utc_now(), title=title.strip(),
                  status='started', voice_a=names[a], voice_b=names[b], words=words,
                  predicted_audio_seconds=round(prediction['audio_seconds'], 2),
                  predicted_cost_usd=round(prediction['cost'], 6), gpu='L4',
                  gpu_usd_hour=prediction['gpu_rate'], cpu_usd_core_hour=prediction['cpu_rate'],
                  memory_usd_gib_hour=prediction['memory_rate'], assumed_cpu_cores=prediction['cores'],
                  assumed_memory_gib=prediction['gib'], cost_basis=prediction['basis'])
    try:
        ledger = UsageSheet(config)
        ledger.upsert(record)
    except Exception:
        record['status'] = 'not_submitted_logging_error'
        st.session_state.pending_usage = record
        st.error('Could not start the usage log. No generation request was sent.')
        st.stop()
    started = time.monotonic()
    with st.spinner('Creating your preview… This may take several minutes.'):
        try:
            import modal
            client = modal_client(config)
            function = modal.Function.from_name('caribbean-podcast-studio', 'generate_preview', client=client)
            st.session_state.result = function.remote(script, {'A': names[a], 'B': names[b]})
            report = st.session_state.result['report']
            actual_estimate = estimate(config, report=report)
            record.update(status='completed', audio_seconds=report['audio_seconds'],
                          worker_seconds=round(report['total_seconds'], 3),
                          estimated_compute_seconds=round(actual_estimate['seconds'], 3),
                          estimated_cost_usd=round(actual_estimate['cost'], 6), cost_basis=actual_estimate['basis'])
            st.session_state.result['estimated_cost_usd'] = actual_estimate['cost']
        except Exception:
            record['status'] = 'failed_or_unknown'
            record['cost_basis'] = 'Cost unknown: a failed/disconnected request may still incur compute charges'
            st.error('Generation did not complete. Ask the organiser to check the service before retrying.')
    record.update(finished_utc=utc_now(), client_seconds=round(time.monotonic() - started, 3))
    try:
        ledger.upsert(record)
    except Exception:
        st.session_state.pending_usage = record
        st.warning('Audio processing finished, but the usage log could not be updated. Use Retry saving usage record on the next interaction.')
if 'result' in st.session_state:
    result = st.session_state.result
    st.audio(result['audio'], format='audio/wav')
    st.download_button('Download synthetic preview', result['audio'], 'synthetic-preview.wav', mime='audio/wav')
    st.caption(f"Audio: {result['report']['audio_seconds']:.1f} seconds")
    if 'estimated_cost_usd' in result:
        st.caption(f"Estimated compute cost: US${result['estimated_cost_usd']:.4f} before credits")
    if st.button('Clear recording'):
        st.session_state.pop('result', None)
        st.rerun()
st.caption('Scripts and audio are held for this session. Generation sends your script to Modal. The organiser’s Google Sheet stores the title, timestamps, voices, duration, status and cost estimates, but no script or recording. Preview voices are provisional.')
