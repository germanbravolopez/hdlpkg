"""IP-XACT (IEEE 1685) export.

IP-XACT is the XML standard for *describing* an IP component: its VLNV identity,
its source filesets, and a model of build views. Many EDA tools (Vivado in
particular) ingest IP-XACT, so exporting one lets a core authored with this
packager be consumed by the wider tool ecosystem. We borrow IP-XACT's VLNV scheme
already (see ``vlnv.py``); here we emit a component document from a manifest.

:func:`to_ipxact` is **pure**: it maps a :class:`~hdlpkg.manifest.Manifest`
to a deterministic XML string (no I/O), so the CLI ``export-ipxact`` command is a
thin write wrapper. It targets **IEEE 1685-2014** by default and **1685-2022** with
``std="2022"`` (the ``--std`` flag), and **validates against the official Accellera XSD**
for the chosen standard (enforced by a test). The emitted shape is the VLNV, a ``model``
of one view + componentInstantiation per ``[targets.*]``, and the ``fileSets``; the only
structural difference between the two standards is where ``description`` sits (2022 carries
it in the ``documentNameGroup`` right after the version; 2014 trails it after ``fileSets``).
The manifest fileset ``type`` vocabulary (``systemVerilogSource``/``verilogSource``/
``vhdlSource``) is already the IP-XACT ``fileType`` enumeration so it passes straight
through; a custom or tool-specific type is emitted as the IP-XACT ``user`` form (see
:func:`_file_type`).
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from collections.abc import Callable
from typing import Literal

from .manifest import Manifest

# A namespace-bound ``sub(parent, tag, text=None)`` element-appender.
_Sub = Callable[..., ET.Element]

__all__ = [
    "DEFAULT_IPXACT_STD",
    "IPXACT_NAMESPACE",
    "IPXACT_NAMESPACES",
    "SUPPORTED_IPXACT_STDS",
    "IpxactStd",
    "to_ipxact",
]

# The IP-XACT standard revisions this exporter can emit, each with its XML namespace.
IpxactStd = Literal["2014", "2022"]
IPXACT_NAMESPACES: dict[IpxactStd, str] = {
    "2014": "http://www.accellera.org/XMLSchema/IPXACT/1685-2014",
    "2022": "http://www.accellera.org/XMLSchema/IPXACT/1685-2022",
}
SUPPORTED_IPXACT_STDS: tuple[IpxactStd, ...] = ("2014", "2022")
DEFAULT_IPXACT_STD: IpxactStd = "2014"

# Back-compat: the original module-level constant kept pointing at 2014.
IPXACT_NAMESPACE = IPXACT_NAMESPACES["2014"]
_XSI_NAMESPACE = "http://www.w3.org/2001/XMLSchema-instance"

# The IEEE 1685-2014 ``ipxact:fileType`` enumeration (from the official schema's
# fileType.xsd). 1685-2022 only *adds* types, so any value valid here is valid there too;
# a value outside this set is not valid as a plain value in either, so IP-XACT expresses it
# as ``<fileType user="...">user</fileType>`` instead (see _file_type).
_FILE_TYPE_ENUM = frozenset(
    {
        "unknown",
        "cSource",
        "cppSource",
        "asmSource",
        "vhdlSource",
        "vhdlSource-87",
        "vhdlSource-93",
        "verilogSource",
        "verilogSource-95",
        "verilogSource-2001",
        "swObject",
        "swObjectLibrary",
        "vhdlBinaryLibrary",
        "verilogBinaryLibrary",
        "unelaboratedHdl",
        "executableHdl",
        "systemVerilogSource",
        "systemVerilogSource-3.0",
        "systemVerilogSource-3.1",
        "systemCSource",
        "systemCSource-2.0",
        "systemCSource-2.0.1",
        "systemCSource-2.1",
        "systemCSource-2.2",
        "veraSource",
        "eSource",
        "perlSource",
        "tclSource",
        "OVASource",
        "SVASource",
        "pslSource",
        "systemVerilogSource-3.1a",
        "SDC",
        "vhdlAmsSource",
        "verilogAmsSource",
        "systemCAmsSource",
        "libertySource",
        "user",
    }
)


def _suber(namespace: str) -> _Sub:
    """Return a ``sub(parent, tag, text=None)`` helper bound to *namespace*."""

    def sub(parent: ET.Element, tag: str, text: str | None = None) -> ET.Element:
        element = ET.SubElement(parent, f"{{{namespace}}}{tag}")
        if text is not None:
            element.text = text
        return element

    return sub


def _file_type(sub: _Sub, parent: ET.Element, file_type: str) -> None:
    """Append an ``ipxact:fileType`` for *file_type*, conformant to the standard's enum.

    A standard type is emitted verbatim; any other (a custom or tool-specific type, e.g.
    from a generator/glob fileset) becomes ``<fileType user="<type>">user</fileType>``,
    the IP-XACT escape for a non-enumerated type.
    """
    if file_type in _FILE_TYPE_ENUM:
        sub(parent, "fileType", file_type)
    else:
        sub(parent, "fileType", "user").set("user", file_type)


def to_ipxact(manifest: Manifest, std: IpxactStd = DEFAULT_IPXACT_STD) -> str:
    """Render *manifest* as an IP-XACT component XML document for IEEE 1685-*std*."""
    namespace = IPXACT_NAMESPACES[std]
    sub = _suber(namespace)
    ET.register_namespace("ipxact", namespace)
    ET.register_namespace("xsi", _XSI_NAMESPACE)

    component = ET.Element(f"{{{namespace}}}component")
    component.set(
        f"{{{_XSI_NAMESPACE}}}schemaLocation",
        f"{namespace} {namespace}/index.xsd",
    )

    vlnv = manifest.vlnv
    sub(component, "vendor", vlnv.vendor)
    sub(component, "library", vlnv.library)
    sub(component, "name", vlnv.name)
    sub(component, "version", str(vlnv.version))

    # 2022 carries description in the documentNameGroup, right after the version; 2014 has
    # no slot here and trails it after fileSets instead (see the end of this function).
    if std == "2022" and manifest.description:
        sub(component, "description", manifest.description)

    # model: one view + componentInstantiation per build target.
    if manifest.targets:
        model = sub(component, "model")
        views = sub(model, "views")
        for target_name in manifest.targets:
            view = sub(views, "view")
            sub(view, "name", target_name)
            sub(view, "componentInstantiationRef", target_name)
        instantiations = sub(model, "instantiations")
        for target_name, target in manifest.targets.items():
            inst = sub(instantiations, "componentInstantiation")
            sub(inst, "name", target_name)
            module = target.top or manifest.top
            if module is not None:
                sub(inst, "moduleName", module)
            for fileset_name in target.filesets:
                ref = sub(inst, "fileSetRef")
                sub(ref, "localName", fileset_name)

    # fileSets: the source files, grouped, with their IP-XACT fileType.
    if manifest.filesets:
        filesets = sub(component, "fileSets")
        for name, fileset in manifest.filesets.items():
            fs_element = sub(filesets, "fileSet")
            sub(fs_element, "name", name)
            for path in fileset.files:
                file_element = sub(fs_element, "file")
                sub(file_element, "name", path)
                _file_type(sub, file_element, fileset.type)

    if std == "2014" and manifest.description:
        sub(component, "description", manifest.description)

    ET.indent(component, space="  ")
    body = ET.tostring(component, encoding="unicode")
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + body + "\n"
