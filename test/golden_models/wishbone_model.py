# Wishbone Golden Model
# SPDX-FileCopyrightText: 2026 TSARKA
# SPDX-License-Identifier: Apache-2.0

"""
Golden reference model for Wishbone B4 bus protocol.
Validates Wishbone transactions for compliance with specification.
"""

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import List, Optional, Callable
import logging

logger = logging.getLogger(__name__)


class WishboneCycleType(Enum):
    CLASSIC = auto()
    REGISTERED_FEEDBACK = auto()
    CONSTANT_ADDRESS_BURST = auto()
    INCREMENTING_BURST = auto()
    END_OF_BURST = auto()


@dataclass
class WishboneTransaction:
    """Represents a single Wishbone bus transaction."""
    address: int
    data: int = 0
    sel: int = 0xF  # Byte select
    we: bool = False  # Write enable
    cycle_type: WishboneCycleType = WishboneCycleType.CLASSIC
    
    # Timing information (in clock cycles)
    cyc_start: int = 0
    stb_start: int = 0
    ack_time: int = 0
    
    # Response
    read_data: int = 0
    ack: bool = False
    err: bool = False
    rty: bool = False
    stall: bool = False


@dataclass 
class WishboneSignals:
    """Current state of Wishbone signals."""
    cyc: bool = False
    stb: bool = False
    we: bool = False
    adr: int = 0
    dat_o: int = 0
    dat_i: int = 0
    sel: int = 0xF
    ack: bool = False
    err: bool = False
    rty: bool = False
    stall: bool = False


class WishboneMaster:
    """
    Golden model for Wishbone master interface.
    Validates that master transactions comply with Wishbone B4 spec.
    """
    
    def __init__(self, data_width: int = 32, addr_width: int = 32):
        self.data_width = data_width
        self.addr_width = addr_width
        self.pending_transactions: List[WishboneTransaction] = []
        self.completed_transactions: List[WishboneTransaction] = []
        self.cycle_count = 0
        self.errors: List[str] = []
        self.current_signals = WishboneSignals()
        self.prev_signals = WishboneSignals()
        
    def reset(self):
        """Reset the model state."""
        self.pending_transactions.clear()
        self.completed_transactions.clear()
        self.cycle_count = 0
        self.errors.clear()
        self.current_signals = WishboneSignals()
        self.prev_signals = WishboneSignals()
        
    def update_signals(self, signals: WishboneSignals):
        """Update signals and validate protocol compliance."""
        self.prev_signals = self.current_signals
        self.current_signals = signals
        self.cycle_count += 1
        self._validate_protocol()
        
    def _validate_protocol(self):
        """Validate Wishbone B4 protocol rules."""
        curr = self.current_signals
        prev = self.prev_signals
        
        # Rule 3.25: MASTER signals must remain stable during STALL
        if prev.stall and prev.cyc and prev.stb:
            if curr.adr != prev.adr:
                self.errors.append(f"Cycle {self.cycle_count}: ADR changed during STALL")
            if curr.dat_o != prev.dat_o and prev.we:
                self.errors.append(f"Cycle {self.cycle_count}: DAT_O changed during STALL")
            if curr.sel != prev.sel:
                self.errors.append(f"Cycle {self.cycle_count}: SEL changed during STALL")
            if curr.we != prev.we:
                self.errors.append(f"Cycle {self.cycle_count}: WE changed during STALL")
                
        # Rule 3.40: STB must be negated if CYC is negated
        if not curr.cyc and curr.stb:
            self.errors.append(f"Cycle {self.cycle_count}: STB asserted while CYC negated")
            
        # Rule 3.35: CYC must remain asserted for entire transaction
        if prev.cyc and not prev.ack and not prev.err and not prev.rty:
            if not curr.cyc and prev.stb:
                self.errors.append(f"Cycle {self.cycle_count}: CYC negated before ACK/ERR/RTY")
                
    def initiate_read(self, address: int, sel: int = 0xF) -> WishboneTransaction:
        """Initiate a read transaction."""
        txn = WishboneTransaction(
            address=address,
            sel=sel,
            we=False,
            cyc_start=self.cycle_count,
            stb_start=self.cycle_count
        )
        self.pending_transactions.append(txn)
        return txn
        
    def initiate_write(self, address: int, data: int, sel: int = 0xF) -> WishboneTransaction:
        """Initiate a write transaction."""
        txn = WishboneTransaction(
            address=address,
            data=data,
            sel=sel,
            we=True,
            cyc_start=self.cycle_count,
            stb_start=self.cycle_count
        )
        self.pending_transactions.append(txn)
        return txn
        
    def complete_transaction(self, read_data: int = 0, ack: bool = True, 
                            err: bool = False, rty: bool = False):
        """Complete the current transaction."""
        if self.pending_transactions:
            txn = self.pending_transactions.pop(0)
            txn.read_data = read_data
            txn.ack = ack
            txn.err = err
            txn.rty = rty
            txn.ack_time = self.cycle_count
            self.completed_transactions.append(txn)
            return txn
        return None
        
    def get_byte_select(self, address: int, size: int) -> int:
        """Generate byte select based on address alignment and size."""
        byte_offset = address & 0x3
        if size == 1:  # 8-bit
            return 1 << byte_offset
        elif size == 2:  # 16-bit
            return 0x3 << (byte_offset & 0x2)  # Use addr[1]
        else:  # 32-bit
            return 0xF
            
    def verify_no_errors(self) -> bool:
        """Check if there are any protocol violations."""
        return len(self.errors) == 0
        
    def get_errors(self) -> List[str]:
        """Return list of protocol errors."""
        return self.errors.copy()


