import os
import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, RisingEdge, Timer
from riscvmodel.insn import (
    InstructionADD,
    InstructionADDI,
    InstructionAND,
    InstructionANDI,
    InstructionLB,
    InstructionLBU,
    InstructionLH,
    InstructionLHU,
    InstructionLW,
    InstructionOR,
    InstructionORI,
    InstructionSB,
    InstructionSH,
    InstructionSLL,
    InstructionSLLI,
    InstructionSLT,
    InstructionSLTI,
    InstructionSLTIU,
    InstructionSLTU,
    InstructionSRA,
    InstructionSRAI,
    InstructionSRL,
    InstructionSRLI,
    InstructionSUB,
    InstructionSW,
    InstructionXOR,
    InstructionXORI,
)


CLOCK_PERIOD_NS = 20
BIT_TIME_115200_NS = 8680
GPIO_BASE_IMM20 = 0x3000
UART_BASE_IMM20 = 0x4000
NIBBLE_SHIFT_ORDER = [4, 0, 12, 8, 20, 16, 28, 24]
DEFAULT_FIRMWARE = "gpio_uart_combo.hex"


def _int_value(signal, name):
    value = signal.value
    assert value.is_resolvable, f"{name} is unresolved: {value}"
    return int(value)


def encode_lui(rd, imm20):
    return ((imm20 & 0xFFFFF) << 12) | ((rd & 0x1F) << 7) | 0x37


def encode_nop():
    return 0x00000013


def sign_extend_12(value):
    value &= 0xFFF
    return value - 0x1000 if value & 0x800 else value


async def start_clock(dut):
    cocotb.start_soon(Clock(dut.clk, CLOCK_PERIOD_NS, units="ns").start())


async def configure_qspi_mode(dut, use_model):
    dut.use_qspi_model.value = 1 if use_model else 0
    dut.manual_qspi_data_in.value = 0


async def reset_dut(dut, latency=1, use_qspi_model=False, ui_in=0x80):
    await configure_qspi_mode(dut, use_qspi_model)
    dut._log.info(f"Reset, latency={latency}, use_qspi_model={int(use_qspi_model)}")
    dut.ena.value = 1
    dut.ui_in_base.value = ui_in
    dut.uio_in_base.value = 0
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 2)
    dut.rst_n.value = 0
    dut.latency_cfg.value = latency
    await ClockCycles(dut.clk, 1)
    assert _int_value(dut.uio_oe, "uio_oe in reset") == 0
    await ClockCycles(dut.clk, 9)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 1)


async def wait_for_fetch_start(dut, timeout_cycles=1000):
    for _ in range(timeout_cycles):
        if _int_value(dut.qspi_flash_select, "qspi_flash_select") == 0:
            return True
        await ClockCycles(dut.clk, 1)
    return False


async def wait_for_gpio_state(dut, expected_out, expected_oe, timeout_cycles=4000):
    for _ in range(timeout_cycles):
        if (
            _int_value(dut.user_project.gpio_out, "gpio_out") == expected_out
            and _int_value(dut.user_project.gpio_oe, "gpio_oe") == expected_oe
        ):
            return
        await ClockCycles(dut.clk, 1)
    raise AssertionError(
        f"GPIO settle timeout: expected out=0x{expected_out:02X}, oe=0x{expected_oe:02X}, "
        f"got out=0x{_int_value(dut.user_project.gpio_out, 'gpio_out'):02X}, "
        f"oe=0x{_int_value(dut.user_project.gpio_oe, 'gpio_oe'):02X}"
    )


async def wait_for_uo_out_mask(dut, expected_value, mask, timeout_cycles=4000):
    last_value = dut.uo_out.value
    for _ in range(timeout_cycles):
        value = dut.uo_out.value
        last_value = value
        if value.is_resolvable and (int(value) & mask) == (expected_value & mask):
            return
        await ClockCycles(dut.clk, 1)
    raise AssertionError(
        f"uo_out settle timeout: expected 0x{expected_value & mask:02X} with mask 0x{mask:02X}, "
        f"got {last_value}"
    )


async def wait_for_uart_idle(dut, cycles=32):
    for _ in range(cycles):
        assert _int_value(dut.uart_tx, "uart_tx") == 1
        await ClockCycles(dut.clk, 1)


