# Makefile for Tiny Tapeout RTL/gate-level simulation with cocotb

SIM ?= icarus
WAVES ?= 1
TOPLEVEL_LANG ?= verilog
.DEFAULT_GOAL := all

TEST_DIR := $(CURDIR)
SRC_DIR := $(TEST_DIR)/../src
TOP_MODULE := $(shell python3 $(TEST_DIR)/gate_level_tools.py top-module 2>/dev/null)
TEST_VENV_DIR := $(TEST_DIR)/.venv
TEST_VENV_PYTHON := $(TEST_VENV_DIR)/bin/python

ifneq ($(wildcard $(TEST_VENV_DIR)/bin),)
export PATH := $(TEST_VENV_DIR)/bin:$(PATH)
export VIRTUAL_ENV := $(TEST_VENV_DIR)
PYTHON_BIN := $(TEST_VENV_PYTHON)
endif

PROJECT_SOURCES = \
	project.v \
	TinyQV/tinyqv.v \
	TinyQV/alu.v \
	TinyQV/core.v \
	TinyQV/counter.v \
	TinyQV/cpu.v \
	TinyQV/decode.v \
	TinyQV/latch_reg.v \
	TinyQV/mem_ctrl.v \
	TinyQV/qspi_ctrl.v \
	TinyQV/register.v \
	TinyQV/time.v \
	TinyQV/wb_bridge.v \
	Peripherals/GPIO/adapter_wb.v \
	Peripherals/GPIO/EF_GPIO8_WB.v \
	Peripherals/GPIO/EF_GPIO8.v \
	Peripherals/GPIO/ef_util_stubs.v \
	Peripherals/UART16550/raminfr.v \
	Peripherals/UART16550/timescale.v \
	Peripherals/UART16550/uart_debug_if.v \
	Peripherals/UART16550/uart_defines.v \
	Peripherals/UART16550/uart_receiver.v \
	Peripherals/UART16550/uart_regs.v \
	Peripherals/UART16550/uart_rfifo.v \
	Peripherals/UART16550/uart_sync_flops.v \
	Peripherals/UART16550/uart_tfifo.v \
	Peripherals/UART16550/uart_top.v \
	Peripherals/UART16550/uart_transmitter.v \
	Peripherals/UART16550/uart_wb.v \
	Peripherals/UART16550/wb_uart16550_adapter.v

RTL_VERILOG_SOURCES := $(addprefix $(SRC_DIR)/,$(PROJECT_SOURCES)) $(TEST_DIR)/tb.v $(TEST_DIR)/sim_qspi_soc.v
BASE_COMPILE_ARGS := -DSIM
BASE_COMPILE_ARGS += -I$(SRC_DIR)
BASE_COMPILE_ARGS += -I$(SRC_DIR)/TinyQV
BASE_COMPILE_ARGS += -I$(SRC_DIR)/Peripherals/GPIO
BASE_COMPILE_ARGS += -I$(SRC_DIR)/Peripherals/UART16550

FIRMWARE_HEX ?= $(TEST_DIR)/firmware/gpio_uart_combo.hex
export TEST_FIRMWARE_HEX := $(abspath $(FIRMWARE_HEX))
PLUSARGS += +firmware=$(TEST_FIRMWARE_HEX)
RANDOM_SEEDS ?= 1 2 3 4 5 6 7 8 9 10
SKY130_SIM_MODELS := $(shell python3 $(TEST_DIR)/gate_level_tools.py sim-models 2>/dev/null)
SKY130_LIBERTY := $(shell python3 $(TEST_DIR)/gate_level_tools.py liberty 2>/dev/null)
GL_POWER_DEFINE := $(shell python3 $(TEST_DIR)/gate_level_tools.py netlist-has-power-pins 2>/dev/null)
GL_COMPILE_ARGS := $(BASE_COMPILE_ARGS) -DGL_TEST -DFUNCTIONAL -DUNIT_DELAY=\#1
ifeq ($(strip $(GL_POWER_DEFINE)),1)
GL_COMPILE_ARGS += -DGL_USE_POWER_PINS
endif
GL_VERILOG_SOURCES := $(SKY130_SIM_MODELS) $(TEST_DIR)/gate_level_netlist.v $(TEST_DIR)/tb.v $(TEST_DIR)/sim_qspi_soc.v

