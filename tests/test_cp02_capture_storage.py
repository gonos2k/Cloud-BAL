import ast
from pathlib import Path


CAPTURE_SCRIPT = (
    Path(__file__).parents[1]
    / "docs/evidence/cp02_inner_capture_20261028/capture_inner.py"
)


class FakeType:
    def __init__(self, name, code, size, fields=()):
        self.name = name
        self.code = code
        self.sizeof = size
        self._fields = list(fields)

    def pointer(self):
        return self

    def fields(self):
        return self._fields

    def __str__(self):
        return self.name


class FakeField:
    def __init__(self, name):
        self.name = name


class FakeValue:
    def __init__(self, address, value_type):
        self.address = address
        self.type = value_type
        self.members = {}

    def cast(self, _pointer_type):
        return self

    def dereference(self):
        return self

    def __getitem__(self, name):
        return self.members[name]


class FakeInferior:
    def __init__(self, values, memory):
        self.values = values
        self.memory = memory

    def read_memory(self, address, size):
        if address not in self.memory or len(self.memory[address]) < size:
            raise RuntimeError("unreadable address")
        return self.memory[address][:size]


class FakeGdb:
    TYPE_CODE_INT = 1
    TYPE_CODE_FLT = 2
    TYPE_CODE_BOOL = 3
    TYPE_CODE_ENUM = 4

    def __init__(self, values, memory):
        self.inferior = FakeInferior(values, memory)

    def Value(self, address):
        try:
            return self.inferior.values[address]
        except KeyError as exc:
            raise RuntimeError("unreadable address") from exc

    def selected_inferior(self):
        return self.inferior


def capture_helpers(gdb_stub):
    module = ast.parse(CAPTURE_SCRIPT.read_text(encoding="utf-8"))
    wanted = {"scalar_record", "immediate_scalar_members", "read_storage"}
    functions = [node for node in module.body
                 if isinstance(node, ast.FunctionDef) and node.name in wanted]
    assert {node.name for node in functions} == wanted
    namespace = {"gdb": gdb_stub}
    exec(compile(ast.Module(body=functions, type_ignores=[]), str(CAPTURE_SCRIPT), "exec"), namespace)
    return namespace


def test_read_storage_reads_integer_four_raw_bytes():
    integer = FakeType("INTEGER*4", FakeGdb.TYPE_CODE_INT, 4)
    value = FakeValue(0x1000, integer)
    helpers = capture_helpers(FakeGdb({0x1000: value}, {0x1000: bytes.fromhex("14000000")}))

    result = helpers["read_storage"](0x1000, integer, "returned_budget")

    assert result == {
        "status": "readable",
        "type": "INTEGER*4",
        "address": "0x1000",
        "raw_bytes_le_hex": "14000000",
    }


def test_read_storage_reads_real_eight_scalar():
    real = FakeType("REAL*8", FakeGdb.TYPE_CODE_FLT, 8)
    value = FakeValue(0x2000, real)
    helpers = capture_helpers(FakeGdb({0x2000: value}, {0x2000: bytes.fromhex("000000000000f43f")}))

    result = helpers["read_storage"](0x2000, real, "returned_real")

    assert result == {
        "status": "readable",
        "type": "REAL*8",
        "address": "0x2000",
        "raw_bytes_le_hex": "000000000000f43f",
    }


def test_read_storage_keeps_structured_budget_members():
    integer = FakeType("INTEGER*4", FakeGdb.TYPE_CODE_INT, 4)
    real = FakeType("REAL*8", FakeGdb.TYPE_CODE_FLT, 8)
    budget_type = FakeType("budget_type", 99, 16, (FakeField("count"), FakeField("total")))
    budget = FakeValue(0x3000, budget_type)
    count = FakeValue(0x3004, integer)
    total = FakeValue(0x3008, real)
    budget.members = {"count": count, "total": total}
    memory = {
        0x3004: bytes.fromhex("2a000000"),
        0x3008: bytes.fromhex("000000000000f03f"),
    }
    helpers = capture_helpers(FakeGdb({0x3000: budget}, memory))

    result = helpers["read_storage"](0x3000, budget_type, "returned_budget")

    assert result["status"] == "readable"
    assert result["fields"] == {
        "count": {"status": "readable", "type": "INTEGER*4", "address": "0x3004", "raw_bytes_le_hex": "2a000000"},
        "total": {"status": "readable", "type": "REAL*8", "address": "0x3008", "raw_bytes_le_hex": "000000000000f03f"},
    }


def test_read_storage_reports_unreadable_address():
    integer = FakeType("INTEGER*4", FakeGdb.TYPE_CODE_INT, 4)
    helpers = capture_helpers(FakeGdb({}, {}))

    result = helpers["read_storage"](0xBAD0, integer, "returned_budget")

    assert result["status"] == "unreadable"
    assert result["address"] == "0xbad0"
    assert result["type"] == "INTEGER*4"
    assert "unreadable address" in result["reason"]
