from plugins.base import AnalysisScript, ScriptConfig, ScriptHooks


def get_script():
    return AnalysisScript(key='my_script_14b9938e', name='Merge `Narration and Dialogues` and `Event Timeline`', description="Configured script fields.", prompt_file='prompts/my_prompt.txt', configs=[ScriptConfig('narration_input_dir', 'Narration and Dialogues folder', 'Input field.', 'A:\\data_2', field_type='input'), ScriptConfig('event_timeline_input_dir', 'Event Timeline folder', 'Input field.', 'A:\\data_2v1', field_type='input'), ScriptConfig('merged_output_file', 'Merged output file', 'Output field.', 'A:\\data_3\\output.json', field_type='output')], hooks=ScriptHooks(include_previous_result=False, merge_json=True))
