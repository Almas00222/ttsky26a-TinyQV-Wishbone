import random

import cocotb
from cocotb.triggers import ClockCycles
from riscvmodel.insn import InstructionADDI

from test_common import (
    _int_value,
    capture_uart_byte,
    debug_signal_value,
    encode_lui,
    encode_nop,
    reset_dut,
    send_instr,
    start_clock,
    start_read,
    wait_for_boot_activity,
    wait_for_fetch_start,
    wait_for_gpio_state,
)


@cocotb.test()
async def test_reset_tristate_and_chip_selects(dut):
    await start_clock(dut)

    dut.use_qspi_model.value = 0
    dut.manual_qspi_data_in.value = 0
    dut.ena.value = 1
    dut.ui_in_base.value = 0x80
    dut.uio_in_base.value = 0
    dut.latency_cfg.value = 1
    dut.rst_n.value = 0

    await ClockCycles(dut.clk, 8)

    assert _int_value(dut.uio_oe, "uio_oe") == 0
    assert _int_value(dut.qspi_flash_select, "qspi_flash_select") == 1
    assert _int_value(dut.qspi_ram_a_select, "qspi_ram_a_select") == 1
    assert _int_value(dut.qspi_ram_b_select, "qspi_ram_b_select") == 1


@cocotb.test()
async def test_reset_release_starts_flash_fetch(dut):
    await start_clock(dut)
    await reset_dut(dut, latency=1, use_qspi_model=False)
    assert await wait_for_fetch_start(dut, timeout_cycles=200)


@cocotb.test()
async def test_manual_qspi_instruction_smoke(dut):
    await start_clock(dut)
    await reset_dut(dut, latency=1, use_qspi_model=False)
    assert await wait_for_fetch_start(dut, timeout_cycles=200)
    await start_read(dut, 0)

    for instr in [
        encode_nop(),
        encode_lui(1, 0x12345),
        InstructionADDI(2, 1, 0x67).encode(),
        encode_nop(),
    ]:
        await send_instr(dut, instr)

    for _ in range(200):
        await ClockCycles(dut.clk, 1)
        if _int_value(dut.user_project.cpu_debug_instr_complete, "cpu_debug_instr_complete"):
            return
    raise AssertionError("CPU never completed an instruction after manual flash injection")


@cocotb.test()
async def test_qspi_chip_select_exclusive(dut):
    await start_clock(dut)
    await reset_dut(dut, latency=1, use_qspi_model=False)

    for _ in range(400):
        cs_low = (
            (1 - _int_value(dut.qspi_flash_select, "qspi_flash_select"))
            + (1 - _int_value(dut.qspi_ram_a_select, "qspi_ram_a_select"))
            + (1 - _int_value(dut.qspi_ram_b_select, "qspi_ram_b_select"))
        )
        assert cs_low <= 1
        await ClockCycles(dut.clk, 1)


@cocotb.test()
async def test_uart_tx_is_always_mirrored_on_uo0(dut):
    await start_clock(dut)
    await reset_dut(dut, latency=1, use_qspi_model=False)

    for mode in (0, 1):
        current = _int_value(dut.ui_in_base, "ui_in_base") & ~0x1
        dut.ui_in_base.value = current | mode
        await ClockCycles(dut.clk, 2)
        assert (_int_value(dut.uo_out, "uo_out") & 0x1) == _int_value(dut.uart_tx, "uart_tx")


@cocotb.test()
async def test_debug_selector_routes_selected_probe_to_uo1(dut):
    await start_clock(dut)
    await reset_dut(dut, latency=1, use_qspi_model=False)

    for sel in range(16):
        dut.ui_in_base.value = 0x80 | 0x01 | (sel << 1)
        await ClockCycles(dut.clk, 2)
        observed = (_int_value(dut.uo_out, "uo_out") >> 1) & 1
        expected = debug_signal_value(dut, sel)
        assert observed == expected, f"selector {sel} mismatch: expected {expected}, got {observed}"


@cocotb.test()
async def test_firmware_combo_boots_gpio_and_uart(dut):
    await start_clock(dut)
    await reset_dut(dut, latency=1, use_qspi_model=True)
    await wait_for_boot_activity(dut)
    await wait_for_gpio_state(dut, 0xBE, 0xFF)
    assert await capture_uart_byte(dut) == 0x55


@cocotb.test()
async def test_gpio_and_debug_views_are_consistent(dut):
    await start_clock(dut)
    await reset_dut(dut, latency=1, use_qspi_model=True)
    await wait_for_boot_activity(dut)
    await wait_for_gpio_state(dut, 0xBE, 0xFF)

    dut.ui_in_base.value = 0x80
    await ClockCycles(dut.clk, 2)
    gpio_mode = _int_value(dut.uo_out, "uo_out")
    assert (gpio_mode & 0x1) == _int_value(dut.uart_tx, "uart_tx")
    assert ((gpio_mode >> 1) & 0x7F) == ((_int_value(dut.user_project.gpio_out, "gpio_out") >> 1) & 0x7F)

    sel = random.randint(0, 15)
    dut.ui_in_base.value = 0x80 | 0x01 | (sel << 1)
    await ClockCycles(dut.clk, 2)
    debug_mode = _int_value(dut.uo_out, "uo_out")
    assert (debug_mode & 0x1) == _int_value(dut.uart_tx, "uart_tx")
    assert ((debug_mode >> 1) & 0x1) == debug_signal_value(dut, sel)


@cocotb.test()
async def test_random_reset_recovery_is_strict(dut):
    await start_clock(dut)

    for latency in [1, 2, 3, 1, 3]:
        await reset_dut(dut, latency=latency, use_qspi_model=False)
        assert await wait_for_fetch_start(dut, timeout_cycles=200), f"fetch did not restart for latency={latency}"
