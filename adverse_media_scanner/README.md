# Adverse Media Scanner

A Python adverse-media screening application with a FastAPI API, a command-line scanner, SQLite persistence, local BERT/BART analysis, and Phoenix tracing. There is no Streamlit/web frontend, Docker setup, or Prometheus metrics endpoint.

## Requirements

- Python 3.11 or newer. Python 3.12 is a good default.
- Internet access for Google News/article retrieval and initial model downloads.
- Several gigabytes of free disk space for Torch, Phoenix, and the Hugging Face models. The first API start downloads the models if they are not cached.

Use a regular Python distribution (python.org, Homebrew, or pyenv), not the macOS Command Line Tools Python. That avoids its older LibreSSL build and the urllib3 compatibility warning.

## Install

Run these commands from this directory.

### Windows PowerShell

```powershell
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

If PowerShell blocks activation, use `.venv\Scripts\python.exe` directly instead of activating the environment.

### macOS

```sh
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### Linux

```sh
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

If Python 3.12 is not installed, use another supported Python 3.11+ executable. Always install and run through the same virtual environment; for example, use `.venv/bin/python` on macOS/Linux or `.venv\Scripts\python.exe` on Windows.

## Run With Phoenix

Use two terminals, both opened in this directory and using the `.venv` created above.

1. Start Phoenix in the first terminal. Binding it to loopback keeps trace data local.

Windows PowerShell:

```powershell
$env:PHOENIX_HOST = "127.0.0.1"
phoenix serve
```

macOS/Linux:

```sh
PHOENIX_HOST=127.0.0.1 phoenix serve
```

Leave this terminal running. Open [http://localhost:6006](http://localhost:6006) to view Phoenix.

2. Start the API in the second terminal:

```sh
python api.py
```

On Windows, run the same command after environment activation. Without activation, use `.venv\Scripts\python.exe api.py`.

3. Open [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs), expand `POST /v1/screen`, choose **Try it out**, and execute a scan. The response includes `scan_id` and `trace_id`.

4. In Phoenix, open the `adverse-media-scanner` project. Select **All** spans to see the nested run stages. Search for the returned trace ID if you need to locate that specific run.

Check the API and tracing connection at:

- `http://127.0.0.1:8000/health`
- `http://127.0.0.1:8000/v1/observability`

Phoenix stores traces in `~/.phoenix/phoenix.db` by default. Traces include subject/KYC values, search queries, URLs, fetched HTML/article text, model decisions, and persisted results. Keep Phoenix local and protect its data directory.

## Run From The Command Line

With the virtual environment active, run:

```sh
python main.py
```

The CLI currently screens the target configured in `main.py` and prompts for the article limit. Phoenix must be running first if you want the CLI graph stages traced.

## API Routes

- `POST /v1/screen`: wait for a complete JSON screening result.
- `POST /v1/screen/stream`: receive live Server-Sent Events and the final result.
- `POST /v1/preview-search`: preview news search results without running the full analysis.
- `GET /v1/screenings/{target_id}`: retrieve saved screening history.
- `GET /v1/configs` and `PUT /v1/configs`: view and update screening settings.

Prometheus was removed; `GET /metrics` returning 404 is expected. Do not run an old Prometheus scraper against this API.

## Troubleshooting

- **`ModuleNotFoundError` for FastAPI or another requirement:** the app is running under a different Python than the one where dependencies were installed. Check `python -c "import sys; print(sys.executable)"` and install/run using the `.venv` interpreter.
- **`phoenix: command not found`:** activate `.venv`, install the requirements there, and run `phoenix serve` from that environment.
- **urllib3 `NotOpenSSLWarning` on macOS:** this usually means Command Line Tools Python is being used. Recreate the environment from a Python 3.11+ distribution linked against OpenSSL.
- **Slow first startup:** the analyzer loads local models when the API starts; first-time downloads and model initialization can take several minutes.
- **No Phoenix trace:** confirm `/v1/observability` reports `instrumentation_enabled: true` and `server_reachable: true`. Restart `api.py` after installing dependencies or changing trace configuration.
