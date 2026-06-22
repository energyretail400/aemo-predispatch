"""
Parses AEMO NEMWEB multi-table CSV files from MTPASA ZIP archives.

AEMO CSV format (single .CSV inside the ZIP):
  C rows  = file header (skip)
  I rows  = column headers:  I, SCHEME, TABLENAME, VERSION, col1, col2, ...
  D rows  = data rows:       D, SCHEME, TABLENAME, VERSION, val1, val2, ...
  END OF REPORT = end marker

Actual MTPASA tables (confirmed from file inspection):
  REGIONRESULT   - daily demand + available generation per region per POE type
  REGIONSUMMARY  - monthly aggregated native demand + USE percentiles
  LOLPRESULT     - daily loss-of-load probability per region
  CASERESULT / CONSTRAINTRESULT / CONSTRAINTSUMMARY / INTERCONNECTORRESULT
"""

import io
import zipfile
import csv
import pandas as pd
from pathlib import Path

TABLES_OF_INTEREST = {"REGIONRESULT", "REGIONSUMMARY", "LOLPRESULT"}

REGION_DISPLAY = {
    "NSW1": "NSW",
    "QLD1": "QLD",
    "VIC1": "VIC",
    "SA1":  "SA",
    "TAS1": "TAS",
}


def parse_zip(zip_path: Path, tables: set[str] | None = None, debug: bool = False) -> dict[str, pd.DataFrame]:
    """
    Parse a MTPASA ZIP and return {table_name: DataFrame} for requested tables.
    If tables is None, returns TABLES_OF_INTEREST. Pass tables=None and debug=True
    to print all table names found without filtering.
    """
    want = tables if tables is not None else TABLES_OF_INTEREST

    zf = zipfile.ZipFile(zip_path)
    csv_names = [n for n in zf.namelist() if n.lower().endswith(".csv")]
    if not csv_names:
        raise ValueError(f"No CSV found inside {zip_path.name}. Contents: {zf.namelist()}")

    table_cols: dict[str, list[str]] = {}
    table_rows: dict[str, list[list]] = {}
    current_table: str | None = None

    with zf.open(csv_names[0]) as raw:
        reader = csv.reader(io.TextIOWrapper(raw, encoding="utf-8", errors="replace"))
        for row in reader:
            if not row:
                continue
            row_type = row[0].strip().upper()

            if row_type == "I":
                if len(row) < 3:
                    continue
                tname = row[2].strip().upper()
                current_table = tname
                if debug:
                    print(f"Table: {tname}, cols: {row[4:8]}...")
                if tname in want or debug:
                    table_cols[tname] = [c.strip() for c in row[4:]]
                    if tname not in table_rows:
                        table_rows[tname] = []

            elif row_type == "D":
                if current_table not in table_rows:
                    continue
                cols = table_cols.get(current_table, [])
                values = row[4:]
                if len(values) < len(cols):
                    values += [""] * (len(cols) - len(values))
                table_rows[current_table].append(values[: len(cols)])

    result: dict[str, pd.DataFrame] = {}
    for name, rows in table_rows.items():
        cols = table_cols.get(name, [])
        if rows and cols:
            result[name] = pd.DataFrame(rows, columns=cols)

    return result


