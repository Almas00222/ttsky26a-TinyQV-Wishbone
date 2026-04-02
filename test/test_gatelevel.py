import os
import random

import cocotb
from cocotb.triggers import ClockCycles

from test_common import (
    _int_value,
    _resolved_int,
    capture_uart_byte,
    capture_uart_string,
    drive_uart_rx_byte,
    expected_firmware_path,
    pulse_external_irq,
    reset_dut,
    start_clock,
    start_read,
    wait_for_boot_activity,
    wait_for_uo_out_mask,
    wait_for_uart_idle,
)


LATENCY_SWEEP = (1, 2, 3)
# Full firmware completion at latency 3 is dramatically slower in the sky130
# gate-level model, so the deep suite covers latency 3 with explicit startup
# and protocol tests while running full-program boots at the two lower settings.
PROGRAM_LATENCY_SWEEP = (1, 2)
RAM_A_BASE = 0x0100_0000
RAM_B_BASE = 0x0180_0000
GPIO_UART_FIRMWARE = "gpio_uart_combo.hex"
QSPI_PROTOCOL_FIRMWARE = "qspi_protocol.hex"
BANNER_FIRMWARE = "uart_banner.hex"
QSPI_PROTOCOL_RAM_A_ADDR = RAM_A_BASE + 0x20
QSPI_PROTOCOL_RAM_B_ADDR = RAM_B_BASE + 0x24
ALU_STRESS_SIGNATURES = {
    "alu_stress_seed1.hex": 0xAE,
    "alu_stress_seed2.hex": 0x10,
}
BUS_STRESS_SIGNATURES = {
    "bus_stress_seed1.hex": 0x48,
    "bus_stress_seed2.hex": 0xF8,
}
UART_LOOPBACK_SEEDS = (0x26A3_0001, 0x26A3_0002)


def _expect_firmware(name):
    actual = os.path.basename(expected_firmware_path())
    assert actual == name, f"expected firmware {name}, got {actual}"


async def _boot_gatelevel(dut, firmware_name, latency=1, boot_timeout_cycles=20000):
    _expect_firmware(firmware_name)
    await reset_dut(dut, latency=latency, use_qspi_model=True)
    await wait_for_boot_activity(dut, timeout_cycles=boot_timeout_cycles)


async def _wait_for_gpio_view(dut, expected_gpio_out, timeout_cycles):
    dut.ui_in_base.value = _int_value(dut.ui_in_base, "ui_in_base") & ~0x1
    await wait_for_uo_out_mask(dut, expected_gpio_out, 0xFE, timeout_cycles=timeout_cycles)


async def _expect_uart_text(
    dut,
    text,
    first_start_timeout_ns=5_000_000,
    inter_byte_timeout_ns=5_000_000,
):
    await capture_uart_string(
        dut,
        text,
        first_start_timeout_ns=first_start_timeout_ns,
        inter_byte_timeout_ns=inter_byte_timeout_ns,
    )


async def _expect_qspi_read(dut, select_signal, label, addr, timeout_cycles):
    for _ in range(timeout_cycles):
        if _resolved_int(select_signal) == 0:
            break
        await ClockCycles(dut.clk, 1)
    else:
        raise AssertionError(f"timed out waiting for {label} read transaction")
    await start_read(dut, addr, timeout_cycles=timeout_cycles)


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
    await start_clock(dut)
    await _boot_gatelevel(dut, GPIO_UART_FIRMWARE)
    await _wait_for_gpio_view(dut, 0xBE, timeout_cycles=20000)

    gpio_view_uart = _int_value(dut.uo_out, "uo_out") & 0x1
    dut.ui_in_base.value = _int_value(dut.ui_in_base, "ui_in_base") | 0x1
    await ClockCycles(dut.clk, 2)
    debug_view_uart = _int_value(dut.uo_out, "uo_out") & 0x1

    assert gpio_view_uart == debug_view_uart == _int_value(dut.uart_tx, "uart_tx")


@cocotb.test()
async def test_gl_flash_fetch_startup_latency_sweep(dut):
    await start_clock(dut)

    for latency in LATENCY_SWEEP:
        dut._log.info("GL flash fetch startup latency=%d", latency)
        await reset_dut(dut, latency=latency, use_qspi_model=True)
        await start_read(dut, 0, timeout_cycles=200)
        await ClockCycles(dut.clk, 8)


@cocotb.test()
async def test_gl_qspi_protocol_firmware_roundtrip(dut):
    await start_clock(dut)
    _expect_firmware(QSPI_PROTOCOL_FIRMWARE)

    await reset_dut(dut, latency=1, use_qspi_model=True)
    await start_read(dut, 0, timeout_cycles=200)
    saw_ram_a = False
    saw_ram_b = False
    saw_flash_after_ram = False

    for _ in range(20000):
        uo_value = dut.uo_out.value
        if _resolved_int(dut.qspi_ram_a_select) == 0:
            saw_ram_a = True
        if _resolved_int(dut.qspi_ram_b_select) == 0:
            saw_ram_b = True
        if (saw_ram_a or saw_ram_b) and _resolved_int(dut.qspi_flash_select) == 0:
            saw_flash_after_ram = True
        if uo_value.is_resolvable and (int(uo_value) & 0xFE) == 0x76:
            break
        await ClockCycles(dut.clk, 1)
    else:
        raise AssertionError("qspi_protocol firmware never reached the expected GPIO signature")

    assert saw_ram_a, "qspi_protocol firmware never exposed RAM A activity on the top-level QSPI port"
    assert saw_ram_b, "qspi_protocol firmware never exposed RAM B activity on the top-level QSPI port"
    assert saw_flash_after_ram, "qspi_protocol firmware never returned to flash fetch after RAM activity"


