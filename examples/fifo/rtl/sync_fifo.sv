// Synchronous first-word-fall-through (FWFT) FIFO.
//
// Part of the HDL IP Packager example cores (acme:common:fifo). It is kept small
// and synthesizable so it can serve as a real dependency for the UART example and
// drive the packager's integration tests and docs against an actual manifest.
module sync_fifo #(
    parameter int WIDTH = 8,
    parameter int DEPTH = 16
) (
    input  logic             clk,
    input  logic             rst_n,
    input  logic             wr_en,
    input  logic [WIDTH-1:0] wr_data,
    input  logic             rd_en,
    output logic [WIDTH-1:0] rd_data,
    output logic             full,
    output logic             empty
);
    localparam int ADDR_W = $clog2(DEPTH);

    logic [WIDTH-1:0]  mem [DEPTH];
    logic [ADDR_W:0]   count;
    logic [ADDR_W-1:0] wr_ptr, rd_ptr;

    assign full    = (count == DEPTH[ADDR_W:0]);
    assign empty   = (count == '0);
    assign rd_data = mem[rd_ptr];

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            wr_ptr <= '0;
            rd_ptr <= '0;
            count  <= '0;
        end else begin
            if (wr_en && !full) begin
                mem[wr_ptr] <= wr_data;
                wr_ptr <= wr_ptr + 1'b1;
            end
            if (rd_en && !empty) begin
                rd_ptr <= rd_ptr + 1'b1;
            end
            // Update the occupancy count from the two enables that actually fired.
            case ({wr_en && !full, rd_en && !empty})
                2'b10:   count <= count + 1'b1;
                2'b01:   count <= count - 1'b1;
                default: count <= count;
            endcase
        end
    end
endmodule
