import unittest

from mavis.annotate.genomic import UsTranscript
from mavis.breakpoint import Breakpoint, BreakpointPair
from mavis.constants import CALL_METHOD, COLUMNS, ORIENT, PROTOCOL, STRAND, SVTYPE
from mavis.pairing.pairing import equivalent_events, predict_transcriptome_breakpoint


class TestPairing(unittest.TestCase):

    def setUp(self):
        self.gev1 = BreakpointPair(
            Breakpoint('1', 1),
            Breakpoint('1', 10),
            opposing_strands=True,
            data={
                COLUMNS.event_type: SVTYPE.DEL,
                COLUMNS.call_method: CALL_METHOD.CONTIG,
                COLUMNS.fusion_sequence_fasta_id: None,
                COLUMNS.protocol: PROTOCOL.GENOME
            }
        )
        self.gev2 = BreakpointPair(
            Breakpoint('1', 1),
            Breakpoint('1', 10),
            opposing_strands=True,
            data={
                COLUMNS.event_type: SVTYPE.DEL,
                COLUMNS.call_method: CALL_METHOD.CONTIG,
                COLUMNS.fusion_sequence_fasta_id: None,
                COLUMNS.protocol: PROTOCOL.GENOME
            }
        )

        self.ust1 = UsTranscript(
            exons=[(1, 100), (301, 400), (501, 600)],
            strand=STRAND.POS,
            name='t1'
        )
        self.ust2 = UsTranscript(
            exons=[(1001, 1100), (1301, 1400), (1501, 1600)],
            strand=STRAND.POS,
            name='t2'
        )
        self.distances = {CALL_METHOD.CONTIG: 0, CALL_METHOD.FLANK: 0, CALL_METHOD.SPLIT: 10}
        self.TRANSCRIPTS = {
            self.ust1.name: self.ust1,
            self.ust2.name: self.ust2
        }

    def test_genome_protocol_diff_chrom(self):
        self.gev2.break1.chr = '2'
        self.assertFalse(equivalent_events(self.gev1, self.gev2, self.TRANSCRIPTS))

    def test_genome_protocol_diff_orient(self):
        self.gev2.break1.orient = ORIENT.LEFT
        self.gev1.break1.orient = ORIENT.RIGHT
        self.assertFalse(equivalent_events(self.gev1, self.gev2, self.TRANSCRIPTS))

    def test_genome_protocol_diff_strand(self):
        self.gev2.break1.strand = STRAND.POS
        self.gev1.break1.strand = STRAND.NEG
        self.assertFalse(equivalent_events(self.gev1, self.gev2, self.TRANSCRIPTS))

    def test_genome_protocol_diff_event_type(self):
        self.gev2.data[COLUMNS.event_type] = SVTYPE.DEL
        self.gev1.data[COLUMNS.event_type] = SVTYPE.INS
        self.assertFalse(equivalent_events(self.gev1, self.gev2, self.TRANSCRIPTS))

    def test_genome_protocol_ns_orient(self):
        self.gev2.break1.orient = ORIENT.LEFT
        self.gev1.break2.orient = ORIENT.RIGHT
        self.assertTrue(equivalent_events(self.gev1, self.gev2, self.TRANSCRIPTS))

    def test_genome_protocol_by_contig(self):
        self.gev1.call_method = CALL_METHOD.CONTIG
        self.gev2.call_method = CALL_METHOD.CONTIG
        self.distances[CALL_METHOD.CONTIG] = 0
        self.distances[CALL_METHOD.SPLIT] = 10
        self.assertTrue(equivalent_events(self.gev1, self.gev2, self.TRANSCRIPTS, distances=self.distances))

        self.gev1.break1.start = 2
        self.gev1.break1.end = 20
        self.assertFalse(equivalent_events(self.gev1, self.gev2, self.TRANSCRIPTS, distances=self.distances))

    def test_genome_protocol_by_split(self):
        self.gev1.call_method = CALL_METHOD.SPLIT
        self.gev2.call_method = CALL_METHOD.SPLIT
        self.assertTrue(equivalent_events(self.gev1, self.gev2, self.TRANSCRIPTS, distances=self.distances))
        self.distances[CALL_METHOD.FLANK] = 100
        self.distances[CALL_METHOD.SPLIT] = 10
        self.gev1.break1.start = 11
        self.gev1.break1.end = 20
        self.assertFalse(equivalent_events(self.gev1, self.gev2, self.TRANSCRIPTS, distances=self.distances))

    def test_genome_protocol_by_flanking(self):
        self.gev1.call_method = CALL_METHOD.FLANK
        self.gev2.call_method = CALL_METHOD.FLANK
        self.assertTrue(equivalent_events(self.gev1, self.gev2, self.TRANSCRIPTS, distances=self.distances))
        self.distances[CALL_METHOD.FLANK] = 10
        self.distances[CALL_METHOD.SPLIT] = 100
        self.gev1.break1.start = 11
        self.gev1.break1.end = 20
        self.assertFalse(equivalent_events(self.gev1, self.gev2, self.TRANSCRIPTS, distances=self.distances))

    def test_mixed_protocol_fusions_same_sequence(self):
        product_sequences = {'a': 'AATG', 'b': 'AATG'}
        genome_ev = BreakpointPair(
            Breakpoint('1', 1),
            Breakpoint('1', 10),
            opposing_strands=True,
            data={
                COLUMNS.event_type: SVTYPE.DEL,
                COLUMNS.call_method: CALL_METHOD.CONTIG,
                COLUMNS.fusion_sequence_fasta_id: None,
                COLUMNS.protocol: PROTOCOL.GENOME,
                COLUMNS.transcript1: None,
                COLUMNS.transcript2: None,
                COLUMNS.fusion_cdna_coding_start: 1,
                COLUMNS.fusion_cdna_coding_end: 10
            }
        )
        trans_ev = BreakpointPair(
            Breakpoint('1', 50),
            Breakpoint('1', 60),
            opposing_strands=True,
            data={
                COLUMNS.event_type: SVTYPE.DEL,
                COLUMNS.call_method: CALL_METHOD.CONTIG,
                COLUMNS.fusion_sequence_fasta_id: None,
                COLUMNS.protocol: PROTOCOL.TRANS,
                COLUMNS.transcript1: None,
                COLUMNS.transcript2: None,
                COLUMNS.fusion_cdna_coding_start: 1,
                COLUMNS.fusion_cdna_coding_end: 10
            }
        )
        self.assertFalse(equivalent_events(genome_ev, trans_ev, self.TRANSCRIPTS))
        genome_ev.data[COLUMNS.fusion_sequence_fasta_id] = 'a'
        trans_ev.data[COLUMNS.fusion_sequence_fasta_id] = 'b'
        self.assertTrue(equivalent_events(genome_ev, trans_ev, self.TRANSCRIPTS, product_sequences=product_sequences))

    def test_mixed_protocol_fusions_same_sequence_diff_translation(self):
        product_sequences = {'a': 'AATG', 'b': 'AATG'}
        genome_ev = BreakpointPair(
            Breakpoint('1', 1),
            Breakpoint('1', 10),
            opposing_strands=True,
            data={
                COLUMNS.event_type: SVTYPE.DEL,
                COLUMNS.call_method: CALL_METHOD.CONTIG,
                COLUMNS.fusion_sequence_fasta_id: 'a',
                COLUMNS.protocol: PROTOCOL.GENOME,
                COLUMNS.transcript1: None,
                COLUMNS.transcript2: None,
                COLUMNS.fusion_cdna_coding_start: 1,
                COLUMNS.fusion_cdna_coding_end: 10
            }
        )
        trans_ev = BreakpointPair(
            Breakpoint('1', 50),
            Breakpoint('1', 60),
            opposing_strands=True,
            data={
                COLUMNS.event_type: SVTYPE.DEL,
                COLUMNS.call_method: CALL_METHOD.CONTIG,
                COLUMNS.fusion_sequence_fasta_id: 'b',
                COLUMNS.protocol: PROTOCOL.TRANS,
                COLUMNS.transcript1: None,
                COLUMNS.transcript2: None,
                COLUMNS.fusion_cdna_coding_start: 1,
                COLUMNS.fusion_cdna_coding_end: 50
            }
        )
        self.assertFalse(equivalent_events(genome_ev, trans_ev, self.TRANSCRIPTS, product_sequences=product_sequences))

    def test_mixed_protocol_fusions_different_sequence(self):
        product_sequences = {'a': 'AATT', 'b': 'AATG'}
        genome_ev = BreakpointPair(
            Breakpoint('1', 1),
            Breakpoint('1', 10),
            opposing_strands=True,
            data={
                COLUMNS.event_type: SVTYPE.DEL,
                COLUMNS.call_method: CALL_METHOD.CONTIG,
                COLUMNS.fusion_sequence_fasta_id: 'a',
                COLUMNS.protocol: PROTOCOL.GENOME,
                COLUMNS.transcript1: None,
                COLUMNS.transcript2: None,
                COLUMNS.fusion_cdna_coding_start: 1,
                COLUMNS.fusion_cdna_coding_end: 10
            }
        )
        trans_ev = BreakpointPair(
            Breakpoint('1', 50),
            Breakpoint('1', 60),
            opposing_strands=True,
            data={
                COLUMNS.event_type: SVTYPE.DEL,
                COLUMNS.call_method: CALL_METHOD.CONTIG,
                COLUMNS.fusion_sequence_fasta_id: 'b',
                COLUMNS.protocol: PROTOCOL.TRANS,
                COLUMNS.transcript1: None,
                COLUMNS.transcript2: None,
                COLUMNS.fusion_cdna_coding_start: 1,
                COLUMNS.fusion_cdna_coding_end: 10
            }
        )
        self.assertFalse(equivalent_events(genome_ev, trans_ev, self.TRANSCRIPTS, product_sequences=product_sequences))

    def test_mixed_protocol_one_predicted_one_match(self):
        genome_ev = BreakpointPair(
            Breakpoint('1', 350, orient=ORIENT.LEFT),
            Breakpoint('1', 400, orient=ORIENT.RIGHT),
            opposing_strands=False,
            data={
                COLUMNS.event_type: SVTYPE.DEL,
                COLUMNS.call_method: CALL_METHOD.CONTIG,
                COLUMNS.fusion_sequence_fasta_id: None,
                COLUMNS.protocol: PROTOCOL.GENOME,
                COLUMNS.transcript1: self.ust1.name,
                COLUMNS.transcript2: None
            }
        )
        trans_ev = BreakpointPair(
            Breakpoint('1', 350, orient=ORIENT.LEFT),
            Breakpoint('1', 400, orient=ORIENT.RIGHT),
            opposing_strands=False,
            data={
                COLUMNS.event_type: SVTYPE.DEL,
                COLUMNS.call_method: CALL_METHOD.CONTIG,
                COLUMNS.fusion_sequence_fasta_id: None,
                COLUMNS.protocol: PROTOCOL.TRANS,
                COLUMNS.transcript1: self.ust1.name,
                COLUMNS.transcript2: None
            }
        )
        self.assertTrue(equivalent_events(genome_ev, trans_ev, self.TRANSCRIPTS))
        self.assertTrue(equivalent_events(trans_ev, genome_ev, self.TRANSCRIPTS))

        genome_ev.data[COLUMNS.transcript2] = self.ust1.name
        genome_ev.data[COLUMNS.transcript1] = None
        trans_ev.data[COLUMNS.transcript2] = self.ust1.name
        trans_ev.data[COLUMNS.transcript1] = None
        self.assertTrue(equivalent_events(genome_ev, trans_ev, self.TRANSCRIPTS))
        self.assertTrue(equivalent_events(trans_ev, genome_ev, self.TRANSCRIPTS))

    def test_mixed_protocol_one_predicted_one_mismatch(self):
        genome_ev = BreakpointPair(
            Breakpoint('1', 350, orient=ORIENT.LEFT),
            Breakpoint('1', 400, orient=ORIENT.RIGHT),
            opposing_strands=False,
            data={
                COLUMNS.event_type: SVTYPE.DEL,
                COLUMNS.call_method: CALL_METHOD.CONTIG,
                COLUMNS.fusion_sequence_fasta_id: None,
                COLUMNS.protocol: PROTOCOL.GENOME,
                COLUMNS.transcript1: self.ust1.name,
                COLUMNS.transcript2: None
            }
        )
        trans_ev = BreakpointPair(
            Breakpoint('1', 350, orient=ORIENT.LEFT),
            Breakpoint('1', 400, orient=ORIENT.RIGHT),
            opposing_strands=False,
            data={
                COLUMNS.event_type: SVTYPE.DEL,
                COLUMNS.call_method: CALL_METHOD.CONTIG,
                COLUMNS.fusion_sequence_fasta_id: None,
                COLUMNS.protocol: PROTOCOL.TRANS,
                COLUMNS.transcript1: self.ust1.name,
                COLUMNS.transcript2: None
            }
        )
        self.assertTrue(equivalent_events(genome_ev, trans_ev, self.TRANSCRIPTS))
        self.assertTrue(equivalent_events(trans_ev, genome_ev, self.TRANSCRIPTS))

        genome_ev.data[COLUMNS.transcript2] = self.ust1.name
        genome_ev.data[COLUMNS.transcript1] = None
        trans_ev.data[COLUMNS.transcript2] = self.ust1.name
        trans_ev.data[COLUMNS.transcript1] = None
        self.assertTrue(equivalent_events(genome_ev, trans_ev, self.TRANSCRIPTS))
        self.assertTrue(equivalent_events(trans_ev, genome_ev, self.TRANSCRIPTS))

    def test_mixed_protocol_both_predicted(self):

        raise unittest.SkipTest('TODO')

    def test_mixed_protocol_neither_predicted_one_match(self):
        raise unittest.SkipTest('TODO')

    def test_mixed_protocol_neither_predicted_no_match(self):
        raise unittest.SkipTest('TODO')

    def test_mixed_protocol_neither_predicted_both_match(self):
        raise unittest.SkipTest('TODO')

    def test_transcriptome_protocol(self):
        raise unittest.SkipTest('TODO')


