`timescale 1ns/1ps

module tb_fifo_sync;

    localparam integer DATA_WIDTH = 8;
    localparam integer DEPTH = 16;

    reg                   clk;
    reg                   rst_n;
    reg                   wr_en;
    reg                   rd_en;
    reg  [DATA_WIDTH-1:0] wr_data;
    wire [DATA_WIDTH-1:0] rd_data;
    wire                  full;
    wire                  empty;
    wire [$clog2(DEPTH):0] count;

    fifo_sync #(
        .DATA_WIDTH(DATA_WIDTH),
        .DEPTH(DEPTH)
    ) uut (
        .clk(clk),
        .rst_n(rst_n),
        .wr_en(wr_en),
        .rd_en(rd_en),
        .wr_data(wr_data),
        .rd_data(rd_data),
        .full(full),
        .empty(empty),
        .count(count)
    );

    always #5 clk = ~clk;

    initial begin
        $dumpfile("fifo.vcd");
        $dumpvars(0, tb_fifo_sync);

        clk = 0;
        rst_n = 0;
        wr_en = 0;
        rd_en = 0;
        wr_data = 0;

        #20;
        rst_n = 1;
        #10;

        if (!empty || full || count !== 0) begin
            $display("ERROR: Initial FIFO state mismatch");
            $fatal(1, "Initial state check failed");
        end

        // Write 3 bytes: 0xAA, 0xBB, 0xCC
        @(posedge clk);
        wr_en <= 1;
        wr_data <= 8'hAA;
        @(posedge clk);
        wr_data <= 8'hBB;
        @(posedge clk);
        wr_data <= 8'hCC;
        @(posedge clk);
        wr_en <= 0;
        wr_data <= 8'h00;

        #10;
        if (count !== 3 || empty) begin
            $display("ERROR: Count should be 3, got %0d", count);
            $fatal(1, "Write count failed");
        end

        // Read 1st byte (expect 0xAA)
        @(posedge clk);
        rd_en <= 1;
        @(posedge clk);
        rd_en <= 0;
        #1;
        if (rd_data !== 8'hAA) begin
            $display("ERROR: Expected 0xAA, got %02h", rd_data);
            $fatal(1, "First read check failed");
        end

        // Read 2nd byte (expect 0xBB)
        @(posedge clk);
        rd_en <= 1;
        @(posedge clk);
        rd_en <= 0;
        #1;
        if (rd_data !== 8'hBB) begin
            $display("ERROR: Expected 0xBB, got %02h", rd_data);
            $fatal(1, "Second read check failed");
        end

        // Read 3rd byte (expect 0xCC)
        @(posedge clk);
        rd_en <= 1;
        @(posedge clk);
        rd_en <= 0;
        #1;
        if (rd_data !== 8'hCC) begin
            $display("ERROR: Expected 0xCC, got %02h", rd_data);
            $fatal(1, "Third read check failed");
        end

        #10;
        if (!empty) begin
            $display("ERROR: FIFO should be empty after reading all items");
            $fatal(1, "Final empty check failed");
        end

        $display("ALL TESTS PASSED: Synchronous FIFO fully verified.");
        $finish;
    end

endmodule