def _to_numeric(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    for col in cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def load_region_result(zip_path: Path) -> pd.DataFrame:
    """
    Returns REGIONRESULT filtered to RUNTYPE=RELIABILITY.
    Key columns: DAY, REGIONID, DEMAND_POE_TYPE, DEMAND, TOTALAVAILABLEGEN10/50/90,
                 AGGREGATEINSTALLEDCAPACITY.
    """
    tables = parse_zip(zip_path)
    df = tables.get("REGIONRESULT")
    if df is None or df.empty:
        raise ValueError("REGIONRESULT table not found. Tables available: " + str(list(tables.keys())))

    df = df.copy()
    df = df[df["RUNTYPE"].str.upper() == "RELIABILITY"].copy()

    numeric_cols = [
        "DEMAND", "AGGREGATEINSTALLEDCAPACITY",
        "TOTALAVAILABLEGEN10", "TOTALAVAILABLEGEN50", "TOTALAVAILABLEGEN90",
        "TOTALAVAILABLEGENMIN", "TOTALAVAILABLEGENMAX",
        "TOTALSCHEDULEDGEN10", "TOTALSCHEDULEDGEN50", "TOTALSCHEDULEDGEN90",
        "TOTALINTERMITTENTGEN10", "TOTALINTERMITTENTGEN50", "TOTALINTERMITTENTGEN90",
        "TOTALSEMISCHEDULEGEN10", "TOTALSEMISCHEDULEGEN50", "TOTALSEMISCHEDULEGEN90",
        "DEMANDSIDEPARTICIPATION10", "DEMANDSIDEPARTICIPATION50", "DEMANDSIDEPARTICIPATION90",
        "USE_AVERAGE",
    ]
    df = _to_numeric(df, numeric_cols)

    df["DAY"] = pd.to_datetime(df["DAY"], errors="coerce")
    df["RUN_DATETIME"] = pd.to_datetime(df["RUN_DATETIME"], errors="coerce")
    df["REGION_LABEL"] = df["REGIONID"].map(REGION_DISPLAY).fillna(df["REGIONID"])

    return df.dropna(subset=["DAY", "REGIONID"])


def load_lolp(zip_path: Path) -> pd.DataFrame:
    """
    Returns LOLPRESULT with daily loss-of-load probability per region.
    Key columns: DAY, REGIONID, LOSSOFLOADPROBABILITY, LOSSOFLOADMAGNITUDE.
    """
    tables = parse_zip(zip_path)
    df = tables.get("LOLPRESULT")
    if df is None or df.empty:
        return pd.DataFrame()

    df = df.copy()
    df = _to_numeric(df, ["LOSSOFLOADPROBABILITY", "LOSSOFLOADMAGNITUDE",
                           "WORST_INTERVAL_DEMAND", "WORST_INTERVAL_INTGEN"])
    df["DAY"] = pd.to_datetime(df["DAY"], errors="coerce")
    df["REGION_LABEL"] = df["REGIONID"].map(REGION_DISPLAY).fillna(df["REGIONID"])
    return df.dropna(subset=["DAY", "REGIONID"])


def load_regionsolution(zip_path: Path) -> pd.DataFrame:
    """
    Returns STPASA REGIONSOLUTION filtered to RUNTYPE=LOR.
    Key columns: INTERVAL_DATETIME, REGIONID, DEMAND10/50/90,
                 SURPLUSCAPACITY, SURPLUSRESERVE, RESERVECONDITION, LORCONDITION,
                 CALCULATEDLOR1LEVEL, CALCULATEDLOR2LEVEL.
    """
    tables = parse_zip(zip_path, tables={"REGIONSOLUTION"})
    df = tables.get("REGIONSOLUTION")
    if df is None or df.empty:
        raise ValueError("REGIONSOLUTION table not found. Tables available: " + str(list(tables.keys())))

    df = df.copy()
    df = df[df["RUNTYPE"].str.strip().str.upper() == "LOR"].copy()

    numeric_cols = [
        "DEMAND10", "DEMAND50", "DEMAND90",
        "SURPLUSCAPACITY", "SURPLUSRESERVE",
        "RESERVECONDITION", "LORCONDITION",
        "CALCULATEDLOR1LEVEL", "CALCULATEDLOR2LEVEL",
        "UNCONSTRAINEDCAPACITY", "CONSTRAINEDCAPACITY",
        "RESERVEREQ", "CAPACITYREQ",
    ]
    df = _to_numeric(df, numeric_cols)
    df["INTERVAL_DATETIME"] = pd.to_datetime(df["INTERVAL_DATETIME"], errors="coerce")
    df["RUN_DATETIME"] = pd.to_datetime(df["RUN_DATETIME"], errors="coerce")
    df["REGION_LABEL"] = df["REGIONID"].map(REGION_DISPLAY).fillna(df["REGIONID"])

    return df.dropna(subset=["INTERVAL_DATETIME", "REGIONID"])


def load_dispatch_price(zip_path: Path) -> pd.DataFrame:
    """
    Returns DISPATCH.PRICE from a DispatchIS ZIP for the physical run (INTERVENTION=0).
    Key columns: SETTLEMENTDATE, REGIONID, RRP.
    """
    tables = parse_zip(zip_path, tables={"PRICE"})
    df = tables.get("PRICE")
    if df is None or df.empty:
        return pd.DataFrame()

    df = df.copy()
    if "INTERVENTION" in df.columns:
        df = df[df["INTERVENTION"].astype(str).str.strip() == "0"].copy()

    df = _to_numeric(df, ["RRP"])
    df["SETTLEMENTDATE"] = pd.to_datetime(df["SETTLEMENTDATE"], errors="coerce")
    df["REGION_LABEL"] = df["REGIONID"].map(REGION_DISPLAY).fillna(df["REGIONID"])

    return df.dropna(subset=["SETTLEMENTDATE", "REGIONID"])


def load_p5min_regionsolution(zip_path: Path) -> pd.DataFrame:
    """
    Returns P5MIN REGIONSOLUTION for the physical (non-intervention) run.
    Key columns: INTERVAL_DATETIME, REGIONID, RRP, TOTALDEMAND.
    """
    tables = parse_zip(zip_path, tables={"REGIONSOLUTION"})
    df = tables.get("REGIONSOLUTION")
    if df is None or df.empty:
        return pd.DataFrame()

    df = df.copy()
    if "INTERVENTION" in df.columns:
        df = df[df["INTERVENTION"].astype(str).str.strip() == "0"].copy()

    df = _to_numeric(df, ["RRP", "TOTALDEMAND"])
    for col in ["INTERVAL_DATETIME", "RUN_DATETIME"]:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")
    df["REGION_LABEL"] = df["REGIONID"].map(REGION_DISPLAY).fillna(df["REGIONID"])

    return df.dropna(subset=["INTERVAL_DATETIME", "REGIONID"])


def load_predispatch_region(zip_path: Path) -> pd.DataFrame:
    """
    Returns 30-min Predispatch PDREGION data for the physical (non-intervention) run.
    Key columns: PREDISPATCHSEQNO (run time), PERIODID (interval time), REGIONID,
                 RRP, TOTALDEMAND.

    Note: PDREGION rows use the scheme field (row[1]) as identifier with an empty
    table-name field (row[2]), so parse_zip() cannot be reused here.
    """
    zf = zipfile.ZipFile(zip_path)
    csv_names = [n for n in zf.namelist() if n.lower().endswith(".csv")]
    if not csv_names:
        return pd.DataFrame()

    cols: list[str] = []
    rows: list[list] = []

    with zf.open(csv_names[0]) as raw:
        reader = csv.reader(io.TextIOWrapper(raw, encoding="utf-8", errors="replace"))
        in_pdregion = False
        for row in reader:
            if not row:
                continue
            rt = row[0].strip().upper()
            scheme = row[1].strip().upper() if len(row) > 1 else ""

            if rt == "I" and scheme == "PDREGION":
                cols = [c.strip() for c in row[4:]]
                in_pdregion = True
            elif rt == "I":
                in_pdregion = False
            elif rt == "D" and in_pdregion and cols:
                values = row[4:]
                if len(values) < len(cols):
                    values += [""] * (len(cols) - len(values))
                rows.append(values[: len(cols)])

    if not rows or not cols:
        return pd.DataFrame()

    df = pd.DataFrame(rows, columns=cols)

    if "INTERVENTION" in df.columns:
        df = df[df["INTERVENTION"].astype(str).str.strip() == "0"].copy()

    df = _to_numeric(df, ["RRP", "TOTALDEMAND"])
    df["PERIODID"] = pd.to_datetime(df["PERIODID"], errors="coerce")
    df["PREDISPATCHSEQNO"] = pd.to_datetime(df["PREDISPATCHSEQNO"], errors="coerce")
    df["REGION_LABEL"] = df["REGIONID"].map(REGION_DISPLAY).fillna(df["REGIONID"])

    return df.dropna(subset=["PERIODID", "REGIONID"])


def load_region_summary(zip_path: Path) -> pd.DataFrame:
    """
    Returns REGIONSUMMARY (monthly aggregation).
    Key columns: PERIOD_ENDING, REGIONID, DEMAND_POE_TYPE, NATIVEDEMAND, USE_AVERAGE.
    """
    tables = parse_zip(zip_path)
    df = tables.get("REGIONSUMMARY")
    if df is None or df.empty:
        return pd.DataFrame()

    df = df.copy()
    df = df[df["RUNTYPE"].str.upper() == "RELIABILITY"].copy()
    pct_cols = [f"USE_PERCENTILE{p}" for p in [10, 20, 30, 40, 50, 60, 70, 80, 90, 100]]
    df = _to_numeric(df, [
        "NATIVEDEMAND", "USE_AVERAGE", "USE_WEIGHTED_AVG", "LRC", "WEIGHT",
        "USE_EVENT_MAX", "USE_EVENT_UPPERQUARTILE", "USE_EVENT_MEDIAN",
        "USE_EVENT_LOWERQUARTILE", "USE_EVENT_MIN",
    ] + pct_cols)
    df["PERIOD_ENDING"] = pd.to_datetime(df["PERIOD_ENDING"], errors="coerce")
    df["REGION_LABEL"] = df["REGIONID"].map(REGION_DISPLAY).fillna(df["REGIONID"])
    return df.dropna(subset=["PERIOD_ENDING", "REGIONID"])
