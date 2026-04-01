# UART16550 Golden Model
# SPDX-FileCopyrightText: 2026 TSARKA
# SPDX-License-Identifier: Apache-2.0

"""
Golden reference model for UART 16550 compatible peripheral.
Provides bit-accurate behavioral model for verification.
"""

from dataclasses import dataclass, field
from enum import IntEnum
from typing import List, Optional, Callable
from collections import deque
import logging

logger = logging.getLogger(__name__)


class UARTRegister(IntEnum):
    """UART 16550 register offsets (DLAB=0)."""
    RBR = 0x00  # Receiver Buffer Register (read)
    THR = 0x00  # Transmitter Holding Register (write)
    IER = 0x04  # Interrupt Enable Register
    IIR = 0x08  # Interrupt Identification Register (read)
    FCR = 0x08  # FIFO Control Register (write)
    LCR = 0x0C  # Line Control Register
    MCR = 0x10  # Modem Control Register
    LSR = 0x14  # Line Status Register
    MSR = 0x18  # Modem Status Register
    SCR = 0x1C  # Scratch Register
    # DLAB=1 registers
    DLL = 0x00  # Divisor Latch Low
    DLM = 0x04  # Divisor Latch High


class UARTInterrupt(IntEnum):
    """UART interrupt types (priority order, highest first)."""
    RECEIVER_LINE_STATUS = 0b0110
    RECEIVER_DATA_AVAILABLE = 0b0100
    CHARACTER_TIMEOUT = 0b1100
    TRANSMITTER_HOLDING_EMPTY = 0b0010
    MODEM_STATUS = 0b0000
    NO_INTERRUPT = 0b0001


@dataclass
class UARTConfig:
    """UART configuration derived from LCR."""
    data_bits: int = 8    # 5, 6, 7, or 8
    stop_bits: float = 1  # 1, 1.5, or 2
    parity_enable: bool = False
    even_parity: bool = False
    stick_parity: bool = False
    break_control: bool = False
    dlab: bool = False
    
    @classmethod
    def from_lcr(cls, lcr: int) -> 'UARTConfig':
        """Create config from LCR register value."""
        data_bits = 5 + (lcr & 0x03)
        stop_bits = 1.5 if (lcr & 0x04) and data_bits == 5 else (2 if (lcr & 0x04) else 1)
        return cls(
            data_bits=data_bits,
            stop_bits=stop_bits,
            parity_enable=bool(lcr & 0x08),
            even_parity=bool(lcr & 0x10),
            stick_parity=bool(lcr & 0x20),
            break_control=bool(lcr & 0x40),
            dlab=bool(lcr & 0x80)
        )


@dataclass
class UARTFrame:
    """Represents a UART serial frame."""
    data: int
    parity_error: bool = False
    framing_error: bool = False
    break_detected: bool = False
    overrun: bool = False
    
    def calc_parity(self, config: UARTConfig) -> int:
        """Calculate expected parity bit."""
        if not config.parity_enable:
            return 0
        if config.stick_parity:
            return 0 if config.even_parity else 1
        bit_count = bin(self.data & ((1 << config.data_bits) - 1)).count('1')
        if config.even_parity:
            return bit_count % 2
        else:
            return (bit_count + 1) % 2


