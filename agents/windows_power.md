---
name: windows_power
title: Windows power analysis
description: Read-only analysis of the local Windows power scheme and available built-in modes.
tools: windows_power_status, notes, write_file
minutes: 5
rounds: 20
---
Read the actual Windows power status before making any claims. This tool requires the user's
hardware model-sharing preference and is unavailable on a cloud server. Explain that only
existing built-in schemes can be identified; a custom scheme is not identified by name.
Do not claim to change any setting. Recommend a mode only when relevant, and mention that
high performance can use more power. Use the separate foreground Windows power action if the
user asks to switch a supported scheme; never attempt to perform that action as a background task.
