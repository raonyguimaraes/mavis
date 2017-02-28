import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.dirname(__file__))

from structural_variant.breakpoint import Breakpoint
from structural_variant.annotate import load_reference_genome, Gene, usTranscript, Transcript
from structural_variant.constants import ORIENT, STRAND, CIGAR, PYSAM_READ_FLAGS, SVTYPE, CALL_METHOD
from structural_variant.interval import Interval
from structural_variant.bam.cache import BamCache
from tests import MockRead, mock_read_pair
import unittest
from tests import REFERENCE_GENOME_FILE, BAM_INPUT, FULL_BAM_INPUT, MockBamFileHandle
from structural_variant.validate.evidence import GenomeEvidence, TranscriptomeEvidence
import structural_variant.validate.call as call
from structural_variant.validate.call import EventCall

REFERENCE_GENOME = None


def setUpModule():
    global REFERENCE_GENOME
    REFERENCE_GENOME = load_reference_genome(REFERENCE_GENOME_FILE)
    if 'CTCCAAAGAAATTGTAGTTTTCTTCTGGCTTAGAGGTAGATCATCTTGGT' != REFERENCE_GENOME['fake'].seq[0:50].upper():
        raise AssertionError('fake genome file does not have the expected contents')
    global BAM_CACHE
    BAM_CACHE = BamCache(BAM_INPUT)
    global FULL_BAM_CACHE
    FULL_BAM_CACHE = BamCache(FULL_BAM_INPUT)
    global READS
    READS = {}
    for read in BAM_CACHE.fetch('reference3', 1, 8000):
        if read.qname not in READS:
            READS[read.qname] = [None, None]
        if read.is_supplementary:
            continue
        if read.is_read1:
            READS[read.qname][0] = read
        else:
            READS[read.qname][1] = read
    # add a check to determine if it is the expected bam file


class TestEventCall(unittest.TestCase):

    def setUp(self):
        self.ev1 = GenomeEvidence(
            Breakpoint('reference3', 1114, orient=ORIENT.RIGHT),
            Breakpoint('reference3', 2187, orient=ORIENT.RIGHT),
            BAM_CACHE, REFERENCE_GENOME,
            opposing_strands=True,
            read_length=125,
            stdev_fragment_size=100,
            median_fragment_size=380,
            stdev_count_abnormal=3,
            min_flanking_pairs_resolution=3
        )
        self.ev = EventCall(
            Breakpoint('reference3', 1114, orient=ORIENT.RIGHT),
            Breakpoint('reference3', 2187, orient=ORIENT.RIGHT),
            source_evidence=self.ev1,
            event_type=SVTYPE.INV,
            call_method=CALL_METHOD.SPLIT
        )

    def test_flanking_support_empty(self):
        self.assertEqual(0, len(self.ev.flanking_pairs))

    def test_flanking_support(self):
        # 1114 ++
        # 2187 ++
        self.ev.flanking_pairs.add(
            mock_read_pair(
                MockRead(
                    query_name='test1',
                    reference_id=3,
                    template_length=500,
                    reference_start=1150,
                    reference_end=1200,
                    is_reverse=True),
                MockRead(
                    reference_id=3,
                    reference_start=2200,
                    reference_end=2250,
                    is_reverse=True
                )
            ))
        self.ev.flanking_pairs.add(mock_read_pair(
            MockRead(
                query_name="test2",
                reference_id=3,
                template_length=560,
                reference_start=1150,
                reference_end=1200,
                is_reverse=True
            ),
            MockRead(
                reference_id=3,
                reference_start=2200,
                reference_end=2250,
                is_reverse=True
            )
        ))
        median, stdev = self.ev.flanking_metrics()
        self.assertEqual(2, len(self.ev.flanking_pairs))
        self.assertEqual(530, median)
        self.assertEqual(30, stdev)

    def test_split_read_support_empty(self):
        self.assertEqual(0, len(self.ev.break1_split_reads) + len(self.ev.break2_split_reads))

    def test_call_by_split_delins_del_only(self):
        raise unittest.SkipTest('TODO')

    def test_call_by_split_delins_both(self):
        raise unittest.SkipTest('TODO')

    def test_call_by_split_delins_ins_only(self):
        # not implemented yet??
        raise unittest.SkipTest('TODO')


