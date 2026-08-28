from plugins.base import AnalysisScript, ScriptConfig


def get_script():
    return AnalysisScript(key='my_script_14b9938e', name='My Script', description='Describe this script.', prompt_file='prompts/my_prompt.txt', configs=[ScriptConfig('input_dir', 'Input clips folder', 'Where clips are read from.', None), ScriptConfig('request_file', 'Prompt file', 'Prompt file used for this script.', 'E:\\project\\AutoVideoPipeline\\.script_workspaces\\14b9938e5b91416d96a2e1987319b364\\prompts\\my_prompt.txt')])
