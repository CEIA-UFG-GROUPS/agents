"""document_generator_tool — build the final travel report. See specs/tools.md."""

from __future__ import annotations

from app.schemas.report import DocumentInput, TravelReport


class DocumentGeneratorTool:
    """Assemble a travel justification/report from the approved trip."""

    name = "document_generator_tool"

    def generate(self, payload: DocumentInput) -> TravelReport:
        # The report is assembled by the DocumentAgent from typed TripRun data;
        # this tool wrapper is kept for the registry and returns an empty report.
        return TravelReport()
