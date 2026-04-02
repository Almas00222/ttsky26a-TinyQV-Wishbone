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


SYSTEM_CLOCK_HZ = 40_000_000
UART_DIVISOR = 22
UART_BAUD_ACTUAL = SYSTEM_CLOCK_HZ / (16 * UART_DIVISOR)

CLOCK_PERIOD_NS = 25
BIT_TIME_115200_NS = 1e9 / UART_BAUD_ACTUAL
GPIO_BASE_IMM20 = 0x3000
UART_BASE_IMM20 = 0x4000
NIBBLE_SHIFT_ORDER = [4, 0, 12, 8, 20, 16, 28, 24]
DEFAULT_FIRMWARE = "gpio_uart_combo.hex"


def _int_value(signal, name):
    value = signal.value
    assert value.is_resolvable, f"{name} is unresolved: {value}"
    return int(value)


def _resolved_int(signal):
    value = signal.value
    if not value.is_resolvable:
        return None
    return int(value)


def encode_lui(rd, imm20):
    return ((imm20 & 0xFFFFF) << 12) | ((rd & 0x1F) << 7) | 0x37


def encode_nop():
    return 0x00000013


def sign_extend_12(value):
    value &= 0xFFF
    return value - 0x1000 if value & 0x800 else value


def mask_u32(value):
    return value & 0xFFFFFFFF


def as_signed32(value):
    value = mask_u32(value)
    return value - 0x1_0000_0000 if value & 0x8000_0000 else value


def split_lui_addi(value):
    value = mask_u32(value)
    upper = (value + 0x800) >> 12
    lower = sign_extend_12((value - ((upper & 0xFFFFF) << 12)) & 0xFFF)
    return upper & 0xFFFFF, lower


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


async def begin_manual_qspi_session(dut, latency=1, ui_in=0x80):
    await reset_dut(dut, latency=latency, use_qspi_model=False, ui_in=ui_in)
    await start_read(dut, 0)


async def wait_for_fetch_start(dut, timeout_cycles=1000):
    for _ in range(timeout_cycles):
        if _resolved_int(dut.qspi_flash_select) == 0:
            return True
        await ClockCycles(dut.clk, 1)
    return False


def _maybe_get_handle(root, path):
    current = root
    for name in path.split("."):
        try:
            current = getattr(current, name)
        except AttributeError:
            return None
    return current


def _first_available_handle(root, paths):
    for path in paths:
        handle = _maybe_get_handle(root, path)
        if handle is not None:
            return handle, path
    return None, None


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


async def capture_uart_byte(dut, bit_time_ns=BIT_TIME_115200_NS, start_timeout_ns=5_000_000):
    await wait_for_uart_start(dut, timeout_ns=start_timeout_ns)
    await Timer(bit_time_ns / 2, units="ns")
    assert _int_value(dut.uart_tx, "uart_tx") == 0, "Expected UART start bit"

    value = 0
    for bit in range(8):
        await Timer(bit_time_ns, units="ns")
        value |= _int_value(dut.uart_tx, "uart_tx") << bit

    await Timer(bit_time_ns, units="ns")
    assert _int_value(dut.uart_tx, "uart_tx") == 1, "Expected UART stop bit"
    return value


async def capture_uart_string(
    dut,
    text,
    bit_time_ns=BIT_TIME_115200_NS,
    first_start_timeout_ns=5_000_000,
    inter_byte_timeout_ns=5_000_000,
):
    for idx, char in enumerate(text):
        received = await capture_uart_byte(
            dut,
            bit_time_ns=bit_time_ns,
            start_timeout_ns=first_start_timeout_ns if idx == 0 else inter_byte_timeout_ns,
        )
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
    debug_handle, debug_path = _first_available_handle(
        dut,
        (
            "user_project.cpu_debug_instr_complete",
            "user_project.i_soc.cpu_debug_instr_complete",
            "user_project.i_soc.i_tinyqv.debug_instr_complete",
            "user_project.i_tinyqv.debug_instr_complete",
        ),
    )

    if debug_handle is not None:
        for _ in range(timeout_cycles):
            if _int_value(debug_handle, debug_path):
                return
            await RisingEdge(dut.clk)
        raise AssertionError("CPU never completed an instruction")

    dut._log.info("Falling back to top-level boot activity detection; cpu_debug_instr_complete is not visible")
    for _ in range(timeout_cycles):
        if _resolved_int(dut.qspi_flash_select) == 0:
            return
        if _resolved_int(dut.qspi_ram_a_select) == 0:
            return
        if _resolved_int(dut.qspi_ram_b_select) == 0:
            return
        if _resolved_int(dut.uart_tx) == 0:
            return
        await RisingEdge(dut.clk)
    raise AssertionError("CPU never showed observable boot activity")


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


