`timescale 1ns / 1ps
`default_nettype none

module sim_qspi_soc #(
    parameter ROM_BITS   = 14,
    parameter RAM_A_BITS = 12,
    parameter RAM_B_BITS = 12
) (
    input  wire [3:0] qspi_data_in,
    output reg  [3:0] qspi_data_out,
    input  wire       qspi_clk,
    input  wire       rst_n,
    input  wire       qspi_flash_select,
    input  wire       qspi_ram_a_select,
    input  wire       qspi_ram_b_select
);

    reg [7:0] flash_mem [0:(1<<ROM_BITS)-1];
    reg [7:0] ram_a_mem [0:(1<<RAM_A_BITS)-1];
    reg [7:0] ram_b_mem [0:(1<<RAM_B_BITS)-1];

    reg [1023:0] firmware_path;
    initial begin
        integer i;

        for (i = 0; i < (1<<ROM_BITS); i = i + 1)
            flash_mem[i] = 8'h00;
        for (i = 0; i < (1<<RAM_A_BITS); i = i + 1)
            ram_a_mem[i] = 8'h00;
        for (i = 0; i < (1<<RAM_B_BITS); i = i + 1)
            ram_b_mem[i] = 8'h00;

        if (!$value$plusargs("firmware=%s", firmware_path))
            firmware_path = "firmware.hex";

        $display("sim_qspi_soc: loading firmware from %0s", firmware_path);
        $readmemh(firmware_path, flash_mem);
    end

    reg [31:0] cmd;
    reg [24:0] addr;
    reg [5:0]  start_count;
    reg        reading_dummy;
    reg        reading;
    reg        writing;
    reg        error;

    wire any_select = qspi_flash_select && qspi_ram_a_select && qspi_ram_b_select;
    wire [5:0] next_start_count = start_count + 6'd1;

    always @(posedge qspi_clk or negedge rst_n or posedge any_select) begin
        if (!rst_n || any_select) begin
            cmd         <= 32'd0;
            start_count <= 6'd0;
        end else begin
            start_count <= next_start_count;
            if (writing) begin
                if (!qspi_ram_a_select)
                    ram_a_mem[addr[RAM_A_BITS:1]][(4 - 4 * addr[0]) +: 4] <= qspi_data_in;
                else if (!qspi_ram_b_select)
                    ram_b_mem[addr[RAM_B_BITS:1]][(4 - 4 * addr[0]) +: 4] <= qspi_data_in;
            end else if (!reading && !writing && !error) begin
                cmd <= {cmd[27:0], qspi_data_in};
            end
        end
    end

    always @(negedge qspi_clk or negedge rst_n or posedge any_select) begin
        if (!rst_n || any_select) begin
            reading_dummy <= 1'b0;
            reading       <= 1'b0;
            writing       <= 1'b0;
            error         <= 1'b0;
            addr          <= 25'd0;
        end else begin
            if (reading || writing) begin
                addr <= addr + 25'd1;
            end else if (reading_dummy) begin
                if (start_count < 6'd8 && cmd[3:0] != 4'hA) begin
                    error <= 1'b1;
                    reading_dummy <= 1'b0;
                end
                if (start_count == 6'd12) begin
                    reading <= 1'b1;
                    reading_dummy <= 1'b0;
                end
            end else if (!error && start_count == (qspi_flash_select ? 6'd8 : 6'd6)) begin
                addr[24] <= 1'b0;
                addr[23:1] <= cmd[22:0];
                addr[0] <= 1'b0;
                if (!qspi_flash_select || cmd[31:24] == 8'h0B)
                    reading_dummy <= 1'b1;
                else if (cmd[31:24] == 8'h02)
                    writing <= 1'b1;
                else
                    error <= 1'b1;
            end
        end
    end

    always @(*) begin
        if (reading) begin
            if (!qspi_flash_select)
                qspi_data_out = flash_mem[addr[ROM_BITS:1]][(4 - 4 * addr[0]) +: 4];
            else if (!qspi_ram_a_select)
                qspi_data_out = ram_a_mem[addr[RAM_A_BITS:1]][(4 - 4 * addr[0]) +: 4];
            else if (!qspi_ram_b_select)
                qspi_data_out = ram_b_mem[addr[RAM_B_BITS:1]][(4 - 4 * addr[0]) +: 4];
            else
                qspi_data_out = 4'b0000;
        end else begin
            qspi_data_out = 4'b0000;
        end
    end

endmodule

`default_nettype wire
