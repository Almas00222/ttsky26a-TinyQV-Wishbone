import os

import cocotb
from cocotb.triggers import ClockCycles

from test_common import (
    capture_uart_byte,
    drive_uart_rx_byte,
    expected_firmware_path,
    pulse_external_irq,
    reset_dut,
    start_clock,
    wait_for_boot_activity,
    wait_for_gpio_state,
)


def _expect_firmware(name):
    actual = os.path.basename(expected_firmware_path())
    assert actual == name, f"expected firmware {name}, got {actual}"


async def _expect_uart_text(dut, text):
    received = []
    for char in text:
        try:
            byte = await capture_uart_byte(dut)
        except AssertionError as exc:
            raise AssertionError(f"UART output stopped after {''.join(received)!r}") from exc
        got = chr(byte)
        received.append(got)
        assert got == char, f"expected {text!r}, got {''.join(received)!r}"


@cocotb.test()
async def test_gpio_write(dut):
    _expect_firmware("gpio_write.hex")
    await start_clock(dut)
    await reset_dut(dut, latency=1, use_qspi_model=True)
    await wait_for_boot_activity(dut)
    await wait_for_gpio_state(dut, 0xA5, 0xFF)


@cocotb.test()
async def test_gpio_readback(dut):
    _expect_firmware("gpio_readback.hex")
    await start_clock(dut)
    await reset_dut(dut, latency=1, use_qspi_model=True)
    await wait_for_boot_activity(dut)
    await wait_for_gpio_state(dut, 0x3C, 0xFF)


@cocotb.test()
async def test_gpio_uart_combo(dut):
    _expect_firmware("gpio_uart_combo.hex")
    await start_clock(dut)
    await reset_dut(dut, latency=1, use_qspi_model=True)
    await wait_for_boot_activity(dut)
    await wait_for_gpio_state(dut, 0xBE, 0xFF)
    assert await capture_uart_byte(dut) == 0x55


@cocotb.test()
async def test_qspi_protocol(dut):
    _expect_firmware("qspi_protocol.hex")
    await start_clock(dut)
    await reset_dut(dut, latency=1, use_qspi_model=True)
    await wait_for_boot_activity(dut)
    await wait_for_gpio_state(dut, 0x77, 0xFF, timeout_cycles=20000)


@cocotb.test()
async def test_uart_hello(dut):
    _expect_firmware("uart_hello.hex")
    await start_clock(dut)
    await reset_dut(dut, latency=1, use_qspi_model=True)
    await wait_for_boot_activity(dut)
    await _expect_uart_text(dut, "Hello, world!\r\n")


@cocotb.test()
async def test_uart_banner(dut):
    _expect_firmware("uart_banner.hex")
    await start_clock(dut)
    await reset_dut(dut, latency=1, use_qspi_model=True)
    await wait_for_boot_activity(dut)
    await _expect_uart_text(dut, "OK\r\n")


@cocotb.test()
async def test_uart_prime(dut):
    _expect_firmware("uart_prime.hex")
    await start_clock(dut)
    await reset_dut(dut, latency=1, use_qspi_model=True)
    await wait_for_boot_activity(dut)
    await _expect_uart_text(dut, "3 5 7 11 13 17 19 23 29 ")


@cocotb.test()
async def test_uart_loopback(dut):
    _expect_firmware("uart_loopback.hex")
    await start_clock(dut)
    await reset_dut(dut, latency=1, use_qspi_model=True)
    await wait_for_boot_activity(dut)
    await drive_uart_rx_byte(dut, 0x4B)
    assert await capture_uart_byte(dut) == 0x4B


@cocotb.test()
async def test_uart_loopback_stress(dut):
    """Drive 16 sequential bytes through RX and verify all echo back on TX."""
    _expect_firmware("uart_loopback.hex")
    await start_clock(dut)
    await reset_dut(dut, latency=1, use_qspi_model=True)
    await wait_for_boot_activity(dut)
    test_bytes = [0x00, 0x01, 0x55, 0xAA, 0xFF, 0x80, 0x7F, 0x42,
                  0xDE, 0xAD, 0xBE, 0xEF, 0x0F, 0xF0, 0x12, 0x34]
    for i, val in enumerate(test_bytes):
        await drive_uart_rx_byte(dut, val)
        echoed = await capture_uart_byte(dut)
        assert echoed == val, f"Byte {i}: sent 0x{val:02X}, got 0x{echoed:02X}"


@cocotb.test()
async def test_timer_demo(dut):
    _expect_firmware("timer_demo.hex")
    await start_clock(dut)
    await reset_dut(dut, latency=1, use_qspi_model=True)
    await wait_for_boot_activity(dut)
    await wait_for_gpio_state(dut, 0x5A, 0xFF, timeout_cycles=12000)


@cocotb.test()
async def test_irq_demo(dut):
    _expect_firmware("irq_demo.hex")
    await start_clock(dut)
    await reset_dut(dut, latency=1, use_qspi_model=True)
    await wait_for_boot_activity(dut)
    await wait_for_gpio_state(dut, 0x00, 0xFF)
    await pulse_external_irq(dut, 1, hold_cycles=12)
    await wait_for_gpio_state(dut, 0xC3, 0xFF, timeout_cycles=6000)
