# What's new

## Flowchart to ST

### v1.2 (October 2026)
- **ELSIF option**: tick "ELSIF" in the Body panel to write ELSE + IF as ELSIF, with a single END_IF (handy for IF / ELSE IF cascades).
- **OVF tag**: when an integer goes out of its type range, it wraps around as on a real PLC; when a REAL or LREAL goes beyond its range, it becomes +INF or -INF (IEEE 754) instead of stopping the simulation. In both cases an orange OVF tag appears next to the variable in the Watch (cleared by Reset).
- **Base 16 / base 2**: hover an integer value in the Watch to see it in decimal, hexadecimal and binary, updated live.
- **IEEE 754**: hover a REAL or LREAL value to see how it is stored: value → IEEE 754 code (hexadecimal, sign, exponent, mantissa) → value read back, digit by digit (0.1 comes back as 0.100000001490116119384765625).
- **Stricter checks**: a badly written duration (T#1s5, '1sXYZ') is now refused with a clear message instead of being guessed; a damaged or hand-edited project file is fully checked before loading, and the current project is kept if it is invalid.
- **True REAL precision**: REAL is now computed in 32 bits like on a real PLC (about 7 significant digits: 16777216.0 + 1.0 stays 16777216.0); LREAL stays 64 bits.

### v1.1 (October 2026)
- Trace: timing diagrams of up to 8 variables (inputs and outputs of function blocks included), trigger on a rising or falling edge, cursor, zoom, export PDF / image / CSV.
- Types guessed from conditions and comparisons (BOOL, REAL, TIME).
- Copy / paste of blocks in the flowchart fixed.
- Works offline, on computer and phone; no external resources.

### v1.0 (October 2026)
- First version: structured flowchart → IEC 61131-3 Structured Text, PLC-like simulation (cyclic or periodic task, watchdog), Watch, PDF export.
