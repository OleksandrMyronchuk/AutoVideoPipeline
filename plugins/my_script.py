from plugins.base import AnalysisScript, ScriptConfig


def get_script():
    return AnalysisScript(key='my_script', name='My Script', description='Describe this script.', prompt_file='prompts/my_prompt.txt', configs=[ScriptConfig('input_dir', 'Input clips folder', 'Where clips are read from.', None)])
