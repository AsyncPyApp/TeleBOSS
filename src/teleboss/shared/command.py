from dataclasses import dataclass
from typing import Callable, Optional


@dataclass
class Command:
    command_func: Callable
    aliases: Optional[tuple[str]]
