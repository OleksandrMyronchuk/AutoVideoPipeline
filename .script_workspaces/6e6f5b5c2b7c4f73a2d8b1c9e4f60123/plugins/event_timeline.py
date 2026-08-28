from plugins.base import AnalysisScript, ScriptConfig, ScriptHooks


def get_script():
    return AnalysisScript(key='event_timeline', name='Event Timeline', description='Build a chronological, timestamp-aware list of important gameplay actions and audio triggers in each clip.', prompt_file='prompts/event_timeline.txt', configs=[ScriptConfig('input_dir', 'Input clips folder', 'Folder containing clips to analyze.', r'A:\clips')], hooks=ScriptHooks(include_previous_result=True))
