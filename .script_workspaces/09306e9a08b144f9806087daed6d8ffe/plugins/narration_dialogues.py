from plugins.base import AnalysisScript, ScriptConfig, ScriptHooks


def get_script():
    return AnalysisScript(key='narration_dialogues', name='Narration and Dialogues', description='Extract story dialogue, mission state, and quest updates from each gameplay clip.', prompt_file='prompts/narration_dialogues.txt', configs=[
        ScriptConfig('input_dir', 'Input clips folder', 'Folder containing clips to analyze.', None),
        ScriptConfig('output_dir', 'Output folder', 'Folder where analysis JSON files are written.', r'A:\data_2'),
        ScriptConfig('request_file', 'Prompt file', 'Optional file containing an extra prompt template.', None),
        ScriptConfig('workflow_path', 'Workflow path', 'Workflow path sent to the API.', r'A:/gemini_extended'),
        ScriptConfig('skip_existing', 'Skip existing outputs', 'Do not send clips that already have an output JSON.', True, 'boolean'),
    ], hooks=ScriptHooks(include_previous_result=True))