ifeq ($(GL_TEST),1)
VERILOG_SOURCES := $(GL_VERILOG_SOURCES)
COMPILE_ARGS += $(GL_COMPILE_ARGS)
else
VERILOG_SOURCES := $(RTL_VERILOG_SOURCES)
COMPILE_ARGS += $(BASE_COMPILE_ARGS)
endif

export PYTHONPATH := $(TEST_DIR):$(PYTHONPATH)

TOPLEVEL := tb
MODULE ?= test_rtl

GL_SMOKE_RESULTS := \
	gl-smoke-reset-results.xml \
	gl-smoke-uio-results.xml \
	gl-smoke-mux-results.xml \
	gl-smoke-chip-select-results.xml \
	gl-smoke-boot-results.xml \
	gl-smoke-stability-results.xml

GL_DEEP_RESULTS := \
	gl-deep-reset-results.xml \
	gl-deep-chip-select-results.xml \
	gl-deep-mux-results.xml \
	gl-deep-flash-fetch-results.xml \
	gl-deep-qspi-protocol-results.xml \
	gl-deep-alu-signature-results.xml \
	gl-deep-alu-stress-seed1-results.xml \
	gl-deep-alu-stress-seed2-results.xml \
	gl-deep-ram-signature-results.xml \
	gl-deep-bus-stress-seed1-results.xml \
	gl-deep-bus-stress-seed2-results.xml \
	gl-deep-uart-scratch-results.xml \
	gl-deep-gpio-write-results.xml \
	gl-deep-gpio-readback-results.xml \
	gl-deep-gpio-uart-results.xml \
	gl-deep-uart-banner-results.xml \
	gl-deep-uart-hello-results.xml \
	gl-deep-uart-prime-results.xml \
	gl-deep-uart-loopback-results.xml \
	gl-deep-timer-results.xml \
	gl-deep-irq-results.xml

COCOTB_MAKEFILES := $(shell cocotb-config --makefiles 2>/dev/null)
ifeq ($(strip $(COCOTB_MAKEFILES)),)
HAVE_COCOTB := 0
else
HAVE_COCOTB := 1
include $(COCOTB_MAKEFILES)/Makefile.sim
endif

.PHONY: all deep-gl-results smoke-gl-results require-cocotb require-gate-netlist \
	require-sky130-models require-sky130-liberty stage-gate-netlist synth-gate-netlist \
	check-results merge-results run-gl-case firmware test-rtl test-golden \
	test-comprehensive test-firmware test-gatelevel test-gatelevel-smoke \
	test-rtl-seeds test-comprehensive-seeds test-firmware-seeds test-gatelevel-smoke-seeds \
	test-all clean-all help $(GL_SMOKE_RESULTS) $(GL_DEEP_RESULTS)

require-cocotb:
	@if ! command -v cocotb-config >/dev/null 2>&1; then \
		echo "cocotb-config not found on PATH. Activate the test virtualenv or install test dependencies first."; \
		exit 1; \
	fi

require-gate-netlist:
	@python3 $(TEST_DIR)/gate_level_tools.py stage-netlist >/dev/null || { \
		echo "No gate-level netlist found. Run 'make synth-gate-netlist' for a fast pre-layout netlist or 'make stage-gate-netlist' after Tiny Tapeout/OpenLane hardening."; \
		exit 1; \
	}

require-sky130-models:
	@if [ -z "$(strip $(SKY130_SIM_MODELS))" ]; then \
		echo "Could not locate sky130 simulation models. Set SKY130A or PDK_ROOT, or install the sky130 PDK."; \
		exit 1; \
	fi

require-sky130-liberty:
	@if [ -z "$(strip $(SKY130_LIBERTY))" ]; then \
		echo "Could not locate sky130 liberty files. Set SKY130A or PDK_ROOT, or install the sky130 PDK."; \
		exit 1; \
	fi

check-results:
	@test -f results.xml || { \
		echo "results.xml not found; cocotb did not produce JUnit output."; \
		exit 1; \
	}
	@python3 -c 'import sys, xml.etree.ElementTree as ET; root = ET.parse("results.xml").getroot(); failures = sum(len(tc.findall("failure")) + len(tc.findall("error")) for tc in root.iter("testcase")); print(f"Detected {failures} failing cocotb testcase(s) in results.xml") if failures else None; sys.exit(1 if failures else 0)'

