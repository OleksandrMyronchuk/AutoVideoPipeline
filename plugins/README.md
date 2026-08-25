# Analysis plugins

Built-in scripts are defined in `builtin.py`. External scripts are discovered from this folder at application startup. An external module only needs to expose `get_script()` and return an `AnalysisScript` from `plugins.base`. Use the **Add a Script** action in **Analyze Video** to open the locally installed Monaco Editor in edit mode, create a plugin file, and save it here.