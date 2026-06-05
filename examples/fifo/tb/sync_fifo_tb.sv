// Minimal smoke testbench for sync_fifo (example core acme:common:fifo).
//
// Pushes one word and pops it back, checking the read data matches. Real
// verification is out of scope for the examples; this exists so the `tb` fileset
// references a file that actually exists and the `sim` target is runnable.
module sync_fifo_tb;
    localparam int WIDTH = 8;
    localparam int DEPTH = 4;

    logic             clk = 0;
    logic             rst_n = 0;
    logic             wr_en = 0, rd_en = 0;
    logic [WIDTH-1:0] wr_data = '0;
    logic [WIDTH-1:0] rd_data;
    logic             full, empty;

    sync_fifo #(.WIDTH(WIDTH), .DEPTH(DEPTH)) dut (.*);

    always #5 clk = ~clk;

    initial begin
        rst_n = 0;
        repeat (2) @(posedge clk);
        rst_n = 1;

        @(posedge clk); wr_en = 1; wr_data = 8'hA5;
        @(posedge clk); wr_en = 0;
        @(posedge clk); rd_en = 1;
        @(posedge clk); rd_en = 0;

        if (rd_data !== 8'hA5) $fatal(1, "FIFO readback mismatch: got %02x", rd_data);
        $finish;
    end
endmodule