class TestPullFlankingSupport(unittest.TestCase):
    def setUp(self):
        self.bam_cache = BamCache(MockBamFileHandle({'1': 0, '2': 1}))
        self.REFERENCE_GENOME = None

    def build_genome_evidence(self, b1, b2, opposing_strands=False):
        evidence = GenomeEvidence(
            b1, b2, self.bam_cache, self.REFERENCE_GENOME,
            opposing_strands=opposing_strands,
            read_length=100, median_fragment_size=500, stdev_fragment_size=50,
            stdev_count_abnormal=3
        )
        return evidence

    def test_deletion(self):
        evidence = self.build_genome_evidence(
            Breakpoint('1', 500, orient=ORIENT.LEFT),
            Breakpoint('1', 1000, orient=ORIENT.RIGHT)
        )
        flanking_pairs = [
            mock_read_pair(
                MockRead('r1', 0, 400, 450, is_reverse=False),
                MockRead('r1', 0, 1200, 1260, is_reverse=True)
            )]
        event = EventCall(
            Breakpoint('1', 500, orient=ORIENT.LEFT),
            Breakpoint('1', 1000, orient=ORIENT.RIGHT),
            evidence, SVTYPE.DEL, CALL_METHOD.SPLIT)

        event.pull_flanking_support(flanking_pairs)
        self.assertEqual(1, len(event.flanking_pairs))

        # now test one where the read pair type is right but the positioning of the reads doesn't
        # support the current call
        flanking_pairs.append(
            mock_read_pair(
                MockRead('r1', 0, 501, 600, is_reverse=False),
                MockRead('r1', 0, 1200, 1260, is_reverse=True)
            ))
        event.pull_flanking_support(flanking_pairs)
        self.assertEqual(1, len(event.flanking_pairs))

    def test_small_deletion_flanking_for_larger_deletion(self):
        evidence = self.build_genome_evidence(
            Breakpoint('1', 900, orient=ORIENT.LEFT),
            Breakpoint('1', 1000, orient=ORIENT.RIGHT)
        )
        flanking_pairs = [
            mock_read_pair(
                MockRead('r1', 0, 400, 450, is_reverse=False),
                MockRead('r1', 0, 1500, 1260, is_reverse=True)
            )]
        event = EventCall(
            Breakpoint('1', 900, orient=ORIENT.LEFT),
            Breakpoint('1', 1000, orient=ORIENT.RIGHT),
            evidence, SVTYPE.DEL, CALL_METHOD.SPLIT)

        event.pull_flanking_support(flanking_pairs)
        self.assertEqual(0, len(event.flanking_pairs))

    def test_insertion(self):
        evidence = self.build_genome_evidence(
            Breakpoint('1', 800, orient=ORIENT.LEFT),
            Breakpoint('1', 900, orient=ORIENT.RIGHT)
            )
        flanking_pairs = [
            mock_read_pair(
                MockRead('r1', 0, 700, 750, is_reverse=False),
                MockRead('r1', 0, 950, 1050, is_reverse=True)
                )]
        event = EventCall(
            Breakpoint('1', 800, orient=ORIENT.LEFT),
            Breakpoint('1', 900, orient=ORIENT.RIGHT),
            evidence, SVTYPE.INS, CALL_METHOD.SPLIT)
        event.pull_flanking_support(flanking_pairs)
        # not sure if there should be 1 or 0 here...
        self.assertEqual(1, len(event.flanking_pairs))

    def test_inversion(self):
        evidence = self.build_genome_evidence(
            Breakpoint('1', 500, orient=ORIENT.LEFT),
            Breakpoint('1', 1000, orient=ORIENT.LEFT),
            opposing_strands=True
        )
        flanking_pairs = [
            mock_read_pair(
                MockRead('r1', 0, 400, 450, is_reverse=False),
                MockRead('r1', 0, 900, 950, is_reverse=False)
            )]
        event = EventCall(
            Breakpoint('1', 500, orient=ORIENT.LEFT),
            Breakpoint('1', 1000, orient=ORIENT.LEFT),
            evidence, SVTYPE.INV, CALL_METHOD.SPLIT)

        event.pull_flanking_support(flanking_pairs)
        self.assertEqual(1, len(event.flanking_pairs))

        # test read that is the right type but the positioning does not support the current call
        flanking_pairs.append(
            mock_read_pair(
                MockRead('r1', 0, 501, 600, is_reverse=False),
                MockRead('r1', 0, 900,950, is_reverse=True)
            ))
        event.pull_flanking_support(flanking_pairs)
        self.assertEqual(1, len(event.flanking_pairs))

    def test_inverted_translocation(self):
        evidence = self.build_genome_evidence(
            Breakpoint('1', 1200, orient=ORIENT.LEFT),
            Breakpoint('2', 1300, orient=ORIENT.LEFT),
            opposing_strands=True
        )
        flanking_pairs = [
            mock_read_pair(
                MockRead('r1', 0, 1100, 1150, is_reverse=True),
                MockRead('r1', 1, 1200, 1250, is_reverse=True)
                )]
        event = EventCall(
            Breakpoint('1', 1200, orient=ORIENT.LEFT),
            Breakpoint('2', 1300, orient=ORIENT.LEFT),
            evidence, SVTYPE.ITRANS, CALL_METHOD.SPLIT)
        event.pull_flanking_support(flanking_pairs)
        self.assertEqual(1, len(event.flanking_pairs))

    def test_translocation(self):
        evidence = self.build_genome_evidence(
            Breakpoint('1', 1200, orient=ORIENT.RIGHT),
            Breakpoint('2', 1250, orient=ORIENT.LEFT)
        )
        flanking_pairs = [
            mock_read_pair(
                MockRead('r1', 0, 1201, 1249, is_reverse=True),
                MockRead('r1', 1, 1201, 1249, is_reverse=False)
            )]
        event = EventCall(
            Breakpoint('1', 1200, orient=ORIENT.RIGHT),
            Breakpoint('2', 1250, orient=ORIENT.LEFT),
            evidence, SVTYPE.TRANS, CALL_METHOD.SPLIT)

        event.pull_flanking_support(flanking_pairs)
        self.assertEqual(1, len(event.flanking_pairs))

        # test read that is the right type but the positioning does not support the current call
        # the mate is on the wrong chromosome (not sure if this would actually be added as flanking support)
        flanking_pairs.append(
            mock_read_pair(
                MockRead('r1', 0, 1200, 1249, is_reverse=True),
                MockRead('r1', 0, 1201, 1249, is_reverse=False)
            ))
        event.pull_flanking_support(flanking_pairs)
        self.assertEqual(1, len(event.flanking_pairs))

    def test_duplication(self):
        raise unittest.SkipTest('TODO')

    def test_outside_call_range(self):
        raise unittest.SkipTest('TODO')


