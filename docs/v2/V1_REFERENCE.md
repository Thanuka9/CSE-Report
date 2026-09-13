# V1 Reference Record

V2 is built in an isolated namespace. V1 extraction remains the production path until cutover gates pass.

| Field | Value |
|---|---|
| V1 reference commit | `ae2a721a332de252c841693b301b52692f8863d8` |
| V1 reference subject | Preserve governed release mode in final workbook |
| Recorded at | 2026-09-13 |
| Isolated V2 package | `src/cse_financial_etl/v2/` |
| Isolated V2 tests | `tests/v2/` |

Do not delete V1 extraction code until V2 has passed the cutover gates in `CUTOVER_CHECKLIST.md`.
