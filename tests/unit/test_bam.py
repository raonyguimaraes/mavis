import unittest
from mavis.bam.read import convert_events_to_softclipping
from mavis.bam.cigar import merge_indels, merge_internal_events, QUERY_ALIGNED_STATES
from mavis.constants import CIGAR, ORIENT
from .mock import Mock


class TestConvertEventsToSoftclipping(unittest.TestCase):
    
    def test_left_large_deletion(self):
        read = Mock(cigar=[(CIGAR.EQ, 10), (CIGAR.D, 10), (CIGAR.EQ, 40)], query_sequence='A' * 50)
        converted = convert_events_to_softclipping(read, ORIENT.LEFT, 5, 5)
        self.assertEqual([(CIGAR.EQ, 10), (CIGAR.S, 40)], converted.cigar)
    
    def test_left_anchor_after_event(self):
        read = Mock(
            cigar=[(CIGAR.EQ, 4), (CIGAR.D, 10), (CIGAR.EQ, 40), (CIGAR.D, 10), (CIGAR.EQ, 6)], query_sequence='A' * 50)
        converted = convert_events_to_softclipping(read, ORIENT.LEFT, 5, 5)
        self.assertEqual([(CIGAR.EQ, 4), (CIGAR.D, 10), (CIGAR.EQ, 40), (CIGAR.S, 6)], converted.cigar)

    def test_left_all_mismatch_error(self):
        read = Mock(cigar=[(CIGAR.X, 10), (CIGAR.D, 10), (CIGAR.X, 40)], query_sequence='A' * 50)
        converted = convert_events_to_softclipping(read, ORIENT.LEFT, 5, 5)
        self.assertEqual(read, converted)

    def test_left_combined_small_events(self):
        read = Mock(cigar=[(CIGAR.EQ, 10), (CIGAR.D, 6), (CIGAR.I, 5), (CIGAR.EQ, 35)], query_sequence='A' * 50)
        converted = convert_events_to_softclipping(read, ORIENT.LEFT, 10, 10)
        self.assertEqual([(CIGAR.EQ, 10), (CIGAR.S, 40)], converted.cigar)

    def test_right_large_deletion(self):
        read = Mock(cigar=[(CIGAR.EQ, 10), (CIGAR.D, 10), (CIGAR.EQ, 40)], query_sequence='A' * 50, reference_start=100)
        converted = convert_events_to_softclipping(read, ORIENT.RIGHT, 5, 5)
        self.assertEqual([(CIGAR.S, 10), (CIGAR.EQ, 40)], converted.cigar)
        self.assertEqual(read.reference_start + 20, converted.reference_start)

    def test_right_anchor_after_event(self):
        read = Mock(
            cigar=[(CIGAR.EQ, 6), (CIGAR.D, 10), (CIGAR.EQ, 40), (CIGAR.D, 10), (CIGAR.EQ, 4)],
            query_sequence='A' * 50, reference_start=100)
        converted = convert_events_to_softclipping(read, ORIENT.RIGHT, 5, 5)
        self.assertEqual([(CIGAR.S, 6), (CIGAR.EQ, 40), (CIGAR.D, 10), (CIGAR.EQ, 4)], converted.cigar)
        self.assertEqual(read.reference_start + 16, converted.reference_start)

    def test_complex_alignment(self):
        cigar = [
            (CIGAR.M, 137), (CIGAR.D, 14823), (CIGAR.M, 19), (CIGAR.D, 1), (CIGAR.M, 5), (CIGAR.I, 18), (CIGAR.D, 18),
            (CIGAR.M, 16), (CIGAR.I, 1), (CIGAR.D, 120), (CIGAR.M, 22), (CIGAR.S, 147)]
        read = Mock(cigar=cigar, query_sequence='A' * 365, reference_start=88217410)
        
        with self.assertRaises(NotImplementedError):
            convert_events_to_softclipping(read, ORIENT.LEFT, 50, 50)
        
        read.cigar = [(CIGAR.EQ if x == CIGAR.M else x, y) for x, y in read.cigar]
        converted = convert_events_to_softclipping(read, ORIENT.LEFT, 50, 50)
        self.assertEqual([(CIGAR.EQ, 137), (CIGAR.S, 365 - 137)], converted.cigar)
        
        converted = convert_events_to_softclipping(read, ORIENT.RIGHT, 50, 100)
        self.assertEqual(read.cigar, converted.cigar)

    def test_multiple_events(self):
        cigar = [
            (CIGAR.EQ, 18), (CIGAR.X, 1), (CIGAR.EQ, 30), (CIGAR.D, 8146), (CIGAR.EQ, 10), 
            (CIGAR.D, 62799), (CIGAR.EQ, 28), (CIGAR.D, 2), (CIGAR.EQ, 27), (CIGAR.S, 77)
        ]
        l = sum([v for c, v in cigar if c in QUERY_ALIGNED_STATES])
        read = Mock(cigar=cigar, query_sequence=('N' * l), reference_start=1000)
        converted = convert_events_to_softclipping(read, ORIENT.RIGHT, 50, 50)
        exp = [(CIGAR.S, 59), (CIGAR.EQ, 28), (CIGAR.D, 2), (CIGAR.EQ, 27), (CIGAR.S, 77)]
        self.assertEqual(exp, converted.cigar)

    def test_multiple_left_with_ins(self):
        cigar = [
            (4, 94), (7, 1), (8, 1), (7, 10), (8, 1), (7, 4), (1, 2), (7, 40),
            (1, 1), (2, 714), (7, 7), (1, 38), (7, 1), (8, 1), 
            (7, 17), (2, 1), (7, 1), (8, 1), (7, 26), (2, 17), (7, 10), (4, 4)
        ]
        exp = [
            (4, 94), (7, 1), (8, 1), (7, 10), (8, 1), (7, 4), (1, 2), (7, 40),
            (4, 38 + 8 + 20 + 1 + 26 + 10 + 4)
        ]
        l = sum([v for c, v in cigar if c in QUERY_ALIGNED_STATES])
        read = Mock(cigar=cigar, query_sequence=('N' * l), reference_start=1000)
        converted = convert_events_to_softclipping(read, ORIENT.LEFT, 50, 50)
        self.assertEqual(exp, converted.cigar)


