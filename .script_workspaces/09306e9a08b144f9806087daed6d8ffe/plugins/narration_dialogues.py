from plugins.base import AnalysisScript, ScriptConfig, ScriptHooks


def get_script():
    return AnalysisScript(key='narration_dialogues', name='Narration and Dialogues', description='Extract story dialogue, mission state, and quest updates from each gameplay clip.', prompt_file='prompts/narration_dialogues.txt', configs=[ScriptConfig('input_dir', 'Input clips folder', 'Folder containing clips to analyze.', None)], hooks=ScriptHooks(include_previous_result=True))
