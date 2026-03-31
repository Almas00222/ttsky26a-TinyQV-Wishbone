import os

import cocotb
from cocotb.triggers import ClockCycles

from test_common import (
    _int_value,
    capture_uart_byte,
    drive_uart_rx_byte,
    expected_firmware_path,
    pulse_external_irq,
    reset_dut,
    start_clock,
    wait_for_uo_out_mask,
    wait_for_uart_idle,
)


def _expect_firmware(name):
    actual = os.path.basename(expected_firmware_path())
    assert actual == name, f"expected firmware {name}, got {actual}"


async def _boot_gatelevel(dut, firmware_name):
    _expect_firmware(firmware_name)
    await start_clock(dut)
    await reset_dut(dut, latency=1, use_qspi_model=True)


async def _wait_for_gpio_view(dut, expected_gpio_out, timeout_cycles):
    dut.ui_in_base.value = _int_value(dut.ui_in_base, "ui_in_base") & ~0x1
    await wait_for_uo_out_mask(dut, expected_gpio_out, 0xFE, timeout_cycles=timeout_cycles)


async def _expect_uart_text(dut, text):
    received = []
    for char in text:
        byte = await capture_uart_byte(dut)
        got = chr(byte)
        received.append(got)
        assert got == char, f"expected {text!r}, got {''.join(received)!r}"


@cocotb.test()
async def test_gl_reset_tristate_and_uart_idle(dut):
    await start_clock(dut)

    dut.use_qspi_model.value = 1
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

    dut.rst_n.value = 1
    await wait_for_uart_idle(dut, cycles=16)
    assert _int_value(dut.uio_oe, "uio_oe") != 0


@cocotb.test()
async def test_gl_qspi_chip_select_exclusive(dut):
    await start_clock(dut)
    await reset_dut(dut, latency=1, use_qspi_model=True)

    for _ in range(400):
        cs_low = (
            (1 - _int_value(dut.qspi_flash_select, "qspi_flash_select"))
            + (1 - _int_value(dut.qspi_ram_a_select, "qspi_ram_a_select"))
            + (1 - _int_value(dut.qspi_ram_b_select, "qspi_ram_b_select"))
        )
        assert cs_low <= 1
        await ClockCycles(dut.clk, 1)


@cocotb.test()
async def test_gl_output_mux_keeps_uart_on_uo0(dut):
    await _boot_gatelevel(dut, "gpio_uart_combo.hex")
    await _wait_for_gpio_view(dut, 0xBE, timeout_cycles=20000)

    gpio_view_uart = _int_value(dut.uo_out, "uo_out") & 0x1
    dut.ui_in_base.value = _int_value(dut.ui_in_base, "ui_in_base") | 0x1
    await ClockCycles(dut.clk, 2)
    debug_view_uart = _int_value(dut.uo_out, "uo_out") & 0x1

    assert gpio_view_uart == debug_view_uart == _int_value(dut.uart_tx, "uart_tx")


@cocotb.test()
async def test_gl_alu_signature(dut):
    await _boot_gatelevel(dut, "alu_signature.hex")
    await _wait_for_gpio_view(dut, 0x6C, timeout_cycles=20000)


@cocotb.test()
async def test_gl_ram_signature(dut):
    await _boot_gatelevel(dut, "ram_signature.hex")
    await _wait_for_gpio_view(dut, 0xAB, timeout_cycles=26000)


@cocotb.test()
async def test_gl_uart_scratch_signature(dut):
    await _boot_gatelevel(dut, "uart_scratch_signature.hex")
    await _wait_for_gpio_view(dut, 0x5C, timeout_cycles=20000)


@cocotb.test()
async def test_gl_gpio_write(dut):
    await _boot_gatelevel(dut, "gpio_write.hex")
    await _wait_for_gpio_view(dut, 0xA5, timeout_cycles=20000)


@cocotb.test()
async def test_gl_gpio_readback(dut):
    await _boot_gatelevel(dut, "gpio_readback.hex")
    await _wait_for_gpio_view(dut, 0x3C, timeout_cycles=20000)


@cocotb.test()
async def test_gl_gpio_uart_combo(dut):
    await _boot_gatelevel(dut, "gpio_uart_combo.hex")
    await _wait_for_gpio_view(dut, 0xBE, timeout_cycles=20000)
    assert await capture_uart_byte(dut) == 0x55


@cocotb.test()
async def test_gl_uart_hello(dut):
    await _boot_gatelevel(dut, "uart_hello.hex")
    await _expect_uart_text(dut, "Hello, world!\r\n")


@cocotb.test()
async def test_gl_uart_prime(dut):
    await _boot_gatelevel(dut, "uart_prime.hex")
    await _expect_uart_text(dut, "3 5 7 11 13 17 19 23 29 ")


@cocotb.test()
async def test_gl_uart_loopback(dut):
    await _boot_gatelevel(dut, "uart_loopback.hex")
    await drive_uart_rx_byte(dut, 0x4B)
    assert await capture_uart_byte(dut) == 0x4B


@cocotb.test()
async def test_gl_timer_demo(dut):
    await _boot_gatelevel(dut, "timer_demo.hex")
    await _wait_for_gpio_view(dut, 0x5A, timeout_cycles=20000)


@cocotb.test()
async def test_gl_irq_demo(dut):
    await _boot_gatelevel(dut, "irq_demo.hex")
    await _wait_for_gpio_view(dut, 0x00, timeout_cycles=20000)
    await pulse_external_irq(dut, 1, hold_cycles=12)
    await _wait_for_gpio_view(dut, 0xC3, timeout_cycles=12000)
