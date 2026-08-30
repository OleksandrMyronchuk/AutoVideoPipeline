from plugins.base import AnalysisScript, ScriptConfig, ScriptHooks


def get_script():
    return AnalysisScript(
        key='my_script_14b9938e',
        name='Merge Narration and Dialogues and Event Timeline',
        description='Combine the chunked narration/dialogue and event timeline JSON files into a single merged output JSON file.',
        prompt_file='prompts/my_prompt.txt',
        configs=[
            ScriptConfig('narration_input_dir', 'Narration and Dialogues folder', 'Folder containing narration/dialogue chunk JSON files.', r'A:\data_2', field_type='input', merge_group='narration_dialogues'),
            ScriptConfig('event_timeline_input_dir', 'Event Timeline folder', 'Folder containing event timeline chunk JSON files.', r'A:\data_2v1', field_type='input', merge_group='event_timeline'),
            ScriptConfig('merged_output_file', 'Merged output file', 'Single JSON file that receives the merged results.', r'A:\data_3\output.json', field_type='output', merge_group='merged_output'),
        ],
        hooks=ScriptHooks(merge_json=True),
    )