class UART16550Model:
    """
    Golden reference model for UART 16550.
    Provides cycle-accurate behavioral model.
    """
    
    FIFO_DEPTH = 16
    
    def __init__(self, clock_freq_hz: int = 40_000_000):
        self.clock_freq = clock_freq_hz
        self.reset()
        
    def reset(self):
        """Reset all registers to default values."""
        # Registers
        self.rbr = 0           # Receiver Buffer
        self.thr = 0           # Transmitter Holding
        self.ier = 0           # Interrupt Enable
        self.iir = 0x01        # Interrupt ID (no interrupt)
        self.fcr = 0           # FIFO Control
        self.lcr = 0           # Line Control
        self.mcr = 0           # Modem Control
        self.lsr = 0x60        # Line Status (THRE=1, TEMT=1)
        self.msr = 0           # Modem Status
        self.scr = 0           # Scratch
        self.dll = 0           # Divisor Latch Low
        self.dlm = 0           # Divisor Latch High
        
        # FIFOs
        self.rx_fifo: deque = deque(maxlen=self.FIFO_DEPTH)
        self.tx_fifo: deque = deque(maxlen=self.FIFO_DEPTH)
        self.fifo_enabled = False
        self.rx_trigger_level = 1
        
        # Transmitter state
        self.tx_shift_reg = 0
        self.tx_shift_count = 0
        self.tx_busy = False
        self.tx_bit_counter = 0
        
        # Receiver state
        self.rx_shift_reg = 0
        self.rx_shift_count = 0
        self.rx_busy = False
        self.rx_bit_counter = 0
        self.rx_sample_count = 0
        
        # Baud rate timing
        self.baud_counter = 0
        self.bit_time_cycles = 0
        
        # Line state
        self.tx_line = 1  # Idle high
        self.rx_line = 1  # Idle high
        self.prev_rx_line = 1
        
        # Error tracking
        self.errors: List[str] = []
        self.cycle_count = 0
        
        # Callbacks
        self.tx_callback: Optional[Callable[[int], None]] = None
        self.interrupt_callback: Optional[Callable[[bool], None]] = None
        
    def get_config(self) -> UARTConfig:
        """Get current UART configuration."""
        return UARTConfig.from_lcr(self.lcr)
        
    def get_baud_rate(self) -> int:
        """Calculate current baud rate."""
        divisor = (self.dlm << 8) | self.dll
        if divisor == 0:
            return 0
        return self.clock_freq // (16 * divisor)
        
    def set_baud_rate(self, baud: int):
        """Set baud rate by calculating divisor."""
        if baud == 0:
            return
        divisor = self.clock_freq // (16 * baud)
        self.dll = divisor & 0xFF
        self.dlm = (divisor >> 8) & 0xFF
        self.bit_time_cycles = self.clock_freq // baud
        
    def write_register(self, offset: int, value: int) -> None:
        """Write to UART register."""
        value = value & 0xFF
        config = self.get_config()
        
        if config.dlab and offset in [0x00, 0x04]:
            # Divisor latch access
            if offset == 0x00:
                self.dll = value
            else:
                self.dlm = value
            self._update_baud_timing()
            return
            
        if offset == UARTRegister.THR:
            self._write_thr(value)
        elif offset == UARTRegister.IER:
            self.ier = value & 0x0F
            self._update_interrupt()
        elif offset == UARTRegister.FCR:
            self._write_fcr(value)
        elif offset == UARTRegister.LCR:
            self.lcr = value
        elif offset == UARTRegister.MCR:
            self.mcr = value & 0x1F
            self._update_modem_loopback()
        elif offset == UARTRegister.SCR:
            self.scr = value
            
    def read_register(self, offset: int) -> int:
        """Read from UART register."""
        config = self.get_config()
        
        if config.dlab and offset in [0x00, 0x04]:
            if offset == 0x00:
                return self.dll
            else:
                return self.dlm
                
        if offset == UARTRegister.RBR:
            return self._read_rbr()
        elif offset == UARTRegister.IER:
            return self.ier
        elif offset == UARTRegister.IIR:
            return self._read_iir()
        elif offset == UARTRegister.LCR:
            return self.lcr
        elif offset == UARTRegister.MCR:
            return self.mcr
        elif offset == UARTRegister.LSR:
            return self._read_lsr()
        elif offset == UARTRegister.MSR:
            return self._read_msr()
        elif offset == UARTRegister.SCR:
            return self.scr
        return 0
        
    def _write_thr(self, value: int):
        """Write to Transmitter Holding Register."""
        if self.fifo_enabled:
            if len(self.tx_fifo) < self.FIFO_DEPTH:
                self.tx_fifo.append(value)
                self._update_lsr()
                self._update_interrupt()
            else:
                logger.warning("TX FIFO overflow")
        else:
            self.thr = value
            self.lsr &= ~0x60  # Clear THRE and TEMT
            self._start_transmission()
            
    def _read_rbr(self) -> int:
        """Read from Receiver Buffer Register."""
        if self.fifo_enabled:
            if self.rx_fifo:
                data = self.rx_fifo.popleft()
                self._update_lsr()
                self._update_interrupt()
                return data
            return 0
        else:
            self.lsr &= ~0x01  # Clear DR
            self._update_interrupt()
            return self.rbr
            
    def _read_iir(self) -> int:
        """Read Interrupt Identification Register."""
        iir = self.iir
        # Reading IIR clears THRE interrupt
        if (iir & 0x0F) == UARTInterrupt.TRANSMITTER_HOLDING_EMPTY:
            self._update_interrupt()
        return iir
        
    def _read_lsr(self) -> int:
        """Read Line Status Register."""
        lsr = self.lsr
        # Reading LSR clears error bits (OE, PE, FE, BI)
        self.lsr &= ~0x1E
        return lsr
        
    def _read_msr(self) -> int:
        """Read Modem Status Register."""
        msr = self.msr
        # Reading MSR clears delta bits
        self.msr &= ~0x0F
        return msr
        
    def _write_fcr(self, value: int):
        """Write to FIFO Control Register."""
        self.fcr = value
        
        if value & 0x01:
            self.fifo_enabled = True
            self.iir |= 0xC0  # FIFO enable bits in IIR
        else:
            self.fifo_enabled = False
            self.iir &= ~0xC0
            
        if value & 0x02:
            # Reset RX FIFO
            self.rx_fifo.clear()
            
        if value & 0x04:
            # Reset TX FIFO
            self.tx_fifo.clear()
            
        # RX trigger level
        trigger_bits = (value >> 6) & 0x03
        self.rx_trigger_level = [1, 4, 8, 14][trigger_bits]
        
    def _update_lsr(self):
        """Update Line Status Register based on FIFO state."""
        if self.fifo_enabled:
            # Data Ready
            if self.rx_fifo:
                self.lsr |= 0x01
            else:
                self.lsr &= ~0x01
                
            # THRE - TX holding register empty
            if len(self.tx_fifo) == 0:
                self.lsr |= 0x20
            else:
                self.lsr &= ~0x20
                
            # TEMT - Transmitter empty
            if len(self.tx_fifo) == 0 and not self.tx_busy:
                self.lsr |= 0x40
            else:
                self.lsr &= ~0x40
                
    def _update_interrupt(self):
        """Update interrupt status based on conditions."""
        pending_int = UARTInterrupt.NO_INTERRUPT
        
        # Priority 1: Receiver Line Status Error
        if (self.ier & 0x04) and (self.lsr & 0x1E):
            pending_int = UARTInterrupt.RECEIVER_LINE_STATUS
            
        # Priority 2: Receiver Data Available / Character Timeout
        elif (self.ier & 0x01):
            if self.fifo_enabled:
                if len(self.rx_fifo) >= self.rx_trigger_level:
                    pending_int = UARTInterrupt.RECEIVER_DATA_AVAILABLE
            elif self.lsr & 0x01:
                pending_int = UARTInterrupt.RECEIVER_DATA_AVAILABLE
                
        # Priority 3: Transmitter Holding Register Empty
        elif (self.ier & 0x02) and (self.lsr & 0x20):
            pending_int = UARTInterrupt.TRANSMITTER_HOLDING_EMPTY
            
        # Priority 4: Modem Status
        elif (self.ier & 0x08) and (self.msr & 0x0F):
            pending_int = UARTInterrupt.MODEM_STATUS
            
        self.iir = (self.iir & 0xF0) | pending_int
        
        # Trigger callback if interrupt pending
        if self.interrupt_callback:
            self.interrupt_callback(pending_int != UARTInterrupt.NO_INTERRUPT)
            
    def _update_baud_timing(self):
        """Update internal timing based on divisor."""
        divisor = (self.dlm << 8) | self.dll
        if divisor > 0:
            self.bit_time_cycles = (self.clock_freq * divisor) // self.clock_freq
            
    def _update_modem_loopback(self):
        """Handle modem loopback mode."""
        if self.mcr & 0x10:  # Loopback mode
            # Internal loopback connections
            self.msr = (self.msr & 0x0F) | ((self.mcr & 0x0F) << 4)
            
    def _start_transmission(self):
        """Start transmitting a byte."""
        if self.tx_busy:
            return
            
        data = None
        if self.fifo_enabled and self.tx_fifo:
            data = self.tx_fifo.popleft()
        elif not self.fifo_enabled and not (self.lsr & 0x20):
            data = self.thr
            self.lsr |= 0x20  # THRE
            
        if data is not None:
            self.tx_shift_reg = data
            self.tx_busy = True
            self.tx_bit_counter = 0
            self.tx_shift_count = 0
            
    def clock_tick(self):
        """Process one clock cycle."""
        self.cycle_count += 1
        
        # Transmitter
        if self.tx_busy:
            self._process_transmitter()
            
        # Receiver
        self._process_receiver()
        
        # Check for more data to transmit
        if not self.tx_busy:
            self._start_transmission()
            
    def _process_transmitter(self):
        """Process transmitter state machine."""
        self.baud_counter += 1
        
        if self.bit_time_cycles == 0:
            return
            
        if self.baud_counter >= self.bit_time_cycles:
            self.baud_counter = 0
            config = self.get_config()
            total_bits = 1 + config.data_bits + (1 if config.parity_enable else 0) + int(config.stop_bits)
            
            if self.tx_bit_counter == 0:
                # Start bit
                self.tx_line = 0
            elif self.tx_bit_counter <= config.data_bits:
                # Data bits (LSB first)
                self.tx_line = (self.tx_shift_reg >> (self.tx_bit_counter - 1)) & 1
            elif self.tx_bit_counter == config.data_bits + 1 and config.parity_enable:
                # Parity bit
                frame = UARTFrame(self.tx_shift_reg)
                self.tx_line = frame.calc_parity(config)
            else:
                # Stop bit(s)
                self.tx_line = 1
                
            self.tx_bit_counter += 1
            
            if self.tx_bit_counter >= total_bits:
                # Transmission complete
                self.tx_busy = False
                self.tx_bit_counter = 0
                if self.tx_callback:
                    self.tx_callback(self.tx_shift_reg)
                    
                # Update status
                if len(self.tx_fifo) == 0 and not self.fifo_enabled:
                    self.lsr |= 0x40  # TEMT
                self._update_interrupt()
                
    def _process_receiver(self):
        """Process receiver state machine."""
        config = self.get_config()
        
        # Detect start bit (falling edge)
        if not self.rx_busy and self.prev_rx_line == 1 and self.rx_line == 0:
            self.rx_busy = True
            self.rx_bit_counter = 0
            self.rx_sample_count = 0
            self.rx_shift_reg = 0
            
        if self.rx_busy and self.bit_time_cycles > 0:
            self.rx_sample_count += 1
            
            # Sample in middle of bit
            if self.rx_sample_count == self.bit_time_cycles // 2:
                self.rx_sample_count = 0
                
                if self.rx_bit_counter == 0:
                    # Verify start bit
                    if self.rx_line != 0:
                        self.rx_busy = False  # False start
                        return
                elif self.rx_bit_counter <= config.data_bits:
                    # Data bit
                    self.rx_shift_reg |= (self.rx_line << (self.rx_bit_counter - 1))
                elif self.rx_bit_counter == config.data_bits + 1 and config.parity_enable:
                    # Check parity
                    frame = UARTFrame(self.rx_shift_reg)
                    expected_parity = frame.calc_parity(config)
                    if self.rx_line != expected_parity:
                        self.lsr |= 0x04  # Parity error
                else:
                    # Stop bit
                    if self.rx_line != 1:
                        self.lsr |= 0x08  # Framing error
                        
                self.rx_bit_counter += 1
                
                total_bits = 1 + config.data_bits + (1 if config.parity_enable else 0) + int(config.stop_bits)
                if self.rx_bit_counter >= total_bits:
                    # Reception complete
                    self._receive_byte(self.rx_shift_reg & ((1 << config.data_bits) - 1))
                    self.rx_busy = False
                    
        self.prev_rx_line = self.rx_line
        
    def _receive_byte(self, data: int):
        """Handle received byte."""
        if self.fifo_enabled:
            if len(self.rx_fifo) >= self.FIFO_DEPTH:
                self.lsr |= 0x02  # Overrun error
            else:
                self.rx_fifo.append(data)
        else:
            if self.lsr & 0x01:
                self.lsr |= 0x02  # Overrun error
            self.rbr = data
            
        self.lsr |= 0x01  # Data ready
        self._update_interrupt()
        
    def set_rx_line(self, value: int):
        """Set RX input line state."""
        self.rx_line = value & 1
        
    def get_tx_line(self) -> int:
        """Get TX output line state."""
        return self.tx_line
        
    def send_byte(self, data: int):
        """Simulate receiving a byte (for testing)."""
        config = self.get_config()
        if config.data_bits < 8:
            data = data & ((1 << config.data_bits) - 1)
        self._receive_byte(data)
        
    def get_pending_tx(self) -> Optional[int]:
        """Get next byte to transmit (for testing)."""
        if self.fifo_enabled and self.tx_fifo:
            return self.tx_fifo[0]
        elif not (self.lsr & 0x20):
            return self.thr
        return None
        
    def verify_lsr(self, expected: int, mask: int = 0xFF) -> bool:
        """Verify LSR matches expected value."""
        actual = self.lsr & mask
        expected = expected & mask
        if actual != expected:
            self.errors.append(f"LSR mismatch: expected 0x{expected:02X}, got 0x{actual:02X}")
            return False
        return True
        
    def get_errors(self) -> List[str]:
        """Return accumulated errors."""
        return self.errors.copy()


