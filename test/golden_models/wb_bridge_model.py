# TinyQV Wishbone Bridge Golden Model
# SPDX-FileCopyrightText: 2026 TSARKA
# SPDX-License-Identifier: Apache-2.0

"""
Golden reference model for TinyQV to Wishbone bridge.
Validates address translation, byte select generation, and protocol conversion.
"""

from dataclasses import dataclass
from enum import IntEnum
from typing import List, Optional, Tuple
import logging

logger = logging.getLogger(__name__)


class TransactionSize(IntEnum):
    """Transaction size encoding (matches TinyQV data_write_n/data_read_n)."""
    SIZE_8BIT = 0b00
    SIZE_16BIT = 0b01
    SIZE_32BIT = 0b10
    NO_TRANSACTION = 0b11


@dataclass
class CPUTransaction:
    """Represents a TinyQV CPU transaction."""
    address: int           # 28-bit address
    data: int = 0          # 32-bit data
    write_n: int = 0b11    # Write size (11=no write)
    read_n: int = 0b11     # Read size (11=no read)
    
    @property
    def is_write(self) -> bool:
        return self.write_n != 0b11
        
    @property
    def is_read(self) -> bool:
        return self.read_n != 0b11
        
    @property
    def is_active(self) -> bool:
        return self.is_write or self.is_read
        
    @property
    def size(self) -> int:
        """Get transaction size (0=8bit, 1=16bit, 2=32bit)."""
        if self.is_read:
            return self.read_n
        return self.write_n


@dataclass
class WBTransaction:
    """Represents a Wishbone transaction."""
    address: int = 0       # 32-bit address
    data: int = 0          # 32-bit data
    sel: int = 0xF         # Byte select
    we: bool = False       # Write enable
    cyc: bool = False      # Cycle
    stb: bool = False      # Strobe


