// Minimal smoke testbench for uart_top (example core acme:comm:uart).
//
// Loops the TX line back into RX and sends one byte, then drains the receive
// FIFO. Real verification is out of scope for the examples; this exists so the
// `tb` fileset references a file that actually exists and `sim` is runnable.
module uart_tb;
    localparam int CLKS_PER_BIT = 4;

    logic       clk = 0;
    logic       rst_n = 0;
    logic       line;  // shared TX -> RX loopback wire
    logic       tx_start = 0;
    logic [7:0] tx_data = '0;
    logic       tx_busy;
    logic       rx_pop = 0;
    logic [7:0] rx_data;
    logic       rx_empty, rx_full;

    uart_top #(.CLKS_PER_BIT(CLKS_PER_BIT), .RX_DEPTH(4)) dut (
        .clk(clk), .rst_n(rst_n),
        .rx(line), .tx(line),
        .tx_start(tx_start), .tx_data(tx_data), .tx_busy(tx_busy),
        .rx_pop(rx_pop), .rx_data(rx_data), .rx_empty(rx_empty), .rx_full(rx_full)
    );

    always #5 clk = ~clk;

    initial begin
        rst_n = 0;
        repeat (4) @(posedge clk);
        rst_n = 1;

        tx_data = 8'h3C;
        tx_start = 1;
        @(posedge clk);
        tx_start = 0;

        // Let a full 8N1 frame elapse, then pop whatever was received.
        repeat (CLKS_PER_BIT * 12) @(posedge clk);
        rx_pop = 1;
        @(posedge clk);
        rx_pop = 0;

        $finish;
    end
endmodule
