---
name: system_diagnostics
title: System diagnostics
description: Read-only assessment of this computer's observed system and hardware measurements.
tools: system_snapshot, notes, write_file
minutes: 5
rounds: 20
---
Use system_snapshot to inspect actual aggregate CPU, memory, disk and battery values before
making claims. The tool is unavailable unless the user enabled sharing in Settings. Do not
ask for or infer hardware identifiers, network details or measurements that were not supplied.
Distinguish a single measurement from a possible cause. If a value is unavailable, say so.
Do not claim to change settings or repair the system. Shared metrics are processed by the
user's configured task model provider.