async def start_read(dut, addr, timeout_cycles=80):
    global SELECTED_CHIP

    if addr is None:
        SELECTED_CHIP = dut.qspi_flash_select
    elif addr >= 0x1800000:
        SELECTED_CHIP = dut.qspi_ram_b_select
    elif addr >= 0x1000000:
        SELECTED_CHIP = dut.qspi_ram_a_select
    else:
        SELECTED_CHIP = dut.qspi_flash_select

    for _ in range(timeout_cycles):
        selected_chip = _resolved_int(SELECTED_CHIP)
        flash_select = _resolved_int(dut.qspi_flash_select)
        ram_a_select = _resolved_int(dut.qspi_ram_a_select)
        ram_b_select = _resolved_int(dut.qspi_ram_b_select)
        qspi_clk_out = _resolved_int(dut.qspi_clk_out)
        if (
            selected_chip == 0
            and flash_select == (0 if dut.qspi_flash_select == SELECTED_CHIP else 1)
            and ram_a_select == (0 if dut.qspi_ram_a_select == SELECTED_CHIP else 1)
            and ram_b_select == (0 if dut.qspi_ram_b_select == SELECTED_CHIP else 1)
            and qspi_clk_out == 0
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


async def start_write(dut, addr, timeout_cycles=80):
    if addr >= 0x1800000:
        selected_chip = dut.qspi_ram_b_select
    else:
        selected_chip = dut.qspi_ram_a_select

    for _ in range(timeout_cycles):
        selected_chip_value = _resolved_int(selected_chip)
        flash_select = _resolved_int(dut.qspi_flash_select)
        qspi_clk_out = _resolved_int(dut.qspi_clk_out)
        qspi_data_oe = _resolved_int(dut.qspi_data_oe)
        if (
            selected_chip_value == 0
            and flash_select == 1
            and qspi_clk_out == 0
            and qspi_data_oe == 0xF
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
        for _ in range(200):
            flash_select = _resolved_int(dut.qspi_flash_select)
            qspi_clk_out = _resolved_int(dut.qspi_clk_out)
            qspi_data_oe = _resolved_int(dut.qspi_data_oe)
            if ok_to_exit and flash_select == 1:
                return
            if (
                flash_select == 0
                and qspi_clk_out == 1
                and qspi_data_oe == 0
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
    for _ in range(400):
        selected_chip_value = _resolved_int(selected_chip)
        flash_select = _resolved_int(dut.qspi_flash_select)
        if selected_chip_value == 0:
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
        if flash_select == 0:
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
    for _ in range(400):
        selected_chip_value = _resolved_int(selected_chip)
        flash_select = _resolved_int(dut.qspi_flash_select)
        if selected_chip_value == 0:
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
        if flash_select == 0:
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


async def set_reg_value(dut, rd, value):
    upper, lower = split_lui_addi(value)
    await send_instr(dut, encode_lui(rd, upper))
    if lower != 0:
        await send_instr(dut, InstructionADDI(rd, rd, lower).encode())


async def load_addr_to_reg(dut, dest_reg, base_reg, offset, abs_addr, expected_value, byte_count=4, signed=False):
    if byte_count == 1:
        load_cls = InstructionLB if signed else InstructionLBU
    elif byte_count == 2:
        load_cls = InstructionLH if signed else InstructionLHU
    elif byte_count == 4:
        load_cls = InstructionLW
    else:
        raise ValueError(f"unsupported load width {byte_count}")

    await send_instr(dut, load_cls(dest_reg, base_reg, offset).encode())
    await expect_load(dut, abs_addr, expected_value, byte_count=byte_count)


async def store_reg_to_addr(dut, base_reg, data_reg, offset, abs_addr, byte_count=4):
    if byte_count == 1:
        store_cls = InstructionSB
    elif byte_count == 2:
        store_cls = InstructionSH
    elif byte_count == 4:
        store_cls = InstructionSW
    else:
        raise ValueError(f"unsupported store width {byte_count}")

    await send_instr(dut, store_cls(base_reg, data_reg, offset).encode())
    return await expect_store(dut, abs_addr, byte_count=byte_count)


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