class TestEvidenceConsumption(unittest.TestCase):
    def test_call_all_methods(self):
        raise unittest.SkipTest('TODO')

    def test_call_contig_only(self):
        raise unittest.SkipTest('TODO')

    def test_call_contig_and_split(self):
        raise unittest.SkipTest('TODO')

    def test_call_split_only(self):
        raise unittest.SkipTest('TODO')

    def test_call_split_and_flanking(self):
        raise unittest.SkipTest('TODO')

    def test_call_flanking_only(self):
        raise unittest.SkipTest('TODO')


class TestCallBySupportingReads(unittest.TestCase):

    def setUp(self):
        self.ev = GenomeEvidence(
            Breakpoint('fake', 50, 150, orient=ORIENT.RIGHT),
            Breakpoint('fake', 450, 550, orient=ORIENT.RIGHT),
            None, None,
            opposing_strands=True,
            read_length=40,
            stdev_fragment_size=25,
            median_fragment_size=100,
            stdev_count_abnormal=2,
            min_splits_reads_resolution=1,
            min_flanking_pairs_resolution=1
        )

    def test_empty(self):
        with self.assertRaises(UserWarning):
            break1, break2 = call._call_by_supporting_reads(self.ev, SVTYPE.INV)[0]

    def test_call_both_by_split_read(self):
        self.ev.split_reads[0].add(
            MockRead(query_name='t1', reference_start=100, cigar=[(CIGAR.S, 20), (CIGAR.EQ, 20)])
        )
        self.ev.split_reads[1].add(
            MockRead(query_name='t1', reference_start=500, cigar=[(CIGAR.S, 20), (CIGAR.EQ, 20)])
        )
        self.ev.split_reads[0].add(
            MockRead(query_name='t2', reference_start=100, cigar=[(CIGAR.S, 20), (CIGAR.EQ, 20)])
        )
        self.ev.split_reads[1].add(
            MockRead(query_name='t2', reference_start=500, cigar=[(CIGAR.S, 20), (CIGAR.EQ, 20)])
        )

        events = call._call_by_supporting_reads(self.ev, SVTYPE.INV)
        self.assertEqual(1, len(events))
        event = events[0]
        self.assertEqual(4, len(event.supporting_reads()))
        self.assertEqual(101, event.break1.start)
        self.assertEqual(101, event.break1.end)
        self.assertEqual(501, event.break2.start)
        self.assertEqual(501, event.break2.end)

    def test_call_both_by_split_read_low_resolution(self):
        self.ev.split_reads[0].add(
            MockRead(query_name='t1', reference_start=100, cigar=[(CIGAR.S, 20), (CIGAR.EQ, 20)])
        )
        self.ev.split_reads[1].add(
            MockRead(query_name='t1', reference_start=500, cigar=[(CIGAR.S, 20), (CIGAR.EQ, 20)])
        )

        break1, break2 = call._call_by_supporting_reads(self.ev, SVTYPE.INV)[0]

        self.assertEqual(101, break1.start)
        self.assertEqual(101, break1.end)
        self.assertEqual(501, break2.start)
        self.assertEqual(501, break2.end)

    def test_mixed_split_then_flanking(self):
        self.ev.split_reads[0].add(
            MockRead(
                query_name='t1', reference_start=100, cigar=[(CIGAR.S, 20), (CIGAR.EQ, 20)]
            )
        )
        self.ev.flanking_pairs.add(mock_read_pair(
            MockRead(query_name='t2', reference_id=0, reference_start=150, reference_end=150),
            MockRead(query_name='t2', reference_id=0, reference_start=505, reference_end=520)
        ))
        break1, break2 = call._call_by_supporting_reads(self.ev, SVTYPE.INV)[0]

        self.assertEqual(101, break1.start)
        self.assertEqual(101, break1.end)
        self.assertEqual(451, break2.start)
        self.assertEqual(506, break2.end)

    def test_split_flanking_read(self):
        self.ev.split_reads[1].add(
            MockRead(query_name='t1', reference_start=500, cigar=[(CIGAR.S, 20), (CIGAR.EQ, 20)])
        )
        self.ev.flanking_pairs.add(mock_read_pair(
            MockRead(query_name='t2', reference_id=0, reference_start=120, reference_end=140),
            MockRead(query_name='t2', reference_id=0, reference_start=520, reference_end=520)
        ))
        break1, break2 = call._call_by_supporting_reads(self.ev, SVTYPE.INV)[0]

        self.assertEqual(71, break1.start)
        self.assertEqual(121, break1.end)
        self.assertEqual(501, break2.start)
        self.assertEqual(501, break2.end)

    def test_both_by_flanking_pairs(self):
        self.ev.flanking_pairs.add(mock_read_pair(
            MockRead(
                query_name='t1', reference_id=0, reference_start=150, reference_end=150
            ),
            MockRead(
                query_name='t1', reference_id=0, reference_start=500, reference_end=520
            )
        ))
        self.ev.flanking_pairs.add(mock_read_pair(
            MockRead(
                query_name='t2', reference_id=0, reference_start=120, reference_end=140
            ),
            MockRead(
                query_name='t2', reference_id=0, reference_start=520, reference_end=520
            )
        ))
        break1, break2 = call._call_by_supporting_reads(self.ev, SVTYPE.INV)[0]
        # 120-149  ..... 500-519
        # max frag = 150 - 80 = 70
        self.assertEqual(82, break1.start)
        self.assertEqual(121, break1.end)
        self.assertEqual(452, break2.start)  # 70 - 21 = 49
        self.assertEqual(501, break2.end)

    def test_call_both_by_split_reads_multiple_calls(self):
        self.ev.split_reads[0].add(
            MockRead(query_name='t1', reference_start=100, cigar=[(CIGAR.S, 20), (CIGAR.EQ, 20)])
        )
        self.ev.split_reads[1].add(
            MockRead(query_name='t1', reference_start=500, cigar=[(CIGAR.S, 20), (CIGAR.EQ, 20)])
        )
        self.ev.split_reads[0].add(
            MockRead(query_name='t2', reference_start=110, cigar=[(CIGAR.S, 20), (CIGAR.EQ, 20)])
        )
        self.ev.split_reads[1].add(
            MockRead(query_name='t2', reference_start=520, cigar=[(CIGAR.S, 20), (CIGAR.EQ, 20)])
        )

        evs = call._call_by_supporting_reads(self.ev, SVTYPE.INV)
        self.assertEqual(4, len(evs))

    def test_call_by_split_reads_consume_flanking(self):
        evidence = GenomeEvidence(
            Breakpoint('reference3', 1114, orient=ORIENT.RIGHT),
            Breakpoint('reference3', 2187, orient=ORIENT.RIGHT),
            BAM_CACHE, REFERENCE_GENOME,
            opposing_strands=True,
            read_length=125,
            stdev_fragment_size=100,
            median_fragment_size=380,
            stdev_count_abnormal=3,
            min_flanking_pairs_resolution=1,
            min_splits_reads_resolution=1,
            min_linking_split_reads=1
        )
        evidence.split_reads[0].add(
            MockRead(
                query_name="test1", cigar=[(CIGAR.S, 110), (CIGAR.EQ, 40)],
                reference_start=1114, reference_end=1150
            ))
        evidence.split_reads[0].add(
            MockRead(
                query_name="test2", cigar=[(CIGAR.EQ, 30), (CIGAR.S, 120)],
                reference_start=1108, reference_end=1115
            ))
        evidence.split_reads[0].add(
            MockRead(
                query_name="test3", cigar=[(CIGAR.S, 30), (CIGAR.EQ, 120)],
                reference_start=1114, reference_end=1154,
                tags=[(PYSAM_READ_FLAGS.TARGETED_ALIGNMENT, 1)]
            ))
        evidence.split_reads[1].add(
            MockRead(
                query_name="test4", cigar=[(CIGAR.EQ, 30), (CIGAR.S, 120)], reference_start=2187
            ))
        evidence.split_reads[1].add(
            MockRead(
                query_name="test5", cigar=[(CIGAR.S, 30), (CIGAR.EQ, 120)], reference_start=2187
            ))
        evidence.split_reads[1].add(
            MockRead(
                query_name="test1", cigar=[(CIGAR.S, 30), (CIGAR.EQ, 120)],
                reference_start=2187, reference_end=2307,
                tags=[(PYSAM_READ_FLAGS.TARGETED_ALIGNMENT, 1)]
            ))

        evidence.flanking_pairs.add(mock_read_pair(
            MockRead(query_name='t1', reference_id=3, reference_start=1200, reference_end=1250, is_reverse=True),
            MockRead(reference_id=3, reference_start=2250, reference_end=2300, is_reverse=True)
        ))

        events = call._call_by_supporting_reads(evidence, event_type=SVTYPE.INV)
        for ev in events:
            print(ev, ev.event_type, ev.call_method)
        self.assertEqual(1, len(events))
        event = events[0]
        self.assertEqual(1, len(event.flanking_pairs))
        self.assertEqual(2, len(event.break1_split_reads))
        self.assertEqual(2, len(event.break2_split_reads))
        b1 = set([read.query_name for read in event.break1_split_reads])
        b2 = set([read.query_name for read in event.break2_split_reads])
        self.assertEqual(1, len(b1 & b2))


