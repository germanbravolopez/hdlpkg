// UART receiver, 8 data bits, no parity, 1 stop bit (8N1), oversampled.
//
// Part of the HDL IP Packager example core acme:comm:uart. CLKS_PER_BIT is the
// number of clock cycles per serial bit (clk frequency / baud rate).
module uart_rx #(
    parameter int CLKS_PER_BIT = 868
) (
    input  logic       clk,
    input  logic       rst_n,
    input  logic       rx,
    output logic [7:0] data,
    output logic       valid
);
    typedef enum logic [1:0] {IDLE, START, DATA, STOP} state_t;

    state_t                          state;
    logic [$clog2(CLKS_PER_BIT)-1:0] clk_count;
    logic [2:0]                      bit_index;
    logic [7:0]                      shifter;

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state     <= IDLE;
            valid     <= 1'b0;
            clk_count <= '0;
            bit_index <= '0;
        end else begin
            valid <= 1'b0;
            case (state)
                IDLE: begin
                    clk_count <= '0;
                    bit_index <= '0;
                    if (!rx) state <= START;  // start bit pulls the line low
                end
                START: begin
                    // Sample the start bit at its midpoint to centre on each bit.
                    if (clk_count == (CLKS_PER_BIT - 1) / 2) begin
                        clk_count <= '0;
                        state     <= DATA;
                    end else begin
                        clk_count <= clk_count + 1'b1;
                    end
                end
                DATA: begin
                    if (clk_count == CLKS_PER_BIT - 1) begin
                        clk_count          <= '0;
                        shifter[bit_index] <= rx;
                        if (bit_index == 3'd7) state <= STOP;
                        else bit_index <= bit_index + 1'b1;
                    end else begin
                        clk_count <= clk_count + 1'b1;
                    end
                end
                STOP: begin
                    if (clk_count == CLKS_PER_BIT - 1) begin
                        valid     <= 1'b1;
                        data      <= shifter;
                        clk_count <= '0;
                        state     <= IDLE;
                    end else begin
                        clk_count <= clk_count + 1'b1;
                    end
                end
            endcase
        end
    end
endmodule
