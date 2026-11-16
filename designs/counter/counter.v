// 8-bit Synchronous Up-Counter with Synchronous Reset, Enable, and Load
module counter #(
    parameter integer WIDTH = 8
)(
    input  wire             clk,
    input  wire             rst_n,      // Synchronous active-low reset
    input  wire             enable,     // Counter enable
    input  wire             load,       // Load enable
    input  wire [WIDTH-1:0] load_data,  // Load data input
    output reg  [WIDTH-1:0] count,      // Current count value
    output wire             overflow    // High when maximum count reached
);

    assign overflow = (count == {WIDTH{1'b1}}) && enable;

    always @(posedge clk) begin
        if (!rst_n) begin
            count <= {WIDTH{1'b0}};
        end else if (load) begin
            count <= load_data;
        end else if (enable) begin
            count <= count + 1'b1;
        end
    end

endmodule