class UARTBitBangModel:
    """
    Bit-bang UART model for generating/verifying serial waveforms.
    """
    
    def __init__(self, baud_rate: int = 115200, clock_freq: int = 40_000_000):
        self.baud_rate = baud_rate
        self.clock_freq = clock_freq
        self.bit_time_ns = int(1e9 / baud_rate)
        self.bit_time_cycles = clock_freq // baud_rate
        
    def encode_byte(self, data: int, data_bits: int = 8, 
                   parity: Optional[str] = None, stop_bits: int = 1) -> List[int]:
        """
        Encode a byte into serial bit stream.
        Returns list of bit values at each bit time.
        """
        bits = []
        
        # Start bit
        bits.append(0)
        
        # Data bits (LSB first)
        for i in range(data_bits):
            bits.append((data >> i) & 1)
            
        # Parity bit
        if parity:
            bit_count = bin(data & ((1 << data_bits) - 1)).count('1')
            if parity == 'even':
                bits.append(bit_count % 2)
            elif parity == 'odd':
                bits.append((bit_count + 1) % 2)
                
        # Stop bit(s)
        for _ in range(stop_bits):
            bits.append(1)
            
        return bits
        
    def decode_bits(self, bits: List[int], data_bits: int = 8,
                   parity: Optional[str] = None, stop_bits: int = 1) -> Optional[int]:
        """
        Decode serial bit stream into a byte.
        Returns None if framing error detected.
        """
        if not bits or bits[0] != 0:
            return None  # No valid start bit
            
        data = 0
        for i in range(data_bits):
            if i + 1 < len(bits):
                data |= (bits[i + 1] << i)
                
        # Verify stop bit
        stop_idx = 1 + data_bits + (1 if parity else 0)
        if stop_idx < len(bits) and bits[stop_idx] != 1:
            return None  # Framing error
            
        return data
        
    def generate_waveform_cycles(self, data: int) -> List[int]:
        """
        Generate waveform as list of clock cycles with bit values.
        Each entry represents one clock cycle.
        """
        bits = self.encode_byte(data)
        waveform = []
        
        for bit in bits:
            for _ in range(self.bit_time_cycles):
                waveform.append(bit)
                
        return waveform
