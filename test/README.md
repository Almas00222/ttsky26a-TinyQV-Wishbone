# TinyQV Wishbone RTL Tests

This folder contains the tapeout-focused verification flow for `tt_um_TSARKA_TinyQV`, adapted from Michael Bell's `ttsky25b` TinyQV regression style and expanded for the `ttsky26a` Wishbone GPIO/UART integration.

## Test Structure

```
test/
├── golden_models/           # Behavioral reference models
│   ├── wishbone_model.py   # Wishbone B4 protocol model
│   ├── uart_model.py       # UART 16550 behavioral model
│   ├── gpio_model.py       # Efabless EF_GPIO8 model
│   └── wb_bridge_model.py  # TinyQV Wishbone bridge model
├── firmware/                # Checked-in firmware hex images used by CI/sim
├── gen_firmware.py          # Regenerates the checked-in firmware images
├── gate_level_tools.py      # Finds/stages sky130 gate netlists and PDK assets
├── sim_qspi_soc.v           # Behavioral QSPI flash/RAM model
├── test_common.py           # Shared cocotb reset/QSPI/UART helpers
├── test_rtl.py              # Fast DUT-facing RTL smoke and pin-contract checks
├── test_comprehensive.py    # Manual-QSPI randomized/core/peripheral tests
├── test_firmware.py         # Firmware-backed QSPI boot/system tests
├── test_gatelevel.py        # Gate-level top-level and firmware-backed checks
├── test_golden_models.py    # Unit tests for golden models
├── tb.v                     # Verilog testbench wrapper
└── Makefile                 # Build and test targets
```

## Test Summary

| Test Suite | Description |
|------------|-------------|
| `test-golden` | Pure Python/unit/vector checks for the reference models |
| `test-rtl` | Fast DUT-facing smoke, reset, mux, and pin-contract checks |
| `test-comprehensive` | Manual-QSPI core/peripheral/randomized integration tests plus firmware-backed regressions |
| `test-gatelevel-smoke` | Quick gate-level reset, chip-select, and combo-boot checks |
| `test-gatelevel` | Full gate-level firmware-backed regression |

## What Is Tested

### Fast RTL Smoke (`test_rtl.py`)
- Reset ownership and QSPI tri-state checks
- Reset release to fetch-start checks
- QSPI chip-select exclusivity
- Manual instruction injection sanity checks
- UART mirroring on `uo[0]`
- Debug selector truth-table coverage for `uo[1]`
- Firmware-backed GPIO/UART combo boot smoke

### Comprehensive DUT Tests (`test_comprehensive.py`)
- Randomized ALU regression in the spirit of Michael Bell's `test_random_alu`
- Core register load/store coverage
- Memory/peripheral interleave coverage
- Direct UART register access checks
- Timer interrupt and external IRQ `mcause` entry checks

### Firmware/System Tests (`test_firmware.py`)
- `gpio_write`
- `gpio_readback`
- `gpio_uart_combo`
- `uart_hello`
- `uart_prime`
- `uart_loopback`
- `timer_demo`
- `irq_demo`

### Gate-Level Regression (`test_gatelevel.py`)
- Reset ownership and QSPI tri-state checks using only top-level observables
- QSPI chip-select exclusivity checks
- GPIO/debug mux sanity while preserving UART on `uo[0]`
- Firmware-backed gate-level checks for ALU, RAM, UART scratch, GPIO, UART hello/prime, loopback, timer, and IRQ demos

### Golden Model Unit Tests (`test_golden_models.py`)
- 39 unit tests validating golden model correctness
- Can run without RTL simulation
- Tests all behavioral models independently

## Golden Models

### Wishbone Model (`wishbone_model.py`)
- `WishboneMaster`: Protocol-compliant master interface
- `WishboneSlave`: Memory-backed slave with byte enables
- `WishboneMonitor`: Passive bus monitor
- `WishboneScoreboard`: Expected vs actual comparison

