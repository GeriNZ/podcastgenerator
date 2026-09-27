# Caribbean Podcast Studio

A shared-password Streamlit frontend for the existing Modal voice service.
Students need only a browser. This repository contains no voice recordings,
models, API credentials or GPU deployment code.

## Deploy to Streamlit Community Cloud

1. Upload this folder's contents to a GitHub repository, including the hidden
   `.streamlit` folder. Keep `app.py` and `requirements.txt` at repository root.
2. In Streamlit Community Cloud, create an app from that repository and select
   `app.py` as the entrypoint. Select Python **3.12** in advanced settings.
3. Copy the contents of `.streamlit/secrets.toml.example` into the app's private
   **Secrets** settings. Replace the placeholders with your shared password and
   Modal token values. The original project's `token_id` becomes `MODAL_TOKEN_ID`,
   and `token_secret` becomes `MODAL_TOKEN_SECRET`.
4. Leave `ENABLE_GENERATION = "false"` for initial deployment. Open the site,
   sign in, and use **Check Modal connection**. This does not start a GPU.
5. To allow paid short tests, change that private setting to
   `ENABLE_GENERATION = "true"`. Share the website address and access password.

Never upload your real `.env` or `secrets.toml` to GitHub. The example contains
placeholders only. Use a strong shared password and keep the Modal credentials
private; those credentials carry account permissions beyond this website.

## Existing backend

This frontend calls the authenticated Modal function `generate_preview` in
`caribbean-podcast-studio`, in the Modal environment selected by the SDK (normally
`main`). It does not deploy a backend or start a GPU when the page loads.
The backend must already exist in the workspace associated with the credentials.
It currently offers Shontelle and Trinidadian weather preview references.

Both frontend and backend are in short-test mode: **60 words including labels**
and **30 seconds maximum**. Use dialogue like:

```text
A: We can walk down to the market together this afternoon.
B: Bring some water, because it is going to be warm.
```

Generation spends Modal credit. The password is shared, and there is no per-user
quota or total spending cap in this app. Keep generation disabled when not testing.
The backend handles one container at a time and has no automatic generation retry.
The frontend never automatically retries failed generation either.

## Data handling

The app holds scripts and generated recordings in session memory, with no
permanent recording library. The script is sent to Modal on Generate; the audio
returns for playback and download. Voice references and model files live on the
existing Modal deployment, not in this repository. Hosting providers' operational
retention policies still apply. Shared-password login includes a brief per-session
retry delay; it is not an account system or a distributed rate limiter.

## Run locally

Install `requirements.txt` in a Python 3.12 virtual environment. Copy
`.streamlit/secrets.toml.example` to `.streamlit/secrets.toml` and fill in the values.
Run `streamlit run app.py` from this folder. Environment variables are also supported.
No reference to the original voiceclone folder is needed.

Run `python -m unittest test_app` to check the login gate and disabled-generation
behaviour. These tests use a dummy password and never call the GPU service.
