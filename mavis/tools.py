import glob
import itertools
import re
import warnings

from braceexpand import braceexpand
import TSV
import vcf
from vocab import Vocab

from .breakpoint import Breakpoint, BreakpointPair, read_bpp_from_input_file
from .constants import COLUMNS
from .constants import ORIENT, STRAND, SVTYPE
from .error import InvalidRearrangement
from .util import devnull

SUPPORTED_TOOL = Vocab(
    MANTA='manta',
    DELLY='delly',
    TA='transabyss',
    # BREAKDANCER='breakdancer',  # TODO: later versions will include support for these tools
    PINDEL='pindel',
    CHIMERASCAN='chimerascan',
    MAVIS='mavis',
    DEFUSE='defuse'
)

TOOL_SVTYPE_MAPPING = {v: [v] for v in SVTYPE.values()}
TOOL_SVTYPE_MAPPING.update({
    'DEL': [SVTYPE.DEL],
    'INS': [SVTYPE.INS],
    'ITX': [SVTYPE.DUP],
    'CTX': [SVTYPE.TRANS, SVTYPE.ITRANS],
    'INV': [SVTYPE.INV],
    'BND': [SVTYPE.TRANS],
    'TRA': [SVTYPE.TRANS, SVTYPE.ITRANS],
    'CNV': [SVTYPE.DUP],
    'RPL': [SVTYPE.INS],
    'DUP:TANDEM': [SVTYPE.DUP],
    'DUP': [SVTYPE.DUP],
    'interchromosomal': [SVTYPE.TRANS, SVTYPE.ITRANS],
    'eversion': [SVTYPE.DUP],
    'translocation': [SVTYPE.TRANS, SVTYPE.ITRANS],
    'ins': [SVTYPE.INS],
    'del': [SVTYPE.DEL],
    'dup': [SVTYPE.DUP],
    'ITD': [SVTYPE.DUP]
})


def convert_tool_output(input_file, file_type=SUPPORTED_TOOL.MAVIS, stranded=False, log=devnull, collapse=True):
    result = []
    fnames = []
    for name in braceexpand(input_file):
        for subname in glob.glob(name):
            fnames.append(subname)
    if len(fnames) == 0:
        raise OSError('no such file', input_file)
    for fname in fnames:
        result.extend(_convert_tool_output(fname, file_type, stranded, log))
    if collapse:
        collapse_mapping = {}
        for bpp in result:
            collapse_mapping.setdefault(bpp, []).append(bpp)
        log('collapsed', len(result), 'to', len(collapse_mapping), 'calls')
        result = list(collapse_mapping.keys())
    return result


