# sheets_api.py
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
from datetime import datetime, timedelta
import logging

logger = logging.getLogger("vershina.sheets")

_global_sheets = None

class SheetsAPI:
    def __init__(self, cred_path: str, spreadsheet_id: str):
        scopes = ['https://spreadsheets.google.com/feeds','https://www.googleapis.com/auth/drive']
        creds = ServiceAccountCredentials.from_json_keyfile_name(cred_path, scopes)
        self.gc = gspread.authorize(creds)
        self.sh = self.gc.open_by_key(spreadsheet_id)
        # ensure worksheets exist done outside
    def worksheet(self, name):
        try:
            return self.sh.worksheet(name)
        except Exception:
            return None

    def get_all_records(self, sheetname):
        ws = self.worksheet(sheetname)
        if not ws:
            return []
        return ws.get_all_records()

    def append_row(self, sheetname, row):
        ws = self.worksheet(sheetname)
        if not ws:
            ws = self.sh.add_worksheet(sheetname, rows=1000, cols=20)
            ws.append_row(list(row.keys()))
        ws.append_row(list(row.values()))

    # specific helpers:
    def append_slot(self, tutor_id, date_iso, time_str, note=""):
        ws = self.worksheet("Slots")
        if not ws:
            ws = self.sh.add_worksheet("Slots", rows=1000, cols=10)
            ws.append_row(["tutor_id","date_iso","time","note"])
        ws.append_row([tutor_id, date_iso, time_str, note])

    def append_lesson(self, date_iso, time_str, tutor_id, student, amount):
        ws = self.worksheet("Lessons")
        if not ws:
            ws = self.sh.add_worksheet("Lessons", rows=1000, cols=20)
            ws.append_row(["lesson_id","date_iso","time","tutor_id","student","amount","paid"])
        # auto id
        next_id = len(ws.get_all_values())
        ws.append_row([next_id, date_iso, time_str, tutor_id, student, amount, "no"])
        return next_id

    def get_slots_for_tutor(self, tutor_id):
        records = self.get_all_records("Slots")
        return [r for r in records if int(r.get("tutor_id",0)) == int(tutor_id)]

    def get_lessons_df(self):
        records = self.get_all_records("Lessons")
        if not records:
            return pd.DataFrame()
        return pd.DataFrame(records)

    def get_lessons_within_minutes(self, minutes=60):
        df = self.get_lessons_df()
        if df.empty:
            return []
        now = datetime.utcnow()
        result = []
        for r in df.to_dict(orient="records"):
            paid = str(r.get("paid","")).lower()
            if paid == "yes":
                continue
            date_iso = r.get("date_iso")
            time_str = r.get("time")
            try:
                dt = datetime.fromisoformat(f"{date_iso}T{time_str}")
            except Exception:
                try:
                    dt = datetime.strptime(f"{date_iso} {time_str}", "%Y-%m-%d %H:%M")
                except Exception:
                    continue
            diff = (dt - now).total_seconds()/60
            if 0 <= diff <= minutes:
                result.append(r)
        return result

    def mark_lesson_paid(self, lesson_id):
        ws = self.worksheet("Lessons")
        if not ws:
            return False
        records = ws.get_all_records()
        for i, rec in enumerate(records, start=2):
            if str(rec.get("lesson_id")) == str(lesson_id):
                ws.update_cell(i, 7, "yes")
                return True
        return False

    def get_tutor_percent(self, tutor_id):
        recs = self.get_all_records("Tutors")
        for r in recs:
            if int(r.get("tutor_id",0)) == int(tutor_id):
                return float(r.get("percent",0))
        return None

def ensure_sheets_exist(sheets: SheetsAPI):
    # create sheets if not present and add headers
    if sheets.worksheet("Tutors") is None:
        sheets.sh.add_worksheet("Tutors", rows=200, cols=10)
        sheets.worksheet("Tutors").append_row(["tutor_id","name","username","percent"])
    if sheets.worksheet("Lessons") is None:
        sheets.sh.add_worksheet("Lessons", rows=1000, cols=20)
        sheets.worksheet("Lessons").append_row(["lesson_id","date_iso","time","tutor_id","student","amount","paid"])
    if sheets.worksheet("Slots") is None:
        sheets.sh.add_worksheet("Slots", rows=1000, cols=10)
        sheets.worksheet("Slots").append_row(["tutor_id","date_iso","time","note"])

def set_global_sheets(sheets):
    global _global_sheets
    _global_sheets = sheets

def get_global_sheets():
    return _global_sheets
