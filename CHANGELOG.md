# What's new

## Fluid Power

### v0.7.0 beta (November 2026)
- First public version, in beta: draw pneumatic or hydraulic circuits with ISO 1219 symbols and watch them run. One technology per project (New asks which).
- Pneumatics: supply, service units (filter, regulator, lubricator), 2/2 to 5/3 valves with the controls of your choice, flow and check valves, OR / AND, cylinders (single and double acting, through rod, tandem, rodless, rod lock), gripper, air motor, vacuum (venturi, pump, cup), gauges, flowmeter, pressure switch, sensors.
- Hydraulics: power unit or pump with motor, fixed or variable pump, relief, reducing, sequence and counterbalance valves, 2/2, 3/2, 4/2 and 4/3 valves (four centres), throttle, one-way and compensated flow control, check and piloted check valves, accumulator, return filter with bypass, cylinders, hydraulic motor.
- Simulation: pressures in colour (bar g, relative to the atmosphere), flows in the pipes, cylinders that move with their load, mounting and friction, limit valves and magnetic sensors, buttons held or locked, coils and manual overrides.
- Oil heating: the losses of the throttled oil heat one tank (20 l by default, natural cooling by its walls); thermal time can be sped up to see it in seconds.
- Curves: displacement-step diagram, pressures and speeds, "pressure and speed" view of a cylinder, cursors, CSV and PNG; save a run and reopen it later.
- 27 examples: P01 to P12 (pneumatics, including a cascade and an industrial forming machine), H01 to H13 (hydraulics, including a goods lift).
- Automatic ISO 1219-2 tags (1A1, 1V1, 1s1, 1YV1-a…), checks while you draw (open ports, missing relief valve…), PDF export (A4 or A3) with the parts list and their settings, PNG and SVG images.
- Save / open projects (JSON, checked and repaired when opened); your work in progress comes back at your next visit. Works offline, on computer and phone (double-tap replaces right-click on a touch screen); no external resources.
- The physics is simplified on purpose: right direction and order of magnitude, not a sizing calculation.

## SysML Starter

### v0.7.1 beta (October 2026)
- First public version, in beta: describe a machine by answering simple questions (9-step guide) and the six SysML v1 diagrams build themselves: requirements (req), block definition (bdd), internal blocks (ibd), use cases (uc), state machine (stm, with a Simulate mode) and sequence (sd).
- One model for all diagrams: renaming or deleting a part, an actor, a state or a message updates every diagram.
- Click any element of a diagram to get its explanation and settings; checks point out what is missing (they check the form, not the technical correctness).
- Five examples, from simple to complete (night light, electric toothbrush, USB power bank, capsule coffee machine, PET bottle recycler), to load at once or to watch being built step by step.
- Choose the diagrams your project needs: unticked diagrams leave the guide, the checks and the PDF, nothing is deleted.
- Export: copy image, PNG, A3 PDF file (large diagrams are split into parts); save / open projects (JSON, checked and repaired when opened).
- French and English; made for a computer or a tablet (768 px and more); works offline, no external resources.

## Grafcet to ST

### v1.0 (October 2026)
- First version: draw several grafcets (IEC 60848) in one project, with steps, transitions, AND / OR divergences and convergences, and links you can move.
- Receptivities in class notation: `.` AND, `+` OR, `/` NOT (drawn as an overline), `↑` `↓` edges, `[C>3]` comparisons, `3s/X12` timers (and `t1/X/t2`); `1` is drawn underlined.
- Actions: continuous, conditional, stored on activation / deactivation / event, each with an optional comment.
- Forcing orders G{steps}, G{*}, G{ }, G{INIT}, in a double frame, with the forcing hierarchy shown as levels.
- Macro-steps: each expansion opens in its own window, with an entry step E and an exit step S; in simulation the macro-step symbol lights its top, middle or bottom band.
- Checks while you draw: errors and warnings, including parallel branches that are not synchronised again.
- PLC-like simulation: RUN, PAUSE, scan by scan, activity times, transitions fired by hand, inputs held or toggled, events log.
- Structured Text with the cf / X method (firing conditions, then steps, then timers, then stored and continuous actions), checked scan by scan against the simulation.
- Save / load projects (JSON, fully checked before loading), PDF export with contents, variables, grafcets and ST code.
- Works offline, on computer and phone; no external resources.
- Fix (14 October): on a phone, the exported PDF no longer gets ".json" added to its name.
- The tool now opens on an empty project (one grafcet G1 with an initial step 0); the examples stay in the Examples list.
- Your work in progress is kept in this browser and comes back at your next visit (a tab closed by mistake); New starts again. Nothing leaves your computer; use Save to keep a project.
- Cleaner drawing: return links under the same AND bar no longer overlap, go around steps, and leave on the side where the transition stands; a dragged element snaps onto the axis of the element linked to it.
- New example "Ressource commune": one shared step used by two AND convergences.

## Flowchart to ST

### v1.2 (October 2026)
- **Trace timing** (update): memory variables are now dated when their block runs inside the scan (scan start + 0.25 ms input reading + 0.05 ms per block), not at the start of the scan. Zoomed in, the trace shows each scan's grey I (reading inputs) and O (writing outputs) bands, and in a periodic task the waiting time until the next tick.
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
