"""Thẻ bằng chứng (evidence card): mỗi nhận định đi kèm chỉ số, kỳ dữ liệu, nguồn và phép tính."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Evidence:
    id: str                      # "E1", "E2"...
    claim: str                   # nhận định hiển thị cho người dùng
    kind: str                    # "thesis" | "risk" | "scenario" | "info"
    metrics: list = field(default_factory=list)   # [(tên chỉ số, giá trị đã định dạng)]
    period: str = ""             # kỳ dữ liệu, VD "FY2021-FY2025" hoặc "04/09/2025-08/10/2026"
    source: str = ""             # nguồn dữ liệu
    formula: str = ""            # công thức tổng quát
    calc: str = ""               # phép tính với số liệu thực tế
    tone: int = 0                # +1 tích cực, -1 tiêu cực, 0 trung tính

    def as_dict(self) -> dict:
        return self.__dict__.copy()


class EvidenceBook:
    """Sổ bằng chứng: cấp mã E1, E2... theo thứ tự xuất hiện."""

    def __init__(self):
        self.items: list[Evidence] = []

    def add(self, claim: str, kind: str, metrics=None, period="", source="", formula="", calc="", tone=0) -> Evidence:
        ev = Evidence(id=f"E{len(self.items) + 1}", claim=claim, kind=kind, metrics=metrics or [], period=period,
                      source=source, formula=formula, calc=calc, tone=tone)
        self.items.append(ev)
        return ev

    def by_kind(self, kind: str) -> list[Evidence]:
        return [e for e in self.items if e.kind == kind]

    def get(self, eid: str) -> Evidence | None:
        return next((e for e in self.items if e.id == eid), None)
