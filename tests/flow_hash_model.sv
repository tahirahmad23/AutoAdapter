`timescale 1ns / 1ps

// Behavioral model of the flow_hash HLS accelerator.
// Matches interface and latency from Vitis HLS synthesis report:
//   - Pipeline latency: 5 cycles (from flow_hash_csynth.xml)
//   - Port naming: s_axis / m_axis (no _in/_out suffix)
//   - TUSER ports exist in the model but the adapter drives 0
//     on them (pass_tuser_to_hls=False from ISL detection).
//     Metadata FIFO handles TUSER preservation.

module flow_hash #(
    parameter DATA_WIDTH  = 512,
    parameter TUSER_WIDTH = 64,
    parameter PIPELINE_LATENCY = 5,
    parameter READY_PROBABILITY = 100
)(
    input  wire                        axis_aclk,
    input  wire                        axis_aresetn,

    input  wire [DATA_WIDTH-1:0]       s_axis_tdata,
    input  wire [DATA_WIDTH/8-1:0]     s_axis_tkeep,
    input  wire                        s_axis_tvalid,
    output reg                         s_axis_tready,
    input  wire                        s_axis_tlast,
    input  wire [TUSER_WIDTH-1:0]      s_axis_tuser,

    output reg  [DATA_WIDTH-1:0]       m_axis_tdata,
    output reg  [DATA_WIDTH/8-1:0]     m_axis_tkeep,
    output reg                         m_axis_tvalid,
    input  wire                        m_axis_tready,
    output reg                         m_axis_tlast,
    output reg  [TUSER_WIDTH-1:0]      m_axis_tuser
);

    reg [DATA_WIDTH-1:0]       pipe_tdata   [0:PIPELINE_LATENCY-1];
    reg [DATA_WIDTH/8-1:0]     pipe_tkeep   [0:PIPELINE_LATENCY-1];
    reg                        pipe_tvalid  [0:PIPELINE_LATENCY-1];
    reg                        pipe_tlast   [0:PIPELINE_LATENCY-1];
    reg [TUSER_WIDTH-1:0]      pipe_tuser   [0:PIPELINE_LATENCY-1];

    wire                         handshake;
    integer i;

    reg [15:0] lfsr = 16'hACE1;

    always @(posedge axis_aclk) begin
        lfsr <= {lfsr[14:0], lfsr[15] ^ lfsr[13] ^ lfsr[12] ^ lfsr[10]};
    end

    wire ready_assert = (READY_PROBABILITY >= 100) ||
                        (READY_PROBABILITY > 0 && lfsr[15:8] < READY_PROBABILITY * 256 / 100);

    wire pipe_advance = m_axis_tready || !pipe_tvalid[PIPELINE_LATENCY-1];

    assign handshake = s_axis_tvalid && s_axis_tready;

    always @(posedge axis_aclk) begin
        if (!axis_aresetn) begin
            for (i = 0; i < PIPELINE_LATENCY; i = i + 1) begin
                pipe_tvalid[i] <= 1'b0;
            end
            m_axis_tvalid <= 1'b0;
            s_axis_tready <= 1'b0;
        end else begin
            s_axis_tready <= ready_assert && pipe_advance;

            if (handshake) begin
                pipe_tdata[0]  <= s_axis_tdata;
                pipe_tkeep[0]  <= s_axis_tkeep;
                pipe_tlast[0]  <= s_axis_tlast;
                pipe_tuser[0]  <= s_axis_tuser;
                pipe_tvalid[0] <= s_axis_tvalid;
            end else if (!s_axis_tvalid) begin
                pipe_tvalid[0] <= 1'b0;
            end

            for (i = 1; i < PIPELINE_LATENCY; i = i + 1) begin
                if (pipe_advance) begin
                    pipe_tdata[i]  <= pipe_tdata[i-1];
                    pipe_tkeep[i]  <= pipe_tkeep[i-1];
                    pipe_tlast[i]  <= pipe_tlast[i-1];
                    pipe_tuser[i]  <= pipe_tuser[i-1];
                    pipe_tvalid[i] <= pipe_tvalid[i-1];
                end
            end

            m_axis_tdata  <= pipe_tdata[PIPELINE_LATENCY-1];
            m_axis_tkeep  <= pipe_tkeep[PIPELINE_LATENCY-1];
            m_axis_tlast  <= pipe_tlast[PIPELINE_LATENCY-1];
            m_axis_tuser  <= pipe_tuser[PIPELINE_LATENCY-1];
            m_axis_tvalid <= pipe_tvalid[PIPELINE_LATENCY-1];
        end
    end

endmodule
