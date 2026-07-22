// AutoAdapter — auto-generated adapter bridge
// Template: adapter_top.sv v2.0.0 (CDC-aware)

`timescale 1ns / 1ps

module auto_adapter_top #(
    parameter C_S_AXIS_TDATA_WIDTH  = ${iface.data_width},
    parameter C_S_AXIS_TUSER_WIDTH  = ${iface.tuser_width},
    parameter C_M_AXIS_TDATA_WIDTH  = ${hls_data_width},
    parameter C_M_AXIS_TUSER_WIDTH  = ${hls_tuser_width},
    parameter C_METADATA_FIFO_DEPTH = ${params.metadata_fifo_depth},
    parameter C_NUM_REG_SLICES      = ${params.num_reg_slices},
    parameter C_CLOCK_CROSSING      = ${'1' if params.clock_crossing else '0'},
    parameter C_PASS_TUSER_TO_HLS   = ${'1' if params.pass_tuser_to_hls else '0'}
)(
    input  wire                        axis_aclk,
    input  wire                        axis_aresetn,

    // HLS-side clock (same as axis_aclk when C_CLOCK_CROSSING=0)
    input  wire                        hls_clk,
    input  wire                        hls_aresetn,

    // Shell-side AXI4-Stream
    input  wire [C_S_AXIS_TDATA_WIDTH-1:0]  s_axis_tdata,
    input  wire [C_S_AXIS_TDATA_WIDTH/8-1:0] s_axis_tkeep,
    input  wire                        s_axis_tvalid,
    output wire                        s_axis_tready,
    input  wire                        s_axis_tlast,
    input  wire [C_S_AXIS_TUSER_WIDTH-1:0]  s_axis_tuser,

    // Shell-side output from adapter
    output wire [C_S_AXIS_TDATA_WIDTH-1:0]  m_axis_tdata,
    output wire [C_S_AXIS_TDATA_WIDTH/8-1:0] m_axis_tkeep,
    output wire                        m_axis_tvalid,
    input  wire                        m_axis_tready,
    output wire                        m_axis_tlast,
    output wire [C_S_AXIS_TUSER_WIDTH-1:0]  m_axis_tuser,

    // HLS-side AXI4-Stream input (to HLS core)
    output wire [C_M_AXIS_TDATA_WIDTH-1:0]  hls_in_tdata,
    output wire [C_M_AXIS_TDATA_WIDTH/8-1:0] hls_in_tkeep,
    output wire                        hls_in_tvalid,
    input  wire                        hls_in_tready,
    output wire                        hls_in_tlast,
    output wire [C_M_AXIS_TUSER_WIDTH-1:0]  hls_in_tuser,

    // HLS-side AXI4-Stream output (from HLS core)
    input  wire [C_M_AXIS_TDATA_WIDTH-1:0]  hls_out_tdata,
    input  wire [C_M_AXIS_TDATA_WIDTH/8-1:0] hls_out_tkeep,
    input  wire                        hls_out_tvalid,
    output wire                        hls_out_tready,
    input  wire                        hls_out_tlast,
    input  wire [C_M_AXIS_TUSER_WIDTH-1:0]  hls_out_tuser
);

    // ------------------------------------------------------------------------
    // Clock assignment
    // ------------------------------------------------------------------------
    wire clk_shell = axis_aclk;
    wire clk_hls   = hls_clk;
    wire rst_n     = axis_aresetn & hls_aresetn;

    // ------------------------------------------------------------------------
    // Ingress: detect first beat of input packet (shell clock domain)
    // ------------------------------------------------------------------------
    reg in_packet;

    wire in_first = s_axis_tvalid && s_axis_tready && !in_packet;

    always @(posedge clk_shell) begin
        if (!axis_aresetn) begin
            in_packet <= 0;
        end else begin
            if (s_axis_tvalid && s_axis_tready && s_axis_tlast) begin
                in_packet <= 0;
            end else if (in_first) begin
                in_packet <= 1;
            end
        end
    end

    // ------------------------------------------------------------------------
    // HLS passthrough (data path — may cross clock domains)
    // ------------------------------------------------------------------------
    generate
        if (C_CLOCK_CROSSING) begin : gen_cdc_data

            localparam ADDR_W = $clog2(C_METADATA_FIFO_DEPTH);
            localparam PTR_W  = ADDR_W + 1;

            // ================================================================
            // Input CDC FIFO: shell -> HLS
            // Gray-code pointer synchronization for clock-domain crossing
            // ================================================================

            reg [C_S_AXIS_TDATA_WIDTH + C_S_AXIS_TDATA_WIDTH/8 + 1 + C_S_AXIS_TUSER_WIDTH - 1:0]
                cdc_fifo_mem [0:C_METADATA_FIFO_DEPTH-1];

            reg [PTR_W-1:0] cdc_wr_ptr, cdc_rd_ptr;
            wire [PTR_W-1:0] cdc_wr_ptr_gray = cdc_wr_ptr ^ (cdc_wr_ptr >> 1);
            wire [PTR_W-1:0] cdc_rd_ptr_gray = cdc_rd_ptr ^ (cdc_rd_ptr >> 1);

            // Synchronize read pointer into write domain (shell clock)
            reg [PTR_W-1:0] cdc_rd_ptr_sync1, cdc_rd_ptr_sync2;
            always @(posedge clk_shell) begin
                cdc_rd_ptr_sync1 <= cdc_rd_ptr_gray;
                cdc_rd_ptr_sync2 <= cdc_rd_ptr_sync1;
            end

            wire cdc_full = (cdc_wr_ptr_gray ==
                {~cdc_rd_ptr_sync2[PTR_W-1:PTR_W-2], cdc_rd_ptr_sync2[PTR_W-3:0]});

            always @(posedge clk_shell) begin
                if (!axis_aresetn) begin
                    cdc_wr_ptr <= 0;
                end else if (s_axis_tvalid && s_axis_tready) begin
                    cdc_fifo_mem[cdc_wr_ptr[ADDR_W-1:0]] <= {
                        s_axis_tuser, s_axis_tlast, s_axis_tkeep, s_axis_tdata
                    };
                    cdc_wr_ptr <= cdc_wr_ptr + 1;
                end
            end

            // Synchronize write pointer into read domain (HLS clock)
            reg [PTR_W-1:0] cdc_wr_ptr_sync1, cdc_wr_ptr_sync2;
            always @(posedge clk_hls) begin
                cdc_wr_ptr_sync1 <= cdc_wr_ptr_gray;
                cdc_wr_ptr_sync2 <= cdc_wr_ptr_sync1;
            end

            wire cdc_empty = (cdc_rd_ptr_gray == cdc_wr_ptr_sync2);

            reg [C_S_AXIS_TUSER_WIDTH-1:0]  cdc_out_tuser;
            reg                             cdc_out_tlast;
            reg [C_S_AXIS_TDATA_WIDTH/8-1:0] cdc_out_tkeep;
            reg [C_S_AXIS_TDATA_WIDTH-1:0]  cdc_out_tdata;
            reg                             cdc_out_tvalid_reg;

            always @(posedge clk_hls) begin
                if (!hls_aresetn) begin
                    cdc_rd_ptr <= 0;
                    cdc_out_tvalid_reg <= 0;
                end else begin
                    if (!cdc_empty && (!cdc_out_tvalid_reg || hls_in_tready)) begin
                        {cdc_out_tuser, cdc_out_tlast, cdc_out_tkeep, cdc_out_tdata}
                            <= cdc_fifo_mem[cdc_rd_ptr[ADDR_W-1:0]];
                        cdc_rd_ptr <= cdc_rd_ptr + 1;
                        cdc_out_tvalid_reg <= 1;
                    end else if (hls_in_tready) begin
                        cdc_out_tvalid_reg <= 0;
                    end
                end
            end

            assign hls_in_tdata  = cdc_out_tdata;
            assign hls_in_tkeep  = cdc_out_tkeep;
            assign hls_in_tvalid = cdc_out_tvalid_reg;
            assign hls_in_tlast  = cdc_out_tlast;
            assign hls_in_tuser  = cdc_out_tuser;
            assign s_axis_tready = !cdc_full;

            // ================================================================
            // Output CDC FIFO: HLS -> shell
            // ================================================================

            reg [C_S_AXIS_TDATA_WIDTH + C_S_AXIS_TDATA_WIDTH/8 + 1 + C_S_AXIS_TUSER_WIDTH - 1:0]
                cdc_out_fifo_mem [0:C_METADATA_FIFO_DEPTH-1];

            reg [PTR_W-1:0] cdc_out_wr_ptr, cdc_out_rd_ptr;
            wire [PTR_W-1:0] cdc_out_wr_ptr_gray = cdc_out_wr_ptr ^ (cdc_out_wr_ptr >> 1);
            wire [PTR_W-1:0] cdc_out_rd_ptr_gray = cdc_out_rd_ptr ^ (cdc_out_rd_ptr >> 1);

            reg [PTR_W-1:0] cdc_out_rd_ptr_sync1, cdc_out_rd_ptr_sync2;
            always @(posedge clk_hls) begin
                cdc_out_rd_ptr_sync1 <= cdc_out_rd_ptr_gray;
                cdc_out_rd_ptr_sync2 <= cdc_out_rd_ptr_sync1;
            end

            wire cdc_out_full = (cdc_out_wr_ptr_gray ==
                {~cdc_out_rd_ptr_sync2[PTR_W-1:PTR_W-2], cdc_out_rd_ptr_sync2[PTR_W-3:0]});

            always @(posedge clk_hls) begin
                if (!hls_aresetn) begin
                    cdc_out_wr_ptr <= 0;
                end else if (hls_out_tvalid && hls_out_tready) begin
                    cdc_out_fifo_mem[cdc_out_wr_ptr[ADDR_W-1:0]] <= {
                        hls_out_tuser, hls_out_tlast, hls_out_tkeep, hls_out_tdata
                    };
                    cdc_out_wr_ptr <= cdc_out_wr_ptr + 1;
                end
            end

            reg [PTR_W-1:0] cdc_out_wr_ptr_sync1, cdc_out_wr_ptr_sync2;
            always @(posedge clk_shell) begin
                cdc_out_wr_ptr_sync1 <= cdc_out_wr_ptr_gray;
                cdc_out_wr_ptr_sync2 <= cdc_out_wr_ptr_sync1;
            end

            wire cdc_out_empty = (cdc_out_rd_ptr_gray == cdc_out_wr_ptr_sync2);

            reg [C_S_AXIS_TUSER_WIDTH-1:0]  cdc_m_tuser;
            reg                             cdc_m_tlast;
            reg [C_S_AXIS_TDATA_WIDTH/8-1:0] cdc_m_tkeep;
            reg [C_S_AXIS_TDATA_WIDTH-1:0]  cdc_m_tdata;
            reg                             cdc_m_tvalid_reg;

            always @(posedge clk_shell) begin
                if (!axis_aresetn) begin
                    cdc_out_rd_ptr <= 0;
                    cdc_m_tvalid_reg <= 0;
                end else begin
                    if (!cdc_out_empty && (!cdc_m_tvalid_reg || m_axis_tready)) begin
                        {cdc_m_tuser, cdc_m_tlast, cdc_m_tkeep, cdc_m_tdata}
                            <= cdc_out_fifo_mem[cdc_out_rd_ptr[ADDR_W-1:0]];
                        cdc_out_rd_ptr <= cdc_out_rd_ptr + 1;
                        cdc_m_tvalid_reg <= 1;
                    end else if (m_axis_tready) begin
                        cdc_m_tvalid_reg <= 0;
                    end
                end
            end

            assign m_axis_tdata   = cdc_m_tdata;
            assign m_axis_tkeep   = cdc_m_tkeep;
            assign m_axis_tvalid  = cdc_m_tvalid_reg;
            assign m_axis_tlast   = cdc_m_tlast;
            assign m_axis_tuser   = cdc_m_tuser;
            assign hls_out_tready = !cdc_out_full;

        end else begin : gen_sync

            // --------------------------------------------------------------------
            // Synchronous mode: HLS passthrough
            // IMPORTANT: hls_in_tvalid is gated by !meta_full to ensure data
            // never enters the HLS pipeline unless the metadata FIFO can
            // capture the TUSER. Without this gate, sustained output
            // backpressure could fill the metadata FIFO while data continues
            // to flow into the HLS module unmonitored, causing TUSER loss.
            // --------------------------------------------------------------------
            assign hls_in_tdata  = s_axis_tdata;
            assign hls_in_tkeep  = s_axis_tkeep;
            assign hls_in_tvalid = s_axis_tvalid && !meta_full;
            assign hls_in_tlast  = s_axis_tlast;
            assign s_axis_tready = hls_in_tready && !meta_full;

            // TUSER is NOT passed to the HLS module by default. The metadata
            // FIFO captures TUSER at ingress and replays it at egress.
            // When C_PASS_TUSER_TO_HLS is set, TUSER is forwarded for use
            // by HLS modules that directly support TUSER metadata.
            assign hls_in_tuser = C_PASS_TUSER_TO_HLS
                ? s_axis_tuser
                : {C_M_AXIS_TUSER_WIDTH{1'b0}};

            // Egress: detect first beat of HLS output packet
            reg hls_out_was_last;

            always @(posedge clk_shell) begin
                if (!rst_n) begin
                    hls_out_was_last <= 1;
                end else if (hls_out_tvalid && hls_out_tready && hls_out_tlast) begin
                    hls_out_was_last <= 1;
                end else if (hls_out_tvalid && hls_out_tready) begin
                    hls_out_was_last <= 0;
                end
            end

            wire hls_out_first_beat = hls_out_tvalid && hls_out_tready && hls_out_was_last;

            // --------------------------------------------------------------------
            // Metadata FIFO (synchronous)
            // --------------------------------------------------------------------
            reg [C_S_AXIS_TUSER_WIDTH-1:0] meta_fifo     [0:C_METADATA_FIFO_DEPTH-1];
            reg [$clog2(C_METADATA_FIFO_DEPTH)-1:0] meta_wr_ptr;
            reg [$clog2(C_METADATA_FIFO_DEPTH)-1:0] meta_rd_ptr;
            reg [C_METADATA_FIFO_DEPTH:0]            meta_count;

            wire meta_full  = (meta_count == C_METADATA_FIFO_DEPTH);
            wire meta_empty = (meta_count == 0);

            wire meta_we = in_first && !meta_full;
            wire meta_re = hls_out_first_beat && !meta_empty;

            always @(posedge clk_shell) begin
                if (!axis_aresetn) begin
                    meta_wr_ptr <= 0;
                    meta_rd_ptr <= 0;
                    meta_count  <= 0;
                end else begin
                    if (meta_we && !meta_re) begin
                        meta_fifo[meta_wr_ptr] <= s_axis_tuser;
                        meta_wr_ptr <= meta_wr_ptr + 1;
                        meta_count  <= meta_count + 1;
                    end else if (!meta_we && meta_re) begin
                        meta_rd_ptr <= meta_rd_ptr + 1;
                        meta_count  <= meta_count - 1;
                    end else if (meta_we && meta_re) begin
                        meta_fifo[meta_wr_ptr] <= s_axis_tuser;
                        meta_wr_ptr <= meta_wr_ptr + 1;
                        meta_rd_ptr <= meta_rd_ptr + 1;
                    end
                end
            end

            wire [C_S_AXIS_TUSER_WIDTH-1:0] meta_data = meta_fifo[meta_rd_ptr];

            // --------------------------------------------------------------------
            // Egress: hold metadata for entire HLS output packet
            // --------------------------------------------------------------------
            reg [C_S_AXIS_TUSER_WIDTH-1:0] egress_tuser;

            always @(posedge clk_shell) begin
                if (!axis_aresetn) begin
                    egress_tuser <= 0;
                end else if (hls_out_first_beat) begin
                    egress_tuser <= meta_data;
                end
            end

            // --------------------------------------------------------------------
            // Output stage with optional register slices
            // --------------------------------------------------------------------
            if (C_NUM_REG_SLICES > 0) begin : gen_reg_slice
                reg [C_S_AXIS_TDATA_WIDTH-1:0]     s0_tdata;
                reg [C_S_AXIS_TDATA_WIDTH/8-1:0]   s0_tkeep;
                reg                                 s0_tvalid;
                reg                                 s0_tlast;
                reg [C_S_AXIS_TUSER_WIDTH-1:0]     s0_tuser;

                if (C_NUM_REG_SLICES > 1) begin : gen_two_slices
                    reg [C_S_AXIS_TDATA_WIDTH-1:0]     s1_tdata;
                    reg [C_S_AXIS_TDATA_WIDTH/8-1:0]   s1_tkeep;
                    reg                                 s1_tvalid;
                    reg                                 s1_tlast;
                    reg [C_S_AXIS_TUSER_WIDTH-1:0]     s1_tuser;

                    wire s1_accept = s0_tvalid && (m_axis_tready || !s1_tvalid);
                    wire s0_ready  = m_axis_tready || !s1_tvalid || !s0_tvalid;

                    always @(posedge clk_shell) begin
                        if (!axis_aresetn) begin
                            s0_tvalid <= 0;
                        end else begin
                            if (hls_out_tvalid && s0_ready) begin
                                s0_tdata  <= hls_out_tdata;
                                s0_tkeep  <= hls_out_tkeep;
                                s0_tvalid <= 1'b1;
                                s0_tlast  <= hls_out_tlast;
                                s0_tuser  <= hls_out_first_beat ? meta_data : egress_tuser;
                            end else if (s1_accept) begin
                                s0_tvalid <= 1'b0;
                            end
                        end
                    end

                    assign hls_out_tready = s0_ready;

                    always @(posedge clk_shell) begin
                        if (!axis_aresetn) begin
                            s1_tvalid <= 0;
                        end else if (m_axis_tready || !s1_tvalid) begin
                            s1_tdata  <= s0_tdata;
                            s1_tkeep  <= s0_tkeep;
                            s1_tvalid <= s0_tvalid;
                            s1_tlast  <= s0_tlast;
                            s1_tuser  <= s0_tuser;
                        end
                    end

                    assign m_axis_tdata  = s1_tdata;
                    assign m_axis_tkeep  = s1_tkeep;
                    assign m_axis_tvalid = s1_tvalid;
                    assign m_axis_tlast  = s1_tlast;
                    assign m_axis_tuser  = s1_tuser;

                end else begin : gen_one_slice
                    always @(posedge clk_shell) begin
                        if (!axis_aresetn) begin
                            s0_tvalid <= 0;
                        end else begin
                            s0_tdata  <= hls_out_tdata;
                            s0_tkeep  <= hls_out_tkeep;
                            s0_tvalid <= hls_out_tvalid;
                            s0_tlast  <= hls_out_tlast;
                            s0_tuser  <= hls_out_first_beat ? meta_data : egress_tuser;
                        end
                    end

                    assign hls_out_tready = m_axis_tready;

                    assign m_axis_tdata  = s0_tdata;
                    assign m_axis_tkeep  = s0_tkeep;
                    assign m_axis_tvalid = s0_tvalid;
                    assign m_axis_tlast  = s0_tlast;
                    assign m_axis_tuser  = s0_tuser;
                end

            end else begin : gen_no_reg_slice
                assign m_axis_tdata   = hls_out_tdata;
                assign m_axis_tkeep   = hls_out_tkeep;
                assign m_axis_tvalid  = hls_out_tvalid;
                assign m_axis_tlast   = hls_out_tlast;
                assign m_axis_tuser   = hls_out_first_beat ? meta_data : egress_tuser;
                assign hls_out_tready = m_axis_tready;
            end

        end
    endgenerate

endmodule
