# **Getting Started**

Starting: *Verify prerequisites (Docker Desktop + LLM key)* (1/6)

Read [](file:///Users/maruti/Documents/TSGit/strix/pyproject.toml#1-1), lines 1 to 220

Good — you hit the Python import error because the repo needs its Python dependencies (the `docker` SDK, etc.). I'll give very simple, step-by-step instructions (easy-to-follow like for a school kid) to get a local environment working on macOS with Docker Desktop and then run the viewer UI.

Summary of what we'll do
- Check Docker is running.
- Make a Python virtual environment for the project.
- Install the project dependencies (this installs the `docker` Python package).
- (Option A) Run the viewer from the repo (no global install).
- (Option B) Install the strix CLI into the venv and use `strix view`.
- Notes about ports and how to open the UI.

1) Check Docker Desktop is running
- Open Docker Desktop app and wait until it reports “Docker is running”.
- Verify in a terminal:
```bash
docker info
```
If that prints info, Docker is running. If it errors, start Docker Desktop and retry.

2) Check Python version (Strix requires Python 3.12+)
- Run:
```bash
python3 --version
```
If the version is lower than 3.12, install Python 3.12 (homebrew example):
```bash
brew install python@3.12
# then optionally:
brew link --force --overwrite python@3.12
```

3) Create and activate a virtual environment inside the repo
- From the repository root:
```bash
cd /Users/maruti/Documents/TSGit/strix
python3 -m venv .venv
# activate it:
source .venv/bin/activate
# upgrade pip
python -m pip install --upgrade pip
```
You should now see `(.venv)` in your shell prompt.

4) Install the project dependencies (this provides the missing `docker` module)
- While the venv is active:
```bash
# install the package in editable mode (will install 'docker' and other deps)
pip install -e .

# optionally also install dev extras (tests, build tools)
pip install -e '.[dev]'
```
Notes:
- This will install many packages (OpenAI, litellm, cryptography, etc.). It may take a few minutes and show many lines.
- If any package fails to build on macOS, read the error; often installing a prebuilt wheel or developer tools (Xcode command line tools: `xcode-select --install`) fixes it.

5A) Quick: run the viewer from the repo (no global strix needed)
- If you already have a run under `./strix_runs` (a past scan), run:
```bash
# from repo root and with the venv still active
PYTHONPATH=$PWD python -c "from strix.interface.viewer.cli import run_view; run_view([])"
```
- To pick a fixed port (e.g., 8080):
```bash
PYTHONPATH=$PWD python -c "from strix.interface.viewer.cli import run_view; run_view(['--port','8080'])"
```
What this does:
- It starts the local Python server that serves the built SPA and run data, and it will auto-open your browser (unless you pass `--no-open`).
- If there are no runs under `./strix_runs`, it will tell you so. You need at least one run directory (created by running a scan) for the viewer to show run data.

5B) Recommended: install the CLI inside the venv and use `strix view`
- With venv active, installing editable package (step 4) registers the strix script in `.venv/bin`. Ensure your shell is using the venv (`source .venv/bin/activate`), then:
```bash
# confirm strix command is available
which strix
# run the viewer
strix view
# or fixed port:
strix view --port 8080
```
Why this is nicer: strix is the normal entrypoint, handles environment validation, pulls the sandbox image if needed, and prints a tokened URL.

6) If you don't have a run yet: run a scan (requires an LLM key)
- Set your LLM model and API key (example OpenAI):
```bash
export STRIX_LLM="openai/gpt-5.4"
export LLM_API_KEY="your-api-key"
```
- Start a basic scan:
```bash
# scan a local directory or a URL (this will pull the Docker sandbox image)
strix --target ./your-app
```
This creates a run under `./strix_runs/<run-name>`. After this run starts or finishes you can open it with `strix view`.

7) If you just want to look at the built UI without run data
- You already ran `npm run build`. To preview the static bundle:
```bash
# from repo root
python -m http.server 8000 --directory strix/interface/viewer/static
# then open http://127.0.0.1:8000 in your browser
```
This shows the UI but it won't have run data or steering functionality.

Important details you asked about
- Why you saw `ModuleNotFoundError: No module named 'docker'`: the Python package `docker` (docker-py) is not installed in your system Python; installing the project deps in a venv (step 4) fixes this.
- Default host/port for the viewer: it binds to `127.0.0.1` and by default uses port 0 (an ephemeral free port). `strix view` prints the full tokened URL it opened. Use `--port <N>` to request a fixed port (e.g., `--port 8080`).

Troubleshooting tips (if things go wrong)
- If pip install fails with cryptography or another compiled dependency, run:
```bash
xcode-select --install
```
and retry the install. Many Python libs ship macOS wheels so retrying after pip upgrade often succeeds.
- If strix command is still “not found”, ensure the venv is activated (`source .venv/bin/activate`) — your shell must use the venv’s `bin` directory.
- If Docker permission or connection errors occur, ensure Docker Desktop is running and that `docker info` works.
- If you do not have an LLM API key, you cannot run a full live scan (the agents use an LLM). You can still test the viewer with static data or previous runs, or use the static preview above.

If you want, I can:
- Run the exact commands here to install deps and start the viewer (I can attempt them in the workspace), or
- Walk you through any failing pip install errors if they appear (copy/paste the error), or
- Show how to create a minimal dummy `strix_runs/<name>/run.json` so you can open the viewer UI immediately without doing a real scan.

Which would you like me to do next? (I can try the venv + install here, or show how to make a dummy run file.)