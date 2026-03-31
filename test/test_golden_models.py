# Unit Tests for Golden Models
# SPDX-FileCopyrightText: 2026 TSARKA
# SPDX-License-Identifier: Apache-2.0

"""
Unit tests for golden models - can run without RTL simulation.
Validates golden model correctness before use in RTL verification.
"""

import unittest
import sys
import os

# Add test directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from golden_models.wishbone_model import (
    WishboneMaster, WishboneSlave, WishboneSignals, 
    WishboneTransaction, WishboneMonitor, WishboneScoreboard
)
from golden_models.uart_model import (
    UART16550Model, UARTRegister, UARTConfig, UARTBitBangModel
)
from golden_models.gpio_model import (
    GPIO8Model, GPIORegister, GPIOScoreboard, GPIOCoverageCollector
)
from golden_models.wb_bridge_model import (
    TinyQVWishboneBridgeModel, CPUTransaction, TransactionSize,
    ByteSelectTestVectors, DataSteeringTestVectors
)


class TestWishboneMaster(unittest.TestCase):
    """Tests for Wishbone master model."""
    
    def setUp(self):
        self.master = WishboneMaster()
        
    def test_reset(self):
        """Test reset clears state."""
        self.master.initiate_write(0x1000, 0xDEADBEEF)
        self.master.reset()
        self.assertEqual(len(self.master.pending_transactions), 0)
        self.assertEqual(len(self.master.completed_transactions), 0)
        self.assertEqual(len(self.master.errors), 0)
        
    def test_read_transaction(self):
        """Test read transaction creation."""
        txn = self.master.initiate_read(0x1000)
        self.assertEqual(txn.address, 0x1000)
        self.assertFalse(txn.we)
        self.assertEqual(len(self.master.pending_transactions), 1)
        
    def test_write_transaction(self):
        """Test write transaction creation."""
        txn = self.master.initiate_write(0x2000, 0xCAFEBABE, sel=0x0F)
        self.assertEqual(txn.address, 0x2000)
        self.assertEqual(txn.data, 0xCAFEBABE)
        self.assertTrue(txn.we)
        
    def test_byte_select_generation(self):
        """Test byte select generation for different sizes."""
        # 8-bit at different offsets
        self.assertEqual(self.master.get_byte_select(0x00, 1), 0x1)
        self.assertEqual(self.master.get_byte_select(0x01, 1), 0x2)
        self.assertEqual(self.master.get_byte_select(0x02, 1), 0x4)
        self.assertEqual(self.master.get_byte_select(0x03, 1), 0x8)
        
        # 16-bit (addr[1] determines upper/lower)
        self.assertEqual(self.master.get_byte_select(0x00, 2), 0x3)  # Lower halfword
        self.assertEqual(self.master.get_byte_select(0x02, 2), 0xC)  # Upper halfword
        
        # 32-bit
        self.assertEqual(self.master.get_byte_select(0x00, 4), 0xF)
        
    def test_protocol_violation_stb_without_cyc(self):
        """Test detection of STB without CYC."""
        signals = WishboneSignals(cyc=False, stb=True)
        self.master.update_signals(signals)
        self.assertIn("STB asserted while CYC negated", self.master.errors[0])


class TestWishboneSlave(unittest.TestCase):
    """Tests for Wishbone slave model."""
    
    def setUp(self):
        self.slave = WishboneSlave(base_address=0x3000, address_mask=0xF000)
        
    def test_address_hit(self):
        """Test address decoding."""
        self.assertTrue(self.slave.address_hit(0x3000))
        self.assertTrue(self.slave.address_hit(0x3FFF))
        self.assertFalse(self.slave.address_hit(0x4000))
        self.assertFalse(self.slave.address_hit(0x2000))
        
    def test_write_read_memory(self):
        """Test memory write and read."""
        signals = WishboneSignals(
            cyc=True, stb=True, we=True,
            adr=0x3000, dat_o=0x12345678, sel=0xF
        )
        self.slave.update_signals(signals)
        self.slave.update_signals(signals)  # ACK delay
        
        # Read back
        signals.we = False
        response = self.slave.update_signals(signals)
        self.assertEqual(self.slave.get_memory(0x3000), 0x12345678)
        
    def test_byte_write(self):
        """Test byte-granularity writes."""
        # Write single byte at offset 1
        signals = WishboneSignals(
            cyc=True, stb=True, we=True,
            adr=0x3001, dat_o=0x0000AB00, sel=0x2
        )
        self.slave.update_signals(signals)
        self.slave.update_signals(signals)
        
        mem = self.slave.get_memory(0x3000)
        self.assertEqual((mem >> 8) & 0xFF, 0xAB)


