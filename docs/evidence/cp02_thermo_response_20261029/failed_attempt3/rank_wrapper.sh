#!/bin/bash
set -euo pipefail
exec /usr/bin/gdb --batch -x "$CP02_CAPTURE_SCRIPT" "$CP02_BINARY" > "$CP02_CAPTURE_DIR/gdb_rank${PMI_RANK}.txt" 2>&1