async def wait_for_uart_start(dut, timeout_ns=5_000_000):
    elapsed = 0
    while elapsed < timeout_ns:
        if _int_value(dut.uart_tx, "uart_tx") == 0:
            return
        await Timer(100, units="ns")
        elapsed += 100
    raise AssertionError("UART start bit timeout")


async def capture_uart_byte(dut, bit_time_ns=BIT_TIME_115200_NS):
    await wait_for_uart_start(dut)
    await Timer(bit_time_ns / 2, units="ns")
    assert _int_value(dut.uart_tx, "uart_tx") == 0, "Expected UART start bit"

    value = 0
    for bit in range(8):
        await Timer(bit_time_ns, units="ns")
        value |= _int_value(dut.uart_tx, "uart_tx") << bit

    await Timer(bit_time_ns, units="ns")
    assert _int_value(dut.uart_tx, "uart_tx") == 1, "Expected UART stop bit"
    return value


async def capture_uart_string(dut, text, bit_time_ns=BIT_TIME_115200_NS):
    for char in text:
        received = await capture_uart_byte(dut, bit_time_ns=bit_time_ns)
        assert received == ord(char), f"Expected {char!r}, got 0x{received:02X}"


async def drive_uart_rx_byte(dut, byte_val, bit_time_ns=BIT_TIME_115200_NS):
    line_state = _int_value(dut.ui_in_base, "ui_in_base") | 0x80
    dut.ui_in_base.value = line_state
    await Timer(bit_time_ns, units="ns")

    dut.ui_in_base.value = line_state & ~0x80
    await Timer(bit_time_ns, units="ns")

    temp = byte_val
    for _ in range(8):
        dut.ui_in_base.value = (line_state | 0x80) if (temp & 1) else (line_state & ~0x80)
        await Timer(bit_time_ns, units="ns")
        temp >>= 1

    dut.ui_in_base.value = line_state | 0x80
    await Timer(bit_time_ns, units="ns")


async def pulse_external_irq(dut, irq_index, hold_cycles=12):
    assert irq_index in (0, 1), f"unsupported external IRQ index {irq_index}"
    irq_mask = 1 << irq_index
    line_state = _int_value(dut.ui_in_base, "ui_in_base")
    dut.ui_in_base.value = line_state | irq_mask
    await ClockCycles(dut.clk, hold_cycles)
    dut.ui_in_base.value = _int_value(dut.ui_in_base, "ui_in_base") & ~irq_mask
    await ClockCycles(dut.clk, 1)


async def wait_for_boot_activity(dut, timeout_cycles=20000):
    for _ in range(timeout_cycles):
        if _int_value(dut.user_project.cpu_debug_instr_complete, "cpu_debug_instr_complete"):
            return
        await RisingEdge(dut.clk)
    raise AssertionError("CPU never completed an instruction")


def firmware_path(name):
    return os.path.join(os.path.dirname(__file__), "firmware", name)


def expected_firmware_path():
    return os.environ.get("TEST_FIRMWARE_HEX", firmware_path(DEFAULT_FIRMWARE))


SELECTED_CHIP = None
SEND_NOPS = False
NOP_TASK = None


def current_instr_fetch_addr(dut):
    try:
        return _int_value(dut.user_project.i_soc.i_tinyqv.instr_addr, "instr_addr") * 2
    except AttributeError:
        pass
    try:
        return _int_value(dut.user_project.i_tinyqv.instr_addr, "instr_addr") * 2
    except AttributeError:
        return None


