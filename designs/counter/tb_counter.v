`timescale 1ns/1ps

module tb_counter;

    localparam integer WIDTH = 8;

    reg             clk;
    reg             rst_n;
    reg             enable;
    reg             load;
    reg [WIDTH-1:0] load_data;
    wire [WIDTH-1:0] count;
    wire            overflow;

    // Instantiate Unit Under Test (UUT)
    counter #(
        .WIDTH(WIDTH)
    ) uut (
        .clk(clk),
        .rst_n(rst_n),
        .enable(enable),
        .load(load),
        .load_data(load_data),
        .count(count),
        .overflow(overflow)
    );

    // Clock generator (100MHz -> 10ns period)
    always #5 clk = ~clk;

    initial begin
        // Configure VCD Waveform dump
        $dumpfile("counter.vcd");
        $dumpvars(0, tb_counter);

        // Initialize signals
        clk = 0;
        rst_n = 0;
        enable = 0;
        load = 0;
        load_data = 0;

        // Apply reset
        #20;
        rst_n = 1;
        #10;

        if (count !== 8'h00) begin
            $display("ERROR: Count after reset should be 0, got %02h", count);
            $fatal(1, "Reset check failed");
        end

        // Enable counting for 5 cycles
        enable = 1;
        #50; // 5 cycles

        if (count !== 8'h05) begin
            $display("ERROR: Count after 5 cycles should be 5, got %02h", count);
            $fatal(1, "Counting check failed");
        end

        // Test Load
        enable = 0;
        load = 1;
        load_data = 8'hFE;
        #10;
        load = 0;
        #10;

        if (count !== 8'hFE) begin
            $display("ERROR: Count after load should be 0xFE, got %02h", count);
            $fatal(1, "Load check failed");
        end

        // Count to overflow
        enable = 1;
        #10; // becomes 0xFF -> overflow active
        if (count !== 8'hFF || overflow !== 1'b1) begin
            $display("ERROR: Overflow failed: count=%02h, overflow=%b", count, overflow);
            $fatal(1, "Overflow check failed");
        end

        #10; // wraps around to 0x00
        if (count !== 8'h00) begin
            $display("ERROR: Wrap-around failed: count=%02h", count);
            $fatal(1, "Wrap-around check failed");
        end

        $display("ALL TESTS PASSED: Counter module fully verified.");
        $finish;
    end

endmodule
