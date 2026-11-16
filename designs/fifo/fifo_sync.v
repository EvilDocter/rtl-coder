// Synchronous FIFO with Status Flags and Word Counter
module fifo_sync #(
    parameter integer DATA_WIDTH = 8,
    parameter integer DEPTH = 16
)(
    input  wire                  clk,
    input  wire                  rst_n,
    input  wire                  wr_en,
    input  wire                  rd_en,
    input  wire [DATA_WIDTH-1:0] wr_data,
    output reg  [DATA_WIDTH-1:0] rd_data,
    output wire                  full,
    output wire                  empty,
    output reg  [$clog2(DEPTH):0] count
);

    localparam integer ADDR_WIDTH = $clog2(DEPTH);

    reg [DATA_WIDTH-1:0] mem [0:DEPTH-1];
    reg [ADDR_WIDTH-1:0] wr_ptr;
    reg [ADDR_WIDTH-1:0] rd_ptr;

    assign full  = (count == DEPTH[$clog2(DEPTH):0]);
    assign empty = (count == {($clog2(DEPTH)+1){1'b0}});

    always @(posedge clk) begin
        if (!rst_n) begin
            wr_ptr  <= {ADDR_WIDTH{1'b0}};
            rd_ptr  <= {ADDR_WIDTH{1'b0}};
            count   <= {($clog2(DEPTH)+1){1'b0}};
            rd_data <= {DATA_WIDTH{1'b0}};
        end else begin
            // Write operation
            if (wr_en && !full) begin
                mem[wr_ptr] <= wr_data;
                wr_ptr      <= wr_ptr + 1'b1;
            end

            // Read operation
            if (rd_en && !empty) begin
                rd_data <= mem[rd_ptr];
                rd_ptr  <= rd_ptr + 1'b1;
            end

            // Occupancy counter update
            case ({wr_en && !full, rd_en && !empty})
                2'b10: count <= count + 1'b1; // Write only
                2'b01: count <= count - 1'b1; // Read only
                default: count <= count;       // Both or neither
            endcase
        end
    end

endmodule
