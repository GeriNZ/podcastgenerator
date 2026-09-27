"""Shared-password frontend. Generation remains disabled during budget testing."""
import hashlib
import hmac
import time

import streamlit as st

from settings import settings, check_connection, modal_client
from script_parser import parse_script

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
    st.write('This check contacts Modal without starting a GPU or sending your script.')
    if st.button('Check Modal connection'):
        try:
            check_connection(config)
            st.success('Connected to Modal. No GPU started and no audio generated.')
        except Exception:
            st.error('Could not connect. Ask the organiser to check the server credentials.')

names = {'Shontelle · preview': 'shontelle-preview', 'Trinidadian weather voice · preview': 'weather-preview'}
left, right = st.columns(2)
a = left.selectbox('Speaker A', list(names), index=0)
b = right.selectbox('Speaker B', list(names), index=1)
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
    valid = True
except ValueError as exc:
    st.warning(str(exc))

if st.button('Generate preview', disabled=not enabled or not valid, type='primary'):
    st.session_state.pop('result', None)
    with st.spinner('Creating your preview… This may take several minutes.'):
        try:
            import modal
            client = modal_client(config)
            function = modal.Function.from_name('caribbean-podcast-studio', 'generate_preview', client=client)
            st.session_state.result = function.remote(script, {'A': names[a], 'B': names[b]})
        except Exception:
            st.error('Generation did not complete. Ask the organiser to check the service before retrying.')
if 'result' in st.session_state:
    result = st.session_state.result
    st.audio(result['audio'], format='audio/wav')
    st.download_button('Download synthetic preview', result['audio'], 'synthetic-preview.wav', mime='audio/wav')
    st.caption(f"Audio: {result['report']['audio_seconds']:.1f} seconds")
    if st.button('Clear recording'):
        st.session_state.pop('result', None)
        st.rerun()
st.caption('Scripts and generated audio are held for this session, not saved to an app library. When enabled, generation sends your script to Modal. Preview voices are provisional.')