class WishboneSlave:
    """
    Golden model for Wishbone slave interface.
    Validates slave responses comply with Wishbone B4 spec.
    """
    
    def __init__(self, base_address: int = 0, address_mask: int = 0xFFFFFFFF,
                 data_width: int = 32):
        self.base_address = base_address
        self.address_mask = address_mask
        self.data_width = data_width
        self.memory: dict = {}
        self.cycle_count = 0
        self.errors: List[str] = []
        self.current_signals = WishboneSignals()
        self.prev_signals = WishboneSignals()
        self.pending_ack = False
        self.ack_delay = 1  # Default 1-cycle ack
        self.ack_countdown = 0
        
    def reset(self):
        """Reset the slave state."""
        self.memory.clear()
        self.cycle_count = 0
        self.errors.clear()
        self.current_signals = WishboneSignals()
        self.prev_signals = WishboneSignals()
        self.pending_ack = False
        self.ack_countdown = 0
        
    def address_hit(self, address: int) -> bool:
        """Check if address falls within slave's range."""
        return (address & self.address_mask) == self.base_address
        
    def update_signals(self, signals: WishboneSignals) -> WishboneSignals:
        """Process incoming signals and generate response."""
        self.prev_signals = self.current_signals
        self.current_signals = signals
        self.cycle_count += 1
        
        response = WishboneSignals()
        
        if signals.cyc and signals.stb and self.address_hit(signals.adr):
            if self.ack_countdown > 0:
                self.ack_countdown -= 1
            else:
                response.ack = True
                self.ack_countdown = self.ack_delay
                
                if signals.we:
                    # Write operation
                    self._write_memory(signals.adr, signals.dat_o, signals.sel)
                else:
                    # Read operation
                    response.dat_i = self._read_memory(signals.adr, signals.sel)
                    
        self._validate_protocol()
        return response
        
    def _write_memory(self, address: int, data: int, sel: int):
        """Write data to memory with byte enables."""
        aligned_addr = address & ~0x3
        existing = self.memory.get(aligned_addr, 0)
        
        for i in range(4):
            if sel & (1 << i):
                byte_val = (data >> (i * 8)) & 0xFF
                mask = ~(0xFF << (i * 8))
                existing = (existing & mask) | (byte_val << (i * 8))
                
        self.memory[aligned_addr] = existing
        
    def _read_memory(self, address: int, sel: int) -> int:
        """Read data from memory with byte enables."""
        aligned_addr = address & ~0x3
        data = self.memory.get(aligned_addr, 0)
        
        result = 0
        for i in range(4):
            if sel & (1 << i):
                result |= (data & (0xFF << (i * 8)))
        return result
        
    def _validate_protocol(self):
        """Validate slave-side protocol rules."""
        curr = self.current_signals
        
        # Rule 3.50: ACK, ERR, RTY must be mutually exclusive
        ack_count = sum([curr.ack, curr.err, curr.rty])
        if ack_count > 1:
            self.errors.append(f"Cycle {self.cycle_count}: Multiple termination signals asserted")
            
    def set_ack_delay(self, cycles: int):
        """Set the ACK delay in clock cycles."""
        self.ack_delay = max(0, cycles)
        
    def preload_memory(self, data: dict):
        """Preload memory with initial values."""
        self.memory.update(data)
        
    def get_memory(self, address: int) -> int:
        """Get memory value at address."""
        return self.memory.get(address & ~0x3, 0)


