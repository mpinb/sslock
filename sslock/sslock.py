"""sslock.py

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

import numpy as np

import os
import sys
from pathlib import Path
import time
import dill
import re
import fcntl



# <<< generic locking functions on GPFS, works for thread safe and process safe, BUT not very efficient

# NOTE: file locking is known to be problematic, this is very much os and file system
#   dependent, but works on GPFS. also this was a much easier solution for now than
#   switching to using a database or a server-based locking or mpi.
# inspired from "Old post, but if anyone else finds it, I get this behaviour:" here:
#   https://stackoverflow.com/questions/9907616/python-fcntl-does-not-lock-as-expected
# lockf and flock behave differently on GPFS, see:
#   https://www.ibm.com/mysupport/s/question/0D50z00006LKy2a/flock-on-gpfs?language=en_US
#   flock works on GPFS for file descriptors within the same processes,
#     but not for file descriptors in different processes.
#   lockf works on GPFS for different processes (same or different nodes),
#     but not for multilple file descriptors within the same process (i.e., threads)
#   implementation here uses both locks so it is both thread and process safe.
# mode 'r+' for lockf handle is because opening 'r' causes lockf to throw Bad File Descriptor (why?).

def gpfs_file_lock(fn, allow_create=False, sleep=None, timeout=None):
    if sleep is None: sleep = [5,10]
    if allow_create and not os.path.isfile(fn): Path(fn).touch()
    busy = True
    fthread = fproc = None
    start_time = time.time()
    while busy:
        try:
            fthread = open(fn, 'rb'); fproc = open(fn, 'rb+')
            fcntl.flock(fthread, fcntl.LOCK_EX | fcntl.LOCK_NB)
            fcntl.lockf(fproc, fcntl.LOCK_EX | fcntl.LOCK_NB)
            busy = False
        except BlockingIOError:
            gpfs_file_unlock(fthread, fproc)
            # if many processes are trying to access the same set of files, polling a lot here
            #   is a disaster. since usually swarms are setup to prevent too many processes from
            #   concurrent file access, and this is an inefficient solution anyways, default
            #   to a relatively long randomized sleep range before trying again.
            time.sleep(sleep[0] if sleep[0] == sleep[1] else np.random.uniform(sleep[0], sleep[1]))
            fthread = fproc = None
            if timeout is not None and (time.time() - start_time) > timeout: busy = False
    return fthread, fproc


def gpfs_file_unlock(fthread, fproc):
    # the order here is important (?), close in the opposite order they were locked.
    if fproc is not None: fproc.close()
    if fthread is not None: fthread.close()

# generic locking functions on GPFS, works for thread safe and process safe, BUT not very efficient >>>



# <<< access functions for reading and atomically writing dills using file lock on GPFS

# mosty for standardizing the names without need for globals
def dill_get_lock_atomic_filenames(fn, lock_same_file=False):
    dn, bfn = os.path.split(fn)
    if lock_same_file:
        dn_lock_file = dn
        fn_lock_file = fn
    else:
        dn_lock_file = os.path.join(dn, '.lock-atomic')
        fn_lock_file = os.path.join(dn_lock_file, '.lock-' + bfn)
    # allow atomic files in the same directory.
    #   this means dill_atomic_dump could still be used with some other locking mechanism.
    #   for example, see report_job_completed
    dn_atomic_file = dn_lock_file if os.path.isdir(dn_lock_file) else dn
    fn_atomic_file = os.path.join(dn_atomic_file, '.atomic-' + bfn)

    return dn_lock_file, fn_lock_file, fn_atomic_file


def dill_init(fn, overwrite_dills=False, lock_same_file=False):
    dn, bfn = os.path.split(fn)
    if dn:
        os.makedirs(dn, exist_ok=True)
    if overwrite_dills and os.path.isfile(fn):
        os.remove(fn)
    if not os.path.isfile(fn):
        with open(fn, 'wb') as f: dill.dump({}, f)
    if not lock_same_file:
        dn_lock_file, fn_lock_file, _ = dill_get_lock_atomic_filenames(fn)
        os.makedirs(dn_lock_file, exist_ok=True)
        if not os.path.isfile(fn_lock_file):
            Path(fn_lock_file).touch()


# this is to make the write operation atomic so it can be resistant to
#   power failures, sudden reboots, etc
# NOTE: this function can only work properly with locking if the file
#   being locked is not the same as the dill filename (fn).
def dill_atomic_dump(fn, d):
    # https://stackoverflow.com/questions/2333872/how-to-make-file-creation-an-atomic-operation
    _, _, fn_atomic_file = dill_get_lock_atomic_filenames(fn)
    with open(fn_atomic_file, 'wb') as f:
        dill.dump(d, f)
        # make sure that all data is on disk
        # see http://stackoverflow.com/questions/7433057/is-rename-without-fsync-safe
        f.flush()
        os.fsync(f.fileno())
    os.replace(fn_atomic_file, fn)  # os.rename pre-3.3, but os.rename won't work on Windows


def dill_lock_and_load(fn, keep_locks=False, lock_same_file=True):
    _, fn_lock_file, _ = dill_get_lock_atomic_filenames(fn, lock_same_file=lock_same_file)
    f1, f2 = gpfs_file_lock(fn_lock_file)
    if lock_same_file:
        # NOTE: with lock_same_file==True the locking mechansim does not work
        #   if another file handle is opened in order to read the file.
        #   use f1 handle since it was opened read-only.
        d = dill.load(f1)
    else:
        with open(fn, 'rb') as f: d = dill.load(f)
    if keep_locks:
        # NOTE: returning open file handles in this case; they need to be closed eventually.
        #   This will block any other threads or processes from accessing this file
        #     if they access the file via these locking functions.
        return d, f1, f2
    else:
        gpfs_file_unlock(f1,f2)
        return d


def dill_lock_and_dump(fn, d, f1=None, f2=None, lock_same_file=True):
    assert( ((f1 is None) and (f2 is None)) or ((f1 is not None) and f2 is not None) )
    open_locks = (f1 is not None)
    if not open_locks:
        _, fn_lock_file, _ = dill_get_lock_atomic_filenames(fn, lock_same_file=lock_same_file)
        f1, f2 = gpfs_file_lock(fn_lock_file)
    if lock_same_file:
        # do the same as for the read and use one of the open file handles to write.
        #   use f2 handle since it was opened with 'rb+'
        f2.truncate()
        dill.dump(d,f2)
    else:
        # the atomic dump does not work with the locking mechanism
        #   if the dill file is also used as the lock file.
        dill_atomic_dump(fn, d)
    gpfs_file_unlock(f1,f2)

# access functions for reading and writing dills using file lock on GPFS >>>



# <<< "database" book-keeping to be sure that a job has completed

__fn_job_id = 'job_id.txt'
__fn_special = 'Twas_brillig_and_the_slithy_toves.dill'
__key_special = 'job_status'
__msg_special = 'Twas brillig, and the slithy toves'

def report_job_completed(
        fn_job_id=__fn_job_id,
        fn_special=__fn_special,
        key_special=__key_special,
        msg_special=__msg_special,
    ):
    batch_env_vars = ['SLURM_ARRAY_JOB_ID', 'SLURM_ARRAY_TASK_ID', 'SWARM_ARRAY_SUBJOB_ID']
    if all([x in os.environ for x in batch_env_vars]):
        # file containing the slurm job id should always be created as part of the swarm submission process.
        # if it's not available, wait for up to about 10 minutes.
        count = 0
        while True:
            if os.path.isfile(fn_job_id):
                break
            else:
                if count < 20:
                    time.sleep(30)
                else:
                    print('FATAL ERROR: no {}'.format(fn_job_id))
                    sys.exit(1)
                count += 1

        # the reason that we are not locking the dill file itself here is because this
        #   would require that it gets pre-created. this seemed a rather unnecessary extra
        #   step, so opted instead for locking the file containing the slurm job id which
        #   is always created as part of the swarm submission process. running log-less without
        #   using swarm will not allow this mechanism, and one would have to default back to the
        #   old grepping for the special message in the standard output file mechanism instead.
        fn = fn_special
        topkey = key_special
        f1, f2 = gpfs_file_lock(fn_job_id)
        if os.path.isfile(fn):
            with open(fn, 'rb') as f: d = dill.load(f)
        else:
            d = {topkey:{}}
        d[topkey]['_'.join([os.environ[x] for x in batch_env_vars])] = True
        dill_atomic_dump(fn, d)
        gpfs_file_unlock(f1,f2)

    print(msg_special) # for the legacy job completion checking mechanism that greps output logs


def parse_job_completed(fn_job_id=__fn_job_id, fn_special=__fn_special, key_special=__key_special):
    assert( os.path.isfile(fn_job_id) ) # should not happen
    f1, f2 = gpfs_file_lock(fn_job_id)
    try:
        with open(fn_special, 'rb') as f: d = dill.load(f)
    except:
        # corrupted dill file
        return None, None, None, None
    gpfs_file_unlock(f1,f2)
    #batch_env_vars = ['SLURM_ARRAY_JOB_ID', 'SLURM_ARRAY_TASK_ID', 'SWARM_ARRAY_SUBJOB_ID']
    pattern = r"(\d+)_(\d+)_(\d+)"
    count = 0; nkeys = len(d[key_special])
    slurm_array_job_id = [None]*nkeys
    slurm_array_task_id = [None]*nkeys
    swarm_array_subjob_id = [None]*nkeys
    string_id = [None]*nkeys
    for s in d[key_special].keys():
        match = re.match(pattern, s)
        if match:
            string_id[count] = s
            ids = [int(x) for x in match.groups()]
            slurm_array_job_id[count], slurm_array_task_id[count], swarm_array_subjob_id[count] = ids
            count += 1
    slurm_array_job_id = slurm_array_job_id[:count]
    slurm_array_task_id = slurm_array_task_id[:count]
    swarm_array_subjob_id = swarm_array_subjob_id[:count]
    string_id = string_id[:count]

    return slurm_array_job_id, slurm_array_task_id, swarm_array_subjob_id, string_id

# "database" book-keeping to be sure that a job has completed >>>

sslock_fn_special = __fn_special
sslock_msg_special = __msg_special
