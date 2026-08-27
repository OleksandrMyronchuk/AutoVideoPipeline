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

Changes to settings and analysis dialog values are saved as they are edited, with a final save when the app closes. They are written atomically to `settings.json`, so they persist whether the app is started from VS Code or directly with `python app.py`. The app also remembers the last main page and restores it when you reopen the project.

The app resolves its settings, plugin, workspace, and upload paths from the project location rather than the current working directory, so direct launches from another folder use the same files.

## Project structure

- `app.py` is the VS Code Run entrypoint.
- `interface.py` is the compatibility facade and state container for the NiceGUI controller.
- `application/runtime.py` composes startup, route registration, logging, and static files.
- `ui/` contains focused presentation mixins: navigation, settings, analysis, the cut-video page, and shared theme.
- `config.py` loads and saves persistent configuration.
- `video_processor.py` contains FFmpeg operations.
- `services/pipeline_service.py` coordinates domain services without depending on NiceGUI.
- `services/api_client.py` contains resilient API requests and buffer safety checks.
- `services/analysis_runner.py` processes configured clips and writes JSON results.
- `plugins/` contains built-in and user-added analysis scripts.
- `docs/PLUGIN_DEVELOPMENT.md` documents the plugin contract and API safety rules.

Open **Analyze Video** to use **Narration and Dialogues** or **Event Timeline**. The `+` button opens the extension menu and documentation.