async def start_read(dut, addr):
    global SELECTED_CHIP

    if addr is None:
        SELECTED_CHIP = dut.qspi_flash_select
    elif addr >= 0x1800000:
        SELECTED_CHIP = dut.qspi_ram_b_select
    elif addr >= 0x1000000:
        SELECTED_CHIP = dut.qspi_ram_a_select
    else:
        SELECTED_CHIP = dut.qspi_flash_select

    for _ in range(20):
        if (
            _int_value(SELECTED_CHIP, "selected_chip") == 0
            and _int_value(dut.qspi_flash_select, "qspi_flash_select") == (0 if dut.qspi_flash_select == SELECTED_CHIP else 1)
            and _int_value(dut.qspi_ram_a_select, "qspi_ram_a_select") == (0 if dut.qspi_ram_a_select == SELECTED_CHIP else 1)
            and _int_value(dut.qspi_ram_b_select, "qspi_ram_b_select") == (0 if dut.qspi_ram_b_select == SELECTED_CHIP else 1)
            and _int_value(dut.qspi_clk_out, "qspi_clk_out") == 0
        ):
            break
        await ClockCycles(dut.clk, 1, False)
    else:
        raise AssertionError("Timed out waiting for QSPI read start")

    if dut.qspi_flash_select != SELECTED_CHIP:
        cmd = 0x0B
        assert _int_value(dut.qspi_data_oe, "qspi_data_oe") == 0xF
        for _ in range(2):
            await ClockCycles(dut.clk, 1, False)
            assert _int_value(SELECTED_CHIP, "selected_chip") == 0
            assert _int_value(dut.qspi_clk_out, "qspi_clk_out") == 1
            assert _int_value(dut.qspi_data_out, "qspi_data_out") == ((cmd & 0xF0) >> 4)
            cmd <<= 4
            await ClockCycles(dut.clk, 1, False)
            assert _int_value(dut.qspi_clk_out, "qspi_clk_out") == 0

    assert _int_value(dut.qspi_data_oe, "qspi_data_oe") == 0xF
    for i in range(6):
        await ClockCycles(dut.clk, 1, False)
        assert _int_value(SELECTED_CHIP, "selected_chip") == 0
        assert _int_value(dut.qspi_clk_out, "qspi_clk_out") == 1
        if addr is not None:
            assert _int_value(dut.qspi_data_out, "qspi_data_out") == ((addr >> (20 - i * 4)) & 0xF)
        assert _int_value(dut.qspi_data_oe, "qspi_data_oe") == 0xF
        await ClockCycles(dut.clk, 1, False)
        assert _int_value(SELECTED_CHIP, "selected_chip") == 0
        assert _int_value(dut.qspi_clk_out, "qspi_clk_out") == 0

    if dut.qspi_flash_select == SELECTED_CHIP:
        for _ in range(2):
            await ClockCycles(dut.clk, 1, False)
            assert _int_value(SELECTED_CHIP, "selected_chip") == 0
            assert _int_value(dut.qspi_clk_out, "qspi_clk_out") == 1
            assert _int_value(dut.qspi_data_oe, "qspi_data_oe") == 0xF
            assert _int_value(dut.qspi_data_out, "qspi_data_out") == 0xA
            await ClockCycles(dut.clk, 1, False)
            assert _int_value(SELECTED_CHIP, "selected_chip") == 0
            assert _int_value(dut.qspi_clk_out, "qspi_clk_out") == 0

    for _ in range(4):
        await ClockCycles(dut.clk, 1, False)
        assert _int_value(SELECTED_CHIP, "selected_chip") == 0
        assert _int_value(dut.qspi_clk_out, "qspi_clk_out") == 1
        assert _int_value(dut.qspi_data_oe, "qspi_data_oe") == 0
        await ClockCycles(dut.clk, 1, False)
        assert _int_value(SELECTED_CHIP, "selected_chip") == 0
        assert _int_value(dut.qspi_clk_out, "qspi_clk_out") == 0


async def start_write(dut, addr):
    if addr >= 0x1800000:
        selected_chip = dut.qspi_ram_b_select
    else:
        selected_chip = dut.qspi_ram_a_select

    for _ in range(20):
        if (
            _int_value(selected_chip, "selected_chip") == 0
            and _int_value(dut.qspi_flash_select, "qspi_flash_select") == 1
            and _int_value(dut.qspi_clk_out, "qspi_clk_out") == 0
            and _int_value(dut.qspi_data_oe, "qspi_data_oe") == 0xF
        ):
            break
        await ClockCycles(dut.clk, 1, False)
    else:
        raise AssertionError("Timed out waiting for QSPI write start")

    cmd = 0x02
    for _ in range(2):
        await ClockCycles(dut.clk, 1, False)
        assert _int_value(selected_chip, "selected_chip") == 0
        assert _int_value(dut.qspi_clk_out, "qspi_clk_out") == 1
        assert _int_value(dut.qspi_data_out, "qspi_data_out") == ((cmd & 0xF0) >> 4)
        cmd <<= 4
        await ClockCycles(dut.clk, 1, False)
        assert _int_value(dut.qspi_clk_out, "qspi_clk_out") == 0

    for i in range(6):
        await ClockCycles(dut.clk, 1, False)
        assert _int_value(selected_chip, "selected_chip") == 0
        assert _int_value(dut.qspi_clk_out, "qspi_clk_out") == 1
        assert _int_value(dut.qspi_data_out, "qspi_data_out") == ((addr >> (20 - i * 4)) & 0xF)
        await ClockCycles(dut.clk, 1, False)
        assert _int_value(dut.qspi_clk_out, "qspi_clk_out") == 0


