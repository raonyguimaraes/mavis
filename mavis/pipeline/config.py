from argparse import Namespace
from configparser import ConfigParser, ExtendedInterpolation
import argparse
import os
import TSV
from .. import __version__
from ..constants import PROTOCOL
from ..validate.constants import VALIDATION_DEFAULTS
from .util import get_blat_version, get_samtools_version, PIPELINE_STEP
from ..illustrate.constants import DEFAULTS as ILLUSTRATION_DEFAULTS

QSUB_TAGS = dict(validate_memory=12, default_memory=4, queue='transabyss.q')

LIBRARY_DEFAULT_TAGS = dict(
    min_clusters_per_file=50,
    max_files=10,
    cluster_clique_size=15,
    cluster_radius=20,
    min_orf_size=120,
    max_orf_cap=3,
    min_domain_mapping_match=0.8,
    max_proximity=5000,
    uninformative_filter=True,
    stranded_bam=False,
    domain_regex_filter='^PF\d+$$'  # $$ is required to represent $ with the config parser options.
)
LIBRARY_DEFAULT_TAGS.update(VALIDATION_DEFAULTS.__dict__)

REFERENCE_DEFAULT_TAGS = dict(
    low_memory=False
)

LIBRARY_REQUIRED_TAGS = dict(
    protocol=PROTOCOL.enforce,
    bam_file=str, 
    read_length=int, 
    median_fragment_size=int, 
    stdev_fragment_size=int, 
    inputs=lambda x: x.split(';') if x else [], 
    pairing=lambda x: x.split(';') if x else []
)

PAIRING_DEFAULTS = dict(
    split_call_distance=10,
    contig_call_distance=0,
    flanking_call_distance=0,
    max_proximity=5000,
    low_memory=False
)

REFERENCE_TAGS = ['template_metadata', 'reference_genome', 'annotations', 'masking', 'blat_2bit_reference', 'blat_prog']

REFERENCE_DEFAULTS_HG19 = dict(
    template_metadata=os.path.abspath(os.path.join(os.path.dirname(os.path.realpath(__file__)), 'cytoBand.txt')),
    reference_genome='/projects/seqref/genomes/Homo_sapiens/GRCh37/1000genomes/bwa_ind/genome/GRCh37-lite.fa',
    annotations='/home/creisle/svn/ensembl_flatfiles/ensembl69_transcript_exons_and_domains_20160808.tsv',
    masking='/projects/tumour_char/analysis_scripts/SVIA/delly/reference_data/GRCh37/human_nspan.hg19.excl.with_header.tsv',
    blat_2bit_reference='/home/pubseq/genomes/Homo_sapiens/GRCh37/blat/hg19.2bit',
    blat_prog='/projects/trans_scratch/software/BLAT/v36/blat',
)

def write_config(filename, include_defaults=False):
    config = ConfigParser()
    
    for sec in ['DEFAULTS', 'reference', '<LIBRARY NAME>', 'qsub', 'illustrate']:
        config[sec] = {}
    
    for tag in REFERENCE_TAGS:
        config['reference'][tag] = '<REQUIRED>'
    for tag in LIBRARY_REQUIRED_TAGS:
        config['<LIBRARY NAME>'][tag] = '<REQUIRED>'
    
    if include_defaults:
        for tag in REFERENCE_TAGS:
            config['reference'][tag] = REFERENCE_DEFAULTS_HG19[tag]
        for tag, val in QSUB_TAGS.items():
            config['qsub'][tag] = str(val)
        for tag, val in LIBRARY_DEFAULT_TAGS.items():
            config['DEFAULTS'][tag] = str(val)
        for tag, val in ILLUSTRATION_DEFAULTS.__dict__.items():
            config['illustrate'][tag] = str(val)
    
    with open(filename, 'w') as configfile:
        config.write(configfile)


def cast(value, cast_func):
    if cast_func == bool:
        value = TSV.tsv_boolean(value)
    else:
        value = cast_func(value)
    return value