merge-results:
	@python3 $(TEST_DIR)/merge_junit.py $(MERGE_INPUTS) > results.xml

run-gl-case: require-cocotb require-gate-netlist require-sky130-models
	rm -rf sim_build results.xml
	$(if $(strip $(CASE_FIRMWARE_HEX)),FIRMWARE_HEX=$(CASE_FIRMWARE_HEX),) GL_TEST=1 MODULE=$(CASE_MODULE) TESTCASE=$(CASE_TESTCASE) $(MAKE) -f $(firstword $(MAKEFILE_LIST)) sim
	$(MAKE) -f $(firstword $(MAKEFILE_LIST)) check-results
	mv results.xml $(CASE_RESULTS)

firmware:
	python3 gen_firmware.py

stage-gate-netlist:
	@python3 $(TEST_DIR)/gate_level_tools.py stage-netlist

synth-gate-netlist: require-sky130-liberty
	@echo "Synthesizing $(TOP_MODULE) to test/gate_level_netlist.v"
	yosys -q -p 'read_verilog -I$(SRC_DIR) -I$(SRC_DIR)/TinyQV -I$(SRC_DIR)/Peripherals/GPIO -I$(SRC_DIR)/Peripherals/UART16550 $(addprefix $(SRC_DIR)/,$(PROJECT_SOURCES)); hierarchy -check -top $(TOP_MODULE); synth -top $(TOP_MODULE); dfflibmap -liberty $(SKY130_LIBERTY); abc -liberty $(SKY130_LIBERTY); setundef -zero; clean; write_verilog -noattr $(TEST_DIR)/gate_level_netlist.v'

test-rtl: require-cocotb
	rm -rf sim_build results.xml
	MODULE=test_rtl $(MAKE) -f $(firstword $(MAKEFILE_LIST)) sim
	$(MAKE) -f $(firstword $(MAKEFILE_LIST)) check-results

test-golden:
	python3 -m pytest test_golden_models.py -v

test-comprehensive: require-cocotb
	rm -rf sim_build results.xml
	FIRMWARE_HEX=$(TEST_DIR)/firmware/alu_signature.hex MODULE=test_comprehensive TESTCASE=test_alu_signature $(MAKE) -f $(firstword $(MAKEFILE_LIST)) sim
	$(MAKE) -f $(firstword $(MAKEFILE_LIST)) check-results
	rm -rf sim_build results.xml
	FIRMWARE_HEX=$(TEST_DIR)/firmware/ram_signature.hex MODULE=test_comprehensive TESTCASE=test_ram_signature $(MAKE) -f $(firstword $(MAKEFILE_LIST)) sim
	$(MAKE) -f $(firstword $(MAKEFILE_LIST)) check-results
	rm -rf sim_build results.xml
	FIRMWARE_HEX=$(TEST_DIR)/firmware/uart_scratch_signature.hex MODULE=test_comprehensive TESTCASE=test_uart_scratch_signature $(MAKE) -f $(firstword $(MAKEFILE_LIST)) sim
	$(MAKE) -f $(firstword $(MAKEFILE_LIST)) check-results
	rm -rf sim_build results.xml
	FIRMWARE_HEX=$(TEST_DIR)/firmware/gpio_uart_combo.hex MODULE=test_comprehensive TESTCASE=test_combo_uart_byte_still_matches $(MAKE) -f $(firstword $(MAKEFILE_LIST)) sim
	$(MAKE) -f $(firstword $(MAKEFILE_LIST)) check-results
	$(MAKE) -f $(firstword $(MAKEFILE_LIST)) test-firmware