### UART Model (`uart_model.py`)
- `UART16550Model`: Full 16550-compatible model
  - FIFO support (16-deep)
  - Interrupt generation
  - All registers (RBR, THR, IER, IIR, FCR, LCR, MCR, LSR, MSR, SCR)
  - Baud rate divisor calculation
- `UARTBitBangModel`: Serial waveform encoder/decoder

### GPIO Model (`gpio_model.py`)
- `GPIO8Model`: Efabless EF_GPIO8 behavioral model
  - 8-bit input/output with direction control
  - 2-stage input synchronizer
  - 32-bit interrupt status (hi/lo/pe/ne per pin)
  - Interrupt masking and clearing
- `GPIOScoreboard`: Model vs RTL comparison
- `GPIOCoverageCollector`: Functional coverage

### Wishbone Bridge Model (`wb_bridge_model.py`)
- `TinyQVWishboneBridgeModel`: CPU to Wishbone translation
  - Byte select generation
  - Write data steering
  - Timeout mechanism
  - ACK handling
- Pre-computed test vectors for verification

## Running Tests

### Prerequisites
```sh
cd test
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Run RTL Tests
```sh
make test-rtl
```

### Run Firmware-Backed Boot Tests
```sh
make test-firmware
```

### Run Golden Model Unit Tests (No RTL)
```sh
make test-golden
```

### Regenerate Firmware Images
```sh
make firmware
```

### Run 10-Seed Confidence Sweeps
```sh
make test-rtl-seeds
make test-comprehensive-seeds
make test-firmware-seeds
make test-gatelevel-smoke-seeds
```

### Build Or Stage A Gate-Level Netlist
```sh
make synth-gate-netlist
make stage-gate-netlist
```

### Run Gate-Level Verification
```sh
make test-gatelevel-smoke
make test-gatelevel
```

### Run All Tests
```sh
make test-all
```

### View Available Targets
```sh
make help
```

### Clean All Artifacts
```sh
make clean-all
```

## Test Results

- `results.xml`: JUnit-format test results (for CI)
- `sim_build/`: Simulation build artifacts
- `sim_build/tb.fst`: FST waveform for debugging

## Memory Map

| Address Range     | Peripheral | Notes |
|------------------|------------|-------|
| `0x00000000-0x00FFFFFF` | Flash/RAM | QSPI memory |
| `0x01000000-0x017FFFFF` | RAM A | QSPI PSRAM |
| `0x01800000-0x01FFFFFF` | RAM B | QSPI PSRAM |
| `0x03000000-0x0300FFFF` | GPIO | EF_GPIO8 |
| `0x04000000-0x0400FFFF` | UART | UART16550 |

## Register Maps

### GPIO (EF_GPIO8)
| Offset | Name | Description |
|--------|------|-------------|
| 0x0000 | DATAI | Input data (read-only) |
| 0x0004 | DATAO | Output data |
| 0x0008 | DIR | Direction (1=output) |
| 0xFF00 | IM | Interrupt mask |
| 0xFF04 | MIS | Masked interrupt status |
| 0xFF08 | RIS | Raw interrupt status |
| 0xFF0C | IC | Interrupt clear |

### UART (16550)
| Offset | Name (DLAB=0) | Name (DLAB=1) |
|--------|---------------|---------------|
| 0x00 | RBR/THR | DLL |
| 0x04 | IER | DLM |
| 0x08 | IIR/FCR | - |
| 0x0C | LCR | - |
| 0x10 | MCR | - |
| 0x14 | LSR | - |
| 0x18 | MSR | - |
| 0x1C | SCR | - |

## Adding New Tests

1. Put pure model/unit tests in `test_golden_models.py`
2. Put fast top-level DUT checks in `test_rtl.py`
3. Put manual-QSPI randomized/core tests in `test_comprehensive.py`
4. Put bootable firmware scenarios in `test_firmware.py`
5. Put top-level observable gate-level checks in `test_gatelevel.py`
6. Keep all shared reset/QSPI/UART helpers in `test_common.py`
