"""Keep legacy URL credentials out of Uvicorn access logs."""
import logging


class RedactAccessQuery(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        # Uvicorn's access tuple is (client, method, path-with-query, version, status).
        # Drop every query value, rather than maintain an incomplete secret-name list.
        if isinstance(record.args, tuple) and len(record.args) == 5:
            args = list(record.args)
            if isinstance(args[2], str) and '?' in args[2]:
                args[2] = args[2].split('?', 1)[0] + '?[redacted]'
                record.args = tuple(args)
        return True


def install_access_log_redaction() -> None:
    logger = logging.getLogger('uvicorn.access')
    if not any(isinstance(item, RedactAccessQuery) for item in logger.filters):
        logger.addFilter(RedactAccessQuery())
