`default_nettype none

// DELIBERATELY BROKEN FSM Sequence Detector (1011)
// Contains intentional syntax and semantic defects to test EDA failure detection!

module fsm_detector (
    input  wire clk,
    input  wire rst_n,
    input  wire in_bit,
    output reg  detected
);

    // Intentional Defect 1: Bit width mismatch (2-bit state vs 4-bit state encoding)
    localparam [1:0] S_RESET = 4'b0000;
    localparam [1:0] S_1     = 4'b0001;
    localparam [1:0] S_10    = 4'b0010;
    localparam [1:0] S_101   = 4'b0011;

    reg [1:0] current_state, next_state;

    // State register
    always @(posedge clk) begin
        if (!rst_n) begin
            current_state <= S_RESET;
        end else begin
            current_state <= next_state;
        end
    end

    // Intentional Defect 2: Reference to undefined identifier
    wire bad_check;
    assign bad_check = undefined_signal_err && in_bit;

    // Next state logic - Intentional Defect 3: Incomplete case without default -> Latches!
    always @(*) begin
        case (current_state)
            S_RESET: next_state = in_bit ? S_1 : S_RESET;
            S_1:     next_state = in_bit ? S_1 : S_10;
            S_10:    next_state = in_bit ? S_101 : S_RESET;
            // Missing S_101 and default clause!
        endcase
    end

endmodule
