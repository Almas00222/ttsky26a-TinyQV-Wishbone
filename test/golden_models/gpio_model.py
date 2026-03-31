# GPIO8 Golden Model (Efabless)
# SPDX-FileCopyrightText: 2026 TSARKA
# SPDX-License-Identifier: Apache-2.0

"""
Golden reference model for Efabless EF_GPIO8 peripheral.
Provides behavioral model for GPIO with interrupt support.
"""

from dataclasses import dataclass, field
from enum import IntEnum
from typing import List, Optional, Callable
import logging

logger = logging.getLogger(__name__)


class GPIORegister(IntEnum):
    """GPIO register offsets."""
    DATAI = 0x0000    # Input Data Register (read-only)
    DATAO = 0x0004    # Output Data Register
    DIR = 0x0008      # Direction Register (1=output, 0=input)
    IM = 0xFF00       # Interrupt Mask
    MIS = 0xFF04      # Masked Interrupt Status (read-only)
    RIS = 0xFF08      # Raw Interrupt Status (read-only)
    IC = 0xFF0C       # Interrupt Clear
    GCLK = 0xFF10     # Gated Clock Control


class GPIOInterruptType(IntEnum):
    """GPIO interrupt types per pin (8 pins x 4 types = 32 bits)."""
    # Bits 0-7: Pin high level
    PIN0_HI = 0
    PIN1_HI = 1
    PIN2_HI = 2
    PIN3_HI = 3
    PIN4_HI = 4
    PIN5_HI = 5
    PIN6_HI = 6
    PIN7_HI = 7
    # Bits 8-15: Pin low level
    PIN0_LO = 8
    PIN1_LO = 9
    PIN2_LO = 10
    PIN3_LO = 11
    PIN4_LO = 12
    PIN5_LO = 13
    PIN6_LO = 14
    PIN7_LO = 15
    # Bits 16-23: Pin positive edge
    PIN0_PE = 16
    PIN1_PE = 17
    PIN2_PE = 18
    PIN3_PE = 19
    PIN4_PE = 20
    PIN5_PE = 21
    PIN6_PE = 22
    PIN7_PE = 23
    # Bits 24-31: Pin negative edge
    PIN0_NE = 24
    PIN1_NE = 25
    PIN2_NE = 26
    PIN3_NE = 27
    PIN4_NE = 28
    PIN5_NE = 29
    PIN6_NE = 30
    PIN7_NE = 31


@dataclass
class GPIOPinState:
    """State of a single GPIO pin."""
    input_value: int = 0
    output_value: int = 0
    direction: int = 0  # 0=input, 1=output
    prev_input: int = 0  # For edge detection
    
    @property
    def actual_output(self) -> int:
        """Get actual pin output considering direction."""
        return self.output_value if self.direction else 0