test-firmware: require-cocotb
	rm -rf sim_build results.xml
	FIRMWARE_HEX=$(TEST_DIR)/firmware/gpio_write.hex MODULE=test_firmware TESTCASE=test_gpio_write $(MAKE) -f $(firstword $(MAKEFILE_LIST)) sim
	$(MAKE) -f $(firstword $(MAKEFILE_LIST)) check-results
	rm -rf sim_build results.xml
	FIRMWARE_HEX=$(TEST_DIR)/firmware/gpio_readback.hex MODULE=test_firmware TESTCASE=test_gpio_readback $(MAKE) -f $(firstword $(MAKEFILE_LIST)) sim
	$(MAKE) -f $(firstword $(MAKEFILE_LIST)) check-results
	rm -rf sim_build results.xml
	FIRMWARE_HEX=$(TEST_DIR)/firmware/gpio_uart_combo.hex MODULE=test_firmware TESTCASE=test_gpio_uart_combo $(MAKE) -f $(firstword $(MAKEFILE_LIST)) sim
	$(MAKE) -f $(firstword $(MAKEFILE_LIST)) check-results
	rm -rf sim_build results.xml
	FIRMWARE_HEX=$(TEST_DIR)/firmware/uart_hello.hex MODULE=test_firmware TESTCASE=test_uart_hello $(MAKE) -f $(firstword $(MAKEFILE_LIST)) sim
	$(MAKE) -f $(firstword $(MAKEFILE_LIST)) check-results
	rm -rf sim_build results.xml
	FIRMWARE_HEX=$(TEST_DIR)/firmware/uart_banner.hex MODULE=test_firmware TESTCASE=test_uart_banner $(MAKE) -f $(firstword $(MAKEFILE_LIST)) sim
	$(MAKE) -f $(firstword $(MAKEFILE_LIST)) check-results
	rm -rf sim_build results.xml
	FIRMWARE_HEX=$(TEST_DIR)/firmware/uart_prime.hex MODULE=test_firmware TESTCASE=test_uart_prime $(MAKE) -f $(firstword $(MAKEFILE_LIST)) sim
	$(MAKE) -f $(firstword $(MAKEFILE_LIST)) check-results
	rm -rf sim_build results.xml
	FIRMWARE_HEX=$(TEST_DIR)/firmware/uart_loopback.hex MODULE=test_firmware TESTCASE=test_uart_loopback $(MAKE) -f $(firstword $(MAKEFILE_LIST)) sim
	$(MAKE) -f $(firstword $(MAKEFILE_LIST)) check-results
	rm -rf sim_build results.xml
	FIRMWARE_HEX=$(TEST_DIR)/firmware/timer_demo.hex MODULE=test_firmware TESTCASE=test_timer_demo $(MAKE) -f $(firstword $(MAKEFILE_LIST)) sim
	$(MAKE) -f $(firstword $(MAKEFILE_LIST)) check-results
	rm -rf sim_build results.xml
	FIRMWARE_HEX=$(TEST_DIR)/firmware/irq_demo.hex MODULE=test_firmware TESTCASE=test_irq_demo $(MAKE) -f $(firstword $(MAKEFILE_LIST)) sim
	$(MAKE) -f $(firstword $(MAKEFILE_LIST)) check-results

all: deep-gl-results

smoke-gl-results: $(GL_SMOKE_RESULTS)
	$(MAKE) -f $(firstword $(MAKEFILE_LIST)) merge-results MERGE_INPUTS="$(GL_SMOKE_RESULTS)"

deep-gl-results: $(GL_DEEP_RESULTS)
	$(MAKE) -f $(firstword $(MAKEFILE_LIST)) merge-results MERGE_INPUTS="$(GL_DEEP_RESULTS)"

test-gatelevel-smoke: smoke-gl-results
	$(MAKE) -f $(firstword $(MAKEFILE_LIST)) check-results

test-gatelevel: deep-gl-results
	$(MAKE) -f $(firstword $(MAKEFILE_LIST)) check-results

gl-smoke-reset-results.xml:
	$(MAKE) -f $(firstword $(MAKEFILE_LIST)) run-gl-case CASE_MODULE=test_gatelevel_smoke CASE_TESTCASE=test_gl_reset_and_uart_idle CASE_RESULTS=$@

gl-smoke-uio-results.xml:
	$(MAKE) -f $(firstword $(MAKEFILE_LIST)) run-gl-case CASE_MODULE=test_gatelevel_smoke CASE_TESTCASE=test_gl_uio_oe_reset_ownership CASE_RESULTS=$@

gl-smoke-mux-results.xml:
	$(MAKE) -f $(firstword $(MAKEFILE_LIST)) run-gl-case CASE_MODULE=test_gatelevel_smoke CASE_TESTCASE=test_gl_top_level_mux_and_uart_mirror CASE_RESULTS=$@

