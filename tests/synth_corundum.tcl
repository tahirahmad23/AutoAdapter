# AutoAdapter — Corundum Shell Synthesis Script (synthesis only)
# Usage: vivado -mode batch -source synth_corundum.tcl

set repo_dir "/home/ubuntu"
set output_dir "${repo_dir}/output/corundum_synth"

set configs [list \
    [list flow_hash   5 16 2 0] \
    [list flow_hash   5 16 2 1] \
    [list packet_monitor 2 8 1 0] \
    [list packet_monitor 2 8 1 1] \
]

set part "xcu200-fsgd2104-2-e"

foreach cfg $configs {
    set accel_name   [lindex $cfg 0]
    set hls_latency  [lindex $cfg 1]
    set fifo_depth   [lindex $cfg 2]
    set num_slices   [lindex $cfg 3]
    set clk_crossing [lindex $cfg 4]

    set build_name "${accel_name}_lat${hls_latency}_fifo${fifo_depth}_slices${num_slices}_xing${clk_crossing}"
    set build_dir "${output_dir}/${build_name}"

    puts "========================================"
    puts "Synthesizing: ${build_name}"
    puts "========================================"

    file mkdir ${build_dir}

    create_project -part ${part} corundum_adapter ${build_dir} -force

    set adapter_rtl "${repo_dir}/output/corundum_mqnic-${accel_name}/hdl/auto_adapter_top.sv"
    if {![file exists ${adapter_rtl}]} {
        puts "ERROR: Adapter RTL not found at ${adapter_rtl}"
        close_project
        continue
    }

    add_files [list ${adapter_rtl} ${repo_dir}/tests/synth_top.sv]

    set_property top synth_top [current_fileset]
    set_property generic "TDATA_WIDTH=512 TUSER_WIDTH=97 FIFO_DEPTH=${fifo_depth} NUM_SLICES=${num_slices} CLK_CROSSING=${clk_crossing} HLS_LATENCY=${hls_latency}" [current_fileset]

    set xdc_file "${build_dir}/constraints.xdc"
    set fh [open ${xdc_file} w]
    puts ${fh} {create_clock -period 4.000 -name clk [get_ports clk]}
    puts ${fh} {create_clock -period 4.000 -name hls_clk [get_ports hls_clk]}
    close ${fh}
    add_files -fileset constrs_1 ${xdc_file}

    puts "  Running synthesis..."
    launch_runs synth_1 -jobs 8
    wait_on_run synth_1

    if {[get_property PROGRESS [get_runs synth_1]] != "100%"} {
        puts "  ERROR: Synthesis failed for ${build_name}"
        close_project
        continue
    }

    open_run synth_1

    puts "  Generating reports..."
    report_utilization -hierarchical -file "${build_dir}/utilization.rpt"
    report_timing_summary -file "${build_dir}/timing.rpt"
    report_timing -sort_by group -max_paths 10 -file "${build_dir}/timing_paths.rpt"

    puts "  Results saved to ${build_dir}"

    close_project
}

puts ""
puts "========================================"
puts "All Corundum synthesis runs complete!"
puts "========================================"
