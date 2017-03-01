"""
wrapper script for the pipeline

- sets up the directory structure
- runs the clustering
- sets up qsub scripts for validation, annotation and pairing jobs
"""
from argparse import Namespace
import argparse
import warnings
import errno
import os
import re
import sys
from configparser import ConfigParser, ExtendedInterpolation
import TSV

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from mavis.constants import PROTOCOL, log
import mavis_cluster
import mavis_validate
from mavis.validate.constants import VALIDATION_DEFAULTS


basedir = os.path.dirname(__file__)

QSUB_HEADER = """#!/bin/bash
#$ -V
#$ -N {name}
#$ -q {queue}
#$ -o {output}
#$ -l mem_free={memory}G,mem_token={memory}G,h_vmem={memory}G
#$ -j y"""

DEFAULTS = Namespace(
    min_clusters_per_file=50,
    max_files=10,
    cluster_clique_size=15,
    cluster_radius=20,
    min_orf_size=120,
    max_orf_cap=3,
    min_domain_mapping_match=0.8,
    domain_regex_filter='^PF\d+$',
    max_proximity=5000,
    uninformative_filter=True,
    blat_2bit_reference='/home/pubseq/genomes/Homo_sapiens/GRCh37/blat/hg19.2bit',
    stranded_bam=False
)

DEFAULTS.__dict__.update(VALIDATION_DEFAULTS.__dict__)


def mkdirp(dirname):
    try:
        os.makedirs(dirname)
    except OSError as exc:  # Python >2.5: http://stackoverflow.com/questions/600268/mkdir-p-functionality-in-python
        if exc.errno == errno.EEXIST and os.path.isdir(dirname):
            pass
        else:
            raise
    return dirname


def read_config(filepath):
    """
    reads the configuration settings from the configuration file

    Args:
        filepath (str): path to the input configuration file

    Returns:
        class:`list` of :class:`Namespace`: namespace arguments for each library
    """
    parser = ConfigParser(interpolation=ExtendedInterpolation())
    parser.read(filepath)

    LIBRARY_REQ_ATTR = ['protocol', 'bam_file', 'read_length', 'median_fragment_size', 'stdev_fragment_size', 'inputs']
    TYPE_CHECK = DEFAULTS.__dict__

    config = {
        'qsub': {
            'memory': 12,
            'queue': 'transabyss.q'
        },
        'reference': {
            'template_metadata': os.path.join(os.path.dirname(__file__), 'cytoBand.txt'),
            'reference_genome': '/home/pubseq/genomes/Homo_sapiens/TCGA_Special/GRCh37-lite.fa',
            'annotations': '/home/creisle/svn/ensembl_flatfiles/ensembl69_transcript_exons_and_domains_20160808.tsv',
            'masking': '/home/creisle/svn/svmerge/trunk/hg19_masked_regions.tsv'
        }
    }

    defaults = dict()
    defaults.update(DEFAULTS.__dict__)
    for attr, value in parser['DEFAULTS'].items():
        if attr == 'protocol':
            PROTOCOL.enforce(value)
        if attr in TYPE_CHECK and type(TYPE_CHECK[attr]) != type(value):
            try:
                if type(TYPE_CHECK[attr]) == bool:
                    value = TSV.tsv_boolean(value)
                else:
                    value = type(TYPE_CHECK[attr])(value)
            except ValueError:
                warnings.warn('type check failed for attr {} with value {}'.format(attr, repr(value)))
        elif attr not in TYPE_CHECK:
            raise ValueError('unexpected value in DEFAULTS section', attr, value)
        defaults[attr] = value

    library_sections = []

    for sec in parser.sections():

        section = dict()
        if sec == 'DEFAULTS':
            continue
        elif sec not in ['reference', 'qsub', 'visualization']:  # assume this is a library configuration
            library_sections.append(sec)
            for attr in LIBRARY_REQ_ATTR:
                if not parser.has_option(sec, attr):
                    raise KeyError(
                        'missing one or more required attribute(s) for the library section',
                        sec, attr, LIBRARY_REQ_ATTR)
            section['library'] = sec

        for attr, value in parser[sec].items():
            if attr == 'protocol':
                PROTOCOL.enforce(value)
            elif attr in TYPE_CHECK and type(TYPE_CHECK[attr]) != type(value):
                try:
                    value = type(TYPE_CHECK[attr])(value)
                except ValueError:
                    warnings.warn('type check failed for attr {} with value {}'.format(attr, repr(value)))
            elif attr in ['stdev_fragment_size', 'median_fragment_size', 'read_length']:
                try:
                    value = int(value)
                except ValueError:
                    value = float(value)
            elif attr == 'inputs':
                value = value.split(';') if value else []
            section[attr] = value
        config.setdefault(sec, dict()).update(section)

    for lib, section in [(l, config[l]) for l in library_sections]:
        d = dict()
        d.update(defaults)
        d.update(config['qsub'])
        d.update(config['visualization'])
        d.update(config['reference'])
        d.update(section)
        config[lib] = Namespace(**d)

    return [config[l] for l in library_sections]


