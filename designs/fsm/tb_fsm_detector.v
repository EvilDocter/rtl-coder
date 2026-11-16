`timescale 1ns/1ps

module tb_fsm_detector;

    reg  clk;
    reg  rst_n;
    reg  in_bit;
    wire detected;

    fsm_detector uut (
        .clk(clk),
        .rst_n(rst_n),
        .in_bit(in_bit),
        .detected(detected)
    );

    always #5 clk = ~clk;

    initial begin
        clk = 0;
        rst_n = 0;
        in_bit = 0;
        #20;
        rst_n = 1;
        #10;
        $finish;
    end

endmodule
