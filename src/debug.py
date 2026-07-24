"""From https://medium.com/@neeraj.online/python-show-file-name-and-line-number-when-calling-print-like-javascript-console-log-eb240d757f9a."""

import inspect
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Any, Self

TAB_DEFAULT = '    '


@dataclass
class Timer:
    """A lap timer that can be used as a context manager or as a callable."""

    _last_time: float | None = None

    def __call__(self) -> float:
        """On first call, stores the current time and returns 0.0.
        On later calls, returns the time since the last call and updates the stored time to the current time.
        """
        now = perf_counter()
        if self._last_time is None:
            self._last_time = now
            return 0.0
        delta = now - self._last_time
        self._last_time = now
        return delta * 1000

    def __enter__(self) -> Self:
        """Start the timer when entering the context."""
        self()  # stores the current time
        return self

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        """Do nothing on exit (cleanup is not needed)."""


class TimerError(Exception):
    """A custom exception used to report errors in use of Timer class."""


def d___(*args: Any, **kwargs: Any) -> None:  # ruff:ignore[any-type]]
    if not hasattr(d___, 'timer'):
        d___.timer = Timer()
    lap = d___.timer()

    if 'only_slow' in kwargs and kwargs.pop('only_slow') and lap < 1:  # skip times < 1ms when configured
        return

    tab = kwargs.pop('tab') if 'tab' in kwargs else TAB_DEFAULT
    offset = kwargs.pop('offset') if 'offset' in kwargs else 0
    end = kwargs.pop('end') if 'end' in kwargs else '\n'

    path = kwargs.pop('path') if 'path' in kwargs else True
    prefix = '\n' if 'new_line' in kwargs and kwargs.pop('new_line') else ''
    prefix += f'  🩺  {lap:5.1f}ms'
    prefix += f', {location(offset=1 + offset)}' if path else ''
    prefix += tab * kwargs.pop('indent') if 'indent' in kwargs else ' '
    if args or kwargs:
        prefix += '🟰 '

    print(prefix, end='')  # noqa: T201
    print(*args, **kwargs, end=end)  # noqa: T201


def location(offset: int = 0, levels: int = 1) -> str:
    output = ''
    for level in range(levels):
        caller_frame_record = inspect.stack()[level + offset + 1]
        frame = caller_frame_record[0]
        info = inspect.getframeinfo(frame)
        file_info = Path(info.filename).stem
        function_info = '' if info.function == '<module>' else f':{info.function}()'
        if output:
            output += ' ❱ '
        output += f'{file_info}:{info.lineno}{function_info}'
    return output


def tup1st(arg: tuple[...]) -> Any:  # ruff:ignore[any-type]]
    return next(zip(*arg, strict=True))
