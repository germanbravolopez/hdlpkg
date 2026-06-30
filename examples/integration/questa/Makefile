# Example: compile a project's IP dependencies (from hdlpkg) into a QuestaSim library.
#
# This is the shape of a typical per-tool Makefile: it owns the project's own RTL and the
# vsim run, while hdlpkg supplies the dependency IP as ordered ".f" filelists compiled
# straight from the cache -- the IP is never vendored into the project tree.
#
# QuestaCDC and Quartus integrate the same way: depend on `hdlpkg-filelist` and read the
# generated $(HDLPKG_OUT)/*.f lists (qverify / quartus_map take filelists too).

HDLPKG_TARGET ?= sim
include ../hdlpkg.mk

# The project's own sources + top, compiled after the IP. Replace with your real flow.
PROJECT_SRC ?= rtl/top.sv
TOP         ?= top
WORK        ?= work

.PHONY: compile simulate clean

## Compile the IP (from the hdlpkg cache) then the project's own RTL, all into one library.
compile: hdlpkg-filelist
	vlib $(WORK)
	# IP first, in dependency order. `-f` reads a filelist of sources (flat single 'work').
	@for f in $(HDLPKG_OUT)/*.vhdl.f; do \
	    [ -e "$$f" ] && vcom -work $(WORK) -f "$$f" || true; \
	done
	@for f in $(HDLPKG_OUT)/*.verilog.f $(HDLPKG_OUT)/*.systemverilog.f; do \
	    [ -e "$$f" ] && vlog -work $(WORK) -f "$$f" || true; \
	done
	# Then the project's own RTL, which may instantiate the IP compiled above.
	vlog -work $(WORK) $(PROJECT_SRC)

simulate: compile
	vsim -c -do "run -all; quit" $(WORK).$(TOP)

clean: hdlpkg-clean
	$(RM) -r $(WORK) transcript vsim.wlf
