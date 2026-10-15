#!/usr/bin/env python3
"""Isolated v4 learning wrapper; reuse v3 pilot logic but NOT its checkpoints."""
import sys
from pathlib import Path
import fr88_v3_pilot as pilot

pilot.OUT=Path("/raw/jbible_fr1988_v4_learning")
pilot.PROMPT=pilot.OUT/"learned_prompt.txt"

if __name__=="__main__":
    sys.exit(pilot.main())
