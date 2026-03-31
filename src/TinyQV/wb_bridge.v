`timescale 1ns / 1ps
module tinyqv_wb_bridge (
    input  wire        clk,
    input  wire        rstn,

    // --- Interface to TinyQV CPU ---
    // Note: Assuming data_addr is byte-aligned. If it's word-aligned, we'll need to shift.
    input  wire [27:0] cpu_data_addr,  
    input  wire [31:0] cpu_data_out,   
    input  wire [1:0]  cpu_data_write_n,
    input  wire [1:0]  cpu_data_read_n,
    output wire [31:0] cpu_data_in,
    output wire        cpu_data_ready,

    // --- Interface to Wishbone Bus ---
    output wire [31:0] wb_addr_o,
    output reg  [31:0] wb_dat_o,
    input  wire [31:0] wb_dat_i,
    output wire        wb_cyc_o,
    output wire        wb_stb_o,
    output wire        wb_we_o,
    output reg  [3:0]  wb_sel_o,
    input  wire        wb_ack_i
);

    // --------------------------------------------------------
    // 1. Control Signals & Activity Detection
    // --------------------------------------------------------
    
    // Determine active transaction type.
    // TinyQV can keep data_write_n non-idle around load cycles, so reads get priority.
    wire read_req  = (cpu_data_read_n  != 2'b11);
    wire write_req = (cpu_data_write_n != 2'b11) && !read_req;
    wire is_active = read_req || write_req;

    reg ack_seen;

    always @(posedge clk or negedge rstn) begin
        if (!rstn)         ack_seen <= 0;
        else if (!is_active) ack_seen <= 0;  // CPU deasserted, reset
        else if (wb_ack_i)   ack_seen <= 1;  // latch ack
    end

    assign wb_cyc_o = is_active && !ack_seen;
    assign wb_stb_o = is_active && !ack_seen;
    // Write Enable: assert only for write cycles
    assign wb_we_o  = write_req;

    // Address Pass-through
    assign wb_addr_o [31:0] = {4'b0000,cpu_data_addr[27:0]};


    // Determine Size (00=8bit, 01=16bit, 10=32bit)
    wire [1:0] size = write_req ? cpu_data_write_n : cpu_data_read_n;


    // --------------------------------------------------------
    // 2. Byte Select Logic (wb_sel_o)
    // --------------------------------------------------------
    always @(*) begin
        case (size)
            2'b00: begin // 8-bit
                case (cpu_data_addr[1:0])
                    2'b00: wb_sel_o = 4'b0001;
                    2'b01: wb_sel_o = 4'b0010;
                    2'b10: wb_sel_o = 4'b0100;
                    2'b11: wb_sel_o = 4'b1000;
                endcase
            end
            2'b01: begin // 16-bit
                case (cpu_data_addr[1])
                    1'b0: wb_sel_o = 4'b0011; // Lower half
                    1'b1: wb_sel_o = 4'b1100; // Upper half
                endcase
            end
            default: wb_sel_o = 4'b1111; // 32-bit
        endcase
    end


    // --------------------------------------------------------
    // 3. Write Data Steering (CPU -> WB)
    // --------------------------------------------------------
    // Replicate data across lanes so the slave picks the right one
    always @(*) begin
        case (size)
            2'b00:   wb_dat_o = {4{cpu_data_out[7:0]}};  // 8-bit: Copy byte 4 times
            2'b01:   wb_dat_o = {2{cpu_data_out[15:0]}}; // 16-bit: Copy half 2 times
            default: wb_dat_o = cpu_data_out;            // 32-bit: Pass through
        endcase
    end


    // --------------------------------------------------------
    // 4. Read Data Handling (WB -> CPU)
    // --------------------------------------------------------
    // For a simple bridge, we often pass data straight through.
    // (Note: If your CPU expects read data to be shifted to LSB, you would add a MUX here)
        
    reg [31:0] cpu_data_in_reg;

    always @(posedge clk) begin
        if (wb_ack_i)
            cpu_data_in_reg <= wb_dat_i;  // latch for hold/timeout
    end

    // Combinatorial pass-through DURING ack, register holds value after
    assign cpu_data_in    = wb_ack_i ? wb_dat_i : cpu_data_in_reg;

    // Back to original undelayed ready
    assign cpu_data_ready = (wb_ack_i || timeout_triggered);    
    // --------------------------------------------------------
    // 5. Watchdog Timer & Handshake
    // --------------------------------------------------------
    reg [6:0] timeout_cnt;
    reg       timeout_triggered;

    always @(posedge clk or negedge rstn) begin
        if (!rstn) begin
            timeout_cnt       <= 0;
            timeout_triggered <= 0;
        end 
        else if (!is_active || wb_ack_i) begin
            // Reset if idle OR if we got a success signal
            timeout_cnt       <= 0;
            timeout_triggered <= 0;
        end 
        else begin
            // Active transaction: Count up
            if (timeout_cnt == 127) begin
                timeout_triggered <= 1'b1; // Freeze and fire fake ready
            end else begin
                timeout_cnt <= timeout_cnt + 1;
            end
        end
    end

`ifdef FORMAL
reg f_past_valid = 1'b0;
initial assume(!rstn);
always @(posedge clk) begin
    f_past_valid <= 1'b1;

    if (!f_past_valid) begin
        assume(!rstn);
    end

    if (rstn) begin
        assert(wb_cyc_o == wb_stb_o);
        assert(wb_we_o == write_req);
        assert(cpu_data_ready == (wb_ack_i || timeout_triggered));

        case (size)
            2'b00: assert(wb_sel_o == (4'b0001 << cpu_data_addr[1:0]));
            2'b01: assert(wb_sel_o == (cpu_data_addr[1] ? 4'b1100 : 4'b0011));
            default: assert(wb_sel_o == 4'b1111);
        endcase

        if (size == 2'b00) assert(wb_dat_o == {4{cpu_data_out[7:0]}});
        if (size == 2'b01) assert(wb_dat_o == {2{cpu_data_out[15:0]}});
        if (size == 2'b10) assert(wb_dat_o == cpu_data_out);

        if (ack_seen && is_active) begin
            assert(!wb_cyc_o);
            assert(!wb_stb_o);
        end

        if (f_past_valid && $past(!rstn || !is_active || wb_ack_i)) begin
            assert(timeout_cnt == 0);
            assert(!timeout_triggered);
        end

        if (timeout_triggered) begin
            assert(timeout_cnt == 7'd127);
            assert(cpu_data_ready);
        end

        if (wb_ack_i) begin
            assert(cpu_data_ready);
        end

        if (f_past_valid && $past(rstn && is_active && !wb_ack_i && timeout_cnt == 7'd126)) begin
            assert(timeout_cnt == 7'd127);
            assert(!timeout_triggered);
        end

        if (f_past_valid && $past(rstn && is_active && !wb_ack_i && timeout_cnt == 7'd127))
            assert(timeout_triggered);

        if (f_past_valid && $past(rstn && wb_ack_i && is_active) && is_active)
            assert(ack_seen);
    end
end
`endif

endmodule
