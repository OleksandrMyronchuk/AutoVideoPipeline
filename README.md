# Auto Video Pipeline

A local NiceGUI tool for splitting videos into clips with FFmpeg.

The default configuration is stored in [settings.json](settings.json). It starts with the paths and 60-second duration from the example script, so the Cut Video page is ready for a single click when that input file exists.

## Run in VS Code

1. Open this folder in VS Code.
2. Select the `.venv` interpreter if VS Code has not selected it automatically.
3. Open `app.py` and click **Run Python File** or press `F5` and choose **Run Auto Video Pipeline**.
4. Open `http://localhost:8080` in your browser.

If port 8080 is already in use, start the app on another port with `$env:AVP_PORT=8081` before running `app.py`, then open `http://localhost:8081`.

Install the optional bundled FFmpeg helper first if needed:

```powershell
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

The app can also use an FFmpeg installation available on your `PATH`, or a custom executable selected in **Settings**.

Change the source path, output folder, FFmpeg executable, or clip duration in **Settings**, then click **Save settings**. Those values are written back to `settings.json` and loaded the next time the app starts.

## Project structure

- `app.py` is the VS Code Run entrypoint.
- `interface.py` contains the NiceGUI screens and user interactions.
- `config.py` loads and saves persistent configuration.
- `video_processor.py` contains FFmpeg operations.
- `services/api_client.py` contains resilient API requests and buffer safety checks.
- `services/analysis_runner.py` processes configured clips and writes JSON results.
- `plugins/` contains built-in and user-added analysis scripts.
- `docs/PLUGIN_DEVELOPMENT.md` documents the plugin contract and API safety rules.

Open **Analyze Video** to use **Narration and Dialogues** or **Event Timeline**. The `+` button opens the extension menu and documentation.