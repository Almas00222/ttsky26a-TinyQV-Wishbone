ROOT_DIR := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))
SRC_DIR := $(ROOT_DIR)src
TEST_DIR := $(ROOT_DIR)test
FORMAL_DIR := $(ROOT_DIR)formal

PROJECT_SOURCES := \
	$(SRC_DIR)/project.v \
	$(SRC_DIR)/TinyQV/tinyqv.v \
	$(SRC_DIR)/TinyQV/alu.v \
	$(SRC_DIR)/TinyQV/core.v \
	$(SRC_DIR)/TinyQV/counter.v \
	$(SRC_DIR)/TinyQV/cpu.v \
	$(SRC_DIR)/TinyQV/decode.v \
	$(SRC_DIR)/TinyQV/latch_reg.v \
	$(SRC_DIR)/TinyQV/mem_ctrl.v \
	$(SRC_DIR)/TinyQV/qspi_ctrl.v \
	$(SRC_DIR)/TinyQV/register.v \
	$(SRC_DIR)/TinyQV/time.v \
	$(SRC_DIR)/TinyQV/wb_bridge.v \
	$(SRC_DIR)/Peripherals/GPIO/adapter_wb.v \
	$(SRC_DIR)/Peripherals/GPIO/EF_GPIO8_WB.v \
	$(SRC_DIR)/Peripherals/GPIO/EF_GPIO8.v \
	$(SRC_DIR)/Peripherals/GPIO/ef_util_stubs.v \
	$(SRC_DIR)/Peripherals/UART16550/raminfr.v \
	$(SRC_DIR)/Peripherals/UART16550/timescale.v \
	$(SRC_DIR)/Peripherals/UART16550/uart_debug_if.v \
	$(SRC_DIR)/Peripherals/UART16550/uart_defines.v \
	$(SRC_DIR)/Peripherals/UART16550/uart_receiver.v \
	$(SRC_DIR)/Peripherals/UART16550/uart_regs.v \
	$(SRC_DIR)/Peripherals/UART16550/uart_rfifo.v \
	$(SRC_DIR)/Peripherals/UART16550/uart_sync_flops.v \
	$(SRC_DIR)/Peripherals/UART16550/uart_tfifo.v \
	$(SRC_DIR)/Peripherals/UART16550/uart_top.v \
	$(SRC_DIR)/Peripherals/UART16550/uart_transmitter.v \
	$(SRC_DIR)/Peripherals/UART16550/uart_wb.v \
	$(SRC_DIR)/Peripherals/UART16550/wb_uart16550_adapter.v

INCLUDE_DIRS := \
	-I$(SRC_DIR) \
	-I$(SRC_DIR)/TinyQV \
	-I$(SRC_DIR)/Peripherals/GPIO \
	-I$(SRC_DIR)/Peripherals/UART16550

.PHONY: firmware stage-gate-netlist synth-gate-netlist \
	test-rtl test-golden test-comprehensive test-firmware test-gatelevel test-all test-gatelevel-smoke \
	test-rtl-seeds test-comprehensive-seeds test-firmware-seeds test-gatelevel-smoke-seeds \
	lint-iverilog lint-verilator formal-qspi formal-qspi-boolector \
	formal-wb-bridge formal-wb-bridge-boolector clean

RANDOM_SEEDS ?= 1 2 3 4 5 6 7 8 9 10

firmware:
	$(MAKE) -C $(TEST_DIR) firmware

test-rtl:
	$(MAKE) -C $(TEST_DIR) test-rtl

test-golden:
	$(MAKE) -C $(TEST_DIR) test-golden

test-comprehensive:
	$(MAKE) -C $(TEST_DIR) test-comprehensive

test-firmware:
	$(MAKE) -C $(TEST_DIR) test-firmware

stage-gate-netlist:
	$(MAKE) -C $(TEST_DIR) stage-gate-netlist

synth-gate-netlist:
	$(MAKE) -C $(TEST_DIR) synth-gate-netlist

test-gatelevel:
	$(MAKE) -C $(TEST_DIR) test-gatelevel

test-gatelevel-smoke:
	$(MAKE) -C $(TEST_DIR) test-gatelevel-smoke

test-rtl-seeds:
	$(MAKE) -C $(TEST_DIR) test-rtl-seeds RANDOM_SEEDS="$(RANDOM_SEEDS)"

test-comprehensive-seeds:
	$(MAKE) -C $(TEST_DIR) test-comprehensive-seeds RANDOM_SEEDS="$(RANDOM_SEEDS)"

test-firmware-seeds:
	$(MAKE) -C $(TEST_DIR) test-firmware-seeds RANDOM_SEEDS="$(RANDOM_SEEDS)"

test-gatelevel-smoke-seeds:
	$(MAKE) -C $(TEST_DIR) test-gatelevel-smoke-seeds RANDOM_SEEDS="$(RANDOM_SEEDS)"

test-all: test-golden test-rtl test-comprehensive

lint-iverilog:
	iverilog -g2012 -Wall $(INCLUDE_DIRS) -s tt_um_TSARKA_TinyQV $(PROJECT_SOURCES) -o /tmp/tinyqv_iverilog_lint.out

lint-verilator:
	verilator --lint-only -Wall --top-module tt_um_TSARKA_TinyQV \
		-Wno-DECLFILENAME -Wno-UNUSEDSIGNAL -Wno-UNDRIVEN \
		$(INCLUDE_DIRS) $(PROJECT_SOURCES)

formal-qspi:
	sby -f $(FORMAL_DIR)/qspi_ctrl_abc.sby

formal-qspi-boolector:
	$(MAKE) formal-qspi

formal-wb-bridge:
	sby -f $(FORMAL_DIR)/tinyqv_wb_bridge_abc.sby

formal-wb-bridge-boolector:
	$(MAKE) formal-wb-bridge

clean:
	$(MAKE) -C $(TEST_DIR) clean-all