def main():
    parser = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('config', help='path to the configuration file')
    parser.add_argument(
        '--output', '-o', help='path to the output directory', default=os.path.join(os.getcwd(), 'output'))
    parser.add_argument(
        '-f', '--force_overwrite', help='will overwrite existing files/directories if they exist',
        default=False, action='store_true')
    args = parser.parse_args()

    READ_FILES = {}

    if os.path.exists(args.output) and not args.force_overwrite:
        print('error: must specify the overwrite option or delete the existing output directory')
        parser.print_help()
        exit(1)
    args.output = os.path.abspath(args.output)
    configs = read_config(args.config)
    # read the config
    # set up the directory structure and run svmerge
    annotation_jobs = []
    for sec in configs:
        base = os.path.join(args.output, '{}_{}'.format(sec.library, sec.protocol))
        log('setting up the directory structure for', sec.library, 'as', base)
        base = os.path.join(args.output, '{}_{}'.format(sec.library, sec.protocol))
        cluster_output = mkdirp(os.path.join(base, 'clustering'))
        validation_output = mkdirp(os.path.join(base, 'validation'))
        annotation_output = mkdirp(os.path.join(base, 'annotation'))

        # run the merge
        log('clustering')
        setattr(sec, 'output', os.path.join(base, 'clustering'))
        merge_args = {
            'output': cluster_output,
            'max_proximity': sec.max_proximity,
            'cluster_radius': mavis_cluster.CLUSTER_RADIUS,
            'cluster_clique_size': mavis_cluster.CLUSTER_CLIQUE_SIZE,
            'max_files': mavis_cluster.MAX_FILES,
            'min_clusters_per_file': mavis_cluster.MIN_CLUSTERS_PER_FILE,
            'uninformative_filter': True
        }
        merge_args.update(sec.__dict__)
        ann = merge_args['annotations']
        merge_args['annotations'] = READ_FILES.get(ann, ann)
        merge_args = Namespace(**merge_args)
        output_files = mavis_cluster.main(merge_args)
        READ_FILES[ann] = getattr(merge_args, 'annotations')
        merge_file_prefix = None
        for f in output_files:
            m = re.match('^(?P<prefix>.*\D)\d+.tab$', f)
            if not m:
                raise UserWarning('cluster file did not match expected format', f)
            if merge_file_prefix is None:
                merge_file_prefix = m.group('prefix')
            elif merge_file_prefix != m.group('prefix'):
                raise UserWarning('merge file prefixes are not consistent', output_files)

        # now set up the qsub script for the validation and the held job for the annotation
        validation_args = {
            'output': validation_output,
            'masking': sec.masking,
            'reference_genome': sec.reference_genome,
            'blat_2bit_reference': sec.blat_2bit_reference,
            'annotations': sec.annotations,
            'library': sec.library,
            'bam_file': sec.bam_file,
            'protocol': sec.protocol,
            'read_length': sec.read_length,
            'stdev_fragment_size': sec.stdev_fragment_size,
            'median_fragment_size': sec.median_fragment_size,
            'force_overwrite': args.force_overwrite,
            'stranded_bam': sec.stranded_bam
        }
        for attr in sorted(VALIDATION_DEFAULTS.__dict__.keys()):
            validation_args[attr] = getattr(sec, attr)

        qsub = os.path.join(validation_output, 'qsub.sh')
        validation_jobname = 'validation_{}_{}'.format(sec.library, sec.protocol)
        with open(qsub, 'w') as fh:
            log('writing:', qsub)
            fh.write(
                QSUB_HEADER.format(
                    queue=sec.queue, memory=sec.memory, name=validation_jobname, output=validation_output
                ) + '\n')
            fh.write('#$ -t {}-{}\n'.format(1, len(output_files)))
            temp = ['--{} {}'.format(k, v) for k, v in validation_args.items() if not isinstance(v, str) and v is not None]
            temp.extend(['--{} "{}"'.format(k, v) for k, v in validation_args.items() if isinstance(v, str) and v is not None])
            validation_args = temp
            validation_args.append('-n {}$SGE_TASK_ID.tab'.format(merge_file_prefix))
            fh.write('python {}/mavis_validate.py {}\n'.format(basedir, ' \\\n\t'.join(validation_args)))

        # set up the annotations job
        # for all files with the right suffix
        annotation_args = {
            'output': annotation_output,
            'reference_genome': sec.reference_genome,
            'annotations': sec.annotations,
            'template_metadata': sec.template_metadata,
            'min_orf_size': sec.min_orf_size,
            'max_orf_cap': sec.max_orf_cap,
            'min_domain_mapping_match': sec.min_domain_mapping_match,
            'domain_regex_filter': sec.domain_regex_filter,
            'max_proximity': sec.max_proximity
        }
        temp = ['--{} {}'.format(k, v) for k, v in annotation_args.items() if not isinstance(v, str) and v is not None]
        temp.extend(['--{} "{}"'.format(k, v) for k, v in annotation_args.items() if isinstance(v, str) and v is not None])
        annotation_args = temp
        annotation_args.append('--input {}/*{}'.format(validation_output, mavis_validate.PASS_SUFFIX))
        qsub = os.path.join(annotation_output, 'qsub.sh')
        annotation_jobname = 'annotation_{}_{}'.format(sec.library, sec.protocol)
        annotation_jobs.append(annotation_jobname)
        with open(qsub, 'w') as fh:
            log('writing:', qsub)
            fh.write(
                QSUB_HEADER.format(
                    queue=sec.queue, memory=sec.memory, name=annotation_jobname, output=annotation_output
                ) + '\n')
            fh.write('#$ -hold_jid {}\n'.format(validation_jobname))
            fh.write('python {}/mavis_annotate.py {}\n'.format(basedir, ' \\\n\t'.join(annotation_args)))

    # set up scripts for the pairing held on all of the annotation jobs
    pairing_output = mkdirp(os.path.join(base, 'pairing'))
    qsub = os.path.join(pairing_output, 'qsub.sh')
    with open(qsub, 'w') as fh:
        log('writing:', qsub)


if __name__ == '__main__':
    main()
