// UART top level: receiver, transmitter, and a FIFO-buffered receive path.
//
// Example core acme:comm:uart. The receive buffer is the acme:common:fifo
// dependency (declared in ip.toml as "acme:common:fifo" = "^1.0.0"), which is why
// this core is a useful end-to-end example for the packager's dependency graph.
module uart_top #(
    parameter int CLKS_PER_BIT = 868,
    parameter int RX_DEPTH     = 16
) (
    input  logic       clk,
    input  logic       rst_n,
    // Serial lines.
    input  logic       rx,
    output logic       tx,
    // Transmit command interface.
    input  logic       tx_start,
    input  logic [7:0] tx_data,
    output logic       tx_busy,
    // Buffered receive interface.
    input  logic       rx_pop,
    output logic [7:0] rx_data,
    output logic       rx_empty,
    output logic       rx_full
);
    logic [7:0] rx_byte;
    logic       rx_valid;

    uart_rx #(.CLKS_PER_BIT(CLKS_PER_BIT)) u_rx (
        .clk(clk), .rst_n(rst_n), .rx(rx), .data(rx_byte), .valid(rx_valid)
    );

    uart_tx #(.CLKS_PER_BIT(CLKS_PER_BIT)) u_tx (
        .clk(clk), .rst_n(rst_n), .start(tx_start), .data(tx_data),
        .tx(tx), .busy(tx_busy)
    );

    // Receive buffer provided by the acme:common:fifo dependency.
    sync_fifo #(.WIDTH(8), .DEPTH(RX_DEPTH)) u_rx_fifo (
        .clk(clk), .rst_n(rst_n),
        .wr_en(rx_valid), .wr_data(rx_byte),
        .rd_en(rx_pop), .rd_data(rx_data),
        .full(rx_full), .empty(rx_empty)
    );
endmodule
