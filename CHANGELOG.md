# What's new

## Flowchart to ST

### v1.2 (October 2026)
- **ELSIF option**: tick "ELSIF" in the Body panel to write ELSE + IF as ELSIF, with a single END_IF (handy for IF / ELSE IF cascades).
- **OVF tag**: when an integer goes out of its type range, it wraps around as on a real PLC, and an orange OVF tag now appears next to the variable in the Watch (cleared by Reset).
- **Base 16 / base 2**: hover an integer value in the Watch to see it in decimal, hexadecimal and binary, updated live.

### v1.1 (October 2026)
- Trace: timing diagrams of up to 8 variables (inputs and outputs of function blocks included), trigger on a rising or falling edge, cursor, zoom, export PDF / image / CSV.
- Types guessed from conditions and comparisons (BOOL, REAL, TIME).
- Copy / paste of blocks in the flowchart fixed.
- Works offline, on computer and phone; no external resources.

### v1.0 (October 2026)
- First version: structured flowchart → IEC 61131-3 Structured Text, PLC-like simulation (cyclic or periodic task, watchdog), Watch, PDF export.
