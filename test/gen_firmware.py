#!/usr/bin/env python3
"""
Generate TinyQV test firmware images as little-endian byte-per-line hex.
"""

from pathlib import Path


GPIO_BASE = 0x0300_0000
GPIO_DATAO = 0x04
GPIO_DIR = 0x08
GPIO_GCLK_ABS = 0x0300_FF10

UART_BASE = 0x0400_0000
UART_THR = 0x00
UART_IER = 0x04
UART_FCR = 0x08
UART_LCR = 0x0C
UART_LSR = 0x14

CSR_MIE = 0x304


def lui(rd, imm20):
    return ((imm20 & 0xFFFFF) << 12) | ((rd & 0x1F) << 7) | 0x37


def addi(rd, rs1, imm12):
    return ((imm12 & 0xFFF) << 20) | ((rs1 & 0x1F) << 15) | (0b000 << 12) | ((rd & 0x1F) << 7) | 0x13


def andi(rd, rs1, imm12):
    return ((imm12 & 0xFFF) << 20) | ((rs1 & 0x1F) << 15) | (0b111 << 12) | ((rd & 0x1F) << 7) | 0x13


def ori(rd, rs1, imm12):
    return ((imm12 & 0xFFF) << 20) | ((rs1 & 0x1F) << 15) | (0b110 << 12) | ((rd & 0x1F) << 7) | 0x13


def xori(rd, rs1, imm12):
    return ((imm12 & 0xFFF) << 20) | ((rs1 & 0x1F) << 15) | (0b100 << 12) | ((rd & 0x1F) << 7) | 0x13


def add(rd, rs1, rs2):
    return (0b0000000 << 25) | ((rs2 & 0x1F) << 20) | ((rs1 & 0x1F) << 15) | (0b000 << 12) | ((rd & 0x1F) << 7) | 0x33


def sub(rd, rs1, rs2):
    return (0b0100000 << 25) | ((rs2 & 0x1F) << 20) | ((rs1 & 0x1F) << 15) | (0b000 << 12) | ((rd & 0x1F) << 7) | 0x33


def slli(rd, rs1, shamt):
    return ((shamt & 0x1F) << 20) | ((rs1 & 0x1F) << 15) | (0b001 << 12) | ((rd & 0x1F) << 7) | 0x13


def srli(rd, rs1, shamt):
    return ((shamt & 0x1F) << 20) | ((rs1 & 0x1F) << 15) | (0b101 << 12) | ((rd & 0x1F) << 7) | 0x13


def lw(rd, rs1, imm12):
    return ((imm12 & 0xFFF) << 20) | ((rs1 & 0x1F) << 15) | (0b010 << 12) | ((rd & 0x1F) << 7) | 0x03


def sw(rs2, rs1, imm12):
    imm = imm12 & 0xFFF
    return (
        (((imm >> 5) & 0x7F) << 25)
        | ((rs2 & 0x1F) << 20)
        | ((rs1 & 0x1F) << 15)
        | (0b010 << 12)
        | ((imm & 0x1F) << 7)
        | 0x23
    )


def beq(rs1, rs2, offset):
    imm = offset & 0x1FFF
    return (
        (((imm >> 12) & 0x1) << 31)
        | (((imm >> 5) & 0x3F) << 25)
        | ((rs2 & 0x1F) << 20)
        | ((rs1 & 0x1F) << 15)
        | (0b000 << 12)
        | (((imm >> 1) & 0xF) << 8)
        | (((imm >> 11) & 0x1) << 7)
        | 0x63
    )


def bne(rs1, rs2, offset):
    imm = offset & 0x1FFF
    return (
        (((imm >> 12) & 0x1) << 31)
        | (((imm >> 5) & 0x3F) << 25)
        | ((rs2 & 0x1F) << 20)
        | ((rs1 & 0x1F) << 15)
        | (0b001 << 12)
        | (((imm >> 1) & 0xF) << 8)
        | (((imm >> 11) & 0x1) << 7)
        | 0x63
    )


def jal(rd, offset):
    imm = offset & 0x1FFFFF
    return (
        (((imm >> 20) & 0x1) << 31)
        | (((imm >> 1) & 0x3FF) << 21)
        | (((imm >> 11) & 0x1) << 20)
        | (((imm >> 12) & 0xFF) << 12)
        | ((rd & 0x1F) << 7)
        | 0x6F
    )


def csrrw(rd, rs1, csr):
    return ((csr & 0xFFF) << 20) | ((rs1 & 0x1F) << 15) | (0b001 << 12) | ((rd & 0x1F) << 7) | 0x73


def nop():
    return addi(0, 0, 0)


