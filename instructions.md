# Comprehensive Failure Handoff

## Objective

Close the `test-comprehensive` credibility gap before treating the design as tapeout-ready.

Do not broaden coverage first. The immediate goal is to make the existing comprehensive suite green and trustworthy.

## Current Local Status

- `make test-golden`: `39/39` pass.
- `make test-rtl`: `22/22` pass.
- `make test-comprehensive`: `20 tests, 8 pass, 12 fail`.
- `make lint-iverilog`: not green; real warnings remain, including implicit wires in `src/Peripherals/UART16550/uart_regs.v`.
- `make lint-verilator`: not green.
- `make formal-qspi` and `make formal-wb-bridge`: targets launch, but full proof completion has not been confirmed.
- `make test-gatelevel-smoke`: not runnable locally without `test/gate_level_netlist.v`.

Important: the latest local `make test-comprehensive` run printed `TESTS=20 PASS=8 FAIL=12`, but the outer `make` still exited with code `0`. Treat that as a verification infrastructure bug and inspect `test/Makefile` target wiring while debugging.

Important nuance on the apparently green basic RTL suite:

- `make test-rtl` is green, but several tests are weak observational checks rather than hard functional gates
- example from a fresh local run:
  - `test_random_gpio_values` logged `1/10 verified` and still passed
  - `test_gpio_all_patterns` logged `0/24 verified` and still passed
- do not treat the basic suite alone as strong evidence that the GPIO/peripheral data path is healthy

## What Was Already Changed

### Verification plumbing

- Added root-level targets in `Makefile` for:
  - `test-golden`
  - `test-rtl`
  - `test-comprehensive`
  - `test-gatelevel-smoke`
  - `lint-iverilog`
  - `lint-verilator`
  - `formal-qspi`
  - `formal-wb-bridge`
- Updated `test/Makefile` to expose `test-comprehensive` and `test-gatelevel-smoke`.
- Added CI signoff workflow in `.github/workflows/signoff.yaml`.
- Added formal manifests under `formal/`.
- Added gate-level smoke scaffold in `test/test_gatelevel_smoke.py`.
- Added signoff/bring-up docs under `docs/`.

### Comprehensive testbench changes

The shared helpers in `test/test_comprehensive.py` were already adjusted to move failures away from an early generic QSPI timeout and toward more specific functional misses:

- Added `flash_stream_needs_sync`.
- Changed flash-side `start_read` behavior to mark a resync boundary instead of greedily consuming the full flash address/dummy phase.
- Reworked `send_instr` to synchronize to actual sample edges and optionally consume a dummy nibble on a fresh flash stream.
- Added `wait_for_gpio_state`.
- Switched several GPIO tests from fixed delay/NOP assumptions to `wait_for_gpio_state`.

These changes improved observability, but the suite is still failing.

## Current Failing Tests

Important nuance: the currently passing comprehensive tests are mostly model-only or reset/timer checks. They do not yet prove that the CPU-to-QSPI-to-peripheral execution path is healthy. Treat the comprehensive pass count accordingly; the current suite is not demonstrating successful end-to-end peripheral traffic yet.

### Passing

- `test_wb_bridge_byte_select_8bit`
- `test_wb_bridge_byte_select_16bit`
- `test_wb_bridge_byte_select_32bit`
- `test_wb_bridge_data_steering`
- `test_wb_bridge_timeout`
- `test_uart_divisor_setting`
- `test_reset_state`
- `test_time_pulse_cadence`

### Failing

- `test_gpio_output_with_golden_model`
- `test_gpio_random_values`
- `test_gpio_direction_random`
- `test_uart_tx_random_bytes`
- `test_uart_rx_random_bytes`
- `test_uart_scratch_register`
- `test_cpu_register_load_store`
- `test_cpu_alu_addi`
- `test_memory_peripheral_interleave`
- `test_rapid_gpio_writes`
- `test_random_register_sequence`
- `test_gpio_full_output_range`

## First Concrete Blocker

The first failing case is `test_gpio_output_with_golden_model`.

Observed failure:

- expected: `gpio_out=0x00`, `gpio_oe=0xFF`
- got: `gpio_out=0x00`, `gpio_oe=0x00`

Interpretation:

- The GPIO direction write path is not taking effect in the comprehensive path.
- This is more specific than the earlier generic flash timeout and should be treated as the current primary blocker.

## Other Failure Signatures

- Several GPIO-focused tests fail waiting for `gpio_oe` and/or `gpio_out` to settle.
- Several UART-path tests fail inside `send_instr` with `Timed out waiting for flash fetch`.
- Several CPU/register/RAM tests fail with `Timed out waiting for RAM load`.
- The failures likely cluster into:
  - one early store/decode path problem affecting GPIO direction writes
  - one instruction-stream or RAM-side handshake problem that later manifests as flash-fetch and RAM-load timeouts

Do not assume these are separate RTL bugs until the first GPIO-direction failure is understood.

## Recommended Debug Order

1. Reproduce only the first failing test:
   - `MODULE=test_comprehensive TESTCASE=test_gpio_output_with_golden_model make -C test sim`
2. Instrument the first GPIO direction write in `test/test_comprehensive.py`:
   - confirm the intended instruction stream
   - confirm the expected register load/store sequence
   - confirm whether the write reaches the Wishbone/GPIO decode
3. Compare the helper flow in `test/test_comprehensive.py` against the working flow in `test/test_rtl.py`, especially:
   - `send_instr`
   - `load_reg`
   - `read_reg`
   - flash/QSPI helper sequencing
4. Inspect whether the first failing GPIO test is blocked by:
   - bad flash instruction delivery
   - bad RAM preload/load helper behavior
   - missing or mistimed peripheral decode/ack
5. Only after the first GPIO-direction failure is understood, revisit the later:
   - `Timed out waiting for flash fetch`
   - `Timed out waiting for RAM load`
6. Separately, fix the test target exit-code propagation so a red comprehensive run cannot exit cleanly.

## Specific Files To Inspect Next

- `test/test_comprehensive.py`
- `test/test_rtl.py`
- `test/Makefile`
- `src/project.v`
- `src/TinyQV/tinyqv.v`
- `src/TinyQV/qspi_ctrl.v`
- `src/TinyQV/mem_ctrl.v`
- `src/TinyQV/wb_bridge.v`
- `src/Peripherals/GPIO/EF_GPIO8_WB.v`
- `src/Peripherals/GPIO/adapter_wb.v`

## Working Hypothesis

Most likely this is still testbench sequencing or helper-model mismatch first, not a proven silicon RTL bug yet.

Reason:

- the helper changes already altered the failure mode substantially
- the first hard failure is a missing GPIO direction effect, not an immediate global bring-up collapse
- the later flash-fetch and RAM-load timeouts may be downstream consequences of the same sequencing problem

That said, do not rule out RTL until the first failing GPIO transaction is traced end-to-end.

## About Adding `sim_qspi_pmod`

Adding a Verilog `sim_qspi_pmod` model is a good idea, but use it as a second verification mode, not as a replacement for the current comprehensive path.

Recommended use:

- add it as an optional, explicit testbench path for top-level smoke, decode checks, and later gate-level-style integration
- use it to validate QSPI chip-select exclusivity, flash vs RAM A/B decode, simple read/write behavior, and top-level muxing with less Python-side bit driving
- keep the current Python-driven `test/test_comprehensive.py` flow for now while triaging the first failing GPIO-direction write

Reason:

- the current blocker may still be in the Python helper sequencing (`send_instr`, `load_reg`, `read_reg`, `start_read`)
- swapping the comprehensive suite over to a Verilog QSPI responder too early could hide a bench-side bug instead of exposing it
- if added, the model should be a separate verification entrypoint so both approaches can cross-check each other

## Deliverable Expected From The Next Agent

Return with:

- whether the first GPIO-direction failure is bench-side or RTL-side
- the exact signal/transaction point where the expected write is lost
- whether the later flash-fetch and RAM-load timeouts are the same root cause or a second issue
- any required code change to make `test-comprehensive` fail the shell/CI job when tests fail