class TestCallByFlankingReads(unittest.TestCase):
    def setUp(self):
        self.ev_LR = GenomeEvidence(
            Breakpoint('fake', 100, orient=ORIENT.LEFT),
            Breakpoint('fake', 200, orient=ORIENT.RIGHT),
            None, None,
            opposing_strands=False,
            read_length=25,
            stdev_fragment_size=25,
            median_fragment_size=100,
            stdev_count_abnormal=2,
            min_flanking_pairs_resolution=1
        )

    def test_call_both_intrachromosomal_LR(self):
        # --LLL-100------------500-RRR-------
        # max fragment size: 100 + 2 * 25 = 150
        # max distance = 150 - read_length = 100
        # coverage ranges: 40->80    600->700
        self.assertEqual(150, self.ev_LR.max_expected_fragment_size)
        self.ev_LR.flanking_pairs.add((
            MockRead(reference_start=19, reference_end=60, next_reference_start=599),
            MockRead(reference_start=599, reference_end=650, next_reference_start=19)
        ))
        self.ev_LR.flanking_pairs.add((
            MockRead(reference_start=39, reference_end=80, next_reference_start=649),
            MockRead(reference_start=649, reference_end=675, next_reference_start=39)
        ))
        # add a pair that will be ignored
        self.ev_LR.flanking_pairs.add((
            MockRead(reference_start=39, reference_end=50, next_reference_start=91),
            MockRead(reference_start=91, reference_end=110, next_reference_start=39)
        ))
        break1, break2 = call._call_by_flanking_pairs(self.ev_LR, SVTYPE.DEL)
        self.assertEqual(80, break1.start)
        self.assertEqual(80 + 39, break1.end)
        self.assertEqual(600 - 24, break2.start)
        self.assertEqual(600, break2.end)

    def test_call_both_intrachromosomal_LR_coverage_overlaps_range(self):
        # this test is for ensuring that if a theoretical window calculated for the
        # first breakpoint overlaps the actual coverage for the second breakpoint (or the reverse)
        # that we adjust the theoretical window accordingly
        self.ev_LR.flanking_pairs.add((
            MockRead(reference_start=21, reference_end=60, next_reference_start=80),
            MockRead(reference_start=80, reference_end=120, next_reference_start=21)
        ))
        self.ev_LR.flanking_pairs.add((
            MockRead(reference_start=41, reference_end=80, next_reference_start=110),
            MockRead(reference_start=110, reference_end=140, next_reference_start=41)
        ))
        # pair to skip
        self.ev_LR.flanking_pairs.add((
            MockRead(reference_start=39, reference_end=80, next_reference_start=649),
            MockRead(reference_start=649, reference_end=675, next_reference_start=39)
        ))
        break1, break2 = call._call_by_flanking_pairs(self.ev_LR, SVTYPE.INS)
        self.assertEqual(80, break1.start)
        self.assertEqual(80, break1.end) # 119
        self.assertEqual(81, break2.start)
        self.assertEqual(81, break2.end)

    def test_intrachromosomal_flanking_coverage_overlap_error(self):
        self.ev_LR.flanking_pairs.add((
            MockRead(reference_start=19, reference_end=60, next_reference_start=599),
            MockRead(reference_start=599, reference_end=650, next_reference_start=19)
        ))
        self.ev_LR.flanking_pairs.add((
            MockRead(reference_start=620, reference_end=80, next_reference_start=780),
            MockRead(reference_start=780, reference_end=820, next_reference_start=620)
        ))
        with self.assertRaises(AssertionError):
            call._call_by_flanking_pairs(self.ev_LR, SVTYPE.DEL)

    def test_coverage_larger_than_max_expected_variance_error(self):
        self.ev_LR.flanking_pairs.add((
            MockRead(reference_start=19, reference_end=60, next_reference_start=599),
            MockRead(reference_start=599, reference_end=650, next_reference_start=19)
        ))
        self.ev_LR.flanking_pairs.add((
            MockRead(reference_start=301, reference_end=350, next_reference_start=780),
            MockRead(reference_start=780, reference_end=820, next_reference_start=301)
        ))
        with self.assertRaises(AssertionError):
            call._call_by_flanking_pairs(self.ev_LR, SVTYPE.DEL)

    def test_call_both_close_to_zero(self):
        # this test is for ensuring that if a theoretical window calculated for the
        # first breakpoint overlaps the actual coverage for the second breakpoint (or the reverse)
        # that we adjust the theoretical window accordingly
        ev = GenomeEvidence(
            Breakpoint('fake', 100, orient=ORIENT.RIGHT),
            Breakpoint('fake', 500, orient=ORIENT.RIGHT),
            None, None,
            opposing_strands=True,
            read_length=40,
            stdev_fragment_size=25,
            median_fragment_size=180,
            stdev_count_abnormal=2,
            min_flanking_pairs_resolution=1
        )
        ev.flanking_pairs.add((
            MockRead(reference_start=19, reference_end=60, next_reference_start=149),
            MockRead(reference_start=149, reference_end=150, next_reference_start=19)
        ))
        ev.flanking_pairs.add((
            MockRead(reference_start=39, reference_end=80, next_reference_start=199),
            MockRead(reference_start=199, reference_end=200, next_reference_start=39)
        ))
        break1, break2 = call._call_by_flanking_pairs(ev, SVTYPE.INV)

        self.assertEqual(1, break1.start)
        self.assertEqual(20, break1.end)
        self.assertEqual(81, break2.start)
        self.assertEqual(150, break2.end)

    def test_call_first_with_second_given_incompatible_error(self):
        self.ev_LR.flanking_pairs.add((
            MockRead(reference_start=100, reference_end=120, next_reference_start=200),
            MockRead(reference_start=200, reference_end=220, next_reference_start=100)
        ))
        with self.assertRaises(AssertionError):
            break1, break2 = call._call_by_flanking_pairs(
                self.ev_LR, SVTYPE.INV,
                second_breakpoint_called=Breakpoint(self.ev_LR.break2.chr, 110, orient=ORIENT.RIGHT)
            )

    def test_call_first_with_second_given_and_overlap(self):
        self.ev_LR.flanking_pairs.add((
            MockRead(reference_start=100, reference_end=120, next_reference_start=200),
            MockRead(reference_start=200, reference_end=220, next_reference_start=100)
        ))
        b2 = Breakpoint(self.ev_LR.break2.chr, 119, 150, orient=ORIENT.RIGHT)
        break1, break2 = call._call_by_flanking_pairs(
            self.ev_LR, SVTYPE.INV,
            second_breakpoint_called=b2
        )
        self.assertEqual(b2, break2)
        self.assertEqual(120, break1.start)
        self.assertEqual(149, break1.end)

    def test_call_second_with_first_given_incompatible_error(self):
        self.ev_LR.flanking_pairs.add((
            MockRead(reference_start=100, reference_end=120, next_reference_start=200),
            MockRead(reference_start=200, reference_end=220, next_reference_start=100)
        ))
        with self.assertRaises(AssertionError):
            break1, break2 = call._call_by_flanking_pairs(
                self.ev_LR, SVTYPE.INV,
                first_breakpoint_called=Breakpoint(self.ev_LR.break2.chr, 210, orient=ORIENT.LEFT)
            )

    def test_call_second_with_first_given_and_overlap(self):
        self.ev_LR.flanking_pairs.add((
            MockRead(reference_start=100, reference_end=120, next_reference_start=200),
            MockRead(reference_start=200, reference_end=220, next_reference_start=100)
        ))
        b1 = Breakpoint(self.ev_LR.break2.chr, 185, orient=ORIENT.LEFT)
        break1, break2 = call._call_by_flanking_pairs(
            self.ev_LR, SVTYPE.INV,
            first_breakpoint_called=b1
        )
        self.assertEqual(b1, break1)
        self.assertEqual(186, break2.start)
        self.assertEqual(201, break2.end)

    def test_call_transcriptome_translocation(self):
        # transcriptome test will use exonic coordinates for the asociated transcripts
        raise unittest.SkipTest('TODO')

    def test_call_transcriptome_inversion(self):
        # transcriptome test will use exonic coordinates for the asociated transcripts
        raise unittest.SkipTest('TODO')

    def test_call_transcriptome_inversion_overlapping_breakpoint_calls(self):
        # transcriptome test will use exonic coordinates for the asociated transcripts
        raise unittest.SkipTest('TODO')

    def test_call_transcriptome_deletion(self):
        # transcriptome test will use exonic coordinates for the asociated transcripts
        raise unittest.SkipTest('TODO')

if __name__ == "__main__":
    unittest.main()
