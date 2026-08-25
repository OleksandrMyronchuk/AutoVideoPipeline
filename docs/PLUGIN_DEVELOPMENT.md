# Auto Video Pipeline script plugins

## Extension model

The `plugins` folder is the extension point. At startup, `ScriptRegistry` loads built-in scripts and imports each external Python file containing a `get_script()` function. The function returns metadata, a prompt, and configurable fields. The application does not need to be edited when adding a new script.

The script editor uses `services.file_system_provider.FileSystemProvider` as its workspace filesystem provider. Every editor tab receives a unique workspace under `.script_workspaces/`, containing only that script's `plugins/` and `prompts/` folders. It presents a VS Code Web-style expandable explorer, keeps all paths inside the current script workspace, and supports source, prompt, JSON, and Markdown files. Monaco reads and writes files through this provider rather than directly managing a flat list.

## Minimal plugin

Create `plugins/my_script.py` and `prompts/my_script.txt`:

```python
from plugins.base import AnalysisScript, ScriptConfig


def get_script():
    return AnalysisScript(
        key='my_script',
        name='My Script',
        description='Describe the result this script produces.',
        prompt_file='prompts/my_script.txt',
        configs=[
            ScriptConfig('input_dir', 'Input clips folder', 'Where clips are read from.', r'A:\clips'),
            ScriptConfig('output_dir', 'Output folder', 'Where JSON output is written.', r'A:\data_2'),
        ],
    )
```

Restart the app, open **Analyze Video**, and the new script appears in the list. Open it to inspect the prompt and configure its fields. Custom scripts can be renamed or deleted from the list; deletion removes the entire script workspace. The **+ Add script** action opens the locally installed Monaco Editor in edit mode with a file manager for plugin and prompt files, and its **Read Docs** button opens this guidance in the app.

## URL navigation

The primary pages have stable paths: `/cut_video`, `/analyze_video`, and `/settings`. The sidebar navigates to these URLs directly, so browser refresh and bookmarks preserve the selected section.

## API safety rules

Use `BufferedAPIClient` for API requests. It resets the external buffer to `nothing` before every request, retries transient HTTP failures, parses JSON or fenced JSON, and raises `APIProcessingError` when:

- the API returns a non-200 status;
- the request times out or cannot connect;
- the response is empty, `nothing`, `none`, or `null`;
- the response is identical to the previous response.

`AnalysisRunner` stops on that exception and writes no output for the failed clip. This protects the checkpoint/output sequence from stale buffer data.

## Configuration metadata

Each `ScriptConfig` has a `key`, human-readable `name`, `description`, `default` value, and `kind`. Use `default=None` when a field must be supplied by the user. Built-in defaults for shared paths are overridden from `settings.json` when the script dialog opens.

Open **Analyze Video**, choose **Configure & Run**, and the prompt plus declared fields are shown together. Values are remembered per script. Supported kinds are `text` (the default), `number`, and `boolean`; unknown kinds use a text field. The runner also sends all values in the API payload as `script_config`.

Use `get_pipeline_logger(__name__, script=script.key)` in plugin services and call `logger.event('your_event', detail=value)` for consistent JSON log records. The application writes these records to `.script_workspaces/script_editor.log`.

## Configuration

API and path defaults live in `settings.json` and are loaded by `config.SettingsStore`. Extend `AppSettings` and the Settings page when a global default should be shared by every plugin.