import cocotb
from cocotb.triggers import ClockCycles

from test_common import (
    _int_value,
    reset_dut,
    start_clock,
    wait_for_boot_activity,
    wait_for_gpio_state,
)


@cocotb.test()
async def test_gl_reset_and_uart_idle(dut):
    await start_clock(dut)
    await reset_dut(dut, latency=1, use_qspi_model=True)
    await ClockCycles(dut.clk, 10)

    assert _int_value(dut.uart_tx, "uart_tx") == 1
    assert _int_value(dut.qspi_flash_select, "qspi_flash_select") in (0, 1)


@cocotb.test()
async def test_gl_uio_oe_reset_ownership(dut):
    await start_clock(dut)

    dut.use_qspi_model.value = 1
    dut.ena.value = 1
    dut.ui_in_base.value = 0x80
    dut.uio_in_base.value = 0
    dut.latency_cfg.value = 1
    dut.rst_n.value = 0

    await ClockCycles(dut.clk, 5)
    assert _int_value(dut.uio_oe, "uio_oe") == 0

    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 5)
    assert _int_value(dut.uio_oe, "uio_oe") != 0


@cocotb.test()
async def test_gl_top_level_mux_and_uart_mirror(dut):
    await start_clock(dut)
    await reset_dut(dut, latency=1, use_qspi_model=True)
    await ClockCycles(dut.clk, 10)

    gpio_mode_uart = _int_value(dut.uo_out, "uo_out") & 0x1
    dut.ui_in_base.value = _int_value(dut.ui_in_base, "ui_in_base") | 0x1
    await ClockCycles(dut.clk, 2)
    debug_mode_uart = _int_value(dut.uo_out, "uo_out") & 0x1
    assert gpio_mode_uart == debug_mode_uart == _int_value(dut.uart_tx, "uart_tx")


@cocotb.test()
async def test_gl_qspi_chip_select_exclusive(dut):
    await start_clock(dut)
    await reset_dut(dut, latency=1, use_qspi_model=True)

    for _ in range(200):
        cs_low = (
            (1 - _int_value(dut.qspi_flash_select, "qspi_flash_select"))
            + (1 - _int_value(dut.qspi_ram_a_select, "qspi_ram_a_select"))
            + (1 - _int_value(dut.qspi_ram_b_select, "qspi_ram_b_select"))
        )
        assert cs_low <= 1
        await ClockCycles(dut.clk, 1)


@cocotb.test()
async def test_gl_firmware_boot_reaches_gpio_signature(dut):
    await start_clock(dut)
    await reset_dut(dut, latency=1, use_qspi_model=True)
    await wait_for_boot_activity(dut)
    await wait_for_gpio_state(dut, 0xBE, 0xFF, timeout_cycles=12000)


@cocotb.test()
async def test_gl_firmware_gpio_stability(dut):
    await start_clock(dut)
    await reset_dut(dut, latency=1, use_qspi_model=True)
    await wait_for_boot_activity(dut)
    await wait_for_gpio_state(dut, 0xBE, 0xFF, timeout_cycles=12000)

    for _ in range(200):
        await ClockCycles(dut.clk, 1)
        assert _int_value(dut.uo_out, "uo_out") & 0xFE == 0xBE & 0xFE
