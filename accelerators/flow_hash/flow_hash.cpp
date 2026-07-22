#include <ap_axi_sdata.h>
#include <hls_stream.h>
#include <ap_int.h>

#define DATA_WIDTH 512
#define KEEP_WIDTH (DATA_WIDTH / 8)

typedef ap_axiu<DATA_WIDTH, KEEP_WIDTH, 1, 0> axis_word;
typedef hls::stream<axis_word> axis_stream;

void flow_hash(
    axis_stream &s_axis,
    axis_stream &m_axis
) {
#pragma HLS INTERFACE axis port=s_axis
#pragma HLS INTERFACE axis port=m_axis
#pragma HLS INTERFACE ap_ctrl_none port=return

    axis_word w = s_axis.read();
    m_axis.write(w);
}