def validate_and_cast_section(section, defaults):
    d = {}
    for attr, value in section.items():
        if attr not in defaults:
            raise KeyError('tag not recognized', attr)
        elif defaults[attr] is None and attr == 'assembly_max_kmer_size':
            if value == 'None':
                d[attr] = None
            elif attr == 'assembly_max_kmer_size':
                d[attr] = cast(value, int)
            else:
                d[attr] = cast(value, type(defaults[attr]))
        else:
            d[attr] = cast(value, type(defaults[attr]))
    return d


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

    # get the library sections and add the default settings
    library_sections = []
    for sec in parser.sections():
        if sec not in ['DEFAULTS', 'reference', 'qsub', 'illustrate']:
            library_sections.append(sec)
    
    all_libs = {}
    args = {}
    args.update(QSUB_TAGS)
    args.update(REFERENCE_DEFAULT_TAGS)
    all_libs.update(LIBRARY_DEFAULT_TAGS)
    illustration_defaults = {}
    for k, v in ILLUSTRATION_DEFAULTS.__dict__.items():
        illustration_defaults[k.lower()] = v
    args.update(illustration_defaults)
    args.update(PAIRING_DEFAULTS)
    # check that the reference files all exist
    for attr, fname in parser['reference'].items():
        if attr in REFERENCE_TAGS and not os.path.exists(fname):
            raise KeyError(attr, 'file at', fname, 'dose not exist')
        args[attr] = fname
    for attr in REFERENCE_TAGS:
        if attr not in parser['reference']:
            raise KeyError('missing required tag', attr, 'in reference section')

    # type check the qsub options
    if 'qsub' in parser:
        args.update(validate_and_cast_section(parser['qsub'], QSUB_TAGS))
    
    # cast the defaults
    if 'DEFAULTS' in parser:
        d = validate_and_cast_section(parser['DEFAULTS'], LIBRARY_DEFAULT_TAGS)
        all_libs.update(d)
    
    if 'illustrate' in parser:
        args.update(validate_and_cast_section(parser['illustrate'], illustration_defaults))
    
    if 'pairing' in parser:
        args.update(validate_and_cast_section(parser['pairing'], PAIRING_DEFAULTS))
    sections = []
    for sec in library_sections:
        d = {}
        d.update(all_libs)
        temp = {k: v for k, v in parser[sec].items() if k not in LIBRARY_REQUIRED_TAGS}
        temp = validate_and_cast_section(temp, LIBRARY_DEFAULT_TAGS)
        d.update(temp)
        for attr in LIBRARY_REQUIRED_TAGS:
            if attr not in parser[sec]:
                raise KeyError('required tag', attr, 'not found in library section', sec)
            d[attr] = LIBRARY_REQUIRED_TAGS[attr](parser[sec][attr])
        d['library'] = sec
        sections.append(Namespace(**d))
    if len(library_sections) < 1:
        raise UserWarning('configuration file must have 1 or more library sections')

    return Namespace(**args), sections


