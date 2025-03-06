import sys

sys.dont_write_bytecode = True

import sys
from pathlib import Path
from threading import Event

parent_dir = str(Path(__file__).parent.parent)
if parent_dir not in sys.path:
    sys.path.append(parent_dir)

from bot.core_test import main


def test_bot() -> bool:
    stop_event = Event()
    result = main(stop_event)
    print(f"Bot initialization result: {result}")
    return result


if __name__ == "__main__":
    test_bot()