class Program:
    def __init__(self):
        self.items = []
        self.labels = {}

    def label(self, name):
        self.labels[name] = len(self.items) * 4

    def emit(self, kind, *args):
        self.items.append((kind, args))

    def inst(self, value):
        self.emit("inst", value)

    def resolve(self):
        out = []
        for index, (kind, args) in enumerate(self.items):
            pc = index * 4
            if kind == "inst":
                out.append(args[0] & 0xFFFFFFFF)
            elif kind == "beq":
                rs1, rs2, label = args
                out.append(beq(rs1, rs2, self.labels[label] - pc))
            elif kind == "bne":
                rs1, rs2, label = args
                out.append(bne(rs1, rs2, self.labels[label] - pc))
            elif kind == "jal":
                rd, label = args
                out.append(jal(rd, self.labels[label] - pc))
            else:
                raise ValueError(f"Unknown item kind {kind}")
        return out


def setup_gpio(prog, data_value=None):
    prog.inst(lui(1, GPIO_BASE >> 12))
    prog.inst(lui(5, (GPIO_GCLK_ABS + 0x800) >> 12))
    prog.inst(addi(2, 0, 1))
    prog.inst(sw(2, 5, (GPIO_GCLK_ABS - ((GPIO_GCLK_ABS + 0x800) & ~0xFFF))))
    prog.inst(addi(2, 0, 0xFF))
    prog.inst(sw(2, 1, GPIO_DIR))
    if data_value is not None:
        prog.inst(addi(2, 0, data_value))
        prog.inst(sw(2, 1, GPIO_DATAO))


def setup_uart_115200(prog):
    prog.inst(lui(10, UART_BASE >> 12))
    prog.inst(addi(2, 0, 0x80))
    prog.inst(sw(2, 10, UART_LCR))
    prog.inst(addi(2, 0, 27))
    prog.inst(sw(2, 10, UART_THR))
    prog.inst(sw(0, 10, UART_IER))
    prog.inst(addi(2, 0, 0x03))
    prog.inst(sw(2, 10, UART_LCR))
    prog.inst(addi(2, 0, 0x07))
    prog.inst(sw(2, 10, UART_FCR))


def emit_uart_wait_thre(prog, loop_label):
    prog.label(loop_label)
    prog.inst(lw(11, 10, UART_LSR))
    prog.inst(andi(11, 11, 0x20))
    prog.emit("beq", 11, 0, loop_label)


def emit_uart_send_byte(prog, byte_value, wait_label):
    emit_uart_wait_thre(prog, wait_label)
    prog.inst(addi(2, 0, byte_value))
    prog.inst(sw(2, 10, UART_THR))


def fw_gpio_write():
    prog = Program()
    setup_gpio(prog, data_value=0xA5)
    prog.label("done")
    prog.emit("jal", 0, "done")
    return prog.resolve()


def fw_gpio_readback():
    prog = Program()
    setup_gpio(prog, data_value=0xBE)
    prog.inst(lw(6, 1, GPIO_DATAO))
    prog.inst(addi(2, 0, 0xBE))
    prog.emit("bne", 6, 2, "readback_fail")
    prog.inst(addi(2, 0, 0x3C))
    prog.inst(sw(2, 1, GPIO_DATAO))
    prog.emit("jal", 0, "halt")
    prog.label("readback_fail")
    prog.inst(addi(2, 0, 0xE1))
    prog.inst(sw(2, 1, GPIO_DATAO))
    prog.label("halt")
    prog.emit("jal", 0, "halt")
    return prog.resolve()


def fw_gpio_uart_combo():
    prog = Program()
    setup_gpio(prog, data_value=0xBE)
    setup_uart_115200(prog)
    emit_uart_send_byte(prog, 0x55, "tx_wait")
    prog.label("halt")
    prog.emit("jal", 0, "halt")
    return prog.resolve()


def fw_uart_hello():
    prog = Program()
    setup_uart_115200(prog)
    for idx, char in enumerate("Hello, world!\r\n"):
        emit_uart_send_byte(prog, ord(char), f"hello_wait_{idx}")
    prog.label("halt")
    prog.emit("jal", 0, "halt")
    return prog.resolve()


def fw_uart_prime():
    prog = Program()
    setup_uart_115200(prog)
    for idx, char in enumerate("3 5 7 11 13 17 19 23 29 "):
        emit_uart_send_byte(prog, ord(char), f"prime_wait_{idx}")
    prog.label("halt")
    prog.emit("jal", 0, "halt")
    return prog.resolve()


def fw_uart_loopback():
    prog = Program()
    setup_uart_115200(prog)
    prog.label("wait_rx")
    prog.inst(lw(11, 10, UART_LSR))
    prog.inst(andi(11, 11, 0x01))
    prog.emit("beq", 11, 0, "wait_rx")
    prog.inst(lw(2, 10, UART_THR))
    emit_uart_wait_thre(prog, "wait_tx")
    prog.inst(sw(2, 10, UART_THR))
    prog.emit("jal", 0, "wait_rx")
    return prog.resolve()


