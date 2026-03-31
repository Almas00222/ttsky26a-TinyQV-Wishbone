`default_nettype none
`timescale 1ns / 1ps

module tb;

    reg        clk;
    reg        rst_n;
    reg        ena;
    reg  [7:0] ui_in_base;
    wire [7:0] ui_in;
    reg  [7:0] uio_in_base;
    wire [7:0] uio_in;
    wire [7:0] uo_out;
    wire [7:0] uio_out;
    wire [7:0] uio_oe;

    reg        use_qspi_model;
    reg  [3:0] manual_qspi_data_in;
    reg  [2:0] latency_cfg;

    wire [3:0] model_qspi_data_in;
    wire [3:0] qspi_source_data = use_qspi_model ? model_qspi_data_in : manual_qspi_data_in;
    reg  [19:0] qspi_data_buffer;
    always @(posedge clk) begin
        qspi_data_buffer <= {qspi_data_buffer[15:0], qspi_source_data};
    end
    wire [3:0] delayed_model_qspi_data = (latency_cfg < 1)
        ? model_qspi_data_in
        : qspi_data_buffer[(latency_cfg - 1) * 4 +: 4];
    wire [3:0] selected_qspi_data_in = rst_n
        ? (use_qspi_model ? delayed_model_qspi_data : manual_qspi_data_in)
        : {1'b0, latency_cfg};
    assign uio_in = {
        uio_in_base[7:6],
        selected_qspi_data_in[3:2],
        uio_in_base[3],
        selected_qspi_data_in[1:0],
        uio_in_base[0]
    };

    wire [3:0] qspi_data_out    = {uio_out[5:4], uio_out[2:1]};
    wire [3:0] qspi_data_oe     = {uio_oe[5:4], uio_oe[2:1]};
    wire       qspi_clk_out     = uio_out[3];
    wire       qspi_flash_select = uio_out[0];
    wire       qspi_ram_a_select = uio_out[6];
    wire       qspi_ram_b_select = uio_out[7];

    wire       uart_tx = uo_out[0];
    wire       uart_rx = ui_in_base[7];
    assign ui_in = {uart_rx, ui_in_base[6:0]};

    sim_qspi_soc i_qspi (
        .qspi_data_in     (qspi_data_out & qspi_data_oe),
        .qspi_data_out    (model_qspi_data_in),
        .qspi_clk         (qspi_clk_out),
        .rst_n            (rst_n),
        .qspi_flash_select(qspi_flash_select),
        .qspi_ram_a_select(qspi_ram_a_select),
        .qspi_ram_b_select(qspi_ram_b_select)
    );

`ifdef GL_USE_POWER_PINS
    wire VPWR = 1'b1;
    wire VGND = 1'b0;
`endif

    tt_um_TSARKA_TinyQV user_project (
`ifdef GL_USE_POWER_PINS
        .VPWR(VPWR),
        .VGND(VGND),
`endif
        .ui_in  (ui_in),
        .uo_out (uo_out),
        .uio_in (uio_in),
        .uio_out(uio_out),
        .uio_oe (uio_oe),
        .ena    (ena),
        .clk    (clk),
        .rst_n  (rst_n)
    );

    initial begin
        clk                = 1'b0;
        rst_n              = 1'b0;
        ena                = 1'b0;
        ui_in_base         = 8'h00;
        uio_in_base        = 8'h00;
        use_qspi_model     = 1'b0;
        manual_qspi_data_in = 4'h0;
        latency_cfg        = 3'd1;
        qspi_data_buffer   = 20'h00000;
    end

endmodule

`default_nettype wire