gl-smoke-chip-select-results.xml:
	$(MAKE) -f $(firstword $(MAKEFILE_LIST)) run-gl-case CASE_MODULE=test_gatelevel_smoke CASE_TESTCASE=test_gl_qspi_chip_select_exclusive CASE_RESULTS=$@

gl-smoke-boot-results.xml:
	$(MAKE) -f $(firstword $(MAKEFILE_LIST)) run-gl-case CASE_MODULE=test_gatelevel_smoke CASE_TESTCASE=test_gl_firmware_boot_reaches_gpio_signature CASE_FIRMWARE_HEX=$(TEST_DIR)/firmware/gpio_uart_combo.hex CASE_RESULTS=$@

gl-smoke-stability-results.xml:
	$(MAKE) -f $(firstword $(MAKEFILE_LIST)) run-gl-case CASE_MODULE=test_gatelevel_smoke CASE_TESTCASE=test_gl_firmware_gpio_stability CASE_FIRMWARE_HEX=$(TEST_DIR)/firmware/gpio_uart_combo.hex CASE_RESULTS=$@

gl-deep-reset-results.xml:
	$(MAKE) -f $(firstword $(MAKEFILE_LIST)) run-gl-case CASE_MODULE=test_gatelevel CASE_TESTCASE=test_gl_reset_tristate_and_uart_idle CASE_RESULTS=$@

gl-deep-chip-select-results.xml:
	$(MAKE) -f $(firstword $(MAKEFILE_LIST)) run-gl-case CASE_MODULE=test_gatelevel CASE_TESTCASE=test_gl_qspi_chip_select_exclusive CASE_RESULTS=$@

gl-deep-mux-results.xml:
	$(MAKE) -f $(firstword $(MAKEFILE_LIST)) run-gl-case CASE_MODULE=test_gatelevel CASE_TESTCASE=test_gl_output_mux_keeps_uart_on_uo0 CASE_FIRMWARE_HEX=$(TEST_DIR)/firmware/gpio_uart_combo.hex CASE_RESULTS=$@

gl-deep-flash-fetch-results.xml:
	$(MAKE) -f $(firstword $(MAKEFILE_LIST)) run-gl-case CASE_MODULE=test_gatelevel CASE_TESTCASE=test_gl_flash_fetch_startup_latency_sweep CASE_RESULTS=$@

gl-deep-qspi-protocol-results.xml:
	$(MAKE) -f $(firstword $(MAKEFILE_LIST)) run-gl-case CASE_MODULE=test_gatelevel CASE_TESTCASE=test_gl_qspi_protocol_firmware_roundtrip CASE_FIRMWARE_HEX=$(TEST_DIR)/firmware/qspi_protocol.hex CASE_RESULTS=$@

gl-deep-alu-signature-results.xml:
	$(MAKE) -f $(firstword $(MAKEFILE_LIST)) run-gl-case CASE_MODULE=test_gatelevel CASE_TESTCASE=test_gl_alu_signature CASE_FIRMWARE_HEX=$(TEST_DIR)/firmware/alu_signature.hex CASE_RESULTS=$@

gl-deep-alu-stress-seed1-results.xml:
	$(MAKE) -f $(firstword $(MAKEFILE_LIST)) run-gl-case CASE_MODULE=test_gatelevel CASE_TESTCASE=test_gl_alu_stress_seed1 CASE_FIRMWARE_HEX=$(TEST_DIR)/firmware/alu_stress_seed1.hex CASE_RESULTS=$@

gl-deep-alu-stress-seed2-results.xml:
	$(MAKE) -f $(firstword $(MAKEFILE_LIST)) run-gl-case CASE_MODULE=test_gatelevel CASE_TESTCASE=test_gl_alu_stress_seed2 CASE_FIRMWARE_HEX=$(TEST_DIR)/firmware/alu_stress_seed2.hex CASE_RESULTS=$@

gl-deep-ram-signature-results.xml:
	$(MAKE) -f $(firstword $(MAKEFILE_LIST)) run-gl-case CASE_MODULE=test_gatelevel CASE_TESTCASE=test_gl_ram_signature CASE_FIRMWARE_HEX=$(TEST_DIR)/firmware/ram_signature.hex CASE_RESULTS=$@

