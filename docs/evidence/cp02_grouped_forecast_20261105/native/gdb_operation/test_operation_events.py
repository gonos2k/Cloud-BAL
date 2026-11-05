"""Focused regression checks for GDB event JSON encoding and lane words."""
import json
import unittest

from operation_events import encode_event, same_phi_operands, vector_lane_word


class OperationEventTests(unittest.TestCase):
    def test_lane_word_is_hex_and_json_safe(self):
        vector = '000000003f8000000000803f000080bf'
        word = vector_lane_word(vector, 2)
        self.assertEqual(word, '0000803f')
        self.assertEqual(json.loads(encode_event({'al_candidate_word': word})),
                         {'al_candidate_word': word})

    def test_all_probe_event_shapes_encode(self):
        events = [
            {'event': 'target_phi_entry', 'addresses': {'ph': '0x1000'},
             'input_words': {'ph': '0000803f'}, 'bounds': {'ids': 1}},
            {'event': 'target_vector_entry', 'vector_registers_at_entry': {'xmm0': '00' * 16},
             'operand_slot_mapping': {'ph': 0}, 'lane': 0},
            {'event': 'instruction', 'instruction': 'store_before',
             'instruction_bytes': '430f110cb4', 'xmm1': '00' * 16,
             'al_candidate_vector': '00' * 16, 'al_candidate_word': '0000803f'},
            {'event': 'instruction', 'instruction': 'store_after',
             'stored_al_word': '0000803f', 'al_store_target_address': '0x1000'},
        ]
        for event in events:
            with self.subTest(event=event['event'], instruction=event.get('instruction')):
                self.assertEqual(json.loads(encode_event(event)), event)

    def test_raw_bytes_fail_closed(self):
        with self.assertRaises(TypeError):
            encode_event({'al_candidate_word': bytes.fromhex('0000803f')})

    def test_phi_bridge_ignores_alb_metadata_and_matches_four_terms(self):
        phi = {'phi_call_ordinal': 1, 'input_words': {
            'ph': '00000000', 'ph_next': '3f800000', 'phb': '40000000',
            'phb_next': '40400000', 'al': '00000000', 'alb': '00000000'}}
        vector = {'phi_call_ordinal': 1, 'input_words': {
            'ph': '00000000', 'ph_next': '3f800000', 'phb': '40000000', 'phb_next': '40400000'}}
        self.assertTrue(same_phi_operands(phi, vector))
        vector['input_words']['phb'] = '40800000'
        self.assertFalse(same_phi_operands(phi, vector))
        vector['input_words']['phb'] = '40000000'
        vector['phi_call_ordinal'] = 2
        self.assertFalse(same_phi_operands(phi, vector))


if __name__ == '__main__':
    unittest.main()