class TestMergeIndels(unittest.TestCase):
    
    def test_no_events(self):
        c = [(CIGAR.EQ, 1)]
        self.assertEqual(c, merge_indels(c))

        c = [(CIGAR.EQ, 1), (CIGAR.X, 3), (CIGAR.EQ, 10)]
        self.assertEqual(c, merge_indels(c))

    def test_del_before_ins(self):
        c = [(CIGAR.EQ, 1), (CIGAR.D, 1), (CIGAR.I, 2), (CIGAR.EQ, 2)]
        exp = [(CIGAR.EQ, 1), (CIGAR.I, 2), (CIGAR.D, 1), (CIGAR.EQ, 2)]
        self.assertEqual(exp, merge_indels(c))

    def test_ins_before_del(self):
        exp = [(CIGAR.EQ, 1), (CIGAR.I, 2), (CIGAR.D, 1), (CIGAR.EQ, 2)]
        self.assertEqual(exp, merge_indels(exp))

    def test_mixed(self):
        c = [(CIGAR.EQ, 1), (CIGAR.I, 2), (CIGAR.D, 1), (CIGAR.I, 2), (CIGAR.D, 1), (CIGAR.EQ, 2)]
        exp = [(CIGAR.EQ, 1), (CIGAR.I, 4), (CIGAR.D, 2), (CIGAR.EQ, 2)]
        self.assertEqual(exp, merge_indels(c))


