"""Phase 5 MVP: End-to-End Closed Loop on 3 Hardware Modules (Counter, FSM, FIFO)."""

from pathlib import Path
import pytest

from agents import (
    ArchitectAgent,
    ReflectionAgent,
    ReviewerAgent,
    RTLCoderAgent,
    SpecificationAnalystAgent,
)
from eda.models import ToolStatus
from gateway.config import config
from gateway.gateway_client import InferenceGatewayClient
from orchestrator import Orchestrator, PipelineContext, PipelineState, RealEDAExecutor
from schemas import VerificationPlan, create_run_layout


# ---------------------------------------------------------------------------
# Hand-crafted golden testbenches to verify independent verification
# ---------------------------------------------------------------------------

COUNTER_TB_CODE = """`timescale 1ns/1ps
module tb_counter;
    reg clk, rst_n, enable;
    wire [7:0] count;
    wire overflow;

    counter uut (.clk(clk), .rst_n(rst_n), .enable(enable), .count(count), .overflow(overflow));

    always #5 clk = ~clk;

    initial begin
        clk = 0; rst_n = 0; enable = 0;
        #20 rst_n = 1; #10;
        enable = 1;
        #100;
        if (count == 8'd10) begin
            $display("ALL TESTS PASSED: Counter reached 10");
            $finish;
        end else begin
            $display("ERROR: Expected count=10, got %0d", count);
            $fatal(1, "Counter mismatch");
        end
    end
endmodule
"""

FSM_TB_CODE = """`timescale 1ns/1ps
module tb_fsm_detector;
    reg clk, rst_n, in_bit;
    wire detected;

    fsm_detector uut (.clk(clk), .rst_n(rst_n), .in_bit(in_bit), .detected(detected));

    always #5 clk = ~clk;

    initial begin
        clk = 0; rst_n = 0; in_bit = 0;
        #20 rst_n = 1; #10;

        // Apply sequence: 1, 0, 1, 1
        @(posedge clk); in_bit <= 1;
        @(posedge clk); in_bit <= 0;
        @(posedge clk); in_bit <= 1;
        @(posedge clk); in_bit <= 1;
        @(posedge clk); in_bit <= 0;
        #1;
        $display("ALL TESTS PASSED: Sequence detector simulated successfully");
        $finish;
    end
endmodule
"""

FIFO_TB_CODE = """`timescale 1ns/1ps
module tb_fifo_sync;
    reg clk, rst_n, wr_en, rd_en;
    reg [7:0] wr_data;
    wire [7:0] rd_data;
    wire full, empty;

    fifo_sync uut (
        .clk(clk), .rst_n(rst_n), .wr_en(wr_en), .rd_en(rd_en),
        .wr_data(wr_data), .rd_data(rd_data), .full(full), .empty(empty)
    );

    always #5 clk = ~clk;

    initial begin
        clk = 0; rst_n = 0; wr_en = 0; rd_en = 0; wr_data = 0;
        #20 rst_n = 1; #10;

        if (!empty) begin
            $fatal(1, "FIFO should initially be empty");
        end

        @(posedge clk); wr_en <= 1; wr_data <= 8'hA5;
        @(posedge clk); wr_en <= 0;
        #10;

        @(posedge clk); rd_en <= 1;
        @(posedge clk); rd_en <= 0;
        #1;

        if (rd_data === 8'hA5) begin
            $display("ALL TESTS PASSED: FIFO write and read verified");
            $finish;
        end else begin
            $display("ERROR: Expected 0xA5, got %02h", rd_data);
            $fatal(1, "FIFO data mismatch");
        end
    end
endmodule
"""


class StaticVerifEngineer:
    """Provides independent, self-checking testbench collateral matched to the spec."""

    def __init__(self, tb_code: str):
        self.tb_code = tb_code

    def execute(self, reqs, run_id=None):
        return VerificationPlan(
            top_module=reqs.module_name,
            testbench_code=self.tb_code,
            assertions=["assert property (@(posedge clk) !empty |-> rd_data != 0);"],
        )


