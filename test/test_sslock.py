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