class GPIO8Model:
    """
    Golden reference model for EF_GPIO8.
    8-bit GPIO with level and edge interrupts.
    """
    
    NUM_PINS = 8
    
    def __init__(self):
        self.reset()
        
    def reset(self):
        """Reset all registers to default values."""
        # Registers
        self.datao = 0          # Output data
        self.dir = 0            # Direction (0=input, 1=output)
        self.im = 0             # Interrupt mask
        self.ris = 0            # Raw interrupt status
        self.gclk = 0           # Gated clock enable
        
        # Pin states
        self.pins: List[GPIOPinState] = [GPIOPinState() for _ in range(self.NUM_PINS)]
        
        # Input synchronization (2-stage sync like hardware)
        self.sync_stage1 = 0
        self.sync_stage2 = 0
        self.prev_sync = 0
        
        # Callbacks
        self.irq_callback: Optional[Callable[[bool], None]] = None
        
        # Error tracking
        self.errors: List[str] = []
        self.cycle_count = 0
        
    def write_register(self, offset: int, value: int) -> None:
        """Write to GPIO register."""
        offset = offset & 0xFFFF  # 16-bit address space
        
        if offset == GPIORegister.DATAO:
            self.datao = value & 0xFF
            self._update_outputs()
        elif offset == GPIORegister.DIR:
            self.dir = value & 0xFF
            self._update_outputs()
        elif offset == GPIORegister.IM:
            self.im = value & 0xFFFFFFFF
            self._update_irq()
        elif offset == GPIORegister.IC:
            # Clear interrupt bits
            self.ris &= ~(value & 0xFFFFFFFF)
            self._update_irq()
        elif offset == GPIORegister.GCLK:
            self.gclk = value & 0x01
        # DATAI, MIS, RIS are read-only
        
    def read_register(self, offset: int) -> int:
        """Read from GPIO register."""
        offset = offset & 0xFFFF
        
        if offset == GPIORegister.DATAI:
            return self.sync_stage2 & 0xFF
        elif offset == GPIORegister.DATAO:
            return self.datao & 0xFF
        elif offset == GPIORegister.DIR:
            return self.dir & 0xFF
        elif offset == GPIORegister.IM:
            return self.im & 0xFFFFFFFF
        elif offset == GPIORegister.MIS:
            return (self.ris & self.im) & 0xFFFFFFFF
        elif offset == GPIORegister.RIS:
            return self.ris & 0xFFFFFFFF
        elif offset == GPIORegister.IC:
            return 0  # Write-only in hardware, but return 0
        elif offset == GPIORegister.GCLK:
            return self.gclk & 0x01
        else:
            return 0xDEADBEEF  # Invalid address marker
            
    def set_input(self, pin: int, value: int) -> None:
        """Set input value for a specific pin."""
        if 0 <= pin < self.NUM_PINS:
            self.pins[pin].input_value = value & 1
            
    def set_inputs(self, value: int) -> None:
        """Set all input values (8-bit)."""
        for i in range(self.NUM_PINS):
            self.pins[i].input_value = (value >> i) & 1
            
    def get_output(self, pin: int) -> int:
        """Get output value for a specific pin."""
        if 0 <= pin < self.NUM_PINS:
            return self.pins[pin].actual_output
        return 0
        
    def get_outputs(self) -> int:
        """Get all output values (8-bit)."""
        result = 0
        for i in range(self.NUM_PINS):
            if self.pins[i].direction:  # Output enabled
                result |= (self.pins[i].output_value << i)
        return result
        
    def get_output_enable(self) -> int:
        """Get output enable mask (8-bit)."""
        return self.dir
        
    def get_irq(self) -> bool:
        """Get combined interrupt request signal."""
        return (self.ris & self.im) != 0
        
    def clock_tick(self) -> None:
        """Process one clock cycle."""
        self.cycle_count += 1
        
        # Only process if gated clock is enabled
        if not self.gclk:
            return
            
        # Update synchronizer
        raw_input = 0
        for i in range(self.NUM_PINS):
            raw_input |= (self.pins[i].input_value << i)
            
        self.prev_sync = self.sync_stage2
        self.sync_stage2 = self.sync_stage1
        self.sync_stage1 = raw_input
        
        # Detect edges and levels
        self._update_interrupts()
        
    def _update_outputs(self) -> None:
        """Update pin output states."""
        for i in range(self.NUM_PINS):
            self.pins[i].output_value = (self.datao >> i) & 1
            self.pins[i].direction = (self.dir >> i) & 1
            
    def _update_interrupts(self) -> None:
        """Update interrupt status based on pin states."""
        synced = self.sync_stage2
        prev = self.prev_sync
        
        for i in range(self.NUM_PINS):
            pin_val = (synced >> i) & 1
            prev_val = (prev >> i) & 1
            
            # High level
            if pin_val == 1:
                self.ris |= (1 << (i + 0))
            
            # Low level
            if pin_val == 0:
                self.ris |= (1 << (i + 8))
            
            # Positive edge (rising)
            if pin_val == 1 and prev_val == 0:
                self.ris |= (1 << (i + 16))
            
            # Negative edge (falling)
            if pin_val == 0 and prev_val == 1:
                self.ris |= (1 << (i + 24))
                
        self._update_irq()
        
    def _update_irq(self) -> None:
        """Update IRQ output."""
        irq = self.get_irq()
        if self.irq_callback:
            self.irq_callback(irq)
            
    def verify_output(self, expected: int, mask: int = 0xFF) -> bool:
        """Verify output matches expected value."""
        actual = self.get_outputs() & mask
        expected = expected & mask
        if actual != expected:
            self.errors.append(
                f"Cycle {self.cycle_count}: Output mismatch: expected 0x{expected:02X}, got 0x{actual:02X}"
            )
            return False
        return True
        
    def verify_direction(self, expected: int) -> bool:
        """Verify direction register matches expected value."""
        if self.dir != expected:
            self.errors.append(
                f"Cycle {self.cycle_count}: Direction mismatch: expected 0x{expected:02X}, got 0x{self.dir:02X}"
            )
            return False
        return True
        
    def verify_irq(self, expected: bool) -> bool:
        """Verify IRQ state."""
        actual = self.get_irq()
        if actual != expected:
            self.errors.append(
                f"Cycle {self.cycle_count}: IRQ mismatch: expected {expected}, got {actual}"
            )
            return False
        return True
        
    def get_errors(self) -> List[str]:
        """Return accumulated errors."""
        return self.errors.copy()