class TestMergeInternalEvents(unittest.TestCase):

    def test_mismatch_and_deletion(self):
        c = [(CIGAR.EQ, 10), (CIGAR.X, 2), (CIGAR.EQ, 5), (CIGAR.D, 2), (CIGAR.EQ, 10)]
        exp = [(CIGAR.EQ, 10), (CIGAR.I, 7), (CIGAR.D, 9), (CIGAR.EQ, 10)]

        self.assertEqual(c, merge_internal_events(c, 5))
        self.assertEqual(exp, merge_internal_events(c, 6))

    def test_mismatch_and_insertion(self):
        c = [(CIGAR.EQ, 10), (CIGAR.X, 2), (CIGAR.EQ, 5), (CIGAR.I, 2), (CIGAR.EQ, 10)]
        exp = [(CIGAR.EQ, 10), (CIGAR.I, 9), (CIGAR.D, 7), (CIGAR.EQ, 10)]

        self.assertEqual(c, merge_internal_events(c, 5))
        self.assertEqual(exp, merge_internal_events(c, 6))

    def test_insertions(self):
        c = [(CIGAR.EQ, 10), (CIGAR.I, 2), (CIGAR.EQ, 5), (CIGAR.I, 2), (CIGAR.EQ, 10)]
        exp = [(CIGAR.EQ, 10), (CIGAR.I, 9), (CIGAR.D, 5), (CIGAR.EQ, 10)]

        self.assertEqual(c, merge_internal_events(c, 5))
        self.assertEqual(exp, merge_internal_events(c, 6))

    def test_deletions(self):
        c = [(CIGAR.EQ, 10), (CIGAR.D, 2), (CIGAR.EQ, 5), (CIGAR.D, 2), (CIGAR.EQ, 10)]
        exp = [(CIGAR.EQ, 10), (CIGAR.I, 5), (CIGAR.D, 9), (CIGAR.EQ, 10)]

        self.assertEqual(c, merge_internal_events(c, 5))
        self.assertEqual(exp, merge_internal_events(c, 6))

    def test_insertion_and_deletion(self):
        c = [(CIGAR.EQ, 10), (CIGAR.I, 2), (CIGAR.EQ, 5), (CIGAR.D, 2), (CIGAR.EQ, 10)]
        exp = [(CIGAR.EQ, 10), (CIGAR.I, 7), (CIGAR.D, 7), (CIGAR.EQ, 10)]

        self.assertEqual(c, merge_internal_events(c, 5))
        self.assertEqual(exp, merge_internal_events(c, 6))
    
    def test_no_internal_events(self):
        c = [(CIGAR.EQ, 10), (CIGAR.EQ, 10)]
        exp = [(CIGAR.EQ, 20)]

        self.assertEqual(exp, merge_internal_events(c, 10))

        c = [(CIGAR.X, 10), (CIGAR.EQ, 10)]

        self.assertEqual(c, merge_internal_events(c, 10))

    def test_single_internal_event(self):
        c = [(CIGAR.EQ, 10), (CIGAR.X, 5), (CIGAR.EQ, 10)]

        self.assertEqual(c, merge_internal_events(c, 10))

    def test_long_suffix_and_prefix(self):
        c = [
            (CIGAR.S, 94), (CIGAR.EQ, 1), (CIGAR.X, 1), (CIGAR.EQ, 10), (CIGAR.X, 1), (CIGAR.EQ, 4), (CIGAR.I, 2),
            (CIGAR.EQ, 40), 
            (CIGAR.I, 1), (CIGAR.D, 714), (CIGAR.EQ, 7), (CIGAR.I, 38), (CIGAR.EQ, 1), (CIGAR.X, 1),
            (CIGAR.EQ, 17), (CIGAR.D, 1), (CIGAR.EQ, 1), (CIGAR.X, 1), 
            (CIGAR.EQ, 26), (CIGAR.D, 17), (CIGAR.EQ, 10), (CIGAR.S, 4)
        ] 
        exp = [
            (CIGAR.S, 94), (CIGAR.EQ, 1), (CIGAR.X, 1), (CIGAR.EQ, 10), (CIGAR.X, 1), (CIGAR.EQ, 4), (CIGAR.I, 2),
            (CIGAR.EQ, 40), 
            (CIGAR.I, 1 + 7 + 38 + 1 + 1 + 17 + 1 + 1), (CIGAR.D, 714 + 7 + 1 + 1 + 17 + 1 + 1 + 1),
            (CIGAR.EQ, 26), (CIGAR.D, 17), (CIGAR.EQ, 10), (CIGAR.S, 4)
        ] 
        actual = merge_internal_events(c, 20, 15)
        print(c)
        print(actual)
        self.assertEqual(exp, actual)