class TestUART16550Model(unittest.TestCase):
    """Tests for UART model."""
    
    def setUp(self):
        self.uart = UART16550Model(clock_freq_hz=50_000_000)
        
    def test_reset(self):
        """Test reset state."""
        self.uart.reset()
        # LSR should have THRE and TEMT set
        lsr = self.uart.read_register(UARTRegister.LSR)
        self.assertEqual(lsr & 0x60, 0x60)
        
    def test_divisor_setting(self):
        """Test baud rate divisor."""
        # Enable DLAB
        self.uart.write_register(UARTRegister.LCR, 0x80)
        self.uart.write_register(UARTRegister.DLL, 27)
        self.uart.write_register(UARTRegister.DLM, 0)
        
        baud = self.uart.get_baud_rate()
        # Should be approximately 115200
        self.assertGreater(baud, 100000)
        self.assertLess(baud, 130000)
        
    def test_lcr_configuration(self):
        """Test LCR decoding."""
        self.uart.write_register(UARTRegister.LCR, 0x03)  # 8N1
        config = self.uart.get_config()
        self.assertEqual(config.data_bits, 8)
        self.assertEqual(config.stop_bits, 1)
        self.assertFalse(config.parity_enable)
        
    def test_scratch_register(self):
        """Test scratch register read/write."""
        self.uart.write_register(UARTRegister.SCR, 0xAB)
        self.assertEqual(self.uart.read_register(UARTRegister.SCR), 0xAB)
        
    def test_fifo_enable(self):
        """Test FIFO enable."""
        self.uart.write_register(UARTRegister.FCR, 0x01)
        self.assertTrue(self.uart.fifo_enabled)
        
    def test_receive_byte(self):
        """Test byte reception."""
        self.uart.write_register(UARTRegister.FCR, 0x01)  # Enable FIFO
        self.uart.write_register(UARTRegister.LCR, 0x03)  # 8N1
        self.uart.send_byte(0x41)
        
        lsr = self.uart.read_register(UARTRegister.LSR)
        self.assertTrue(lsr & 0x01)  # DR set
        
        data = self.uart.read_register(UARTRegister.RBR)
        self.assertEqual(data, 0x41)


class TestUARTBitBang(unittest.TestCase):
    """Tests for UART bit-bang model."""
    
    def setUp(self):
        self.bb = UARTBitBangModel(baud_rate=115200)
        
    def test_encode_byte(self):
        """Test byte encoding to bit stream."""
        bits = self.bb.encode_byte(0x55, data_bits=8)  # 01010101
        
        # Start bit
        self.assertEqual(bits[0], 0)
        # Data bits (LSB first): 1,0,1,0,1,0,1,0
        self.assertEqual(bits[1:9], [1, 0, 1, 0, 1, 0, 1, 0])
        # Stop bit
        self.assertEqual(bits[9], 1)
        
    def test_decode_bits(self):
        """Test bit stream decoding."""
        bits = [0, 1, 0, 1, 0, 1, 0, 1, 0, 1]  # Start, 0x55, Stop
        data = self.bb.decode_bits(bits)
        self.assertEqual(data, 0x55)
        
    def test_encode_decode_roundtrip(self):
        """Test encoding then decoding."""
        for test_byte in [0x00, 0xFF, 0x55, 0xAA, 0x12]:
            bits = self.bb.encode_byte(test_byte)
            decoded = self.bb.decode_bits(bits)
            self.assertEqual(decoded, test_byte)


