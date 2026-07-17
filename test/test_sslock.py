"""test_sslock.py

minimum test case for CI
  low-level file locking for parallel access on gpfs (spectrum storage)

Copyright (C) 2018-2026 Max Planck Institute for Neurobiology of Behavior

This program is free software: you can redistribute it and/or modify it under
the terms of the GNU General Public License as published by the Free Software
Foundation, either version 3 of the License, or (at your option) any later
version.

This program is distributed in the hope that it will be useful, but WITHOUT
ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.

You should have received a copy of the GNU General Public License along with
this program. If not, see <http://www.gnu.org/licenses/>.
"""

from pathlib import Path

import numpy as np


def test__dill_locks(tmp_path: Path, output_path: Path) -> None:
    from sslock import dill_init, dill_lock_and_load, dill_lock_and_dump

    output_path = output_path if output_path is not None else tmp_path

    dill_fn = output_path / 'test.dill'

    dill_init(dill_fn)

    d, f1, f2 = dill_lock_and_load(dill_fn, keep_locks=True)
    d['amazing_stuff'] = np.arange(1000)
    dill_lock_and_dump(dill_fn, d, f1, f2)