class WishboneMonitor:
    """
    Passive Wishbone bus monitor for protocol checking.
    Does not drive signals, only observes and validates.
    """
    
    def __init__(self, name: str = "wb_monitor"):
        self.name = name
        self.transactions: List[WishboneTransaction] = []
        self.errors: List[str] = []
        self.cycle_count = 0
        self.in_transaction = False
        self.current_txn: Optional[WishboneTransaction] = None
        
    def sample(self, signals: WishboneSignals):
        """Sample bus signals each clock cycle."""
        self.cycle_count += 1
        
        if signals.cyc and signals.stb:
            if not self.in_transaction:
                # Start new transaction
                self.in_transaction = True
                self.current_txn = WishboneTransaction(
                    address=signals.adr,
                    data=signals.dat_o if signals.we else 0,
                    sel=signals.sel,
                    we=signals.we,
                    cyc_start=self.cycle_count,
                    stb_start=self.cycle_count
                )
                
            # Check for ACK/ERR/RTY
            if signals.ack or signals.err or signals.rty:
                if self.current_txn:
                    self.current_txn.ack = signals.ack
                    self.current_txn.err = signals.err
                    self.current_txn.rty = signals.rty
                    self.current_txn.read_data = signals.dat_i if not signals.we else 0
                    self.current_txn.ack_time = self.cycle_count
                    self.transactions.append(self.current_txn)
                    self.current_txn = None
                    self.in_transaction = False
                    
        elif not signals.cyc:
            if self.in_transaction and self.current_txn:
                # Transaction aborted
                self.errors.append(f"Cycle {self.cycle_count}: Transaction aborted without ACK")
            self.in_transaction = False
            self.current_txn = None
            
    def get_transaction_count(self) -> int:
        """Return number of completed transactions."""
        return len(self.transactions)
        
    def get_last_transaction(self) -> Optional[WishboneTransaction]:
        """Return the most recent transaction."""
        return self.transactions[-1] if self.transactions else None


class WishboneScoreboard:
    """
    Scoreboard for comparing expected vs actual Wishbone transactions.
    """
    
    def __init__(self):
        self.expected: List[WishboneTransaction] = []
        self.actual: List[WishboneTransaction] = []
        self.matches = 0
        self.mismatches = 0
        self.mismatch_details: List[str] = []
        
    def add_expected(self, txn: WishboneTransaction):
        """Add expected transaction."""
        self.expected.append(txn)
        
    def add_actual(self, txn: WishboneTransaction):
        """Add actual transaction and compare."""
        self.actual.append(txn)
        
        if self.expected:
            exp = self.expected.pop(0)
            self._compare(exp, txn)
            
    def _compare(self, expected: WishboneTransaction, actual: WishboneTransaction):
        """Compare expected and actual transactions."""
        match = True
        details = []
        
        if expected.address != actual.address:
            match = False
            details.append(f"Address mismatch: expected 0x{expected.address:08X}, got 0x{actual.address:08X}")
            
        if expected.we != actual.we:
            match = False
            details.append(f"WE mismatch: expected {expected.we}, got {actual.we}")
            
        if expected.we and expected.data != actual.data:
            match = False
            details.append(f"Write data mismatch: expected 0x{expected.data:08X}, got 0x{actual.data:08X}")
            
        if not expected.we and expected.read_data != actual.read_data:
            match = False
            details.append(f"Read data mismatch: expected 0x{expected.read_data:08X}, got 0x{actual.read_data:08X}")
            
        if expected.sel != actual.sel:
            match = False
            details.append(f"SEL mismatch: expected 0x{expected.sel:X}, got 0x{actual.sel:X}")
            
        if match:
            self.matches += 1
        else:
            self.mismatches += 1
            self.mismatch_details.extend(details)
            
    def report(self) -> str:
        """Generate comparison report."""
        total = self.matches + self.mismatches
        report = f"Wishbone Scoreboard Report:\n"
        report += f"  Total comparisons: {total}\n"
        report += f"  Matches: {self.matches}\n"
        report += f"  Mismatches: {self.mismatches}\n"
        
        if self.mismatch_details:
            report += "  Mismatch details:\n"
            for detail in self.mismatch_details:
                report += f"    - {detail}\n"
                
        if self.expected:
            report += f"  Outstanding expected transactions: {len(self.expected)}\n"
            
        return report
