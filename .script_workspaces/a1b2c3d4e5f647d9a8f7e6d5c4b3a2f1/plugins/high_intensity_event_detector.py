from plugins.base import AnalysisScript, ScriptConfig, ScriptHooks


def get_script():
    return AnalysisScript(key='high_intensity_event_detector', name='High Intensity Event Detector', description="Configured script fields.", configs=[ScriptConfig('video_clips', 'Video clips', 'Input field.', 'A:\\clips', field_type='input'), ScriptConfig('sensitivity', 'Sensitivity', 'Input field.', '75', field_type='input'), ScriptConfig('before_action', 'Before action (seconds)', 'Input field.', '1.0', field_type='input'), ScriptConfig('after_action', 'After action (seconds)', 'Input field.', '0.5', field_type='input'), ScriptConfig('output_dir', 'Output folder', 'Output field.', 'A:\\analysis\\high_intensity', field_type='output')], hooks=ScriptHooks(include_previous_result=False, merge_json=False))
