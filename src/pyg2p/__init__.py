version = (3, 0, 0)
__authors__ = "Domenico Nappo"
#__version__ = 'v' + '.'.join(list(map(str, version)))
__version__ = '3.0.0-01'

import logging


class Loggable:

    def __init__(self):
        self._logger = logging.getLogger()

    def _log(self, message, level='DEBUG'):
        self._logger.log(logging._checkLevel(level), message)