gl-deep-bus-stress-seed1-results.xml:
	$(MAKE) -f $(firstword $(MAKEFILE_LIST)) run-gl-case CASE_MODULE=test_gatelevel CASE_TESTCASE=test_gl_bus_stress_seed1 CASE_FIRMWARE_HEX=$(TEST_DIR)/firmware/bus_stress_seed1.hex CASE_RESULTS=$@

gl-deep-bus-stress-seed2-results.xml:
	$(MAKE) -f $(firstword $(MAKEFILE_LIST)) run-gl-case CASE_MODULE=test_gatelevel CASE_TESTCASE=test_gl_bus_stress_seed2 CASE_FIRMWARE_HEX=$(TEST_DIR)/firmware/bus_stress_seed2.hex CASE_RESULTS=$@

gl-deep-uart-scratch-results.xml:
	$(MAKE) -f $(firstword $(MAKEFILE_LIST)) run-gl-case CASE_MODULE=test_gatelevel CASE_TESTCASE=test_gl_uart_scratch_signature CASE_FIRMWARE_HEX=$(TEST_DIR)/firmware/uart_scratch_signature.hex CASE_RESULTS=$@

gl-deep-gpio-write-results.xml:
	$(MAKE) -f $(firstword $(MAKEFILE_LIST)) run-gl-case CASE_MODULE=test_gatelevel CASE_TESTCASE=test_gl_gpio_write CASE_FIRMWARE_HEX=$(TEST_DIR)/firmware/gpio_write.hex CASE_RESULTS=$@

gl-deep-gpio-readback-results.xml:
	$(MAKE) -f $(firstword $(MAKEFILE_LIST)) run-gl-case CASE_MODULE=test_gatelevel CASE_TESTCASE=test_gl_gpio_readback CASE_FIRMWARE_HEX=$(TEST_DIR)/firmware/gpio_readback.hex CASE_RESULTS=$@

gl-deep-gpio-uart-results.xml:
	$(MAKE) -f $(firstword $(MAKEFILE_LIST)) run-gl-case CASE_MODULE=test_gatelevel CASE_TESTCASE=test_gl_gpio_uart_combo CASE_FIRMWARE_HEX=$(TEST_DIR)/firmware/gpio_uart_combo.hex CASE_RESULTS=$@

gl-deep-uart-banner-results.xml:
	$(MAKE) -f $(firstword $(MAKEFILE_LIST)) run-gl-case CASE_MODULE=test_gatelevel CASE_TESTCASE=test_gl_uart_banner_latency_sweep CASE_FIRMWARE_HEX=$(TEST_DIR)/firmware/uart_banner.hex CASE_RESULTS=$@

gl-deep-uart-hello-results.xml:
	$(MAKE) -f $(firstword $(MAKEFILE_LIST)) run-gl-case CASE_MODULE=test_gatelevel CASE_TESTCASE=test_gl_uart_hello CASE_FIRMWARE_HEX=$(TEST_DIR)/firmware/uart_hello.hex CASE_RESULTS=$@

gl-deep-uart-prime-results.xml:
	$(MAKE) -f $(firstword $(MAKEFILE_LIST)) run-gl-case CASE_MODULE=test_gatelevel CASE_TESTCASE=test_gl_uart_prime CASE_FIRMWARE_HEX=$(TEST_DIR)/firmware/uart_prime.hex CASE_RESULTS=$@

gl-deep-uart-loopback-results.xml:
	$(MAKE) -f $(firstword $(MAKEFILE_LIST)) run-gl-case CASE_MODULE=test_gatelevel CASE_TESTCASE=test_gl_uart_loopback_seeded_stress CASE_FIRMWARE_HEX=$(TEST_DIR)/firmware/uart_loopback.hex CASE_RESULTS=$@

gl-deep-timer-results.xml:
	$(MAKE) -f $(firstword $(MAKEFILE_LIST)) run-gl-case CASE_MODULE=test_gatelevel CASE_TESTCASE=test_gl_timer_demo CASE_FIRMWARE_HEX=$(TEST_DIR)/firmware/timer_demo.hex CASE_RESULTS=$@

