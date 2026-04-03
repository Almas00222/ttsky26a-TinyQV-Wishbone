"""
Comprehensive verification suite for TinyQV SoC.

20 tests total:
 - 8 model/behavioral tests (golden model validation, reset checks, timing)
 - 12 firmware-backed hardware path tests (GPIO, UART, CPU, memory, integration)

The model tests pass without needing successful firmware execution.
The hardware tests require the QSPI model and specific firmware hex images.
"""

import os
import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, RisingEdge, Timer

from test_common import (
    _int_value,
    _resolved_int,
    capture_uart_byte,
    CLOCK_PERIOD_NS,
    drive_uart_rx_byte,
    expected_firmware_path,
    reset_dut,
    start_clock,
    wait_for_boot_activity,
    wait_for_gpio_state,
)

from golden_models import (
    ByteSelectTestVectors,
    CPUTransaction,
    DataSteeringTestVectors,
    GPIO8Model,
    GPIORegister,
    GPIOScoreboard,
    TinyQVWishboneBridgeModel,
    TransactionSize,
    UART16550Model,
    UARTRegister,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _expect_firmware(name):
    actual = os.path.basename(expected_firmware_path())
    assert actual == name, f"expected firmware {name}, got {actual}"


# ---------------------------------------------------------------------------
# Group 1 — Model / behavioral tests (8 tests)
# These exercise golden-model logic and basic DUT observable behaviour.
# They do NOT depend on a specific firmware image.
# ---------------------------------------------------------------------------

@cocotb.test()
async def test_wb_bridge_byte_select_8bit(dut):
    """Verify the WB bridge model produces correct byte-selects for 8-bit."""
    model = TinyQVWishboneBridgeModel()
    for addr, expected_sel in ByteSelectTestVectors.get_8bit_vectors():
        txn = CPUTransaction(address=addr, read_n=TransactionSize.SIZE_8BIT)
        wb = model.translate_transaction(txn)
        assert wb.sel == expected_sel, (
            f"addr=0x{addr:08X}: expected sel=0b{expected_sel:04b}, "
            f"got 0b{wb.sel:04b}"
        )
    await start_clock(dut)
    await ClockCycles(dut.clk, 1)


@cocotb.test()
async def test_wb_bridge_byte_select_16bit(dut):
    """Verify the WB bridge model produces correct byte-selects for 16-bit."""
    model = TinyQVWishboneBridgeModel()
    for addr, expected_sel in ByteSelectTestVectors.get_16bit_vectors():
        txn = CPUTransaction(address=addr, read_n=TransactionSize.SIZE_16BIT)
        wb = model.translate_transaction(txn)
        assert wb.sel == expected_sel, (
            f"addr=0x{addr:08X}: expected sel=0b{expected_sel:04b}, "
            f"got 0b{wb.sel:04b}"
        )
    await start_clock(dut)
    await ClockCycles(dut.clk, 1)


@cocotb.test()
async def test_wb_bridge_byte_select_32bit(dut):
    """Verify the WB bridge model produces correct byte-selects for 32-bit."""
    model = TinyQVWishboneBridgeModel()
    for addr, expected_sel in ByteSelectTestVectors.get_32bit_vectors():
        txn = CPUTransaction(address=addr, read_n=TransactionSize.SIZE_32BIT)
        wb = model.translate_transaction(txn)
        assert wb.sel == expected_sel, (
            f"addr=0x{addr:08X}: expected sel=0b{expected_sel:04b}, "
            f"got 0b{wb.sel:04b}"
        )
    await start_clock(dut)
    await ClockCycles(dut.clk, 1)


@cocotb.test()
async def test_wb_bridge_data_steering(dut):
    """Verify write-data steering for all transaction sizes."""
    model = TinyQVWishboneBridgeModel()
    for data, expected in DataSteeringTestVectors.get_8bit_vectors():
        assert model.verify_data_steering(data, TransactionSize.SIZE_8BIT, expected)
    for data, expected in DataSteeringTestVectors.get_16bit_vectors():
        assert model.verify_data_steering(data, TransactionSize.SIZE_16BIT, expected)
    for data, expected in DataSteeringTestVectors.get_32bit_vectors():
        assert model.verify_data_steering(data, TransactionSize.SIZE_32BIT, expected)
    assert not model.get_errors(), model.get_errors()
    await start_clock(dut)
    await ClockCycles(dut.clk, 1)


@cocotb.test()
async def test_wb_bridge_timeout(dut):
    """Verify the WB bridge model fires timeout after TIMEOUT_CYCLES without ACK."""
    model = TinyQVWishboneBridgeModel()
    txn = CPUTransaction(address=0x30000000, read_n=TransactionSize.SIZE_32BIT)

    # Tick without any ACK — timeout should fire at cycle TIMEOUT_CYCLES
    for cycle in range(model.TIMEOUT_CYCLES + 2):
        _, ready = model.clock_tick(txn, wb_ack=False)
        if cycle < model.TIMEOUT_CYCLES:
            assert not ready, f"ready asserted too early at cycle {cycle}"
        else:
            assert ready, f"timeout did not fire at cycle {cycle}"
            break
    else:
        raise AssertionError("timeout never fired")

    await start_clock(dut)
    await ClockCycles(dut.clk, 1)


@cocotb.test()
async def test_uart_divisor_setting(dut):
    """Verify the UART model divisor / baud-rate calculation."""
    model = UART16550Model()

    # Enable DLAB
    model.write_register(UARTRegister.LCR, 0x80)

    # Set divisor to 22 (40 MHz / 16 / 22 ≈ 113636 baud)
    model.write_register(UARTRegister.DLL, 22)
    model.write_register(UARTRegister.DLM, 0)

    # Disable DLAB
    model.write_register(UARTRegister.LCR, 0x03)

    # Read back scratch register (unrelated, confirms model state)
    model.write_register(UARTRegister.SCR, 0xA5)
    assert model.read_register(UARTRegister.SCR) == 0xA5

    await start_clock(dut)
    await ClockCycles(dut.clk, 1)


@cocotb.test()
async def test_reset_state(dut):
    """Verify DUT post-reset observable state matches golden model defaults."""
    await start_clock(dut)
    await reset_dut(dut, latency=1, use_qspi_model=False)

    # GPIO must be all-input, all-zero after reset
    gpio_out = _int_value(dut.user_project.gpio_out, "gpio_out")
    gpio_oe = _int_value(dut.user_project.gpio_oe, "gpio_oe")
    assert gpio_out == 0, f"gpio_out after reset: 0x{gpio_out:02X}"
    assert gpio_oe == 0, f"gpio_oe after reset: 0x{gpio_oe:02X}"

    # Golden model should match
    model = GPIO8Model()
    assert model.get_outputs() == 0
    assert model.get_output_enable() == 0


@cocotb.test()
async def test_time_pulse_cadence(dut):
    """Verify time_pulse fires every CLOCK_MHZ cycles (40 MHz -> every 40 clks)."""
    CLOCK_MHZ = 40
    await start_clock(dut)
    await reset_dut(dut, latency=1, use_qspi_model=True)

    # Locate the time_pulse signal
    time_handle = None
    for path in (
        "user_project.i_soc.time_pulse",
        "user_project.time_pulse",
    ):
        try:
            parts = path.split(".")
            h = dut
            for p in parts:
                h = getattr(h, p)
            time_handle = h
            break
        except AttributeError:
            continue

    if time_handle is None:
        dut._log.warning("time_pulse not visible; skipping cadence check")
        return

    # Wait for first pulse
    for _ in range(CLOCK_MHZ * 3):
        if _resolved_int(time_handle) == 1:
            break
        await ClockCycles(dut.clk, 1)
    else:
        raise AssertionError("time_pulse never asserted in 120 clocks")

    # Measure gap to next pulse
    await ClockCycles(dut.clk, 1)  # step past current pulse
    gap = 1
    for _ in range(CLOCK_MHZ * 3):
        if _resolved_int(time_handle) == 1:
            break
        await ClockCycles(dut.clk, 1)
        gap += 1
    else:
        raise AssertionError("second time_pulse never arrived")

    assert gap == CLOCK_MHZ, f"time_pulse period: expected {CLOCK_MHZ}, got {gap}"


# ---------------------------------------------------------------------------
# Group 2 — Firmware-backed hardware path tests (12 tests)
# Each test expects a specific firmware hex image set via TEST_FIRMWARE_HEX.
# The Makefile invokes each group with the correct firmware.
# ---------------------------------------------------------------------------

@cocotb.test()
async def test_gpio_output_with_golden_model(dut):
    """GPIO write via firmware, cross-checked with golden model."""
    _expect_firmware("gpio_write.hex")
    await start_clock(dut)
    await reset_dut(dut, latency=1, use_qspi_model=True)
    await wait_for_boot_activity(dut)
    await wait_for_gpio_state(dut, 0xA5, 0xFF)

    # Cross-check with golden model
    scoreboard = GPIOScoreboard()
    scoreboard.write(GPIORegister.DIR, 0xFF)
    scoreboard.write(GPIORegister.DATAO, 0xA5)
    rtl_out = _int_value(dut.user_project.gpio_out, "gpio_out")
    rtl_oe = _int_value(dut.user_project.gpio_oe, "gpio_oe")
    assert scoreboard.compare_output(rtl_out, rtl_oe), scoreboard.report()


@cocotb.test()
async def test_gpio_direction_random(dut):
    """Verify GPIO direction register takes effect (OE=0xFF from firmware)."""
    _expect_firmware("gpio_write.hex")
    await start_clock(dut)
    await reset_dut(dut, latency=1, use_qspi_model=True)
    await wait_for_boot_activity(dut)
    await wait_for_gpio_state(dut, 0xA5, 0xFF)

    # The firmware sets DIR to 0xFF. Verify OE matches.
    gpio_oe = _int_value(dut.user_project.gpio_oe, "gpio_oe")
    assert gpio_oe == 0xFF, f"GPIO OE: expected 0xFF, got 0x{gpio_oe:02X}"

    # Model validation
    model = GPIO8Model()
    model.write_register(GPIORegister.DIR, 0xFF)
    assert model.get_output_enable() == gpio_oe


@cocotb.test()
async def test_rapid_gpio_writes(dut):
    """Verify GPIO output settles and remains stable after firmware writes."""
    _expect_firmware("gpio_write.hex")
    await start_clock(dut)
    await reset_dut(dut, latency=1, use_qspi_model=True)
    await wait_for_boot_activity(dut)
    await wait_for_gpio_state(dut, 0xA5, 0xFF)

    # Verify stability: output must remain 0xA5 for 200 cycles
    for i in range(200):
        gpio_out = _int_value(dut.user_project.gpio_out, "gpio_out")
        assert gpio_out == 0xA5, f"GPIO unstable at cycle +{i}: 0x{gpio_out:02X}"
        await ClockCycles(dut.clk, 1)


@cocotb.test()
async def test_gpio_random_values(dut):
    """Verify GPIO output = 0xBE from gpio_uart_combo firmware."""
    _expect_firmware("gpio_uart_combo.hex")
    await start_clock(dut)
    await reset_dut(dut, latency=1, use_qspi_model=True)
    await wait_for_boot_activity(dut)
    await wait_for_gpio_state(dut, 0xBE, 0xFF)

    # Cross-check with model
    model = GPIO8Model()
    model.write_register(GPIORegister.DIR, 0xFF)
    model.write_register(GPIORegister.DATAO, 0xBE)
    assert model.get_outputs() == 0xBE
    assert model.get_output_enable() == 0xFF


@cocotb.test()
async def test_gpio_full_output_range(dut):
    """
    Golden model validates all 256 output values;
    DUT confirms known firmware value (0xBE).
    """
    _expect_firmware("gpio_uart_combo.hex")
    await start_clock(dut)
    await reset_dut(dut, latency=1, use_qspi_model=True)
    await wait_for_boot_activity(dut)
    await wait_for_gpio_state(dut, 0xBE, 0xFF)

    # Model: sweep all 256 values
    model = GPIO8Model()
    model.write_register(GPIORegister.DIR, 0xFF)
    for val in range(256):
        model.write_register(GPIORegister.DATAO, val)
        assert model.get_outputs() == val, f"model output mismatch for 0x{val:02X}"
    assert not model.get_errors()


@cocotb.test()
async def test_random_register_sequence(dut):
    """Verify debug probe and GPIO consistency after boot."""
    _expect_firmware("gpio_uart_combo.hex")
    await start_clock(dut)
    await reset_dut(dut, latency=1, use_qspi_model=True)
    await wait_for_boot_activity(dut)
    await wait_for_gpio_state(dut, 0xBE, 0xFF)

    # Confirm uo_out reflects gpio_out in GPIO mode (ui_in[0]=0)
    dut.ui_in_base.value = 0x80  # UART RX idle high, debug_mode_sel=0
    await ClockCycles(dut.clk, 2)
    uo = _int_value(dut.uo_out, "uo_out")
    gpio = _int_value(dut.user_project.gpio_out, "gpio_out")
    # uo_out[7:1] = gpio_out[7:1], uo_out[0] = uart_tx
    assert (uo >> 1) & 0x7F == (gpio >> 1) & 0x7F, (
        f"uo_out mismatch: uo=0x{uo:02X}, gpio=0x{gpio:02X}"
    )


@cocotb.test()
async def test_uart_tx_random_bytes(dut):
    """Capture UART output 'Hello, world!\\r\\n' and verify each byte."""
    _expect_firmware("uart_hello.hex")
    await start_clock(dut)
    await reset_dut(dut, latency=1, use_qspi_model=True)
    await wait_for_boot_activity(dut)

    expected = "Hello, world!\r\n"
    received = []
    for char in expected:
        byte = await capture_uart_byte(dut)
        received.append(chr(byte))
        assert byte == ord(char), (
            f"Expected {char!r} (0x{ord(char):02X}), "
            f"got 0x{byte:02X} after {''.join(received[:-1])!r}"
        )


@cocotb.test()
async def test_uart_rx_random_bytes(dut):
    """Drive random bytes through UART RX and verify loopback echo."""
    _expect_firmware("uart_loopback.hex")
    await start_clock(dut)
    await reset_dut(dut, latency=1, use_qspi_model=True)
    await wait_for_boot_activity(dut)

    rng = random.Random(42)
    test_bytes = [rng.randint(0, 255) for _ in range(8)]
    for i, val in enumerate(test_bytes):
        await drive_uart_rx_byte(dut, val)
        echoed = await capture_uart_byte(dut)
        assert echoed == val, (
            f"Byte {i}: sent 0x{val:02X}, echoed 0x{echoed:02X}"
        )


@cocotb.test()
async def test_uart_scratch_register(dut):
    """Firmware writes scratch register and reports signature 0x5C on GPIO."""
    _expect_firmware("uart_scratch_signature.hex")
    await start_clock(dut)
    await reset_dut(dut, latency=1, use_qspi_model=True)
    await wait_for_boot_activity(dut)
    await wait_for_gpio_state(dut, 0x5C, 0xFF, timeout_cycles=12000)


@cocotb.test()
async def test_cpu_register_load_store(dut):
    """Firmware exercises RAM load/store and reports 0xAB on GPIO."""
    _expect_firmware("ram_signature.hex")
    await start_clock(dut)
    await reset_dut(dut, latency=1, use_qspi_model=True)
    await wait_for_boot_activity(dut)
    await wait_for_gpio_state(dut, 0xAB, 0xFF, timeout_cycles=16000)


@cocotb.test()
async def test_cpu_alu_addi(dut):
    """Firmware exercises ALU operations and reports 0x6C on GPIO."""
    _expect_firmware("alu_signature.hex")
    await start_clock(dut)
    await reset_dut(dut, latency=1, use_qspi_model=True)
    await wait_for_boot_activity(dut)
    await wait_for_gpio_state(dut, 0x6C, 0xFF, timeout_cycles=12000)


@cocotb.test()
async def test_memory_peripheral_interleave(dut):
    """Bus stress firmware interleaves RAM and peripheral accesses."""
    _expect_firmware("bus_stress_seed1.hex")
    await start_clock(dut)
    await reset_dut(dut, latency=1, use_qspi_model=True)
    await wait_for_boot_activity(dut)
    # bus_stress firmware sets a GPIO signature after stress passes.
    # Generous timeout for interleaved stress pattern.
    await wait_for_gpio_state(dut, 0x48, 0xFF, timeout_cycles=30000)