def fw_timer_demo():
    prog = Program()
    prog.emit("jal", 0, "main")
    prog.inst(nop())
    prog.label("trap_vector")
    prog.inst(addi(2, 0, 0x5A))
    prog.inst(sw(2, 1, GPIO_DATAO))
    prog.label("trap_halt")
    prog.emit("jal", 0, "trap_halt")
    prog.label("main")
    setup_gpio(prog, data_value=0x00)
    prog.inst(addi(2, 0, 20))
    prog.inst(sw(2, 4, 0x38))
    prog.inst(addi(2, 0, 0x80))
    prog.inst(csrrw(0, 2, CSR_MIE))
    prog.label("wait_irq")
    prog.inst(nop())
    prog.emit("jal", 0, "wait_irq")
    return prog.resolve()


def fw_irq_demo():
    prog = Program()
    prog.emit("jal", 0, "main")
    prog.inst(nop())
    prog.label("trap_vector")
    prog.inst(addi(2, 0, 0xC3))
    prog.inst(sw(2, 1, GPIO_DATAO))
    prog.label("trap_halt")
    prog.emit("jal", 0, "trap_halt")
    prog.label("main")
    setup_gpio(prog, data_value=0x00)
    # TinyQV writes CSR nibbles on staggered subcycles, so mie[3:0] must be
    # sourced from architectural bits [19:16] rather than the low nibble.
    prog.inst(lui(2, 0x20))
    prog.inst(csrrw(0, 2, CSR_MIE))
    prog.label("wait_irq")
    prog.inst(nop())
    prog.emit("jal", 0, "wait_irq")
    return prog.resolve()


def fw_alu_signature():
    prog = Program()
    setup_gpio(prog, data_value=0x00)
    prog.inst(addi(5, 0, 0x12))
    prog.inst(addi(6, 0, 0x34))
    prog.inst(add(7, 5, 6))
    prog.inst(xori(7, 7, 0x55))
    prog.inst(slli(7, 7, 2))
    prog.inst(ori(7, 7, 0x22))
    prog.inst(addi(7, 7, -2))
    prog.inst(sw(7, 1, GPIO_DATAO))
    prog.label("halt")
    prog.emit("jal", 0, "halt")
    return prog.resolve()


def fw_ram_signature():
    prog = Program()
    setup_gpio(prog, data_value=0x00)
    prog.inst(addi(2, 0, 0x21))
    prog.inst(sw(2, 3, -0x20))
    prog.inst(addi(2, 0, 0x34))
    prog.inst(sw(2, 3, -0x1C))
    prog.inst(addi(2, 0, 0x56))
    prog.inst(sw(2, 3, -0x18))
    prog.inst(lw(5, 3, -0x20))
    prog.inst(lw(6, 3, -0x1C))
    prog.inst(lw(7, 3, -0x18))
    prog.inst(add(8, 5, 6))
    prog.inst(add(8, 8, 7))
    prog.inst(andi(8, 8, 0x0FF))
    prog.inst(sw(8, 1, GPIO_DATAO))
    prog.label("halt")
    prog.emit("jal", 0, "halt")
    return prog.resolve()


def fw_uart_scratch_signature():
    prog = Program()
    setup_gpio(prog, data_value=0x00)
    setup_uart_115200(prog)
    prog.inst(addi(2, 0, 0xA7))
    prog.inst(sw(2, 10, 0x1C))
    prog.inst(lw(6, 10, 0x1C))
    prog.inst(addi(2, 0, 0xA7))
    prog.emit("bne", 6, 2, "fail")
    prog.inst(addi(2, 0, 0x5C))
    prog.inst(sw(2, 1, GPIO_DATAO))
    prog.emit("jal", 0, "halt")
    prog.label("fail")
    prog.inst(addi(2, 0, 0xE4))
    prog.inst(sw(2, 1, GPIO_DATAO))
    prog.label("halt")
    prog.emit("jal", 0, "halt")
    return prog.resolve()


PROGRAMS = {
    "alu_signature.hex": fw_alu_signature,
    "gpio_write.hex": fw_gpio_write,
    "gpio_readback.hex": fw_gpio_readback,
    "gpio_uart_combo.hex": fw_gpio_uart_combo,
    "ram_signature.hex": fw_ram_signature,
    "uart_hello.hex": fw_uart_hello,
    "uart_prime.hex": fw_uart_prime,
    "uart_loopback.hex": fw_uart_loopback,
    "uart_scratch_signature.hex": fw_uart_scratch_signature,
    "timer_demo.hex": fw_timer_demo,
    "irq_demo.hex": fw_irq_demo,
}


def write_hex(program, path):
    lines = []
    for inst in program:
        for shift in range(0, 32, 8):
            lines.append(f"{(inst >> shift) & 0xFF:02x}")
    path.write_text("\n".join(lines) + "\n")


def main():
    outdir = Path(__file__).parent / "firmware"
    outdir.mkdir(parents=True, exist_ok=True)
    for name, build in PROGRAMS.items():
        write_hex(build(), outdir / name)
        print(f"wrote {outdir / name}")


if __name__ == "__main__":
    main()
