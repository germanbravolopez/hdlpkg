// UART transmitter, 8 data bits, no parity, 1 stop bit (8N1).
//
// Part of the HDL IP Packager example core acme:comm:uart. Asserting `start`
// while `busy` is low latches `data` and shifts it out LSB first.
module uart_tx #(
    parameter int CLKS_PER_BIT = 868
) (
    input  logic       clk,
    input  logic       rst_n,
    input  logic       start,
    input  logic [7:0] data,
    output logic       tx,
    output logic       busy
);
    typedef enum logic [1:0] {IDLE, START_BIT, DATA, STOP_BIT} state_t;

    state_t                          state;
    logic [$clog2(CLKS_PER_BIT)-1:0] clk_count;
    logic [2:0]                      bit_index;
    logic [7:0]                      shifter;

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state     <= IDLE;
            tx        <= 1'b1;  // line idles high
            busy      <= 1'b0;
            clk_count <= '0;
            bit_index <= '0;
        end else begin
            case (state)
                IDLE: begin
                    tx        <= 1'b1;
                    busy      <= 1'b0;
                    clk_count <= '0;
                    bit_index <= '0;
                    if (start) begin
                        shifter <= data;
                        busy    <= 1'b1;
                        state   <= START_BIT;
                    end
                end
                START_BIT: begin
                    tx <= 1'b0;
                    if (clk_count == CLKS_PER_BIT - 1) begin
                        clk_count <= '0;
                        state     <= DATA;
                    end else begin
                        clk_count <= clk_count + 1'b1;
                    end
                end
                DATA: begin
                    tx <= shifter[bit_index];
                    if (clk_count == CLKS_PER_BIT - 1) begin
                        clk_count <= '0;
                        if (bit_index == 3'd7) state <= STOP_BIT;
                        else bit_index <= bit_index + 1'b1;
                    end else begin
                        clk_count <= clk_count + 1'b1;
                    end
                end
                STOP_BIT: begin
                    tx <= 1'b1;
                    if (clk_count == CLKS_PER_BIT - 1) begin
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