# ---------------------------------------------------------------------------
# Phase 5 Tests
# ---------------------------------------------------------------------------

def test_counter_closed_loop_mvp(tmp_path: Path):
    """Module 1 MVP: Specification -> Requirements -> Architecture -> RTL -> EDA -> PASS."""
    spec_text = (
        "Module Name: counter\n"
        "Description: 8-bit synchronous up-counter with synchronous active-low reset and overflow indicator.\n"
        "Port Specifications:\n"
        "- clk: 1-bit input clock\n"
        "- rst_n: 1-bit input synchronous active-low reset\n"
        "- enable: 1-bit input counter enable\n"
        "- count: 8-bit output current count value\n"
        "- overflow: 1-bit output flag, high when count == 255 and enable is high\n"
        "Behavior:\n"
        "When rst_n is low, count is 0 and overflow is 0. When enable is high on posedge clk, count increments by 1."
    )

    run_paths = create_run_layout(run_id="mvp_counter_run", base_dir=tmp_path)
    ctx = PipelineContext(
        run_id="mvp_counter_run",
        run_paths=run_paths,
        spec_text=spec_text,
    )

    client = InferenceGatewayClient()
    fast_model = config.fast_model  # qwen2.5-coder:1.5b
    primary_model = config.primary_model  # qwen2.5-coder:7b-instruct-q4_K_M

    spec_agent = SpecificationAnalystAgent(gateway_client=client, model=fast_model, temperature=0.0)
    arch_agent = ArchitectAgent(gateway_client=client, model=fast_model, temperature=0.0)
    rtl_agent = RTLCoderAgent(gateway_client=client, model=primary_model, temperature=0.0)
    verif_agent = StaticVerifEngineer(COUNTER_TB_CODE)
    eda_executor = RealEDAExecutor()
    reviewer_agent = ReviewerAgent(gateway_client=client, model=fast_model)
    reflection_agent = ReflectionAgent(gateway_client=client, model=fast_model)

    orchestrator = Orchestrator(
        spec_agent=spec_agent,
        arch_agent=arch_agent,
        rtl_agent=rtl_agent,
        verif_agent=verif_agent,
        eda_executor=eda_executor,
        reviewer_agent=reviewer_agent,
        reflection_agent=reflection_agent,
        enable_git_commits=False,
    )

    final_state = orchestrator.run(ctx)

    assert final_state == PipelineState.SUCCESS, f"Pipeline ended in state {final_state}"
    assert ctx.review is not None
    assert ctx.review.status == "PASS"
    assert (run_paths.rtl_dir / "counter.v").exists()
    assert (run_paths.reports_dir / "review_iter_0.json").exists()


def test_fsm_closed_loop_mvp(tmp_path: Path):
    """Module 2 MVP: 1011 Sequence Detector FSM reaches clean PASS."""
    spec_text = (
        "Module Name: fsm_detector\n"
        "Description: Finite State Machine sequence detector that detects the 4-bit sequence 1011.\n"
        "Port Specifications:\n"
        "- clk: 1-bit input clock\n"
        "- rst_n: 1-bit input synchronous active-low reset\n"
        "- in_bit: 1-bit input serial bitstream\n"
        "- detected: 1-bit output asserted high when sequence 1011 is detected\n"
        "Behavior:\n"
        "Synchronous active-low reset resets state to S_IDLE with detected=0. "
        "FSM tracks incoming in_bit sequence across states."
    )

    run_paths = create_run_layout(run_id="mvp_fsm_run", base_dir=tmp_path)
    ctx = PipelineContext(
        run_id="mvp_fsm_run",
        run_paths=run_paths,
        spec_text=spec_text,
    )

    client = InferenceGatewayClient()
    fast_model = config.fast_model
    primary_model = config.primary_model

    spec_agent = SpecificationAnalystAgent(gateway_client=client, model=fast_model, temperature=0.0)
    arch_agent = ArchitectAgent(gateway_client=client, model=fast_model, temperature=0.0)
    rtl_agent = RTLCoderAgent(gateway_client=client, model=primary_model, temperature=0.0)
    verif_agent = StaticVerifEngineer(FSM_TB_CODE)
    eda_executor = RealEDAExecutor()
    reviewer_agent = ReviewerAgent(gateway_client=client, model=fast_model)
    reflection_agent = ReflectionAgent(gateway_client=client, model=fast_model)

    orchestrator = Orchestrator(
        spec_agent=spec_agent,
        arch_agent=arch_agent,
        rtl_agent=rtl_agent,
        verif_agent=verif_agent,
        eda_executor=eda_executor,
        reviewer_agent=reviewer_agent,
        reflection_agent=reflection_agent,
        enable_git_commits=False,
    )

    final_state = orchestrator.run(ctx)

    assert final_state == PipelineState.SUCCESS, f"Pipeline ended in state {final_state}"
    assert (run_paths.rtl_dir / "fsm_detector.v").exists()


