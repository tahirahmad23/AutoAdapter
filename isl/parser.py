import json
import os
from dataclasses import dataclass, field
from typing import Optional

try:
    import jsonschema
    HAS_JSONSCHEMA = True
except ImportError:
    HAS_JSONSCHEMA = False

SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "schema.json")


class ISLError(Exception):
    pass


class ISLValidationError(ISLError):
    pass


@dataclass
class TUSERField:
    field: str
    width: int
    offset: int
    valid_on: str
    description: str = ""

    @property
    def msb(self) -> int:
        return self.offset + self.width - 1

    @property
    def lsb(self) -> int:
        return self.offset

    def bit_slice(self) -> str:
        return f"[{self.msb}:{self.lsb}]"


@dataclass
class ProtocolQuirks:
    tlast_required: bool = True
    tkeep_required: bool = True
    backpressure: str = "ready_valid"
    metadata_must_span_entire_packet: bool = True
    tuser_keep_on_idle: bool = False
    tstrb_present: bool = False


@dataclass
class ClockDomain:
    name: str
    freq: float


@dataclass
class ShellInterface:
    name: str
    clock_freq: float
    data_width: int
    tuser_width: int
    tuser_fields: list[TUSERField] = field(default_factory=list)
    tuser_encoding: dict = field(default_factory=lambda: {
        "byte_offset": 0, "bit_order": "little_endian"
    })
    protocol_quirks: ProtocolQuirks = field(default_factory=ProtocolQuirks)
    clock_domains: list[ClockDomain] = field(default_factory=list)
    description: str = ""

    @classmethod
    def from_isl(cls, path: str, validate: bool = True) -> "ShellInterface":
        with open(path) as f:
            data = json.load(f)
        if validate:
            errors = cls._validate_schema(data)
            if errors:
                msg = "\n  ".join(errors)
                raise ISLValidationError(
                    f"Schema validation failed for {path}:\n  {msg}"
                )
        return cls.from_dict(data)

    @staticmethod
    def _validate_schema(data: dict) -> list[str]:
        if not HAS_JSONSCHEMA:
            print("Warning: jsonschema not installed, skipping schema validation")
            return []
        with open(SCHEMA_PATH) as f:
            schema = json.load(f)
        validator = jsonschema.Draft7Validator(schema)
        return [str(e.message) for e in validator.iter_errors(data)]

    @classmethod
    def from_dict(cls, data: dict) -> "ShellInterface":
        fields = []
        auto_offset = 0
        for fd in data.get("tuser_fields", []):
            offset = fd.get("offset", auto_offset)
            fields.append(TUSERField(
                field=fd["field"],
                width=fd["width"],
                offset=offset,
                valid_on=fd.get("valid_on", "first_beat"),
                description=fd.get("description", ""),
            ))
            auto_offset = offset + fd["width"]

        tuser_width = data.get("tuser_width", 0)
        if not tuser_width and fields:
            tuser_width = max(f.offset + f.width for f in fields)

        quirks_data = data.get("protocol_quirks", {})
        quirks = ProtocolQuirks(
            tlast_required=quirks_data.get("tlast_required", True),
            tkeep_required=quirks_data.get("tkeep_required", True),
            backpressure=quirks_data.get("backpressure", "ready_valid"),
            metadata_must_span_entire_packet=quirks_data.get(
                "metadata_must_span_entire_packet", True
            ),
            tuser_keep_on_idle=quirks_data.get("tuser_keep_on_idle", False),
            tstrb_present=quirks_data.get("tstrb_present", False),
        )

        clock_domains = [
            ClockDomain(name=cd["name"], freq=cd["freq"])
            for cd in data.get("clock_domains", [])
        ]

        return cls(
            name=data["name"],
            description=data.get("description", ""),
            clock_freq=data["clock_freq"],
            data_width=data["data_width"],
            tuser_width=tuser_width,
            tuser_fields=fields,
            tuser_encoding=data.get("tuser_encoding", {
                "byte_offset": 0, "bit_order": "little_endian"
            }),
            protocol_quirks=quirks,
            clock_domains=clock_domains,
        )

    def validate_semantic(self) -> list[str]:
        errors = []
        total_tuser = self.tuser_width

        if not self.tuser_fields:
            errors.append("No TUSER fields defined")

        if total_tuser <= 0:
            errors.append(f"tuser_width={total_tuser} must be positive")

        for f in self.tuser_fields:
            if f.offset + f.width > total_tuser:
                errors.append(
                    f"Field '{f.field}' (offset={f.offset}, width={f.width}) "
                    f"exceeds tuser_width={total_tuser}"
                )

        if self.data_width % 8 != 0:
            errors.append(f"data_width={self.data_width} is not byte-aligned")

        offsets = [(f.field, f.offset, f.offset + f.width - 1)
                   for f in self.tuser_fields]
        for i, (name_i, lo_i, hi_i) in enumerate(offsets):
            for j, (name_j, lo_j, hi_j) in enumerate(offsets):
                if i < j and lo_i <= hi_j and lo_j <= hi_i:
                    errors.append(
                        f"Field '{name_i}' [{lo_i}:{hi_i}] overlaps "
                        f"with '{name_j}' [{lo_j}:{hi_j}]"
                    )

        return errors

    def get_field(self, name: str) -> Optional[TUSERField]:
        for f in self.tuser_fields:
            if f.field == name:
                return f
        return None

    def tuser_map(self) -> dict[str, tuple[int, int]]:
        return {f.field: (f.offset, f.width) for f in self.tuser_fields}

    def summary(self) -> str:
        lines = [
            f"Interface: {self.name}",
            f"  Clock:    {self.clock_freq} MHz",
            f"  Data:     {self.data_width}-bit",
            f"  TUSER:    {self.tuser_width}-bit",
            "  Fields:",
        ]
        for f in self.tuser_fields:
            lines.append(
                f"    {f.field:12s}  bits [{f.msb:3d}:{f.lsb:3d}]  "
                f"width={f.width:2d}  valid_on={f.valid_on}"
            )
        lines.append(f"  Quirks:   tlast={self.protocol_quirks.tlast_required}, "
                      f"tkeep={self.protocol_quirks.tkeep_required}, "
                      f"bp={self.protocol_quirks.backpressure}")
        if self.clock_domains:
            lines.append("  Domains:")
            for cd in self.clock_domains:
                lines.append(f"    {cd.name}: {cd.freq} MHz")
        return "\n".join(lines)


def load(path: str, validate_schema: bool = True) -> ShellInterface:
    return ShellInterface.from_isl(path, validate=validate_schema)


if __name__ == "__main__":
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else None
    if not path:
        print("Usage: python3 parser.py <isl_file.json>")
        sys.exit(1)
    try:
        iface = load(path)
        errors = iface.validate_semantic()
        if errors:
            print("Semantic errors:")
            for e in errors:
                print(f"  - {e}")
            sys.exit(1)
        print(iface.summary())
    except ISLError as e:
        print(f"Error: {e}")
        sys.exit(1)