@cocotb.test()
async def test_gl_alu_signature(dut):
    await start_clock(dut)
    await _boot_gatelevel(dut, "alu_signature.hex")
    await _wait_for_gpio_view(dut, 0x6C, timeout_cycles=20000)


@cocotb.test()
async def test_gl_alu_stress_seed1(dut):
    await start_clock(dut)
    await _boot_gatelevel(dut, "alu_stress_seed1.hex")
    await _wait_for_gpio_view(dut, ALU_STRESS_SIGNATURES["alu_stress_seed1.hex"], timeout_cycles=26000)


@cocotb.test()
async def test_gl_alu_stress_seed2(dut):
    await start_clock(dut)
    await _boot_gatelevel(dut, "alu_stress_seed2.hex")
    await _wait_for_gpio_view(dut, ALU_STRESS_SIGNATURES["alu_stress_seed2.hex"], timeout_cycles=26000)


@cocotb.test()
async def test_gl_ram_signature(dut):
    await start_clock(dut)
    _expect_firmware("ram_signature.hex")

    for latency in PROGRAM_LATENCY_SWEEP:
        dut._log.info("GL ram_signature latency=%d", latency)
        await reset_dut(dut, latency=latency, use_qspi_model=True)
        await _wait_for_gpio_view(dut, 0xAB, timeout_cycles=120000)


@cocotb.test()
async def test_gl_bus_stress_seed1(dut):
    await start_clock(dut)
    await _boot_gatelevel(dut, "bus_stress_seed1.hex")
    await _wait_for_gpio_view(dut, BUS_STRESS_SIGNATURES["bus_stress_seed1.hex"], timeout_cycles=26000)


@cocotb.test()
async def test_gl_bus_stress_seed2(dut):
    await start_clock(dut)
    await _boot_gatelevel(dut, "bus_stress_seed2.hex")
    await _wait_for_gpio_view(dut, BUS_STRESS_SIGNATURES["bus_stress_seed2.hex"], timeout_cycles=26000)


@cocotb.test()
async def test_gl_uart_scratch_signature(dut):
    await start_clock(dut)
    await _boot_gatelevel(dut, "uart_scratch_signature.hex")
    await _wait_for_gpio_view(dut, 0x5C, timeout_cycles=20000)


@cocotb.test()
async def test_gl_gpio_write(dut):
    await start_clock(dut)
    await _boot_gatelevel(dut, "gpio_write.hex")
    await _wait_for_gpio_view(dut, 0xA5, timeout_cycles=20000)


@cocotb.test()
async def test_gl_gpio_readback(dut):
    await start_clock(dut)
    await _boot_gatelevel(dut, "gpio_readback.hex")
    await _wait_for_gpio_view(dut, 0x3C, timeout_cycles=20000)


@cocotb.test()
async def test_gl_gpio_uart_combo(dut):
    await start_clock(dut)
    await _boot_gatelevel(dut, GPIO_UART_FIRMWARE)
    await _wait_for_gpio_view(dut, 0xBE, timeout_cycles=20000)
    assert await capture_uart_byte(dut) == 0x55


@cocotb.test()
async def test_gl_uart_banner_latency_sweep(dut):
    await start_clock(dut)
    _expect_firmware(BANNER_FIRMWARE)

    for latency in PROGRAM_LATENCY_SWEEP:
        dut._log.info("GL uart_banner latency=%d", latency)
        await reset_dut(dut, latency=latency, use_qspi_model=True)
        await _expect_uart_text(
            dut,
            "OK\r\n",
            first_start_timeout_ns=12_000_000,
            inter_byte_timeout_ns=1_000_000,
        )


@cocotb.test()
async def test_gl_uart_hello(dut):
    await start_clock(dut)
    _expect_firmware("uart_hello.hex")
    await _boot_gatelevel(dut, "uart_hello.hex", latency=1)
    await _expect_uart_text(dut, "Hello, world!\r\n")


@cocotb.test()
async def test_gl_uart_prime(dut):
    await start_clock(dut)
    _expect_firmware("uart_prime.hex")
    await _boot_gatelevel(dut, "uart_prime.hex", latency=1)
    await _expect_uart_text(dut, "3 5 7 11 13 17 19 23 29 ")


@cocotb.test()
async def test_gl_uart_loopback_seeded_stress(dut):
    await start_clock(dut)
    await _boot_gatelevel(dut, "uart_loopback.hex")

    for seed in UART_LOOPBACK_SEEDS:
        rng = random.Random(seed)
        dut._log.info("GL uart loopback seed=0x%08X", seed)
        for _ in range(8):
            byte = rng.randint(0, 0xFF)
            await drive_uart_rx_byte(dut, byte)
            assert await capture_uart_byte(dut) == byte


@cocotb.test()
async def test_gl_timer_demo(dut):
    await start_clock(dut)
    await _boot_gatelevel(dut, "timer_demo.hex")
    await _wait_for_gpio_view(dut, 0x5A, timeout_cycles=20000)


@cocotb.test()
async def test_gl_irq_demo(dut):
    await start_clock(dut)
    await _boot_gatelevel(dut, "irq_demo.hex")
    await _wait_for_gpio_view(dut, 0x00, timeout_cycles=20000)
    await pulse_external_irq(dut, 1, hold_cycles=12)
    await _wait_for_gpio_view(dut, 0xC3, timeout_cycles=12000)