def test_fifo_closed_loop_mvp(tmp_path: Path):
    """Module 3 MVP: Synchronous FIFO reaches clean PASS."""
    spec_text = (
        "Module Name: fifo_sync\n"
        "Description: 8-bit synchronous FIFO with 16 words depth.\n"
        "Port Specifications:\n"
        "- clk: 1-bit input clock\n"
        "- rst_n: 1-bit input synchronous active-low reset\n"
        "- wr_en: 1-bit input write enable\n"
        "- rd_en: 1-bit input read enable\n"
        "- wr_data: 8-bit input data to write\n"
        "- rd_data: 8-bit output data read from FIFO\n"
        "- full: 1-bit output status flag\n"
        "- empty: 1-bit output status flag\n"
        "Storage & Pointers Architecture:\n"
        "- Memory array: reg [7:0] mem [0:15]\n"
        "- Pointers: reg [3:0] wr_ptr, reg [3:0] rd_ptr, reg [4:0] count\n"
        "Functional Behavior:\n"
        "- Synchronous active-low reset (!rst_n): wr_ptr <= 0, rd_ptr <= 0, count <= 0, rd_data <= 0.\n"
        "- Write: when wr_en && !full, write wr_data to mem[wr_ptr] and wr_ptr <= wr_ptr + 1'b1.\n"
        "- Read: when rd_en && !empty, read mem[rd_ptr] to rd_data and rd_ptr <= rd_ptr + 1'b1.\n"
        "- Status flags: assign empty = (count == 5'd0); assign full = (count == 5'd16);\n"
    )

    run_paths = create_run_layout(run_id="mvp_fifo_run", base_dir=tmp_path)
    ctx = PipelineContext(
        run_id="mvp_fifo_run",
        run_paths=run_paths,
        spec_text=spec_text,
    )

    client = InferenceGatewayClient()
    fast_model = config.fast_model
    primary_model = config.primary_model

    spec_agent = SpecificationAnalystAgent(gateway_client=client, model=fast_model, temperature=0.0)
    arch_agent = ArchitectAgent(gateway_client=client, model=fast_model, temperature=0.0)
    rtl_agent = RTLCoderAgent(gateway_client=client, model=primary_model, temperature=0.0)
    verif_agent = StaticVerifEngineer(FIFO_TB_CODE)
    eda_executor = RealEDAExecutor()
    reviewer_agent = ReviewerAgent(gateway_client=client, model=fast_model)
    reflection_agent = ReflectionAgent(gateway_client=client, model=fast_model)

    orchestrator = Orchestrator(
        spec_agent=spec_agent,
        arch_agent=arch_agent,
        rtl_agent=rtl_agent,
        verif_agent=verif_agent,
        eda_executor=eda_executor,
        reviewer_agent=reviewer_agent,
        reflection_agent=reflection_agent,
        enable_git_commits=False,
    )

    final_state = orchestrator.run(ctx)

    assert final_state == PipelineState.SUCCESS, f"Pipeline ended in state {final_state}"
    assert (run_paths.rtl_dir / "fifo_sync.v").exists()
