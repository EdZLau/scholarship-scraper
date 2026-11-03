"""
Google Sheets API integration.

Writes scholarship data to a Google Sheet.
Requires a service account JSON credentials file.

Setup:
  1. Create a Google Cloud project
  2. Enable Google Sheets API + Google Drive API
  3. Create a service account → download JSON key
  4. Set env var GOOGLE_CREDENTIALS_PATH=/path/to/credentials.json
  5. Share your target sheet with the service account email
  6. Set env var GOOGLE_SHEET_ID=your_sheet_id
"""

import os
import logging
from typing import List

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from data.models import Scholarship

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

SHEET_NAME = "Scholarships"


def _build_service():
    creds_path = os.environ.get("GOOGLE_CREDENTIALS_PATH")
    if not creds_path:
        raise EnvironmentError("GOOGLE_CREDENTIALS_PATH not set.")
    creds = Credentials.from_service_account_file(creds_path, scopes=SCOPES)
    return build("sheets", "v4", credentials=creds)


def write_to_sheet(scholarships: List[Scholarship]) -> str:
    """
    Writes all scholarships to the Google Sheet.
    Clears existing data, writes headers, then writes all rows.
    Returns the sheet URL.
    """
    sheet_id = os.environ.get("GOOGLE_SHEET_ID")
    if not sheet_id:
        raise EnvironmentError("GOOGLE_SHEET_ID not set.")

    service = _build_service()
    sheet = service.spreadsheets()

    # Ensure tab exists
    _ensure_sheet_tab(service, sheet_id)

    # Build rows
    headers = Scholarship.sheets_headers()
    rows = [headers] + [s.to_sheets_row() for s in scholarships]

    # Clear existing content
    range_name = f"{SHEET_NAME}!A1:Z10000"
    sheet.values().clear(spreadsheetId=sheet_id, range=range_name).execute()

    # Write data
    body = {"values": rows}
    result = sheet.values().update(
        spreadsheetId=sheet_id,
        range=f"{SHEET_NAME}!A1",
        valueInputOption="RAW",
        body=body,
    ).execute()

    # Format header row
    _format_headers(service, sheet_id)

    # Auto-resize columns
    _auto_resize(service, sheet_id)

    rows_written = result.get("updatedRows", 0)
    url = f"https://docs.google.com/spreadsheets/d/{sheet_id}"
    logger.info(f"[sheets] wrote {rows_written} rows → {url}")
    return url


def _ensure_sheet_tab(service, sheet_id: str):
    """Create the 'Scholarships' tab if it doesn't exist."""
    try:
        meta = service.spreadsheets().get(spreadsheetId=sheet_id).execute()
        existing = [s["properties"]["title"] for s in meta.get("sheets", [])]
        if SHEET_NAME not in existing:
            body = {"requests": [{"addSheet": {"properties": {"title": SHEET_NAME}}}]}
            service.spreadsheets().batchUpdate(
                spreadsheetId=sheet_id, body=body
            ).execute()
            logger.info(f"[sheets] created tab '{SHEET_NAME}'")
    except HttpError as e:
        logger.error(f"[sheets] could not ensure tab: {e}")


def _format_headers(service, sheet_id: str):
    """Bold the header row and freeze it."""
    try:
        meta = service.spreadsheets().get(spreadsheetId=sheet_id).execute()
        tab_id = next(
            s["properties"]["sheetId"]
            for s in meta["sheets"]
            if s["properties"]["title"] == SHEET_NAME
        )
        requests = [
            # Bold header
            {
                "repeatCell": {
                    "range": {"sheetId": tab_id, "startRowIndex": 0, "endRowIndex": 1},
                    "cell": {
                        "userEnteredFormat": {
                            "textFormat": {"bold": True},
                            "backgroundColor": {"red": 0.2, "green": 0.4, "blue": 0.8},
                        }
                    },
                    "fields": "userEnteredFormat(textFormat,backgroundColor)",
                }
            },
            # Freeze header row
            {
                "updateSheetProperties": {
                    "properties": {
                        "sheetId": tab_id,
                        "gridProperties": {"frozenRowCount": 1},
                    },
                    "fields": "gridProperties.frozenRowCount",
                }
            },
        ]
        service.spreadsheets().batchUpdate(
            spreadsheetId=sheet_id, body={"requests": requests}
        ).execute()
    except Exception as e:
        logger.warning(f"[sheets] header formatting failed (non-fatal): {e}")


def _auto_resize(service, sheet_id: str):
    """Auto-resize all columns for readability."""
    try:
        meta = service.spreadsheets().get(spreadsheetId=sheet_id).execute()
        tab_id = next(
            s["properties"]["sheetId"]
            for s in meta["sheets"]
            if s["properties"]["title"] == SHEET_NAME
        )
        service.spreadsheets().batchUpdate(
            spreadsheetId=sheet_id,
            body={
                "requests": [{
                    "autoResizeDimensions": {
                        "dimensions": {
                            "sheetId": tab_id,
                            "dimension": "COLUMNS",
                            "startIndex": 0,
                            "endIndex": 11,
                        }
                    }
                }]
            },
        ).execute()
    except Exception as e:
        logger.warning(f"[sheets] auto-resize failed (non-fatal): {e}")
