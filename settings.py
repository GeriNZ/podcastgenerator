import os

def settings(overrides=None):
    return {**os.environ, **(overrides or {})}

def modal_client(values):
    import modal
    token_id = values.get('MODAL_TOKEN_ID') or values.get('token_id')
    secret = values.get('MODAL_TOKEN_SECRET') or values.get('token_secret')
    if not token_id or not secret:
        raise ValueError('Modal credentials are missing from the server configuration.')
    return modal.Client.from_credentials(token_id, secret)

def check_connection(values):
    # Control-plane handshake only: no deployed function, image build or GPU.
    modal_client(values).hello()
    return {'connected': True, 'gpu_started': False, 'generation_performed': False}
