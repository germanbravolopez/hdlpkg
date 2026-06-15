# hdl-ip-packager — renamed to **hdlpkg**

This project was renamed. **`hdl-ip-packager` is deprecated**; all development continues
under **[`hdlpkg`](https://pypi.org/project/hdlpkg/)**.

```bash
pip install hdlpkg
```

This `hdl-ip-packager` distribution (0.12.1+) is a metadata-only shim that simply depends
on `hdlpkg`, so an existing `pip install hdl-ip-packager` keeps installing the working tool
and the `hdlpkg` command. It ships no code of its own.

**Import note:** the Python import package was also renamed, with no alias —
use `import hdlpkg` (not `import hdl_ip_packager`). The CLI command (`hdlpkg`) and the
on-disk formats (`ip.toml`, `ip.lock`) are unchanged.

Source and issues: https://github.com/germanbravolopez/hdlpkg