class TinyQVWishboneBridgeModel:
    """
    Golden reference model for TinyQV to Wishbone bridge.
    Implements the same logic as wb_bridge.v.
    """
    
    TIMEOUT_CYCLES = 127
    
    def __init__(self):
        self.reset()
        
    def reset(self):
        """Reset bridge state."""
        self.ack_seen = False
        self.timeout_cnt = 0
        self.timeout_triggered = False
        self.cpu_data_in_reg = 0
        self.cycle_count = 0
        self.errors: List[str] = []
        
    def translate_transaction(self, cpu_txn: CPUTransaction) -> WBTransaction:
        """
        Translate CPU transaction to Wishbone transaction.
        Returns expected Wishbone signals.
        """
        wb = WBTransaction()
        
        # Read has priority over write
        is_read = cpu_txn.read_n != 0b11
        is_write = (cpu_txn.write_n != 0b11) and not is_read
        is_active = is_read or is_write
        
        # Determine cycle/strobe
        wb.cyc = is_active and not self.ack_seen
        wb.stb = is_active and not self.ack_seen
        wb.we = is_write
        
        # Address pass-through (28-bit to 32-bit)
        wb.address = cpu_txn.address & 0x0FFFFFFF
        
        # Calculate byte select
        size = cpu_txn.read_n if is_read else cpu_txn.write_n
        wb.sel = self._calc_byte_select(cpu_txn.address, size)
        
        # Data steering for writes
        wb.data = self._steer_write_data(cpu_txn.data, size)
        
        return wb
        
    def _calc_byte_select(self, address: int, size: int) -> int:
        """
        Calculate Wishbone byte select based on address and size.
        Matches the logic in wb_bridge.v.
        """
        byte_offset = address & 0x3
        
        if size == TransactionSize.SIZE_8BIT:
            return 1 << byte_offset
        elif size == TransactionSize.SIZE_16BIT:
            # addr[1] selects lower or upper halfword
            return 0b0011 if (byte_offset & 0x2) == 0 else 0b1100
        else:  # 32-bit
            return 0b1111
            
    def _steer_write_data(self, data: int, size: int) -> int:
        """
        Steer write data to correct byte lanes.
        Replicates data across lanes so slave picks the right one.
        """
        if size == TransactionSize.SIZE_8BIT:
            byte_val = data & 0xFF
            return (byte_val << 24) | (byte_val << 16) | (byte_val << 8) | byte_val
        elif size == TransactionSize.SIZE_16BIT:
            half_val = data & 0xFFFF
            return (half_val << 16) | half_val
        else:
            return data & 0xFFFFFFFF
            
    def extract_read_data(self, wb_data: int, address: int, size: int) -> int:
        """
        Extract read data from Wishbone data based on address and size.
        For a simple pass-through bridge, returns data as-is.
        If the CPU expects data shifted to LSB, add extraction logic here.
        """
        return wb_data
        
    def clock_tick(self, cpu_txn: CPUTransaction, wb_ack: bool, wb_data: int = 0) -> Tuple[int, bool]:
        """
        Process one clock cycle.
        
        Args:
            cpu_txn: Current CPU transaction signals
            wb_ack: Wishbone ACK signal
            wb_data: Wishbone read data
            
        Returns:
            Tuple of (cpu_data_in, cpu_data_ready)
        """
        self.cycle_count += 1
        
        is_read = cpu_txn.read_n != 0b11
        is_write = (cpu_txn.write_n != 0b11) and not is_read
        is_active = is_read or is_write
        
        # ACK tracking
        if not is_active:
            self.ack_seen = False
        elif wb_ack:
            self.ack_seen = True
            self.cpu_data_in_reg = wb_data
            
        # Timeout counter
        if not is_active or wb_ack:
            self.timeout_cnt = 0
            self.timeout_triggered = False
        elif is_active:
            if self.timeout_cnt >= self.TIMEOUT_CYCLES:
                self.timeout_triggered = True
            else:
                self.timeout_cnt += 1
                
        # Output signals
        cpu_data_in = wb_data if wb_ack else self.cpu_data_in_reg
        cpu_data_ready = wb_ack or self.timeout_triggered
        
        return cpu_data_in, cpu_data_ready
        
    def verify_byte_select(self, address: int, size: int, expected_sel: int) -> bool:
        """Verify byte select calculation."""
        actual_sel = self._calc_byte_select(address, size)
        if actual_sel != expected_sel:
            self.errors.append(
                f"Byte select mismatch at addr 0x{address:08X}, size {size}: "
                f"expected 0x{expected_sel:X}, got 0x{actual_sel:X}"
            )
            return False
        return True
        
    def verify_data_steering(self, data: int, size: int, expected: int) -> bool:
        """Verify write data steering."""
        actual = self._steer_write_data(data, size)
        if actual != expected:
            self.errors.append(
                f"Data steering mismatch for data 0x{data:08X}, size {size}: "
                f"expected 0x{expected:08X}, got 0x{actual:08X}"
            )
            return False
        return True
        
    def get_errors(self) -> List[str]:
        """Return accumulated errors."""
        return self.errors.copy()