class TestGPIO8Model(unittest.TestCase):
    """Tests for GPIO model."""
    
    def setUp(self):
        self.gpio = GPIO8Model()
        self.gpio.gclk = 1  # Enable clock
        
    def test_reset(self):
        """Test reset state."""
        self.gpio.reset()
        self.assertEqual(self.gpio.datao, 0)
        self.assertEqual(self.gpio.dir, 0)
        
    def test_output_direction(self):
        """Test output direction control."""
        self.gpio.write_register(GPIORegister.DIR, 0xFF)
        self.assertEqual(self.gpio.get_output_enable(), 0xFF)
        
        self.gpio.write_register(GPIORegister.DIR, 0x0F)
        self.assertEqual(self.gpio.get_output_enable(), 0x0F)
        
    def test_output_value(self):
        """Test output value."""
        self.gpio.write_register(GPIORegister.DIR, 0xFF)
        self.gpio.write_register(GPIORegister.DATAO, 0xA5)
        self.assertEqual(self.gpio.get_outputs(), 0xA5)
        
    def test_input_synchronizer(self):
        """Test input synchronization delay."""
        self.gpio.set_inputs(0xFF)
        
        # First tick - stage 1
        self.gpio.clock_tick()
        self.assertEqual(self.gpio.read_register(GPIORegister.DATAI), 0)
        
        # Second tick - stage 2
        self.gpio.clock_tick()
        self.assertEqual(self.gpio.read_register(GPIORegister.DATAI), 0xFF)
        
    def test_interrupt_mask(self):
        """Test interrupt masking."""
        self.gpio.write_register(GPIORegister.IM, 0x00000001)  # Enable pin 0 high
        self.gpio.set_inputs(0x01)
        self.gpio.clock_tick()
        self.gpio.clock_tick()
        
        mis = self.gpio.read_register(GPIORegister.MIS)
        self.assertTrue(mis & 0x01)
        
    def test_interrupt_clear(self):
        """Test interrupt clearing."""
        self.gpio.write_register(GPIORegister.IM, 0x00000001)
        self.gpio.set_inputs(0x01)
        self.gpio.clock_tick()
        self.gpio.clock_tick()
        
        # Clear interrupt
        self.gpio.write_register(GPIORegister.IC, 0x00000001)
        
        ris = self.gpio.read_register(GPIORegister.RIS)
        self.assertFalse(ris & 0x01)


class TestTinyQVBridge(unittest.TestCase):
    """Tests for Wishbone bridge model."""
    
    def setUp(self):
        self.bridge = TinyQVWishboneBridgeModel()
        
    def test_byte_select_8bit(self):
        """Test 8-bit byte select."""
        for addr, expected in ByteSelectTestVectors.get_8bit_vectors():
            actual = self.bridge._calc_byte_select(addr, TransactionSize.SIZE_8BIT)
            self.assertEqual(actual, expected, f"Failed at address 0x{addr:08X}")
            
    def test_byte_select_16bit(self):
        """Test 16-bit byte select."""
        for addr, expected in ByteSelectTestVectors.get_16bit_vectors():
            actual = self.bridge._calc_byte_select(addr, TransactionSize.SIZE_16BIT)
            self.assertEqual(actual, expected, f"Failed at address 0x{addr:08X}")
            
    def test_byte_select_32bit(self):
        """Test 32-bit byte select."""
        for addr, expected in ByteSelectTestVectors.get_32bit_vectors():
            actual = self.bridge._calc_byte_select(addr, TransactionSize.SIZE_32BIT)
            self.assertEqual(actual, expected, f"Failed at address 0x{addr:08X}")
            
    def test_data_steering_8bit(self):
        """Test 8-bit data steering."""
        for input_data, expected in DataSteeringTestVectors.get_8bit_vectors():
            actual = self.bridge._steer_write_data(input_data, TransactionSize.SIZE_8BIT)
            self.assertEqual(actual, expected)
            
    def test_data_steering_16bit(self):
        """Test 16-bit data steering."""
        for input_data, expected in DataSteeringTestVectors.get_16bit_vectors():
            actual = self.bridge._steer_write_data(input_data, TransactionSize.SIZE_16BIT)
            self.assertEqual(actual, expected)
            
    def test_data_steering_32bit(self):
        """Test 32-bit data steering."""
        for input_data, expected in DataSteeringTestVectors.get_32bit_vectors():
            actual = self.bridge._steer_write_data(input_data, TransactionSize.SIZE_32BIT)
            self.assertEqual(actual, expected)
            
    def test_timeout_mechanism(self):
        """Test bridge timeout."""
        cpu_txn = CPUTransaction(address=0x05000000, read_n=0b10)
        
        # Simulate cycles without ACK
        for cycle in range(150):
            _, ready = self.bridge.clock_tick(cpu_txn, wb_ack=False)
            if ready:
                self.assertGreaterEqual(cycle, 127)
                return
                
        self.fail("Timeout never triggered")
        
    def test_ack_handling(self):
        """Test ACK signal handling."""
        cpu_txn = CPUTransaction(address=0x05000000, read_n=0b10)
        
        # First cycle - no ACK yet
        _, ready = self.bridge.clock_tick(cpu_txn, wb_ack=False)
        self.assertFalse(ready)
        
        # Second cycle - ACK
        data, ready = self.bridge.clock_tick(cpu_txn, wb_ack=True, wb_data=0xDEADBEEF)
        self.assertTrue(ready)
        self.assertEqual(data, 0xDEADBEEF)
        
    def test_transaction_translation(self):
        """Test CPU to Wishbone translation."""
        # Read transaction
        cpu_txn = CPUTransaction(address=0x03000004, read_n=0b10)
        wb_txn = self.bridge.translate_transaction(cpu_txn)
        
        self.assertTrue(wb_txn.cyc)
        self.assertTrue(wb_txn.stb)
        self.assertFalse(wb_txn.we)
        self.assertEqual(wb_txn.address, 0x03000004)
        self.assertEqual(wb_txn.sel, 0xF)
        
        # Write transaction
        cpu_txn = CPUTransaction(
            address=0x03000008, data=0xCAFEBABE, write_n=0b10
        )
        self.bridge.reset()  # Reset ack_seen
        wb_txn = self.bridge.translate_transaction(cpu_txn)
        
        self.assertTrue(wb_txn.we)
        self.assertEqual(wb_txn.data, 0xCAFEBABE)


