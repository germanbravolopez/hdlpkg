# Integrating hdlpkg with a Makefile-based build flow

hdlpkg can emit plain, ordered **`.f` filelists** so a Makefile-based build flow (QuestaSim,
QuestaCDC, Quartus, Vivado, ...) can compile the **IP dependencies** straight from the cache —
without committing or vendoring the IP source into the project. hdlpkg supplies the IP; the
build flow compiles it.

## The idea

1. Your project's `ip.toml` declares its IP dependencies; `ip.lock` pins them (commit both).
2. `hdlpkg install` fetches the locked IP into the content-addressed **cache**
   (`~/.hdlpkg/cache`, or a shared dir via `--cache-dir`). **No source lands in your repo.**
3. `hdlpkg gen <target> --format filelist` materializes those dependencies in the cache and
   writes ordered `.f` lists — one per HDL type — of **absolute cache paths**, in compile
   order (dependencies first):

   ```
   build/hdlpkg/<name>.vhdl.f
   build/hdlpkg/<name>.systemverilog.f
   build/hdlpkg/<name>.verilog.f
   ```

4. Your existing `compile` / `simulate` / `synthesize` targets read those `.f` lists (most
   tools accept `-f <filelist>`) and build the IP from the cache, then build your own RTL.

The IP stays **out of the project** (not a submodule, not vendored); it lives in the cache and
is referenced by path. Note this keeps the IP out of your *repo*, not cryptographically hidden
from the compiler — the cache files are readable. Source that is unreadable even to the build
needs IEEE 1735 encrypted IP, which is on the hdlpkg roadmap.

## Files here

| File | What it is |
|------|------------|
| [`hdlpkg.mk`](hdlpkg.mk) | A reusable include: variables + `hdlpkg-install` / `hdlpkg-filelist` / `hdlpkg-clean` targets. Drop it in your makefiles submodule. |
| [`questa/Makefile`](questa/Makefile) | A worked QuestaSim example: compile the IP filelists into a `work` library, then the project's own RTL, then `vsim`. |

## Wiring it in

```make
HDLPKG_TARGET := sim
include path/to/hdlpkg.mk

compile: hdlpkg-filelist          # ensure the IP is installed + filelists are current
	# ... your vcom/vlog -f $(HDLPKG_OUT)/*.f, then your own sources ...
```

One-time per project, create the lockfile (then commit it):

```bash
hdlpkg resolve --registry oci://harbor.corp.local/ip   # writes ip.lock
```

After that the Make flow is reproducible and needs no `--registry` — `hdlpkg install --locked`
and `hdlpkg gen --locked` fetch each core from the source the lock recorded, fully offline once
the cache is warm.

## Knobs (`hdlpkg.mk` variables)

| Variable | Default | Meaning |
|----------|---------|---------|
| `HDLPKG_MANIFEST` | `ip.toml` | the project manifest |
| `HDLPKG_TARGET` | `sim` | which `[targets.*]` to build the filelist for |
| `HDLPKG_OUT` | `build/hdlpkg` | where the `.f` lists are written |
| `HDLPKG_CACHE` | _(unset)_ | a shared cache dir (else `~/.hdlpkg/cache`) |
| `HDLPKG_INSTALL_FLAGS` | `--locked` | reproducible by default; clear to allow re-resolve |

> Tip: the filelists carry a single flat list compiled into one library (`work`). hdlpkg's
> name-mangling keeps two versions of the same core from colliding. A future "one library per
> core" mode can map each IP to its own logical library if your flow prefers that.