async def send_instr(dut, data, ok_to_exit=False):
    instr_len = 8 if (data & 3) == 3 else 4
    for i in range(instr_len):
        dut.manual_qspi_data_in.value = (data >> NIBBLE_SHIFT_ORDER[i]) & 0xF
        await ClockCycles(dut.clk, 1, False)
        for _ in range(40):
            if ok_to_exit and _int_value(dut.qspi_flash_select, "qspi_flash_select") == 1:
                return
            if (
                _int_value(dut.qspi_flash_select, "qspi_flash_select") == 0
                and _int_value(dut.qspi_clk_out, "qspi_clk_out") == 1
                and _int_value(dut.qspi_data_oe, "qspi_data_oe") == 0
            ):
                break
            await ClockCycles(dut.clk, 1, False)
        else:
            raise AssertionError("Timed out waiting for flash fetch")

        assert _int_value(dut.qspi_clk_out, "qspi_clk_out") == 1
        assert _int_value(dut.qspi_data_oe, "qspi_data_oe") == 0
        await ClockCycles(dut.clk, 1, False)
        assert _int_value(dut.qspi_clk_out, "qspi_clk_out") == 0


async def expect_load(dut, addr, val, byte_count=4):
    if addr >= 0x1800000:
        selected_chip = dut.qspi_ram_b_select
    elif addr >= 0x1000000:
        selected_chip = dut.qspi_ram_a_select
    else:
        raise AssertionError("Load from flash not handled here")

    saw_selected = False
    saw_flash_fetch = False
    for _ in range(200):
        if _int_value(selected_chip, "selected_chip") == 0:
            saw_selected = True
            await start_read(dut, addr)
            dut.manual_qspi_data_in.value = (val >> NIBBLE_SHIFT_ORDER[0]) & 0xF
            for j in range(1, byte_count * 2):
                await ClockCycles(dut.clk, 1, False)
                assert _int_value(selected_chip, "selected_chip") == 0
                assert _int_value(dut.qspi_clk_out, "qspi_clk_out") == 1
                assert _int_value(dut.qspi_data_oe, "qspi_data_oe") == 0
                await ClockCycles(dut.clk, 1, False)
                assert _int_value(dut.qspi_clk_out, "qspi_clk_out") == 0
                dut.manual_qspi_data_in.value = (val >> NIBBLE_SHIFT_ORDER[j]) & 0xF
            break
        if _int_value(dut.qspi_flash_select, "qspi_flash_select") == 0:
            saw_flash_fetch = True
            await send_instr(dut, 0x0001, True)
        else:
            await ClockCycles(dut.clk, 1, False)
    else:
        raise AssertionError(
            "Timed out waiting for RAM load: "
            f"saw_selected={saw_selected}, saw_flash_fetch={saw_flash_fetch}, "
            f"flash={_int_value(dut.qspi_flash_select, 'qspi_flash_select')}, "
            f"ram_a={_int_value(dut.qspi_ram_a_select, 'qspi_ram_a_select')}, "
            f"ram_b={_int_value(dut.qspi_ram_b_select, 'qspi_ram_b_select')}, "
            f"clk={_int_value(dut.qspi_clk_out, 'qspi_clk_out')}, "
            f"oe=0x{_int_value(dut.qspi_data_oe, 'qspi_data_oe'):X}, "
            f"instr_addr={current_instr_fetch_addr(dut)}"
        )

    for _ in range(8):
        await ClockCycles(dut.clk, 1)
        if _int_value(dut.qspi_flash_select, "qspi_flash_select") == 0:
            await start_read(dut, current_instr_fetch_addr(dut))
            return
    raise AssertionError("Timed out waiting for flash fetch restart")


