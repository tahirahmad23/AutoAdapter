`timescale 1ns / 1ps

// AutoAdapter Verification Testbench Top
// Instantiates the adapter + HLS pass-through for cocotb simulation
// In synchronous mode (C_CLOCK_CROSSING=0), hls_clk is tied to axis_aclk.
// For CDC testing (C_CLOCK_CROSSING=1), define CDC_TEST during build.

module testbench_top #(
    parameter C_S_AXIS_TDATA_WIDTH  = 512,
    parameter C_S_AXIS_TUSER_WIDTH  = 64,
    parameter C_METADATA_FIFO_DEPTH = 32,
    parameter C_NUM_REG_SLICES      = 2,
    parameter HLS_DATA_WIDTH        = 512,
    parameter HLS_TUSER_WIDTH       = 64,
    parameter HLS_LATENCY           = 8,
    parameter HLS_READY_PROBABILITY  = 100,
    parameter C_CLOCK_CROSSING      = 0
)(
    input  wire                        axis_aclk,
    input  wire                        axis_aresetn,

`ifdef CDC_TEST
    input  wire                        hls_clk,
    input  wire                        hls_aresetn,
`endif

    // Shell-side AXI4-Stream (driven by testbench)
    input  wire [C_S_AXIS_TDATA_WIDTH-1:0]  s_axis_tdata,
    input  wire [C_S_AXIS_TDATA_WIDTH/8-1:0] s_axis_tkeep,
    input  wire                        s_axis_tvalid,
    output wire                        s_axis_tready,
    input  wire                        s_axis_tlast,
    input  wire [C_S_AXIS_TUSER_WIDTH-1:0]  s_axis_tuser,

    // Shell-side AXI4-Stream output (observed by testbench)
    output wire [C_S_AXIS_TDATA_WIDTH-1:0]  m_axis_tdata,
    output wire [C_S_AXIS_TDATA_WIDTH/8-1:0] m_axis_tkeep,
    output wire                        m_axis_tvalid,
    input  wire                        m_axis_tready,
    output wire                        m_axis_tlast,
    output wire [C_S_AXIS_TUSER_WIDTH-1:0]  m_axis_tuser
);

    // Internal clock selection
`ifdef CDC_TEST
    wire hls_clk_int    = hls_clk;
    wire hls_aresetn_int = hls_aresetn;
`else
    wire hls_clk_int    = axis_aclk;
    wire hls_aresetn_int = axis_aresetn;
`endif

    // Internal connections between adapter and HLS pass-through
    wire [HLS_DATA_WIDTH-1:0]          hls_in_tdata;
    wire [HLS_DATA_WIDTH/8-1:0]        hls_in_tkeep;
    wire                                hls_in_tvalid;
    wire                                hls_in_tready;
    wire                                hls_in_tlast;
    wire [HLS_TUSER_WIDTH-1:0]         hls_in_tuser;

    wire [HLS_DATA_WIDTH-1:0]          hls_out_tdata;
    wire [HLS_DATA_WIDTH/8-1:0]        hls_out_tkeep;
    wire                                hls_out_tvalid;
    wire                                hls_out_tready;
    wire                                hls_out_tlast;
    wire [HLS_TUSER_WIDTH-1:0]         hls_out_tuser;

    // Instantiate the adapter
    auto_adapter_top #(
        .C_S_AXIS_TDATA_WIDTH(C_S_AXIS_TDATA_WIDTH),
        .C_S_AXIS_TUSER_WIDTH(C_S_AXIS_TUSER_WIDTH),
        .C_M_AXIS_TDATA_WIDTH(HLS_DATA_WIDTH),
        .C_M_AXIS_TUSER_WIDTH(HLS_TUSER_WIDTH),
        .C_METADATA_FIFO_DEPTH(C_METADATA_FIFO_DEPTH),
        .C_NUM_REG_SLICES(C_NUM_REG_SLICES),
        .C_CLOCK_CROSSING(C_CLOCK_CROSSING)
    ) dut_adapter (
        .axis_aclk(axis_aclk),
        .axis_aresetn(axis_aresetn),
        .hls_clk(hls_clk_int),
        .hls_aresetn(hls_aresetn_int),

        .s_axis_tdata(s_axis_tdata),
        .s_axis_tkeep(s_axis_tkeep),
        .s_axis_tvalid(s_axis_tvalid),
        .s_axis_tready(s_axis_tready),
        .s_axis_tlast(s_axis_tlast),
        .s_axis_tuser(s_axis_tuser),

        .m_axis_tdata(m_axis_tdata),
        .m_axis_tkeep(m_axis_tkeep),
        .m_axis_tvalid(m_axis_tvalid),
        .m_axis_tready(m_axis_tready),
        .m_axis_tlast(m_axis_tlast),
        .m_axis_tuser(m_axis_tuser),

        .hls_in_tdata(hls_in_tdata),
        .hls_in_tkeep(hls_in_tkeep),
        .hls_in_tvalid(hls_in_tvalid),
        .hls_in_tready(hls_in_tready),
        .hls_in_tlast(hls_in_tlast),
        .hls_in_tuser(hls_in_tuser),

        .hls_out_tdata(hls_out_tdata),
        .hls_out_tkeep(hls_out_tkeep),
        .hls_out_tvalid(hls_out_tvalid),
        .hls_out_tready(hls_out_tready),
        .hls_out_tlast(hls_out_tlast),
        .hls_out_tuser(hls_out_tuser)
    );

    // Instantiate the HLS accelerator module
    // Selected by build-time define: HLS_MODEL_MOCK, HLS_MODEL_FLOW_HASH, or HLS_MODEL_PACKET_MONITOR
`ifdef HLS_MODEL_FLOW_HASH
    flow_hash #(
        .DATA_WIDTH(HLS_DATA_WIDTH),
        .TUSER_WIDTH(HLS_TUSER_WIDTH),
        .PIPELINE_LATENCY(HLS_LATENCY),
        .READY_PROBABILITY(HLS_READY_PROBABILITY)
    ) dut_hls (
`elsif HLS_MODEL_PACKET_MONITOR
    packet_monitor #(
        .DATA_WIDTH(HLS_DATA_WIDTH),
        .TUSER_WIDTH(HLS_TUSER_WIDTH),
        .PIPELINE_LATENCY(HLS_LATENCY),
        .READY_PROBABILITY(HLS_READY_PROBABILITY)
    ) dut_hls (
`else
    hls_pass_through #(
        .DATA_WIDTH(HLS_DATA_WIDTH),
        .TUSER_WIDTH(HLS_TUSER_WIDTH),
        .PIPELINE_LATENCY(HLS_LATENCY),
        .READY_PROBABILITY(HLS_READY_PROBABILITY)
    ) dut_hls (
`endif
        .axis_aclk(hls_clk_int),
        .axis_aresetn(hls_aresetn_int),

        .s_axis_tdata(hls_in_tdata),
        .s_axis_tkeep(hls_in_tkeep),
        .s_axis_tvalid(hls_in_tvalid),
        .s_axis_tready(hls_in_tready),
        .s_axis_tlast(hls_in_tlast),
        .s_axis_tuser(hls_in_tuser),

        .m_axis_tdata(hls_out_tdata),
        .m_axis_tkeep(hls_out_tkeep),
        .m_axis_tvalid(hls_out_tvalid),
        .m_axis_tready(hls_out_tready),
        .m_axis_tlast(hls_out_tlast),
        .m_axis_tuser(hls_out_tuser)
    );

endmodule
