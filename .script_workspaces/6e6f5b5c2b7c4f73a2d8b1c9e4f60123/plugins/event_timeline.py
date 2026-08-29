from plugins.base import AnalysisScript, ScriptConfig, ScriptHooks


def get_script():
    return AnalysisScript(key='event_timeline', name='Event Timeline', description="Configured script fields.", prompt_file='prompts/event_timeline.txt', configs=[ScriptConfig('input_dir', 'Input clips folder', 'Input field.', 'A:\\clips', field_type='input'), ScriptConfig('output_dir', 'Output folder', 'Output field.', 'A:\\data_2v1', field_type='output'), ScriptConfig('request_file', 'Prompt file', 'Prompt field.', 'E:\\project\\AutoVideoPipeline\\.script_workspaces\\6e6f5b5c2b7c4f73a2d8b1c9e4f60123\\prompts\\event_timeline.txt', field_type='prompt'), ScriptConfig('workflow_path', 'Workflow path', 'Input field.', 'A:/gemini_extended', field_type='input'), ScriptConfig('skip_existing', 'Skip existing outputs', 'Input field.', 'True', field_type='input')], hooks=ScriptHooks(include_previous_result=True, merge_json=False))