class GPIOScoreboard:
    """
    Scoreboard for comparing GPIO model vs RTL.
    """
    
    def __init__(self):
        self.model = GPIO8Model()
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
        
    def write(self, offset: int, value: int):
        """Apply write to model."""
        self.model.write_register(offset, value)
        
    def read(self, offset: int) -> int:
        """Read from model."""
        return self.model.read_register(offset)
        
    def set_inputs(self, value: int):
        """Set input pins."""
        self.model.set_inputs(value)
        
    def tick(self):
        """Clock tick."""
        self.model.clock_tick()
        
    def compare_output(self, rtl_output: int, rtl_oe: int) -> bool:
        """Compare model output with RTL."""
        self.comparisons += 1
        
        model_output = self.model.get_outputs()
        model_oe = self.model.get_output_enable()
        
        match = True
        
        if model_oe != rtl_oe:
            match = False
            self.mismatch_log.append(
                f"OE mismatch: model=0x{model_oe:02X}, rtl=0x{rtl_oe:02X}"
            )
            
        # Only compare outputs where OE is set
        masked_model = model_output & model_oe
        masked_rtl = rtl_output & rtl_oe
        
        if masked_model != masked_rtl:
            match = False
            self.mismatch_log.append(
                f"Output mismatch: model=0x{masked_model:02X}, rtl=0x{masked_rtl:02X}"
            )
            
        if match:
            self.matches += 1
        else:
            self.mismatches += 1
            
        return match
        
    def compare_irq(self, rtl_irq: bool) -> bool:
        """Compare model IRQ with RTL."""
        self.comparisons += 1
        
        model_irq = self.model.get_irq()
        
        if model_irq != rtl_irq:
            self.mismatches += 1
            self.mismatch_log.append(
                f"IRQ mismatch: model={model_irq}, rtl={rtl_irq}"
            )
            return False
            
        self.matches += 1
        return True
        
    def report(self) -> str:
        """Generate comparison report."""
        report = f"GPIO Scoreboard Report:\n"
        report += f"  Total comparisons: {self.comparisons}\n"
        report += f"  Matches: {self.matches}\n"
        report += f"  Mismatches: {self.mismatches}\n"
        
        if self.mismatch_log:
            report += "  Recent mismatches:\n"
            for entry in self.mismatch_log[-10:]:
                report += f"    - {entry}\n"
                
        return report


class GPIOCoverageCollector:
    """
    Coverage collector for GPIO verification.
    """
    
    def __init__(self):
        self.reset()
        
    def reset(self):
        """Reset coverage."""
        self.output_values_seen = set()
        self.direction_configs_seen = set()
        self.interrupt_types_seen = set()
        self.register_accesses = {reg.name: 0 for reg in GPIORegister}
        self.edge_transitions = {'rising': 0, 'falling': 0}
        
    def sample_output(self, value: int):
        """Sample output value."""
        self.output_values_seen.add(value & 0xFF)
        
    def sample_direction(self, value: int):
        """Sample direction configuration."""
        self.direction_configs_seen.add(value & 0xFF)
        
    def sample_register_access(self, offset: int, is_write: bool):
        """Sample register access."""
        for reg in GPIORegister:
            if offset == reg.value:
                self.register_accesses[reg.name] += 1
                break
                
    def sample_interrupt(self, ris: int):
        """Sample interrupt status."""
        for i in range(32):
            if ris & (1 << i):
                self.interrupt_types_seen.add(i)
                
    def sample_edge(self, prev: int, curr: int):
        """Sample pin transitions."""
        for i in range(8):
            prev_bit = (prev >> i) & 1
            curr_bit = (curr >> i) & 1
            if prev_bit == 0 and curr_bit == 1:
                self.edge_transitions['rising'] += 1
            elif prev_bit == 1 and curr_bit == 0:
                self.edge_transitions['falling'] += 1
                
    def get_coverage_report(self) -> dict:
        """Generate coverage report."""
        return {
            'output_values_coverage': len(self.output_values_seen) / 256 * 100,
            'direction_configs_coverage': len(self.direction_configs_seen) / 256 * 100,
            'interrupt_types_coverage': len(self.interrupt_types_seen) / 32 * 100,
            'register_accesses': dict(self.register_accesses),
            'edge_transitions': dict(self.edge_transitions),
            'unique_outputs': len(self.output_values_seen),
            'unique_directions': len(self.direction_configs_seen),
            'unique_interrupts': len(self.interrupt_types_seen)
        }
