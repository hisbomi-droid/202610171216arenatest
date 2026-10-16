# Mock-as-live guard fix

## Changed file
- `kospi_master_controller_mock_guard_fixed.py` (derived from `kospi_master_controller_repaired.py`; original files preserved)

## Changes
- Restored `_reject_mock_as_live(raw)` to reject source labels that are exclusively `mock` / `mock_*`.
- Applied the guard in all three collection paths: `data_port`, `UMEBarSource`, and `universal_quant_engine.Market`.
- Normalized quality labels with `strip().lower()` before mapping.

## Tests run
- `python -m py_compile kospi_master_controller_mock_guard_fixed.py`: PASS.
- Isolated mock/live classification test for all three UME paths: 6/6 PASS.
  - `source=mock` => `demo_replay(fallback)`, error `UME_RuntimeError`.
  - `source=krx` => provider `ume`, no error.

## Limits
- Tests used isolated fake providers and function extraction; they do not prove live KRX/Naver/Yahoo network connectivity.
- This file should replace only the intended controller after reviewing the diff. Do not unpack the arena repaired bundle over the real project; its Arena/cockpit/ledger entries are stubs/fixtures according to the project review.
