"""SheetsPort on the Google Sheets API. All cells are written RAW (plain strings)."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from .base import PermanentError
from .google_auth import build_service
from .google_errors import execute


def column_letter(index: int) -> str:
    """0 -> A, 25 -> Z, 26 -> AA, 701 -> ZZ, 702 -> AAA."""
    letters, n = "", index + 1
    while n:
        n, rem = divmod(n - 1, 26)
        letters = chr(65 + rem) + letters
    return letters


def quote_tab(tab: str) -> str:
    """Tab name as an A1 sheet reference: 'Jobs', with quotes doubled."""
    return "'" + tab.replace("'", "''") + "'"


class GoogleSheets:
    def __init__(self, spreadsheet_id: str, service: Any | None = None) -> None:
        self.spreadsheet_id = spreadsheet_id
        self._svc = service or build_service("sheets", "v4")

    @property
    def url(self) -> str:
        return f"https://docs.google.com/spreadsheets/d/{self.spreadsheet_id}/edit"

    @staticmethod
    def create_spreadsheet(title: str, tabs: Sequence[str] = (), service: Any | None = None) -> str:
        """Create a spreadsheet (optionally with these tabs instead of 'Sheet1'). Returns its id."""
        svc = service or build_service("sheets", "v4")
        body: dict[str, Any] = {"properties": {"title": title}}
        if tabs:
            body["sheets"] = [{"properties": {"title": t}} for t in tabs]
        return execute(svc.spreadsheets().create(body=body, fields="spreadsheetId"))["spreadsheetId"]

    def title(self) -> str | None:
        """Spreadsheet title, or None if it no longer exists."""
        got = execute(self._svc.spreadsheets().get(spreadsheetId=self.spreadsheet_id, fields="properties.title"),
                      none_on=(404,))
        return None if got is None else got["properties"]["title"]

    # ---------- SheetsPort ----------
    def read_tab(self, tab: str) -> list[list[str]]:
        got = execute(self._svc.spreadsheets().values().get(spreadsheetId=self.spreadsheet_id, range=quote_tab(tab)))
        return [[str(cell) for cell in row] for row in got.get("values", [])]

    def write_tab(self, tab: str, rows: list[list[str]]) -> None:
        sheet_id = self._ensure_tab(tab)
        values = self._svc.spreadsheets().values()
        execute(values.clear(spreadsheetId=self.spreadsheet_id, range=quote_tab(tab), body={}))
        if rows:
            execute(values.update(spreadsheetId=self.spreadsheet_id, range=f"{quote_tab(tab)}!A1",
                                  valueInputOption="RAW", body={"values": [[str(c) for c in r] for r in rows]}))
        # Plain-text cells (so a hand edit like "8:00" stays text), bold frozen header, fitted columns.
        width = max((len(r) for r in rows), default=1)
        execute(self._svc.spreadsheets().batchUpdate(spreadsheetId=self.spreadsheet_id, body={"requests": [
            {"repeatCell": {"range": {"sheetId": sheet_id},
                            "cell": {"userEnteredFormat": {"numberFormat": {"type": "TEXT"}}},
                            "fields": "userEnteredFormat.numberFormat"}},
            {"repeatCell": {"range": {"sheetId": sheet_id, "startRowIndex": 0, "endRowIndex": 1},
                            "cell": {"userEnteredFormat": {"textFormat": {"bold": True}}},
                            "fields": "userEnteredFormat.textFormat.bold"}},
            {"updateSheetProperties": {"properties": {"sheetId": sheet_id, "gridProperties": {"frozenRowCount": 1}},
                                       "fields": "gridProperties.frozenRowCount"}},
            {"autoResizeDimensions": {"dimensions": {"sheetId": sheet_id, "dimension": "COLUMNS",
                                                     "startIndex": 0, "endIndex": width}}},
        ]}))

    def update_row(self, tab: str, key: str, values: dict[str, str]) -> None:
        rows = self.read_tab(tab)
        if not rows:
            raise PermanentError(f"Tab {tab!r} is empty")
        header = [h.strip() for h in rows[0]]
        if "id" not in header:
            raise PermanentError(f"Tab {tab!r} has no 'id' column")
        id_col = header.index("id")
        row_number = next((n for n, row in enumerate(rows[1:], start=2)
                           if len(row) > id_col and row[id_col].strip() == key), None)
        if row_number is None:
            raise PermanentError(f"No row with id {key!r} in {tab!r}")
        missing = [col for col in values if col not in header]
        if missing:
            raise PermanentError(f"Tab {tab!r} has no column(s) {missing}")
        data = [{"range": f"{quote_tab(tab)}!{column_letter(header.index(col))}{row_number}", "values": [[str(v)]]}
                for col, v in values.items()]
        if data:
            execute(self._svc.spreadsheets().values().batchUpdate(
                spreadsheetId=self.spreadsheet_id, body={"valueInputOption": "RAW", "data": data}))

    # ---------- helpers ----------
    def _ensure_tab(self, tab: str) -> int:
        """sheetId of `tab`, adding the tab if it doesn't exist."""
        meta = execute(self._svc.spreadsheets().get(spreadsheetId=self.spreadsheet_id,
                                                    fields="sheets.properties(sheetId,title)"))
        for sheet in meta.get("sheets", []):
            if sheet["properties"]["title"] == tab:
                return sheet["properties"]["sheetId"]
        reply = execute(self._svc.spreadsheets().batchUpdate(
            spreadsheetId=self.spreadsheet_id, body={"requests": [{"addSheet": {"properties": {"title": tab}}}]}))
        return reply["replies"][0]["addSheet"]["properties"]["sheetId"]
