`timescale 1ns / 1ps

module synth_top #(
    parameter TDATA_WIDTH  = 512,
    parameter TUSER_WIDTH  = 97,
    parameter FIFO_DEPTH   = 16,
    parameter NUM_SLICES   = 2,
    parameter CLK_CROSSING = 0,
    parameter HLS_LATENCY  = 5
)(
    input  wire                        clk,
    input  wire                        hls_clk,
    input  wire                        rst_n,
    output wire [TDATA_WIDTH-1:0]      m_axis_tdata,
    output wire                        m_axis_tvalid,
    output wire                        m_axis_tlast,
    output wire [TUSER_WIDTH-1:0]      m_axis_tuser,
    output wire [TDATA_WIDTH-1:0]      hls_in_tdata,
    output wire                        hls_in_tvalid,
    output wire                        hls_in_tlast,
    output wire [TUSER_WIDTH-1:0]      hls_in_tuser
);

    localparam TKEEP_WIDTH = TDATA_WIDTH / 8;

    wire [TDATA_WIDTH-1:0]  s_axis_tdata;
    wire [TKEEP_WIDTH-1:0]  s_axis_tkeep;
    wire                    s_axis_tvalid;
    wire                    s_axis_tready;
    wire                    s_axis_tlast;
    wire [TUSER_WIDTH-1:0]  s_axis_tuser;

    wire                    m_axis_tready;

    wire [TKEEP_WIDTH-1:0]  m_axis_tkeep;
    wire [TDATA_WIDTH-1:0]  hls_out_tdata;
    wire [TKEEP_WIDTH-1:0]  hls_out_tkeep;
    wire                    hls_out_tvalid;
    wire                    hls_out_tready;
    wire                    hls_out_tlast;
    wire [TUSER_WIDTH-1:0]  hls_out_tuser;

    wire                    hls_in_tready;

    reg [TDATA_WIDTH-1:0]   data_delay [0:HLS_LATENCY-1];
    reg [TKEEP_WIDTH-1:0]   keep_delay [0:HLS_LATENCY-1];
    reg                     last_delay [0:HLS_LATENCY-1];
    reg [TUSER_WIDTH-1:0]   user_delay [0:HLS_LATENCY-1];
    reg                     valid_delay [0:HLS_LATENCY-1];
    integer i;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            for (i = 0; i < HLS_LATENCY; i++) begin
                data_delay[i] <= 0;
                keep_delay[i] <= 0;
                last_delay[i] <= 0;
                user_delay[i] <= 0;
                valid_delay[i] <= 0;
            end
        end else begin
            data_delay[0] <= hls_in_tdata;
            keep_delay[0] <= hls_in_tkeep;
            last_delay[0] <= hls_in_tlast;
            user_delay[0] <= hls_in_tuser;
            valid_delay[0] <= hls_in_tvalid && hls_in_tready;
            for (i = 1; i < HLS_LATENCY; i++) begin
                data_delay[i] <= data_delay[i-1];
                keep_delay[i] <= keep_delay[i-1];
                last_delay[i] <= last_delay[i-1];
                user_delay[i] <= user_delay[i-1];
                valid_delay[i] <= valid_delay[i-1];
            end
        end
    end

    assign hls_out_tdata  = data_delay[HLS_LATENCY-1];
    assign hls_out_tkeep  = keep_delay[HLS_LATENCY-1];
    assign hls_out_tlast  = last_delay[HLS_LATENCY-1];
    assign hls_out_tuser  = user_delay[HLS_LATENCY-1];
    assign hls_out_tvalid = valid_delay[HLS_LATENCY-1];

    auto_adapter_top #(
        .C_S_AXIS_TDATA_WIDTH (TDATA_WIDTH),
        .C_S_AXIS_TUSER_WIDTH (TUSER_WIDTH),
        .C_M_AXIS_TDATA_WIDTH (TDATA_WIDTH),
        .C_M_AXIS_TUSER_WIDTH (TUSER_WIDTH),
        .C_METADATA_FIFO_DEPTH(FIFO_DEPTH),
        .C_NUM_REG_SLICES     (NUM_SLICES),
        .C_CLOCK_CROSSING     (CLK_CROSSING),
        .C_PASS_TUSER_TO_HLS  (0)
    ) u_adapter (
        .axis_aclk    (clk),
        .axis_aresetn (rst_n),
        .hls_clk      (hls_clk),
        .hls_aresetn  (rst_n),
        .s_axis_tdata (s_axis_tdata),
        .s_axis_tkeep (s_axis_tkeep),
        .s_axis_tvalid(s_axis_tvalid),
        .s_axis_tready(s_axis_tready),
        .s_axis_tlast (s_axis_tlast),
        .s_axis_tuser (s_axis_tuser),
        .m_axis_tdata (m_axis_tdata),
        .m_axis_tkeep (m_axis_tkeep),
        .m_axis_tvalid(m_axis_tvalid),
        .m_axis_tready(m_axis_tready),
        .m_axis_tlast (m_axis_tlast),
        .m_axis_tuser (m_axis_tuser),
        .hls_in_tdata (hls_in_tdata),
        .hls_in_tkeep (hls_in_tkeep),
        .hls_in_tvalid(hls_in_tvalid),
        .hls_in_tready(hls_in_tready),
        .hls_in_tlast (hls_in_tlast),
        .hls_in_tuser (hls_in_tuser),
        .hls_out_tdata (hls_out_tdata),
        .hls_out_tkeep (hls_out_tkeep),
        .hls_out_tvalid(hls_out_tvalid),
        .hls_out_tready(hls_out_tready),
        .hls_out_tlast (hls_out_tlast),
        .hls_out_tuser (hls_out_tuser)
    );

    assign hls_out_tready = hls_in_tready;

    assign s_axis_tdata  = {TDATA_WIDTH{rst_n}};
    assign s_axis_tkeep  = {TKEEP_WIDTH{1'b1}};
    assign s_axis_tvalid = 1'b1;
    assign s_axis_tlast  = 1'b0;
    assign s_axis_tuser  = {TUSER_WIDTH{1'b0}};
    assign m_axis_tready = 1'b1;

endmodule
