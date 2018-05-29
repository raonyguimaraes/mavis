import multiprocessing


from ..constants import MavisNamespace, nullable_int
from ..util import WeakMavisNamespace



JOB_STATUS = MavisNamespace(
    'SUBMITTED',
    'COMPLETED',
    'ERROR',
    'RUNNING',
    'FAILED',
    'PENDING',
    'CANCELLED',
    NOT_SUBMITTED='NOT SUBMITTED'
)

def cumulative_job_state(states):
    priority = [JOB_STATUS.ERROR, JOB_STATUS.FAILED, JOB_STATUS.CANCELLED, JOB_STATUS.NOT_SUBMITTED, JOB_STATUS.PENDING, JOB_STATUS.SUBMITTED, JOB_STATUS.RUNNING, JOB_STATUS.COMPLETED]
    for state in priority:
        if state in states:
            return state
    return JOB_STATUS.NOT_SUBMITTED


SCHEDULER = MavisNamespace('SGE', 'SLURM', 'TORQUE', 'LOCAL', __name__='~mavis.submit.SCHEDULER')
""":class:`~mavis.constants.MavisNamespace`: scheduler types

- :term:`SGE`
- :term:`SLURM`
"""

MAIL_TYPE = MavisNamespace('BEGIN', 'END', 'FAIL', 'ALL', 'NONE')
"""
only supporting common mail type options between sge and slurm
https://slurm.schedmd.com/sbatch.html
http://gridscheduler.sourceforge.net/htmlman/htmlman1/qsub.html
"""

STD_OPTIONS = ['memory_limit', 'queue', 'time_limit', 'import_env', 'mail_user', 'mail_type']

OPTIONS = WeakMavisNamespace(__name__='~mavis.submit.options')
""":class:`~mavis.constants.MavisNamespace`: submission options

- :term:`annotation_memory`
- :term:`import_env`
- :term:`memory_limit`
- :term:`queue`
- :term:`scheduler`
- :term:`time_limit`
- :term:`trans_validation_memory`
- :term:`validation_memory`

"""
OPTIONS.add('annotation_memory', 12000, defn='default memory limit (MB) for the annotation stage')
OPTIONS.add('import_env', True, defn='flag to import environment variables')
OPTIONS.add('mail_type', 'NONE', cast_type=MAIL_TYPE.enforce, defn='When to notify the mail_user (if given)')
OPTIONS.add('mail_user', '', defn='User(s) to send notifications to')
OPTIONS.add('memory_limit', 16000, defn='the maximum number of megabytes (MB) any given job is allowed')  # 16 GB
OPTIONS.add('queue', '', cast_type=str, defn='the queue jobs are to be submitted to')
OPTIONS.add('scheduler', SCHEDULER.SLURM, defn='The scheduler being used', cast_type=SCHEDULER)
OPTIONS.add('time_limit', 16 * 60 * 60, defn='the time in seconds any given jobs is allowed')  # 16 hours
OPTIONS.add('trans_validation_memory', 18000, defn='default memory limit (MB) for the validation stage (for transcriptomes)')
OPTIONS.add('validation_memory', 16000, defn='default memory limit (MB) for the validation stage')
OPTIONS.add(
    'concurrency_limit',
    None,
    cast_type=nullable_int,
    defn='The concurrency limit for tasks in any given job array or the number of concurrent processes allowed for a local run')