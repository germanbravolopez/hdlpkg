# hdlpkg.mk -- drop-in Make integration for hdlpkg (https://hdlpkg.io)
#
# Resolves the IP your ip.toml depends on, installs it into the hdlpkg *cache* (the IP
# sources are never vendored into your repo), and emits ordered ".f" filelists you can feed
# straight to your compiler -- so a Make-based flow (QuestaSim, Quartus, ...) can build the
# IP from the cache without pulling its source.
#
# Usage: from your tool Makefile,
#
#     HDLPKG_TARGET := sim
#     include path/to/hdlpkg.mk
#     compile: hdlpkg-filelist          # make the IP filelists a prerequisite of your build
#         ... your vlog/vcom -f $(HDLPKG_OUT)/*.f ...
#
# One-time per project: run `hdlpkg resolve --registry <your-registry>` to create ip.lock
# (commit it). After that this include is reproducible and needs no --registry.

# --- configuration (override on the make command line or before `include`) -------------
HDLPKG               ?= hdlpkg
HDLPKG_MANIFEST      ?= ip.toml
HDLPKG_TARGET        ?= sim              # the [targets.*] in ip.toml to build a filelist for
HDLPKG_OUT           ?= build/hdlpkg     # where the .f filelists are written
HDLPKG_CACHE         ?=                  # optional shared cache dir (else ~/.hdlpkg/cache)
HDLPKG_INSTALL_FLAGS ?= --locked         # reproducible by default; clear to allow re-resolve

# --- derived ---------------------------------------------------------------------------
_HDLPKG_CACHE_ARG := $(if $(HDLPKG_CACHE),--cache-dir $(HDLPKG_CACHE),)
_HDLPKG_STAMP     := $(HDLPKG_OUT)/.hdlpkg.stamp

# Read these in your recipes (shell-glob at recipe time, not here, since they are generated):
#   $(HDLPKG_OUT)/*.vhdl.f           VHDL sources, in compile order
#   $(HDLPKG_OUT)/*.systemverilog.f  SystemVerilog sources, in compile order
#   $(HDLPKG_OUT)/*.verilog.f        Verilog sources, in compile order

# --- targets ---------------------------------------------------------------------------
.PHONY: hdlpkg-install hdlpkg-filelist hdlpkg-clean

## Fetch the locked IP into the hdlpkg cache (no sources pulled into the repo).
hdlpkg-install:
	$(HDLPKG) install $(HDLPKG_MANIFEST) $(HDLPKG_INSTALL_FLAGS) $(_HDLPKG_CACHE_ARG)

## Emit the ordered .f filelists for $(HDLPKG_TARGET); regenerated when the manifest changes.
$(_HDLPKG_STAMP): $(HDLPKG_MANIFEST) | hdlpkg-install
	$(HDLPKG) gen $(HDLPKG_TARGET) $(HDLPKG_MANIFEST) --format filelist \
	    $(HDLPKG_INSTALL_FLAGS) $(_HDLPKG_CACHE_ARG) --output $(HDLPKG_OUT)
	@touch $@

## Phony alias: depend on this from your compile target.
hdlpkg-filelist: $(_HDLPKG_STAMP)

hdlpkg-clean:
	$(RM) -r $(HDLPKG_OUT)