class WishboneBridgeScoreboard:
    """
    Scoreboard for comparing bridge model vs RTL.
    """
    
    def __init__(self):
        self.model = TinyQVWishboneBridgeModel()
        self.comparisons = 0
        self.matches = 0
        self.mismatches = 0
        self.mismatch_log: List[str] = []
        
    def reset(self):
        """Reset scoreboard and model."""
        self.model.reset()
        self.comparisons = 0
        self.matches = 0
        self.mismatches = 0
        self.mismatch_log.clear()
        
    def compare_transaction(self, cpu_txn: CPUTransaction,
                           rtl_wb_addr: int, rtl_wb_data: int,
                           rtl_wb_sel: int, rtl_wb_we: bool,
                           rtl_wb_cyc: bool, rtl_wb_stb: bool) -> bool:
        """Compare model output with RTL."""
        self.comparisons += 1
        
        expected = self.model.translate_transaction(cpu_txn)
        
        match = True
        
        if expected.cyc != rtl_wb_cyc:
            match = False
            self.mismatch_log.append(f"CYC mismatch: model={expected.cyc}, rtl={rtl_wb_cyc}")
            
        if expected.stb != rtl_wb_stb:
            match = False
            self.mismatch_log.append(f"STB mismatch: model={expected.stb}, rtl={rtl_wb_stb}")
            
        if expected.we != rtl_wb_we:
            match = False
            self.mismatch_log.append(f"WE mismatch: model={expected.we}, rtl={rtl_wb_we}")
            
        if expected.address != rtl_wb_addr:
            match = False
            self.mismatch_log.append(
                f"ADDR mismatch: model=0x{expected.address:08X}, rtl=0x{rtl_wb_addr:08X}"
            )
            
        if expected.sel != rtl_wb_sel:
            match = False
            self.mismatch_log.append(
                f"SEL mismatch: model=0x{expected.sel:X}, rtl=0x{rtl_wb_sel:X}"
            )
            
        if cpu_txn.is_write and expected.data != rtl_wb_data:
            match = False
            self.mismatch_log.append(
                f"DATA mismatch: model=0x{expected.data:08X}, rtl=0x{rtl_wb_data:08X}"
            )
            
        if match:
            self.matches += 1
        else:
            self.mismatches += 1
            
        return match
        
    def report(self) -> str:
        """Generate comparison report."""
        report = f"Wishbone Bridge Scoreboard Report:\n"
        report += f"  Total comparisons: {self.comparisons}\n"
        report += f"  Matches: {self.matches}\n"
        report += f"  Mismatches: {self.mismatches}\n"
        
        if self.mismatch_log:
            report += "  Recent mismatches:\n"
            for entry in self.mismatch_log[-10:]:
                report += f"    - {entry}\n"
                
        return report


class ByteSelectTestVectors:
    """
    Pre-computed test vectors for byte select verification.
    """
    
    @staticmethod
    def get_8bit_vectors() -> List[Tuple[int, int]]:
        """Get (address, expected_sel) for 8-bit accesses."""
        return [
            (0x00000000, 0b0001),
            (0x00000001, 0b0010),
            (0x00000002, 0b0100),
            (0x00000003, 0b1000),
            (0x00001000, 0b0001),
            (0x00001001, 0b0010),
            (0x00001002, 0b0100),
            (0x00001003, 0b1000),
        ]
        
    @staticmethod
    def get_16bit_vectors() -> List[Tuple[int, int]]:
        """Get (address, expected_sel) for 16-bit accesses."""
        return [
            (0x00000000, 0b0011),  # Lower halfword
            (0x00000002, 0b1100),  # Upper halfword
            (0x00001000, 0b0011),  # Lower halfword
            (0x00001002, 0b1100),  # Upper halfword
            (0x00002004, 0b0011),  # Lower halfword (addr[1]=0)
            (0x00002006, 0b1100),  # Upper halfword (addr[1]=1)
        ]
        
    @staticmethod
    def get_32bit_vectors() -> List[Tuple[int, int]]:
        """Get (address, expected_sel) for 32-bit accesses."""
        return [
            (0x00000000, 0b1111),
            (0x00001000, 0b1111),
            (0x00002000, 0b1111),
            (0x0FFFFFF0, 0b1111),
        ]


class DataSteeringTestVectors:
    """
    Pre-computed test vectors for data steering verification.
    """
    
    @staticmethod
    def get_8bit_vectors() -> List[Tuple[int, int]]:
        """Get (input_data, expected_output) for 8-bit steering."""
        return [
            (0x00000012, 0x12121212),
            (0x000000AB, 0xABABABAB),
            (0x000000FF, 0xFFFFFFFF),
            (0x00000000, 0x00000000),
        ]
        
    @staticmethod
    def get_16bit_vectors() -> List[Tuple[int, int]]:
        """Get (input_data, expected_output) for 16-bit steering."""
        return [
            (0x00001234, 0x12341234),
            (0x0000ABCD, 0xABCDABCD),
            (0x0000FFFF, 0xFFFFFFFF),
            (0x00000000, 0x00000000),
        ]
        
    @staticmethod
    def get_32bit_vectors() -> List[Tuple[int, int]]:
        """Get (input_data, expected_output) for 32-bit pass-through."""
        return [
            (0x12345678, 0x12345678),
            (0xABCDEF01, 0xABCDEF01),
            (0xFFFFFFFF, 0xFFFFFFFF),
            (0x00000000, 0x00000000),
        ]
