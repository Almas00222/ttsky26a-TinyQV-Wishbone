// =============================================================================
// stubs.v — Lightweight behavioural stubs for modules that are not available
//           as synthesisable source in this testbench.
// =============================================================================
`timescale 1ns / 1ps
`default_nettype wire

// ---------------------------------------------------------------------------
// ef_util_gating_cell — simple AND clock gate
// ---------------------------------------------------------------------------
module ef_util_gating_cell (
    input  wire clk,
    input  wire clk_en,
    output wire clk_o
);
    assign clk_o = clk & clk_en;
endmodule

// ---------------------------------------------------------------------------
// ef_util_sync — 2-FF synchroniser (used by EF_GPIO8 for io_in)
// ---------------------------------------------------------------------------
module ef_util_sync (
    input  wire clk,
    input  wire in,
    output reg  out
);
    reg meta;
    always @(posedge clk) begin
        meta <= in;
        out  <= meta;
    end
endmodule

// ---------------------------------------------------------------------------
// ef_util_ped — positive-edge detector
// ---------------------------------------------------------------------------
module ef_util_ped (
    input  wire clk,
    input  wire in,
    output wire out
);
    reg prev;
    always @(posedge clk) prev <= in;
    assign out = in & ~prev;
endmodule

// ---------------------------------------------------------------------------
// ef_util_ned — negative-edge detector (in case it's needed)
// ---------------------------------------------------------------------------
module ef_util_ned (
    input  wire clk,
    input  wire in,
    output wire out
);
    reg prev;
    always @(posedge clk) prev <= in;
    assign out = ~in & prev;
endmodule

// ---------------------------------------------------------------------------
// tinyQV_time — timer stub for TinyQV CPU (used by tinyqv_cpu)
// ---------------------------------------------------------------------------
module tiny_time (
    input clk,
    input rstn,
    input time_pulse,
    input set_mtime,
    input set_mtimecmp,
    input [3:0] data_in,
    input [2:0] counter,
    input read_mtimecmp,
    output reg [3:0] data_out,
    output reg timer_interrupt
);
    initial begin
        data_out = 0;
        timer_interrupt = 0;
    end
endmodule

`default_nettype wire
