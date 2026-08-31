from plugins.base import AnalysisScript, ScriptConfig, ScriptHooks


def get_script():
    return AnalysisScript(key='narration_dialogues', name='Narration and Dialogues', description='Extract story dialogue, mission state, and quest updates from each gameplay clip.', configs=[
        ScriptConfig('input_dir', 'Input clips folder', 'Folder containing clips to analyze.', None),
        ScriptConfig('output_dir', 'Output folder', 'Folder where analysis JSON files are written.', r'A:\data_2'),
        ScriptConfig('workflow_path', 'Workflow path', 'Workflow path sent to the API.', r'A:/gemini_extended'),
    ], hooks=ScriptHooks(include_previous_result=True))
