"""JSON-safe scalar-lane and event encoding for the GDB operation probe."""
import json


def vector_lane_word(vector_hex, lane):
    raw = bytes.fromhex(vector_hex)
    if len(raw) != 16 or not 0 <= lane < 4:
        raise ValueError('expected one four-lane REAL32 vector and a valid lane')
    return raw[4 * lane:4 * lane + 4].hex()


def encode_event(event):
    return json.dumps(event, sort_keys=True)


def same_phi_operands(phi_entry, vector_entry):
    names = ('ph', 'ph_next', 'phb', 'phb_next')
    return (phi_entry.get('phi_call_ordinal') == vector_entry.get('phi_call_ordinal') and
            all(phi_entry.get('input_words', {}).get(name) ==
                vector_entry.get('input_words', {}).get(name) for name in names))