def _convert_tool_row(row, file_type, stranded):
    std_row = {}
    orient1 = orient2 = ORIENT.NS
    strand1 = strand2 = STRAND.NS
    result = []
    # convert the specified file type to a standard format
    if file_type in [SUPPORTED_TOOL.DELLY, SUPPORTED_TOOL.MANTA, SUPPORTED_TOOL.PINDEL]:

        if row.INFO['SVTYPE'] == 'BND':
            chr2 = row.ALT[0].chr
            end = row.ALT[0].pos
        else:
            chr2 = row.INFO.get('CHR2', row.CHROM)
            end = row.INFO.get('END', row.POS)

        std_row.update({
            'chr1': row.CHROM, 'chr2': chr2,
            'pos1_start': max(1, row.POS + row.INFO.get('CIPOS', (0, 0))[0]),
            'pos1_end': row.POS + row.INFO.get('CIPOS', (0, 0))[1],
            'pos2_start': max(1, end + row.INFO.get('CIEND', (0, 0))[0]),
            'pos2_end': end + row.INFO.get('CIEND', (0, 0))[1]
        })
        std_row['event_type'] = row.INFO['SVTYPE']
        try:
            o1, o2 = row.INFO['CT'].split('to')
            ct = {'3': ORIENT.LEFT, '5': ORIENT.RIGHT, 'N': ORIENT.NS}
            orient1 = ct[o1]
            orient2 = ct[o2]
        except KeyError:
            pass

    elif file_type == SUPPORTED_TOOL.CHIMERASCAN:

        std_row.update({'chr1': row['chrom5p'], 'chr2': row['chrom3p']})
        if row['strand5p'] == '+':
            std_row['pos1_start'] = row['end5p']
            orient1 = ORIENT.LEFT
        else:
            std_row['pos1_start'] = row['start5p']
            orient1 = ORIENT.RIGHT
        if row['strand3p'] == '+':
            std_row['pos2_start'] = row['start3p']
            orient2 = ORIENT.RIGHT
        else:
            std_row['pos2_start'] = row['end3p']
            orient2 = ORIENT.LEFT
        std_row['opposing_strands'] = row['strand5p'] != row['strand3p']

    # TODO: later versions will include support for these tools
    # elif file_type == SUPPORTED_TOOL.BREAKDANCER:
    #     std_row.update({
    #         'chr1': row['Chr1'], 'chr2': row['Chr2'],
    #         'pos1_start': row['Pos1'], 'pos2_start': row['Pos2'],
    #         'event_type': row['Type']
    #     })

    elif file_type == SUPPORTED_TOOL.DEFUSE:

        orient1 = ORIENT.LEFT if row['genomic_strand1'] == STRAND.POS else ORIENT.RIGHT
        orient2 = ORIENT.LEFT if row['genomic_strand2'] == STRAND.POS else ORIENT.RIGHT
        std_row.update({
            'chr1': row['gene_chromosome1'], 'chr2': row['gene_chromosome2'],
            'pos1_start': row['genomic_break_pos1'], 'pos2_start': row['genomic_break_pos2']
        })

    elif file_type == SUPPORTED_TOOL.TA:

        std_row['event_type'] = row.get('rearrangement', row['type'])
        if std_row['event_type'] in ['LSR', 'translocation']:
            del std_row['event_type']
        if 'breakpoint' in row:
            orient1, orient2 = row['orientations'].split(',')
            if stranded:
                strand1, strand2 = row['strands'].split(',')
                strand1 = STRAND.POS if strand1 == STRAND.NEG else STRAND.NEG
                strand2 = STRAND.POS if strand2 == STRAND.NEG else STRAND.NEG
            m = re.match(
                '^(?P<chr1>[^:]+):(?P<pos1_start>\d+)\|(?P<chr2>[^:]+):(?P<pos2_start>\d+)$', row['breakpoint'])
            if not m:
                raise OSError(
                    'file format error: the breakpoint column did not satisfy the expected pattern', row)
            std_row.update({k: m[k] for k in ['chr1', 'pos1_start', 'chr2', 'pos2_start']})
        else:
            std_row.update({
                'chr1': row['chr'], 'pos1_start': row['chr_start'], 'pos2_start': int(row['chr_end']) + 1
            })
            if stranded:
                strand1 = strand2 = (STRAND.POS if row['ctg_strand'] == STRAND.NEG else STRAND.NEG)
    else:
        raise NotImplementedError('unsupported file type', file_type)

    if stranded:
        strand1 = STRAND.expand(strand1)
        strand2 = STRAND.expand(strand2)
    else:
        strand1 = [strand1]
        strand2 = [strand2]

    combinations = list(itertools.product(
        ORIENT.expand(orient1), ORIENT.expand(orient2),
        strand1, strand2, TOOL_SVTYPE_MAPPING[std_row['event_type']] if 'event_type' in std_row else [None],
        [True, False] if 'opposing_strands' not in std_row else [std_row['opposing_strands']]
    ))
    # add the product of all uncertainties as breakpoint pairs
    for orient1, orient2, strand1, strand2, event_type, oppose in combinations:
        try:

            bpp = BreakpointPair(
                Breakpoint(
                    std_row['chr1'],
                    std_row['pos1_start'],
                    std_row.get('pos1_end', std_row['pos1_start']),
                    orient=orient1, strand=strand1
                ),
                Breakpoint(
                    std_row.get('chr2', std_row['chr1']),
                    std_row['pos2_start'],
                    std_row.get('pos2_end', std_row['pos2_start']),
                    orient=orient2, strand=strand2
                ),
                opposing_strands=oppose,
                event_type=event_type,
                data={
                    COLUMNS.tools: file_type
                },
                stranded=stranded
            )
            if not event_type or event_type in BreakpointPair.classify(bpp):
                result.append(bpp)

        except (InvalidRearrangement, AssertionError):
            pass
    if len(result) == 0:
        raise UserWarning(
            'row failed to create any breakpoint pairs. This generally indicates an input formatting error',
            row, std_row, combinations)
    return result


def _convert_tool_output(input_file, file_type=SUPPORTED_TOOL.MAVIS, stranded=False, log=devnull):
    log('reading:', input_file)
    result = []
    if file_type == SUPPORTED_TOOL.TA:
        warnings.warn('currently assuming that trans-abyss is calling the strand exactly opposite and swapping them')
    if file_type == SUPPORTED_TOOL.MAVIS:
        result = read_bpp_from_input_file(input_file)
    else:
        if file_type in [SUPPORTED_TOOL.DELLY, SUPPORTED_TOOL.MANTA, SUPPORTED_TOOL.PINDEL]:
            rows = list(vcf.Reader(filename=input_file))
        else:
            header, rows = TSV.read_file(input_file)
        log('found', len(rows), 'rows')
        for row in rows:
            std_rows = _convert_tool_row(row, file_type, stranded)
            result.extend(std_rows)
    log('generated', len(result), 'breakpoint pairs')
    return result
