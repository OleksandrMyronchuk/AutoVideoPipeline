import logging
import json
from typing import Any


class PipelineLogger(logging.LoggerAdapter):
    """Logger hook that adds a stable event name and shared context."""

    def event(self, name: str, **fields: Any) -> None:
        self.info(name, extra={'event': name, **fields})

    def process(self, message, kwargs):
        event_fields = kwargs.get('extra', {})
        kwargs['extra'] = {**self.extra, **event_fields}
        return message, kwargs


def get_pipeline_logger(name: str, **context: Any) -> PipelineLogger:
    return PipelineLogger(logging.getLogger(name), context)


class PipelineFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        standard = logging.LogRecord(None, 0, '', 0, '', (), None).__dict__
        fields = {key: value for key, value in record.__dict__.items() if key not in standard}
        return json.dumps({
            'time': self.formatTime(record),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
            'fields': fields,
        }, default=str)