class TestBreakpointPrediction(unittest.TestCase):

    def setUp(self):
        self.ust = UsTranscript([(101, 200), (301, 400), (501, 600)], strand=STRAND.POS)
        self.n_ust = UsTranscript([(101, 200), (301, 400), (501, 600)], strand=STRAND.NEG)

    def test_exonic_five_prime(self):
        b = Breakpoint('1', 350, orient=ORIENT.LEFT)
        breaks = predict_transcriptome_breakpoint(b, self.ust)
        self.assertEqual(2, len(breaks))
        self.assertEqual(200, breaks[0].start)
        self.assertEqual(b, breaks[1])

    def test_exonic_five_prime_first_exon(self):
        b = Breakpoint('1', 150, orient=ORIENT.LEFT)
        breaks = predict_transcriptome_breakpoint(b, self.ust)
        self.assertEqual(1, len(breaks))
        self.assertEqual(b, breaks[0])

    def test_exonic_three_prime(self):
        b = Breakpoint('1', 350, orient=ORIENT.RIGHT)
        breaks = predict_transcriptome_breakpoint(b, self.ust)
        self.assertEqual(2, len(breaks))
        self.assertEqual(501, breaks[1].start)
        self.assertEqual(b, breaks[0])

    def test_exonic_three_prime_last_exon(self):
        b = Breakpoint('1', 550, orient=ORIENT.RIGHT)
        breaks = predict_transcriptome_breakpoint(b, self.ust)
        self.assertEqual(1, len(breaks))
        self.assertEqual(b, breaks[0])

    def test_intronic_five_prime(self):
        b = Breakpoint('1', 450, orient=ORIENT.LEFT)
        breaks = predict_transcriptome_breakpoint(b, self.ust)
        self.assertEqual(1, len(breaks))
        self.assertEqual(400, breaks[0].start)

    def test_intronic_three_prime(self):
        b = Breakpoint('1', 250, orient=ORIENT.RIGHT)
        breaks = predict_transcriptome_breakpoint(b, self.ust)
        self.assertEqual(1, len(breaks))
        self.assertEqual(301, breaks[0].start)

    def test_outside_transcript(self):
        b = Breakpoint('1', 100, orient=ORIENT.RIGHT)
        with self.assertRaises(AssertionError):
            predict_transcriptome_breakpoint(b, self.ust)

    # for neg transcripts
    def test_exonic_three_prime_neg(self):
        b = Breakpoint('1', 350, orient=ORIENT.LEFT, strand=STRAND.NEG)
        breaks = predict_transcriptome_breakpoint(b, self.n_ust)
        self.assertEqual(2, len(breaks))
        self.assertEqual(200, breaks[0].start)
        self.assertEqual(b, breaks[1])

    def test_intronic_three_prime_neg(self):
        b = Breakpoint('1', 450, orient=ORIENT.LEFT, strand=STRAND.NEG)
        breaks = predict_transcriptome_breakpoint(b, self.n_ust)
        self.assertEqual(1, len(breaks))
        self.assertEqual(400, breaks[0].start)

    def test_exonic_five_prime_neg_first_exon(self):
        b = Breakpoint('1', 150, orient=ORIENT.LEFT)
        breaks = predict_transcriptome_breakpoint(b, self.n_ust)
        self.assertEqual(1, len(breaks))
        self.assertEqual(b, breaks[0])

    def test_exonic_three_prime_neg_first_exon(self):
        b = Breakpoint('1', 150, orient=ORIENT.LEFT)
        breaks = predict_transcriptome_breakpoint(b, self.n_ust)
        self.assertEqual(1, len(breaks))
        self.assertEqual(b, breaks[0])

    def test_exonic_five_prime_neg(self):
        b = Breakpoint('1', 350, orient=ORIENT.RIGHT)
        breaks = predict_transcriptome_breakpoint(b, self.n_ust)
        self.assertEqual(2, len(breaks))
        self.assertEqual(501, breaks[1].start)
        self.assertEqual(b, breaks[0])

    def test_exonic_five_prime_neg_last_exon(self):
        b = Breakpoint('1', 550, orient=ORIENT.RIGHT)
        breaks = predict_transcriptome_breakpoint(b, self.n_ust)
        self.assertEqual(1, len(breaks))
        self.assertEqual(b, breaks[0])

    def test_intronic_five_prime_neg(self):
        b = Breakpoint('1', 250, orient=ORIENT.RIGHT)
        breaks = predict_transcriptome_breakpoint(b, self.n_ust)
        self.assertEqual(1, len(breaks))
        self.assertEqual(301, breaks[0].start)