def parse_arguments(pstep):
    PIPELINE_STEP.enforce(pstep)

    parser = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument(
        '-v', '--version', action='version', version='%(prog)s version ' + __version__,
        help='Outputs the version number'
    )

    if pstep != PIPELINE_STEP.PIPELINE:
        g = parser.add_argument_group('reference input arguments')
        g.add_argument(
            '--annotations',
            default=REFERENCE_DEFAULTS_HG19['annotations'],
            help='path to the reference annotations of genes, transcript, exons, domains, etc.'
        )
        if pstep in [PIPELINE_STEP.ANNOTATE, PIPELINE_STEP.VALIDATE]:
            g.add_argument(
                '--reference_genome',
                default=REFERENCE_DEFAULTS_HG19['reference_genome'],
                help='path to the human reference genome in fa format'
            )
        if pstep == PIPELINE_STEP.ANNOTATE:
            g.add_argument(
                '--template_metadata', default=REFERENCE_DEFAULTS_HG19['template_metadata'],
                help='file containing the cytoband template information'
            )
        if pstep in [PIPELINE_STEP.CLUSTER, PIPELINE_STEP.VALIDATE]:
            g.add_argument(
                '--masking',
                default=REFERENCE_DEFAULTS_HG19['masking'],
            )
        g.add_argument(
            '--low_memory', default=PAIRING_DEFAULTS['low_memory'], type=TSV.tsv_boolean,
            help='when working on a machine with less memory this is sacrifice time for memory where possible'
        )
        if pstep == PIPELINE_STEP.VALIDATE:
            g.add_argument(
                '--blat_prog', default=REFERENCE_DEFAULTS_HG19['blat_prog'],
                help='path to blat'
            )
            g.add_argument(
                '--blat_2bit_reference', default=REFERENCE_DEFAULTS_HG19['blat_2bit_reference'],
                help='path to the 2bit reference file used for blatting contig sequences'
            )
    else:
        parser.add_argument('config', help='path to the pipeline configuration file')
        parser.add_argument(
            '-f', '--force_overwrite', default=False, type=TSV.tsv_boolean,
            help='set flag to overwrite existing reviewed files'
        )
    if pstep == PIPELINE_STEP.PIPELINE:
        m = parser.add_mutually_exclusive_group(required=True)
        m.add_argument('--output', help='path to the output directory')
        m.add_argument('--write', default=False, action='store_true', help='write a config')
    else:
        parser.add_argument('--output', help='path to the output directory', required=True)

    if pstep == PIPELINE_STEP.ANNOTATE:
        parser.add_argument(
            '--output_svgs', default=True, type=TSV.tsv_boolean,
            help='set flag to suppress svg drawings of putative annotations')
        parser.add_argument(
            '--min_orf_size', default=LIBRARY_DEFAULT_TAGS['min_orf_size'], type=int, 
            help='minimum size for putative ORFs'
        )
        parser.add_argument(
            '--max_orf_cap', default=LIBRARY_DEFAULT_TAGS['max_orf_cap'], type=int, 
            help='keep the n longest orfs'
        )
        parser.add_argument(
            '--min_domain_mapping_match', default=LIBRARY_DEFAULT_TAGS['min_domain_mapping_match'], type=float,
            help='minimum percent match for the domain to be considered aligned'
        )
        g = parser.add_argument_group('visualization options')
        g.add_argument(
            '--domain_regex_filter', default='^PF\d+$',
            help='only show domains which names (external identifiers) match the given pattern'
        )

    if pstep == PIPELINE_STEP.CLUSTER or pstep == PIPELINE_STEP.ANNOTATE or pstep == PIPELINE_STEP.PAIR:
        parser.add_argument(
            '--max_proximity', default=LIBRARY_DEFAULT_TAGS['max_proximity'], type=int,
            help='The maximum distance away from breakpoints to look for proximal genes'
        )
        parser.add_argument('-n', '--inputs', required=True, nargs='+', help='1 or more input files')
    elif pstep == PIPELINE_STEP.VALIDATE:
        parser.add_argument('-n', '--input', help='path to the input file', required=True)

    if pstep == PIPELINE_STEP.CLUSTER or pstep == PIPELINE_STEP.VALIDATE:
        parser.add_argument('-l', '--library', help='library name')
        parser.add_argument('--protocol', help='the library protocol: genome or transcriptome', choices=PROTOCOL.values())

    if pstep == PIPELINE_STEP.CLUSTER:
        g = parser.add_argument_group('output arguments')
        g.add_argument(
            '--max_files', default=LIBRARY_DEFAULT_TAGS['max_files'], type=int, dest='max_files',
            help='defines the maximum number of files that can be created')
        g.add_argument(
            '--min_clusters_per_file', default=LIBRARY_DEFAULT_TAGS['min_clusters_per_file'], type=int,
            help='defines the minimum number of clusters per file')
        parser.add_argument(
            '-r', '--cluster_radius', help='radius to use in clustering', 
            default=LIBRARY_DEFAULT_TAGS['cluster_radius'], type=int)
        parser.add_argument(
            '-k', '--cluster_clique_size',
            help='parameter used for computing cliques, smaller is faster, above 20 will be slow',
            default=LIBRARY_DEFAULT_TAGS['cluster_clique_size'], type=int
        )
        parser.add_argument(
            '--uninformative_filter', default=LIBRARY_DEFAULT_TAGS['uninformative_filter'], 
            help='If flag is False then the clusters will not be filtered '
            'based on lack of annotation', type=TSV.tsv_boolean
        )

    if pstep == PIPELINE_STEP.PAIR:
        parser.add_argument(
            '--split_call_distance', default=10, type=int,
            help='distance allowed between breakpoint calls when pairing from split read (and higher) resolution calls'
        )
        parser.add_argument(
            '--contig_call_distance', default=0, type=int,
            help='distance allowed between breakpoint calls when pairing from contig (and higher) resolution calls'
        )
        parser.add_argument(
            '--flanking_call_distance', default=0, type=int,
            help='distance allowed between breakpoint calls when pairing from contig (and higher) resolution calls'
        )

    if pstep == PIPELINE_STEP.VALIDATE:
        g = parser.add_argument_group('evidence arguments')
        for attr, value in VALIDATION_DEFAULTS.__dict__.items():
            vtype = type(value)
            if type(value) == bool:
                vtype = TSV.tsv_boolean
            g.add_argument('--{}'.format(attr), default=value, type=vtype, help='see user manual for desc')
        parser.add_argument(
            '-b', '--bam_file',
            help='path to the input bam file', required=True
        )
        parser.add_argument(
            '--stranded_bam', default=False, type=TSV.tsv_boolean,
            help='indicates that the input bam file is strand specific'
        )
        g.add_argument('--read_length', type=int, help='the length of the reads in the bam file', required=True)
        g.add_argument(
            '--stdev_fragment_size', type=int, help='expected standard deviation in insert sizes', required=True
        )
        g.add_argument(
            '--median_fragment_size', type=int, help='median inset size for pairs in the bam file', required=True
        )

    args = parser.parse_args()
    if pstep == PIPELINE_STEP.VALIDATE:
        args.samtools_version = get_samtools_version()
        args.blat_version = get_blat_version(args.blat_prog)
    try:
        args.output = os.path.abspath(args.output)
        if os.path.exists(args.output) and not args.force_overwrite:
            parser.print_help()
            print(
                '\nerror: output directory {} exists, --force_overwrite must be specified or the directory removed'.format(
                    repr(args.output)))
            exit(1)
    except (AttributeError, TypeError):
        pass

    return args

