# Golden Models for TinyQV SoC Verification
# SPDX-FileCopyrightText: 2026 TSARKA
# SPDX-License-Identifier: Apache-2.0

"""
Golden reference models for verification of TinyQV SoC components:
- Wishbone Bus Protocol
- UART16550 
- GPIO8 (Efabless)
- TinyQV CPU Wishbone Bridge
"""

from .wishbone_model import (
    WishboneMaster, WishboneSlave, WishboneTransaction,
    WishboneSignals, WishboneMonitor, WishboneScoreboard, WishboneCycleType
)
from .uart_model import (
    UART16550Model, UARTRegister, UARTBitBangModel,
    UARTInterrupt, UARTConfig, UARTFrame
)
from .gpio_model import (
    GPIO8Model, GPIORegister, GPIOScoreboard, GPIOCoverageCollector,
    GPIOInterruptType, GPIOPinState
)
from .wb_bridge_model import (
    TinyQVWishboneBridgeModel, CPUTransaction, WishboneBridgeScoreboard,
    ByteSelectTestVectors, DataSteeringTestVectors, TransactionSize, WBTransaction
)

__all__ = [
    # Wishbone
    'WishboneMaster',
    'WishboneSlave', 
    'WishboneTransaction',
    'WishboneSignals',
    'WishboneMonitor',
    'WishboneScoreboard',
    'WishboneCycleType',
    # UART
    'UART16550Model',
    'UARTRegister',
    'UARTBitBangModel',
    'UARTInterrupt',
    'UARTConfig',
    'UARTFrame',
    # GPIO
    'GPIO8Model',
    'GPIORegister',
    'GPIOScoreboard',
    'GPIOCoverageCollector',
    'GPIOInterruptType',
    'GPIOPinState',
    # Bridge
    'TinyQVWishboneBridgeModel',
    'CPUTransaction',
    'WishboneBridgeScoreboard',
    'ByteSelectTestVectors',
    'DataSteeringTestVectors',
    'TransactionSize',
    'WBTransaction',
]
