from plugins.base import AnalysisScript, ScriptConfig, ScriptHooks


def get_script():
    return AnalysisScript(key='event_timeline', name='Event Timeline', description="Configured script fields.", configs=[ScriptConfig('input_dir', 'Input clips folder', 'Input field.', 'A:\\clips', field_type='input'), ScriptConfig('output_dir', 'Output folder', 'Output field.', 'A:\\data_2v1', field_type='output'), ScriptConfig('workflow_path', 'Workflow path', 'Input field.', 'A:/gemini_extended', field_type='input')], hooks=ScriptHooks(include_previous_result=True, merge_json=False))
