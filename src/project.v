/*
 * Copyright (c) 2024 TSARKA
 * SPDX-License-Identifier: Apache-2.0
 */

`default_nettype none
`timescale 1ns / 1ps

module tt_um_TSARKA_TinyQV (
    input  wire [7:0] ui_in,
    output wire [7:0] uo_out,
    input  wire [7:0] uio_in,
    output wire [7:0] uio_out,
    output wire [7:0] uio_oe,
    input  wire       ena,
    input  wire       clk,
    input  wire       rst_n
);

    // QSPI map on UIO:
    // uio[0]=flash_cs, uio[1]=sd0, uio[2]=sd1, uio[3]=sck,
    // uio[4]=sd2, uio[5]=sd3, uio[6]=ram_a_cs, uio[7]=ram_b_cs
    wire [3:0] qspi_data_in  = {uio_in[5:4], uio_in[2:1]};
    wire [3:0] qspi_data_out;
    wire [3:0] qspi_data_oe;
    wire       qspi_clk_out;
    wire       qspi_flash_select;
    wire       qspi_ram_a_select;
    wire       qspi_ram_b_select;

    assign uio_out = {qspi_ram_b_select, qspi_ram_a_select,
                      qspi_data_out[3:2], qspi_clk_out,
                      qspi_data_out[1:0], qspi_flash_select};
    assign uio_oe  = rst_n ? {2'b11, qspi_data_oe[3:2], 1'b1,
                               qspi_data_oe[1:0], 1'b1}
                           : 8'h00;

    wire [7:0] gpio_out;
    wire [7:0] gpio_oe;
    wire       gpio_irq;
    wire       uart_tx;
    wire       uart_irq;
    wire [2:0] led;

    wire       cpu_debug_instr_complete;
    wire       cpu_debug_instr_ready;
    wire       cpu_debug_instr_valid;
    wire       cpu_debug_fetch_restart;
    wire       cpu_debug_data_ready;
    wire       cpu_debug_interrupt_pending;
    wire       cpu_debug_branch;
    wire       cpu_debug_early_branch;
    wire       cpu_debug_ret;
    wire       cpu_debug_reg_wen;
    wire       cpu_debug_counter_0;
    wire       cpu_debug_data_continue;
    wire       cpu_debug_stall_txn;
    wire       cpu_debug_stop_txn;

    tinyqv_soc_top #(
        .CLOCK_MHZ(50)
    ) i_soc (
        .clk                        (clk),
        .rstn                       (rst_n),
        .gpio_in                    (ui_in),
        .gpio_out                   (gpio_out),
        .gpio_oe                    (gpio_oe),
        .gpio_irq                   (gpio_irq),
        .uart_rx                    (ui_in[7]),
        .uart_tx                    (uart_tx),
        .uart_irq                   (uart_irq),
        .qspi_data_in               (qspi_data_in),
        .qspi_data_out              (qspi_data_out),
        .qspi_data_oe               (qspi_data_oe),
        .qspi_clk_out               (qspi_clk_out),
        .qspi_flash_select          (qspi_flash_select),
        .qspi_ram_a_select          (qspi_ram_a_select),
        .qspi_ram_b_select          (qspi_ram_b_select),
        .led                        (led),
        .cpu_debug_instr_complete   (cpu_debug_instr_complete),
        .cpu_debug_instr_ready      (cpu_debug_instr_ready),
        .cpu_debug_instr_valid      (cpu_debug_instr_valid),
        .cpu_debug_fetch_restart    (cpu_debug_fetch_restart),
        .cpu_debug_data_ready       (cpu_debug_data_ready),
        .cpu_debug_interrupt_pending(cpu_debug_interrupt_pending),
        .cpu_debug_branch           (cpu_debug_branch),
        .cpu_debug_early_branch     (cpu_debug_early_branch),
        .cpu_debug_ret              (cpu_debug_ret),
        .cpu_debug_reg_wen          (cpu_debug_reg_wen),
        .cpu_debug_counter_0        (cpu_debug_counter_0),
        .cpu_debug_data_continue    (cpu_debug_data_continue),
        .cpu_debug_stall_txn        (cpu_debug_stall_txn),
        .cpu_debug_stop_txn         (cpu_debug_stop_txn)
    );

    // ui_in[0] = 0: GPIO view, ui_in[0] = 1: debug view.
    // uo_out[0] always carries uart_tx for a stable UART probe point.
    wire [15:0] debug_bus = {
        uart_irq,
        cpu_debug_stop_txn,
        cpu_debug_stall_txn,
        cpu_debug_data_continue,
        cpu_debug_counter_0,
        cpu_debug_reg_wen,
        cpu_debug_ret,
        cpu_debug_early_branch,
        gpio_irq,
        cpu_debug_branch,
        cpu_debug_interrupt_pending,
        cpu_debug_data_ready,
        cpu_debug_fetch_restart,
        cpu_debug_instr_valid,
        cpu_debug_instr_ready,
        cpu_debug_instr_complete
    };

    wire debug_mode_sel   = ui_in[0];
    wire debug_signal_sel = debug_bus[ui_in[4:1]];

    wire [7:0] gpio_bus  = {gpio_out[7:1], uart_tx};
    wire [7:0] debug_out = {
        cpu_debug_interrupt_pending,
        cpu_debug_data_ready,
        cpu_debug_fetch_restart,
        cpu_debug_branch,
        cpu_debug_instr_ready,
        cpu_debug_instr_complete,
        debug_signal_sel,
        uart_tx
    };

    assign uo_out = debug_mode_sel ? debug_out : gpio_bus;

    wire _unused = &{ena, led, gpio_oe, debug_signal_sel, 1'b0};

endmodule

module tinyqv_soc_top #(
    parameter CLOCK_MHZ = 50
) (
    input  wire        clk,
    input  wire        rstn,
    input  wire [ 7:0] gpio_in,
    output wire [ 7:0] gpio_out,
    output wire [ 7:0] gpio_oe,
    output wire        gpio_irq,
    input  wire        uart_rx,
    output wire        uart_tx,
    output wire        uart_irq,
    input  wire [ 3:0] qspi_data_in,
    output wire [ 3:0] qspi_data_out,
    output wire [ 3:0] qspi_data_oe,
    output wire        qspi_clk_out,
    output wire        qspi_flash_select,
    output wire        qspi_ram_a_select,
    output wire        qspi_ram_b_select,
    output wire [ 2:0] led,
    output wire        cpu_debug_instr_complete,
    output wire        cpu_debug_instr_ready,
    output wire        cpu_debug_instr_valid,
    output wire        cpu_debug_fetch_restart,
    output wire        cpu_debug_data_ready,
    output wire        cpu_debug_interrupt_pending,
    output wire        cpu_debug_branch,
    output wire        cpu_debug_early_branch,
    output wire        cpu_debug_ret,
    output wire        cpu_debug_reg_wen,
    output wire        cpu_debug_counter_0,
    output wire        cpu_debug_data_continue,
    output wire        cpu_debug_stall_txn,
    output wire        cpu_debug_stop_txn
);

    /* verilator lint_off SYNCASYNCNET */
    reg rst_reg_n;
    /* verilator lint_on SYNCASYNCNET */
    always @(negedge clk) rst_reg_n <= rstn;

    reg [7:0] time_count;
    wire      time_pulse = (time_count == (CLOCK_MHZ - 1));
    always @(posedge clk) begin
        if (!rst_reg_n)
            time_count <= 0;
        else if (time_pulse)
            time_count <= 0;
        else
            time_count <= time_count + 1;
    end

    wire [27:0] cpu_addr;
    wire [ 1:0] cpu_write_n;
    wire [ 1:0] cpu_read_n;
    wire        cpu_read_complete;
    wire [31:0] cpu_data_to_write;
    wire        cpu_data_ready;
    wire [31:0] cpu_data_from_read;

    wire        uart_int;
    wire [3:0]  debug_rd;
    wire [15:0] interrupt_req = {12'b0, uart_int, 1'b0, gpio_in[1:0]};

    tinyQV i_tinyqv (
        .clk                    (clk),
        .rstn                   (rst_reg_n),
        .led                    (led),
        .data_addr              (cpu_addr),
        .data_write_n           (cpu_write_n),
        .data_read_n            (cpu_read_n),
        .data_read_complete     (cpu_read_complete),
        .data_out               (cpu_data_to_write),
        .data_ready             (cpu_data_ready),
        .data_in                (cpu_data_from_read),
        .interrupt_req          (interrupt_req),
        .time_pulse             (time_pulse),
        .spi_data_in            (rst_reg_n ? qspi_data_in : 4'b0010),
        .spi_data_out           (qspi_data_out),
        .spi_data_oe            (qspi_data_oe),
        .spi_clk_out            (qspi_clk_out),
        .spi_flash_select       (qspi_flash_select),
        .spi_ram_a_select       (qspi_ram_a_select),
        .spi_ram_b_select       (qspi_ram_b_select),
        .debug_instr_complete   (cpu_debug_instr_complete),
        .debug_instr_ready      (cpu_debug_instr_ready),
        .debug_instr_valid      (cpu_debug_instr_valid),
        .debug_fetch_restart    (cpu_debug_fetch_restart),
        .debug_data_ready       (cpu_debug_data_ready),
        .debug_interrupt_pending(cpu_debug_interrupt_pending),
        .debug_branch           (cpu_debug_branch),
        .debug_early_branch     (cpu_debug_early_branch),
        .debug_ret              (cpu_debug_ret),
        .debug_reg_wen          (cpu_debug_reg_wen),
        .debug_counter_0        (cpu_debug_counter_0),
        .debug_data_continue    (cpu_debug_data_continue),
        .debug_stall_txn        (cpu_debug_stall_txn),
        .debug_stop_txn         (cpu_debug_stop_txn),
        .debug_rd               (debug_rd)
    );

    wire [31:0] wb_addr;
    wire [31:0] wb_wdata;
    wire [31:0] wb_rdata;
    wire        wb_cyc;
    wire        wb_stb;
    wire        wb_we;
    wire [ 3:0] wb_sel;
    wire        wb_ack;

    tinyqv_wb_bridge i_bridge (
        .clk              (clk),
        .rstn             (rst_reg_n),
        .cpu_data_addr    (cpu_addr),
        .cpu_data_out     (cpu_data_to_write),
        .cpu_data_write_n (cpu_write_n),
        .cpu_data_read_n  (cpu_read_n),
        .cpu_data_in      (cpu_data_from_read),
        .cpu_data_ready   (cpu_data_ready),
        .wb_addr_o        (wb_addr),
        .wb_dat_o         (wb_wdata),
        .wb_dat_i         (wb_rdata),
        .wb_cyc_o         (wb_cyc),
        .wb_stb_o         (wb_stb),
        .wb_we_o          (wb_we),
        .wb_sel_o         (wb_sel),
        .wb_ack_i         (wb_ack)
    );

    wire sel_gpio = wb_cyc && (wb_addr[27:24] == 4'h3);
    wire sel_uart = wb_cyc && (wb_addr[27:24] == 4'h4);

    wire [31:0] gpio_rdata;
    wire        gpio_ack;

    wb_gpio8_adapter gpio_inst (
        .clk     (clk),
        .rst     (~rst_reg_n),
        .wb_adr_i(wb_addr),
        .wb_dat_i(wb_wdata),
        .wb_dat_o(gpio_rdata),
        .wb_sel_i(wb_sel),
        .wb_cyc_i(sel_gpio),
        .wb_stb_i(sel_gpio),
        .wb_we_i (wb_we),
        .wb_ack_o(gpio_ack),
        .gpio_in (gpio_in),
        .gpio_out(gpio_out),
        .gpio_oe (gpio_oe),
        .gpio_irq(gpio_irq)
    );

    wire [31:0] uart_rdata;
    wire        uart_ack;
    wire        uart_rts;
    wire        uart_dtr;

    wb_uart16550_adapter uart_inst (
        .clk     (clk),
        .rst     (~rst_reg_n),
        .wb_adr_i(wb_addr),
        .wb_dat_i(wb_wdata),
        .wb_dat_o(uart_rdata),
        .wb_sel_i(wb_sel),
        .wb_cyc_i(sel_uart),
        .wb_stb_i(sel_uart),
        .wb_we_i (wb_we),
        .wb_ack_o(uart_ack),
        .uart_irq(uart_int),
        .uart_rx (uart_rx),
        .uart_tx (uart_tx),
        .uart_cts(1'b0),
        .uart_rts(uart_rts),
        .uart_dtr(uart_dtr),
        .uart_dsr(1'b0),
        .uart_ri (1'b0),
        .uart_dcd(1'b0)
    );

    assign uart_irq = uart_int;

    assign wb_rdata = sel_gpio ? gpio_rdata :
                      sel_uart ? uart_rdata :
                      32'h0000_0000;

    assign wb_ack   = sel_gpio ? gpio_ack :
                      sel_uart ? uart_ack :
                      1'b0;

    wire _unused = &{debug_rd, cpu_read_complete, wb_stb, 1'b0};

endmodule

`default_nettype wire
