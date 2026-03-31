import os

import cocotb

from test_common import (
    capture_uart_byte,
    expected_firmware_path,
    reset_dut,
    start_clock,
    wait_for_boot_activity,
    wait_for_gpio_state,
)


def _expect_firmware(name):
    actual = os.path.basename(expected_firmware_path())
    assert actual == name, f"expected firmware {name}, got {actual}"


@cocotb.test()
async def test_alu_signature(dut):
    _expect_firmware("alu_signature.hex")
    await start_clock(dut)
    await reset_dut(dut, latency=1, use_qspi_model=True)
    await wait_for_boot_activity(dut)
    await wait_for_gpio_state(dut, 0x6C, 0xFF, timeout_cycles=12000)


@cocotb.test()
async def test_ram_signature(dut):
    _expect_firmware("ram_signature.hex")
    await start_clock(dut)
    await reset_dut(dut, latency=1, use_qspi_model=True)
    await wait_for_boot_activity(dut)
    await wait_for_gpio_state(dut, 0xAB, 0xFF, timeout_cycles=16000)


@cocotb.test()
async def test_uart_scratch_signature(dut):
    _expect_firmware("uart_scratch_signature.hex")
    await start_clock(dut)
    await reset_dut(dut, latency=1, use_qspi_model=True)
    await wait_for_boot_activity(dut)
    await wait_for_gpio_state(dut, 0x5C, 0xFF, timeout_cycles=12000)


@cocotb.test()
async def test_combo_uart_byte_still_matches(dut):
    _expect_firmware("gpio_uart_combo.hex")
    await start_clock(dut)
    await reset_dut(dut, latency=1, use_qspi_model=True)
    await wait_for_boot_activity(dut)
    await wait_for_gpio_state(dut, 0xBE, 0xFF, timeout_cycles=12000)
    assert await capture_uart_byte(dut) == 0x55