gl-deep-irq-results.xml:
	$(MAKE) -f $(firstword $(MAKEFILE_LIST)) run-gl-case CASE_MODULE=test_gatelevel CASE_TESTCASE=test_gl_irq_demo CASE_FIRMWARE_HEX=$(TEST_DIR)/firmware/irq_demo.hex CASE_RESULTS=$@

test-rtl-seeds: require-cocotb
	@for seed in $(RANDOM_SEEDS); do \
		echo "== test_rtl seed $$seed =="; \
		rm -rf sim_build results.xml; \
		RANDOM_SEED=$$seed MODULE=test_rtl $(MAKE) -f $(firstword $(MAKEFILE_LIST)) sim || exit $$?; \
		$(MAKE) -f $(firstword $(MAKEFILE_LIST)) check-results || exit $$?; \
	done

test-comprehensive-seeds: require-cocotb
	@for seed in $(RANDOM_SEEDS); do \
		echo "== test_comprehensive seed $$seed =="; \
		rm -rf sim_build results.xml; \
		RANDOM_SEED=$$seed MODULE=test_comprehensive $(MAKE) -f $(firstword $(MAKEFILE_LIST)) sim || exit $$?; \
		$(MAKE) -f $(firstword $(MAKEFILE_LIST)) check-results || exit $$?; \
	done

test-firmware-seeds: require-cocotb
	@for seed in $(RANDOM_SEEDS); do \
		echo "== test_firmware seed $$seed =="; \
		RANDOM_SEED=$$seed $(MAKE) -f $(firstword $(MAKEFILE_LIST)) test-firmware || exit $$?; \
	done

test-gatelevel-smoke-seeds: require-cocotb require-gate-netlist require-sky130-models
	@for seed in $(RANDOM_SEEDS); do \
		echo "== test_gatelevel_smoke seed $$seed =="; \
		rm -rf sim_build results.xml; \
		RANDOM_SEED=$$seed FIRMWARE_HEX=$(TEST_DIR)/firmware/gpio_uart_combo.hex GL_TEST=1 MODULE=test_gatelevel_smoke TESTCASE=test_gl_firmware_gpio_stability $(MAKE) -f $(firstword $(MAKEFILE_LIST)) sim || exit $$?; \
		$(MAKE) -f $(firstword $(MAKEFILE_LIST)) check-results || exit $$?; \
	done

test-all: test-golden test-rtl test-comprehensive

clean-all: clean
	rm -rf sim_build __pycache__ golden_models/__pycache__
	rm -f results.xml *.vcd *.fst $(GL_SMOKE_RESULTS) $(GL_DEEP_RESULTS)

help:
	@echo "TinyQV Test Targets:"
	@echo "  make              - Run the deep gate-level signoff suite and merge results.xml"
	@echo "  make test-rtl     - Run RTL simulation tests"
	@echo "  make test-golden  - Run golden model unit tests (no RTL)"
	@echo "  make test-comprehensive - Run manual-QSPI plus firmware-backed comprehensive tests"
	@echo "  make test-firmware - Run the checked-in firmware boot regressions"
	@echo "  make synth-gate-netlist - Build a pre-layout sky130 gate netlist into test/gate_level_netlist.v"
	@echo "  make stage-gate-netlist - Copy the best Tiny Tapeout/OpenLane gate netlist into test/gate_level_netlist.v"
	@echo "  make test-gatelevel - Run the full deep GL signoff regression"
	@echo "  make test-gatelevel-smoke - Run quick GL smoke tests"
	@echo "  make firmware     - Regenerate checked-in firmware hex images"
	@echo "  make test-rtl-seeds RANDOM_SEEDS='1 2 3 4 5 6 7 8 9 10'"
	@echo "  make test-comprehensive-seeds RANDOM_SEEDS='1 2 3 4 5 6 7 8 9 10'"
	@echo "  make test-firmware-seeds RANDOM_SEEDS='1 2 3 4 5 6 7 8 9 10'"
	@echo "  make test-gatelevel-smoke-seeds RANDOM_SEEDS='1 2 3 4 5 6 7 8 9 10'"
	@echo "  make test-all     - Run all tests (golden + RTL + comprehensive)"
	@echo "  make clean-all    - Clean all artifacts"