async def expect_store(dut, addr, byte_count=4):
    if addr >= 0x1800000:
        selected_chip = dut.qspi_ram_b_select
    elif addr >= 0x1000000:
        selected_chip = dut.qspi_ram_a_select
    else:
        raise AssertionError("Store target outside RAM window")

    value = 0
    for _ in range(200):
        if _int_value(selected_chip, "selected_chip") == 0:
            await start_write(dut, addr)
            for j in range(byte_count * 2):
                await ClockCycles(dut.clk, 1, False)
                assert _int_value(selected_chip, "selected_chip") == 0
                assert _int_value(dut.qspi_clk_out, "qspi_clk_out") == 1
                assert _int_value(dut.qspi_data_oe, "qspi_data_oe") == 0xF
                value |= _int_value(dut.qspi_data_out, "qspi_data_out") << NIBBLE_SHIFT_ORDER[j]
                await ClockCycles(dut.clk, 1, False)
                if j == (byte_count * 2 - 1):
                    assert _int_value(selected_chip, "selected_chip") == 1
                else:
                    assert _int_value(selected_chip, "selected_chip") == 0
                assert _int_value(dut.qspi_clk_out, "qspi_clk_out") == 0
            break
        if _int_value(dut.qspi_flash_select, "qspi_flash_select") == 0:
            await send_instr(dut, 0x0001, True)
        else:
            await ClockCycles(dut.clk, 1, False)
    else:
        raise AssertionError("Timed out waiting for RAM store")

    for _ in range(8):
        await ClockCycles(dut.clk, 1)
        if _int_value(dut.qspi_flash_select, "qspi_flash_select") == 0:
            await start_read(dut, current_instr_fetch_addr(dut))
            return value
    raise AssertionError("Timed out waiting for flash fetch restart after store")


async def load_reg(dut, reg, value):
    offset = random.randint(-0x400, 0x3FF)
    await send_instr(dut, InstructionLW(reg, 3, offset).encode())
    await expect_load(dut, 0x1000400 + offset, value)


async def read_reg(dut, reg):
    offset = random.randint(-0x400, 0x3FF)
    await send_instr(dut, InstructionSW(3, reg, offset).encode())
    return await expect_store(dut, 0x1000400 + offset)


async def nops_loop(dut):
    while SEND_NOPS:
        await send_instr(dut, encode_nop())


def start_nops(dut):
    global SEND_NOPS, NOP_TASK
    SEND_NOPS = True
    NOP_TASK = cocotb.start_soon(nops_loop(dut))


async def stop_nops():
    global SEND_NOPS, NOP_TASK
    if NOP_TASK is None:
        return
    SEND_NOPS = False
    await NOP_TASK
    NOP_TASK = None


async def setup_bases(dut):
    await send_instr(dut, encode_lui(5, GPIO_BASE_IMM20))
    await send_instr(dut, encode_lui(6, UART_BASE_IMM20))


def debug_signal_value(dut, sel):
    bus = [
        _int_value(dut.user_project.cpu_debug_instr_complete, "cpu_debug_instr_complete"),
        _int_value(dut.user_project.cpu_debug_instr_ready, "cpu_debug_instr_ready"),
        _int_value(dut.user_project.cpu_debug_instr_valid, "cpu_debug_instr_valid"),
        _int_value(dut.user_project.cpu_debug_fetch_restart, "cpu_debug_fetch_restart"),
        _int_value(dut.user_project.cpu_debug_data_ready, "cpu_debug_data_ready"),
        _int_value(dut.user_project.cpu_debug_interrupt_pending, "cpu_debug_interrupt_pending"),
        _int_value(dut.user_project.cpu_debug_branch, "cpu_debug_branch"),
        _int_value(dut.user_project.gpio_irq, "gpio_irq"),
        _int_value(dut.user_project.cpu_debug_early_branch, "cpu_debug_early_branch"),
        _int_value(dut.user_project.cpu_debug_ret, "cpu_debug_ret"),
        _int_value(dut.user_project.cpu_debug_reg_wen, "cpu_debug_reg_wen"),
        _int_value(dut.user_project.cpu_debug_counter_0, "cpu_debug_counter_0"),
        _int_value(dut.user_project.cpu_debug_data_continue, "cpu_debug_data_continue"),
        _int_value(dut.user_project.cpu_debug_stall_txn, "cpu_debug_stall_txn"),
        _int_value(dut.user_project.cpu_debug_stop_txn, "cpu_debug_stop_txn"),
        _int_value(dut.user_project.uart_irq, "uart_irq"),
    ]
    return bus[sel & 0xF]
