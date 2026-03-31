# Lint Waivers

Approved cosmetic waivers:

- Tool: `iverilog -Wall`
  Warning text: inherited `timescale` warnings in the vendored `src/Peripherals/UART16550/*.v` files
  Justification: these OpenCores UART sources intentionally inherit `timescale` through `timescale.v`; the warnings do not indicate width, connectivity, or behavioral issues, and `lint-verilator` is clean on the same sources
  Approval date: 2026-03-31

Only cosmetic warnings may be waived, and every waiver must name the tool, warning text, justification, and approval date.
