"""Hardware Design and Verification Patterns Knowledge Base."""

from typing import Dict, List


HARDWARE_PATTERNS: Dict[str, Dict[str, str]] = {
    "synchronous_counter": {
        "description": "N-bit synchronous up/down counter with load, enable, and overflow",
        "guidelines": (
            "1. Single clocked always block: @(posedge clk).\n"
            "2. Direct non-blocking assignment: count <= count + 1'b1;\n"
            "3. Do not declare intermediate count_reg or next_count unless pipelined.\n"
            "4. Overflow flag generated combinationally or synchronously at count == (2^N - 1)."
        ),
        "template": (
            "module counter #(\n"
            "  parameter WIDTH = 8\n"
            ") (\n"
            "  input wire clk,\n"
            "  input wire rst_n,\n"
            "  input wire enable,\n"
            "  output reg [WIDTH-1:0] count,\n"
            "  output reg overflow\n"
            ");\n"
            "  always @(posedge clk) begin\n"
            "    if (!rst_n) begin\n"
            "      count <= {WIDTH{1'b0}};\n"
            "      overflow <= 1'b0;\n"
            "    end else begin\n"
            "      if (enable) begin\n"
            "        count <= count + 1'b1;\n"
            "        overflow <= (count == {WIDTH{1'b1}});\n"
            "      end else begin\n"
            "        overflow <= 1'b0;\n"
            "      end\n"
            "    end\n"
            "  end\n"
            "endmodule\n"
        ),
    },
    "synchronous_fifo": {
        "description": "Circular synchronous FIFO with full/empty flags and word counter",
        "guidelines": (
            "1. Memory array: reg [DATA_WIDTH-1:0] mem [0:DEPTH-1];\n"
            "2. Pointers: wr_ptr [ADDR_WIDTH-1:0], rd_ptr [ADDR_WIDTH-1:0].\n"
            "3. Count register: [ADDR_WIDTH:0] count (1 extra bit to represent DEPTH).\n"
            "4. Continuous assign: empty = (count == 0); full = (count == DEPTH);\n"
            "5. On write: when wr_en && !full, mem[wr_ptr] <= wr_data; wr_ptr <= wr_ptr + 1;\n"
            "6. On read: when rd_en && !empty, rd_data <= mem[rd_ptr]; rd_ptr <= rd_ptr + 1;\n"
            "7. Update count based on simultaneous write and read."
        ),
    },
    "sequence_fsm": {
        "description": "Moore/Mealy Finite State Machine sequence detector",
        "guidelines": (
            "1. Define states with localparam: localparam S_IDLE = 3'd0, S_1 = 3'd1, ...\n"
            "2. Two-always block or single-always block architecture.\n"
            "3. Initialize state <= S_IDLE and output <= 0 under reset.\n"
            "4. Default case in all case statements to prevent unintentional latches.\n"
            "5. Moore output depends only on state; Mealy output depends on state and input."
        ),
    },
    "alu": {
        "description": "Parameterized Arithmetic Logic Unit with status flags (Zero, Carry, Overflow, Negative)",
        "guidelines": (
            "1. Combinational always @(*) or clocked always @(posedge clk).\n"
            "2. Operations: ADD, SUB, AND, OR, XOR, NOT, SHL, SHR.\n"
            "3. Flags: zero = (result == 0); neg = result[WIDTH-1];\n"
            "4. Carry and overflow: extend operands by 1 bit for addition/subtraction."
        ),
    },
    "uart_transmitter": {
        "description": "UART Transmitter (8-N-1 format) with configurable baud generator",
        "guidelines": (
            "1. Baud rate divider: counts clk cycles per bit period (e.g. 50MHz / 115200 = 434 cycles).\n"
            "2. States: IDLE (tx=1), START (tx=0), DATA (8 bits LSB first), STOP (tx=1).\n"
            "3. Busy / Ready handshaking flag for the host interface."
        ),
    },
    "spi_master": {
        "description": "SPI Master controller with configurable CPOL/CPHA and chip select",
        "guidelines": (
            "1. SCLK generation via clock divider.\n"
            "2. MOSI shifts data out on designated clock edge; MISO samples on opposite edge.\n"
            "3. Active-low slave select (cs_n) asserted during transaction."
        ),
    },
}


def get_pattern(pattern_name: str) -> Dict[str, str]:
    """Retrieves design pattern guidelines and templates."""
    return HARDWARE_PATTERNS.get(pattern_name, {})


def list_patterns() -> List[str]:
    """Returns available hardware pattern keys."""
    return list(HARDWARE_PATTERNS.keys())
