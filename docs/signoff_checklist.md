# Tapeout Signoff Checklist

Status date: 2026-03-31

Current blocker:

- Final post-layout gate-level evidence is still pending until the hardened Tiny Tapeout/OpenLane netlist is available and staged with `make stage-gate-netlist`.
- A pre-layout synthesized sky130 gate netlist can already be generated with `make synth-gate-netlist` for early gate-level regression, but the final release should still be rerun against the staged post-layout netlist.
- Full 10-seed signoff sweeps are still pending and must be rerun from the exact release commit before submission.
- Treat any red verification, lint, formal, precheck, DRC, LVS, or timing result as a tapeout blocker until it is either fixed or documented as an explicitly approved cosmetic waiver.

Verification suites:

- `make firmware`
- `make test-golden`
- `make test-rtl`
- `make test-firmware`
- `make test-comprehensive`
- `make synth-gate-netlist`
- `make stage-gate-netlist`
- `make test-gatelevel`
- `make test-gatelevel-smoke`

Random confidence sweep:

- Re-run `test-rtl` with 10 distinct `RANDOM_SEED` values (`make test-rtl-seeds`)
- Re-run `test-comprehensive` with 10 distinct `RANDOM_SEED` values (`make test-comprehensive-seeds`)
- Re-run `test-firmware` with 10 distinct `RANDOM_SEED` values (`make test-firmware-seeds`)
- Re-run `test-gatelevel-smoke` with 10 distinct `RANDOM_SEED` values (`make test-gatelevel-smoke-seeds`)
- Record zero-failure evidence before submission

Static analysis:

- `make lint-iverilog`
- `make lint-verilator`
- `docs/lint_waivers.md` reviewed so only explicitly approved cosmetic waivers remain

Formal:

- `make formal-qspi`
- `make formal-wb-bridge`

Top-level behavior:

- `uio_oe` ownership verified across reset and post-reset
- `uo_out[0]` verified to mirror UART TX in both output modes
- `ui[0]` GPIO/debug mux behavior verified
- `ui[4:1]` debug selector truth-table on `uo[1]` verified
- QSPI chip-select exclusivity verified
- Published pinout in `info.yaml` and `docs/info.md` matches `src/project.v`

Final Tiny Tapeout gates:

- GDS built from the exact submission commit
- Tiny Tapeout precheck green
- Full GL regression green on the staged post-layout netlist
- Timing met at 20 ns
- DRC clean
- LVS clean
- No unresolved antenna or power issues

Release record:

- Attach the reviewed signoff note to the submission commit or PR
- Note the exact commit SHA used for GDS/precheck/GL evidence