class TestWishboneScoreboard(unittest.TestCase):
    """Tests for Wishbone scoreboard."""
    
    def setUp(self):
        self.scoreboard = WishboneScoreboard()
        
    def test_matching_transactions(self):
        """Test matching transaction comparison."""
        expected = WishboneTransaction(address=0x1000, data=0x1234, we=True, sel=0xF)
        actual = WishboneTransaction(address=0x1000, data=0x1234, we=True, sel=0xF)
        
        self.scoreboard.add_expected(expected)
        self.scoreboard.add_actual(actual)
        
        self.assertEqual(self.scoreboard.matches, 1)
        self.assertEqual(self.scoreboard.mismatches, 0)
        
    def test_mismatching_transactions(self):
        """Test mismatched transaction detection."""
        expected = WishboneTransaction(address=0x1000, data=0x1234, we=True, sel=0xF)
        actual = WishboneTransaction(address=0x2000, data=0x1234, we=True, sel=0xF)
        
        self.scoreboard.add_expected(expected)
        self.scoreboard.add_actual(actual)
        
        self.assertEqual(self.scoreboard.matches, 0)
        self.assertEqual(self.scoreboard.mismatches, 1)
        self.assertIn("Address mismatch", self.scoreboard.mismatch_details[0])


class TestGPIOScoreboard(unittest.TestCase):
    """Tests for GPIO scoreboard."""
    
    def setUp(self):
        self.scoreboard = GPIOScoreboard()
        self.scoreboard.model.gclk = 1
        
    def test_output_comparison(self):
        """Test output comparison."""
        self.scoreboard.write(GPIORegister.DIR, 0xFF)
        self.scoreboard.write(GPIORegister.DATAO, 0xA5)
        
        # Should match
        self.assertTrue(self.scoreboard.compare_output(0xA5, 0xFF))
        self.assertEqual(self.scoreboard.matches, 1)
        
    def test_output_mismatch(self):
        """Test output mismatch detection."""
        self.scoreboard.write(GPIORegister.DIR, 0xFF)
        self.scoreboard.write(GPIORegister.DATAO, 0xA5)
        
        # Should mismatch
        self.assertFalse(self.scoreboard.compare_output(0x5A, 0xFF))
        self.assertEqual(self.scoreboard.mismatches, 1)


class TestGPIOCoverage(unittest.TestCase):
    """Tests for GPIO coverage collector."""
    
    def setUp(self):
        self.coverage = GPIOCoverageCollector()
        
    def test_output_coverage(self):
        """Test output value coverage."""
        for i in range(256):
            self.coverage.sample_output(i)
            
        report = self.coverage.get_coverage_report()
        self.assertEqual(report['output_values_coverage'], 100.0)
        
    def test_direction_coverage(self):
        """Test direction configuration coverage."""
        for i in range(256):
            self.coverage.sample_direction(i)
            
        report = self.coverage.get_coverage_report()
        self.assertEqual(report['direction_configs_coverage'], 100.0)
        
    def test_edge_sampling(self):
        """Test edge transition sampling."""
        self.coverage.sample_edge(0x00, 0x01)  # Rising on pin 0
        self.coverage.sample_edge(0x01, 0x00)  # Falling on pin 0
        
        report = self.coverage.get_coverage_report()
        self.assertEqual(report['edge_transitions']['rising'], 1)
        self.assertEqual(report['edge_transitions']['falling'], 1)


if __name__ == '__main__':
    unittest.main(verbosity=2)
