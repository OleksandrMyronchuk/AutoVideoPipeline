from .base import AnalysisScript, ScriptConfig


PROMPTS_DIR = 'prompts'


def builtin_scripts() -> list[AnalysisScript]:
    shared = [
        ScriptConfig('input_dir', 'Input clips folder', 'Folder containing video clips to analyze.', r'A:\clips'),
        ScriptConfig('output_dir', 'Output folder', 'Folder where analysis JSON files are written.', r'A:\data_2'),
        ScriptConfig('request_file', 'Prompt file', 'Optional file containing an extra prompt template.', r'A:\requests\request1.txt'),
        ScriptConfig('workflow_path', 'Workflow path', 'Workflow path sent to the API.', r'A:\aistudio_g37_norm'),
        ScriptConfig('skip_existing', 'Skip existing outputs', 'Do not send clips that already have an output JSON.', True, 'boolean'),
    ]
    return [
        AnalysisScript('narration_dialogues', 'Narration and Dialogues', 'Extract narration, spoken dialogue, speaker context, and continuity state from every clip.', f'{PROMPTS_DIR}/narration_dialogues.txt', shared),
        AnalysisScript('event_timeline', 'Event Timeline', 'Build a chronological, timestamp-aware list of important events, actions, and transitions in each clip.', f'{PROMPTS_DIR}/event_timeline.txt', shared),
    ]