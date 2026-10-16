# -*- coding: utf-8 -*-
"""
kospi_master_controller.py
=======================================================================
KOSPI 통합 퀀트 콕핏 - Master Controller (단일 진입점)

세 개의 독립 프로그램을 하나의 프로세스에서 병렬 구동하고, 하나의 통합
대시보드(브라우저)로 모은다.

  1) kospi_model_arena_observatory_v4.py  (Arena: 모델 경쟁 + OOS Ledger)
     - v4가 없으면 기존 v2로 자동 폴백한다.
  2) kospi_cockpit_sensor_hub_v1.1.py     (3센서: TIR/Friction/State-Space + Cascade Gate)
  3) tir_reflection_backtest_v1_connected.py (TIR v1 기준선 + 원장 어댑터 3함수)
     - connected 버전이 없으면 tir_reflection_backtest_v1.py 로 폴백
       (이 경우 TIR binary_event 원장 기록은 비활성화된다).
  4) market_runtime_kospi_v3_consolidated.py (핵심 로직 요약본: 실제 동작 인터페이스인
     SessionClock/Phase 장 구간 상태머신과 market_context.json 계약만 연결.
     R_dynamic은 실제 계산이 아니므로 ReferenceFormulas 예시 재현값만 표시)
  5) prediction_ledger.py (공용 원장: Arena/TIR/콕핏 예측의 영구 기록 + 신뢰도 검증)

[2026-10-14 UMEBarSource 연결 경로 갱신]
  data_port 어댑터 → 별도 UMEBarSource → universal_quant_engine.Market 공개 API
  순으로 탐색한다. UME 연결에 실패하면 demo_replay(fallback)과 원인을 상태에 남긴다.

[2026-10-09 버그 수정 내역 — stage2_ume 업로드본 기준 3건]
  (g) TIR 버그 재발 수정: tir_df가 (1) 블록의 어댑터 조건문 안에서만
      할당되어, connected 없이 기본 v1으로 폴백된 경우 (1b)가 tir_df를
      참조하다 UnboundLocalError('cannot access local variable')로 죽었다.
      run_backtest_v1()을 어댑터 조건과 무관한 공용 계산으로 상단 이동.
  (h) UME 에러 원인 보존: 기존 코드는 문자열 err에 대해
      isinstance(err, Exception)이 항상 False라 "UME_IMPORT_ERROR" 고정
      문구만 남고 실제 원인(예: ModuleNotFoundError: No module named
      'kospi_arena')이 사라졌다. UME_IMPORT_ERROR를 그대로 전달한다.
  (i) 기동 배너 정직화: "Arena DATA: ume"은 요청 모드일 뿐이므로
      실제 데이터 원천은 data_source로 확인하도록 표기하고, UME 미연결
      시 배너에서 demo_replay(fallback) 동작과 import 원인을 즉시 표시.

[2026-09-26 갱신 내역]
  (a) 크래시 수정: _load_module()이 sys.modules[alias] 등록을 빼먹어
      Arena의 @dataclass가 모듈 레지스트리를 못 찾고
      "AttributeError: 'NoneType' object has no attribute '__dict__'"
      로 즉사하던 버그를 고쳤다. sys.modules[alias] = mod를
      exec_module() 앞에 추가했다(등록 후 로드 — 데코레이터가 로드 중
      sys.modules를 참조하기 때문). 이 등록은 부수 효과도 있다:
      prediction_ledger를 alias "prediction_ledger"로 등록해 두면,
      importlib로 로드되는 센서 허브/TIR connected가 하는 plain
      "import prediction_ledger"도 정상 해석된다.
  (b) Arena 로드 대상을 v4 우선(v2 폴백)으로 변경.
  (c) ledger_worker 신설: TIR connected 어댑터로 binary_event 예측을
      원장에 기록·평가하고, 콕핏 cascade 경보를 direction 예측으로
      기록·평가한 뒤, OOSAnalyzer 신뢰도(VERIFIED / NO_EDGE /
      INSUFFICIENT_SAMPLE / DUPLICATED_SAMPLE)를 산출해 STATE에 올린다.
      prediction_ledger.py가 없으면 원장 기능만 비활성화(경고 표시)하고
      나머지 워커는 정상 동작한다.
  (d) 대시보드에 2개 섹션 추가: "예측 원장 — 신뢰도 (direction OOS)" 표와
      "TIR binary_event 신뢰도" 표 + 원장 상태 카드.
  (e) TIR v2 4분류 결과를 원본 classify_v2_states/compute_breakout_forward/
      compare_with_baseline 함수로 계산해 상태 분포와 그룹별 Wilson CI를 표시한다.
  (f) Stage 2: Arena v4 무수정. 기존 kospi_arena.data_port를 통해 UME 실데이터를
      연결하고, Master arena_worker의 입력부만 교체한다. demo fallback은
      명시적으로 표시한다.

주의) import 문에서 '.v'나 '.1' 같은 문자는 모듈명에 쓸 수 없으므로, 실제
배포 시 파일명에서 점을 빼거나(kospi_cockpit_sensor_hub_v11.py) 아래의
importlib 로딩 방식을 그대로 사용한다. 아래 코드는 점이 있는 파일명도
안전하게 불러오는 importlib 방식을 기본으로 한다.

연결부 검증 결과 (2026-09-25 업로드 원본 기준 정적 검증 + 2026-09-26 갱신)
----------------------------------------------------
- Arena: generate_demo_data/normalize_bars/Arena.run_backtest_replay(horizon=5)/
  evaluate_current(provider, quality) 및 ArenaResult 필드(regime, current_priority,
  oos_leader, current_reason, market_state, predictions, oos) 모두 확인됨.
- Cockpit Hub: generate_mock_daily_bars(n_days)/generate_mock_intraday_bars(n_bars,
  start)/KospiCockpitSensorHub.run(df_intraday, df_daily)/tir_sensor.compute/
  using_real_module/using_real_engine 및 FINAL_COLUMNS(tir_event, Q_z, friction_score,
  friction_spike, x_t, v_t, a_t, cascade_label, regime_alert) 모두 확인됨.
- TIR connected: record_tir_predictions(df, ledger, horizon, symbol, source) /
  evaluate_tir_predictions(df, ledger) / summarize_tir_predictions(ledger)
  시그니처 확인됨 (task='binary_event', at_prediction_timestamp=True 사용).
- Cockpit: record_cascade_predictions(fused, df_intraday, ledger, horizon=30, ...)
  시그니처 확인됨 (regime_alert만 direction 예측으로 기록, v_t 부호로 방향).
- 운영 주의 1: Arena의 run_backtest_replay는 720바 walk-forward(약 645회 x 4모델)로
  첫 사이클에 수십 초~수 분이 걸릴 수 있다. 대시보드 "계산 대기 중" 표시가 오래
  지속되면 --interval을 늘리거나 첫 렌더 완료를 기다린다.
- 운영 주의 2: CockpitGate.fuse는 정렬된(오름차순) 타임스탬프를 가정한다.
  실데이터 연동 시 분봉/일봉 모드 시간 오름차순 정렬 후 hub.run()에 전달한다.
- 운영 주의 3: friction_engine.py가 없으면 매 사이클 RuntimeWarning 폴백 경고가
  stdout에 출력된다(정상 동작, 실제 엔진 연결 시 소멸).
- 운영 주의 4: ledger_worker는 cockpit_worker와 같은 mock 생성기를 쓰지만
  자체 허브 인스턴스로 계산한다(모듈 무결성: 워커 간 상태 공유는 STATE뿐).
  원장 dedup 키가 같은 mock 타임스탬프를 반복 기록하지 않으므로 재계산해도
  원장은 append-only 원칙을 유지한다.
- 운영 주의 5: UME는 data_port, 별도 UMEBarSource, universal_quant_engine.Market
  순으로 연결한다. 모두 없으면 UME 기능만 비활성화되고 Arena는
  demo_replay(fallback)로 정직하게 표시되며 동작한다.

실행
----
    python kospi_master_controller.py
    python kospi_master_controller.py --port 8765 --no-browser
    python kospi_master_controller.py --interval 30        # 30초마다 재계산
    python kospi_master_controller.py --ledger 04_data/local/ledger_master_kospi.jsonl
    python kospi_master_controller.py --data-source demo   # UME 대신 demo_replay

설계 원칙 (기존 프로젝트 원칙 유지)
----------------------------------
- 각 모듈은 "그대로 import"해서 재사용한다. 어떤 모듈도 수정/덮어쓰지 않는다.
  (예외 없음: 이 컨트롤러만이 갱신 대상이다.)
- Arena(예측 모델)과 센서(TIR/Friction/State-Space)는 서로 다른 것을 측정하는
  독립 계층이므로 하나의 점수로 합치지 않는다. 통합 대시보드는 "같은 화면에
  나란히 보여줄" 뿐이다.
- 센서 간 계산 순서 의존 없음(병렬). 결합은 CockpitGate의 조건부 cascade로만.
- 데모는 synthetic replay. LIVE 표시는 실제 데이터 원천이 연결될 때만.
- UME 실패 시 무조건 조용히 demo로 대체하지 않는다. 대체가 발생하면
  data_source="demo_replay(fallback)"와 ume_error로 명시한다.
- 공유 상태는 state.json(디스크)으로 주고받는다 - 외부 프로세스(consolidated
  엔진 등)가 나중에 붙어도 같은 계약을 따르면 된다.
- 원장 파일(ledger*.jsonl)은 04_data/local/ 아래에 두고 Git에 커밋하지 않는다
  (SEC-402/403). 컨트롤러는 save() 호출 시에만 파일을 쓴다.
"""

from __future__ import annotations

import argparse
import html
import importlib.util
import json
import os
import sys
import threading
import time
import webbrowser
from dataclasses import dataclass, field
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd


# ======================================================================
# Stage 2 — UME 연결 (data_port/UMEBarSource 선택 → Market 공개 API 직접)
# ======================================================================

UME_DATA_PORT = None
UME_IMPORT_ERROR = ""
UME_BAR_SOURCE_CLS = None
UME_MODE = ""  # "", "data_port", "bar_source", "market" — 실제 사용 계층


def _load_ume_bar_source_cls():
    """data_port 내장 또는 별도 UMEBarSource 어댑터를 찾는다."""
    import importlib

    try:
        module = importlib.import_module("kospi_arena.ume_bar_source")
        return module.UMEBarSource
    except (ImportError, AttributeError) as package_exc:
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ume_bar_source.py")
        if not os.path.isfile(path):
            raise package_exc
        spec = importlib.util.spec_from_file_location("_master_ume_bar_source", path)
        if spec is None or spec.loader is None:
            raise ImportError("cannot load co-located ume_bar_source.py") from package_exc
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.UMEBarSource


def _load_ume_layer():
    """UME 계층을 확정한다. 반환: (mode, data_port_or_None, market_cls_or_None).

    오류는 유형+모듈명만 남긴다(SEC-206: 스택·URL·응답본문 미노출).
    """
    global UME_DATA_PORT, UME_BAR_SOURCE_CLS, UME_IMPORT_ERROR, UME_MODE
    if UME_MODE:
        return UME_MODE, UME_DATA_PORT, globals().get("_UME_MARKET_CLS", None)
    here = os.path.dirname(os.path.abspath(__file__))
    for sub in ("01_strategy", "01_strategy/kospi_arena",
                "02_engine", "02_engine/universal_quant_engine"):
        path = os.path.join(here, *sub.split("/"))
        if os.path.isdir(path) and path not in sys.path:
            sys.path.insert(0, path)
    data_port_error = "ModuleNotFoundError"
    try:
        import importlib
        UME_DATA_PORT = importlib.import_module("kospi_arena.data_port")
        if not callable(getattr(UME_DATA_PORT, "to_arena_bars", None)):
            raise AttributeError("kospi_arena.data_port missing to_arena_bars")
        UME_BAR_SOURCE_CLS = getattr(UME_DATA_PORT, "UMEBarSource", None)
        if not callable(UME_BAR_SOURCE_CLS):
            UME_BAR_SOURCE_CLS = _load_ume_bar_source_cls()
        if not callable(UME_BAR_SOURCE_CLS):
            raise TypeError("UMEBarSource must be callable")
        UME_IMPORT_ERROR = ""
        UME_MODE = "data_port"
        return UME_MODE, UME_DATA_PORT, None
    except Exception as exc:
        data_port_error = type(exc).__name__
        UME_DATA_PORT = None
    try:
        UME_BAR_SOURCE_CLS = _load_ume_bar_source_cls()
        UME_IMPORT_ERROR = ""
        UME_MODE = "bar_source"
        return UME_MODE, None, None
    except Exception as exc:
        adapter_error = type(exc).__name__
    try:
        import importlib
        uqe = importlib.import_module("universal_quant_engine")
        globals()["_UME_MARKET_CLS"] = uqe.Market
        UME_IMPORT_ERROR = ""
        UME_MODE = "market"
        return UME_MODE, None, uqe.Market
    except Exception as exc:
        UME_IMPORT_ERROR = (
            f"data_port: {data_port_error} | adapter: {adapter_error} | "
            f"market: {type(exc).__name__}"
        )
        UME_BAR_SOURCE_CLS = None
        UME_MODE = ""
        return "", None, None


_UME_QUALITY_MAP = {
    "normal": "GOOD", "good": "GOOD",
    "delayed": "STALE", "stale": "STALE", "degraded": "STALE",
    "manual": "MANUAL", "missing": "MISSING",
}


# ======================================================================
# 0. 의존 모듈 로드 (파일명에 점이 있어도 안전하게 import)
# ======================================================================

def _load_module(filename: str, alias: str):
    """같은 폴더의 .py 파일을 모듈로 로드. 없으면 None.

    [크래시 수정 2026-09-26] sys.modules[alias] = mod 를 exec_module() 앞에
    등록한다. 등록이 없으면 Arena 쪽 @dataclass가 sys.modules를 참조할 때
    None 을 만나 즉사한다('NoneType' object has no attribute '__dict__').
    등록을 먼저 해도 exec_module 실패 시에는 아래 except 에서 다시 제거한다.
    """
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), filename)
    if not os.path.exists(path):
        return None
    spec = importlib.util.spec_from_file_location(alias, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[alias] = mod  # <-- 빠져 있던 등록 (크래시 원인)
    try:
        spec.loader.exec_module(mod)
    except Exception:
        sys.modules.pop(alias, None)
        raise
    return mod


# --- 공용 원장 모듈 (없으면 원장 기능만 비활성화) ---
# 센서 허브/TIR connected가 plain "import prediction_ledger"를 하므로
# 가능하면 표준 import로 해석되게 하고, 실패 시 importlib로 같은 폴더를 찾는다.
try:
    import prediction_ledger as ledger_mod  # type: ignore
except ImportError:
    ledger_mod = _load_module("prediction_ledger.py", "prediction_ledger")

# --- Arena: v4 우선, v2 폴백 ---
observatory = _load_module("kospi_model_arena_observatory_v4.py", "observatory")
observatory_version = "v4"
if observatory is None:
    observatory = _load_module("kospi_model_arena_observatory_v2.py", "observatory")
    observatory_version = "v2(fallback)"

cockpit = _load_module("kospi_cockpit_sensor_hub_v1.1.py", "cockpit")

if observatory is None or cockpit is None:
    raise SystemExit(
        "필수 모듈을 찾을 수 없습니다. 다음 파일들을 이 스크립트와 같은 폴더에 두세요:\n"
        "  - kospi_model_arena_observatory_v4.py (없으면 v2)\n"
        "  - kospi_cockpit_sensor_hub_v1.1.py\n"
        "  - tir_reflection_backtest_v1.py (센서 허브가 import)"
    )

# --- TIR: connected(원장 어댑터 포함) 우선, 기본 v1 폴백 ---
# Preserve the currently configured connected wrapper first. The timestamp-key-fixed
# reference candidate is not auto-wired because its loader/ledger compatibility has
# not been proven against the real UME deployment.
tir_connected = _load_module("tir_reflection_backtest_v1_connected.py", "tir_connected")
if tir_connected is None:
    tir_connected = _load_module("tir_reflection_backtest_v1.py", "tir_connected")
# [수정 2026-10-10] 폴백 경로에서 점검 없이 False로 고정하던 것을 없앴다. 일반 파일명
# tir_reflection_backtest_v1.py 에 어댑터 3함수가 함께 들어 있는 구성(연결본_260930)에서도
# 실제 보유 함수로 판정해야 TIR binary_event 원장 기록이 켜진다.
tir_has_adapter = tir_connected is not None and all(
    hasattr(tir_connected, f) for f in
    ("record_tir_predictions", "evaluate_tir_predictions", "summarize_tir_predictions")
)


# ======================================================================
# 1. 통합 상태 (공유 계약)
# ======================================================================

@dataclass
class MasterState:
    """모든 워커가 갱신하는 통합 스냅샷. 대시보드는 이것만 읽어 렌더링한다."""
    lock: threading.Lock = field(default_factory=threading.Lock)
    updated_at: str = ""
    # Arena 계층
    regime: str = ""
    current_priority: Optional[str] = None
    oos_leader: Optional[str] = None
    priority_reason: str = ""
    market_state: Dict[str, float] = field(default_factory=dict)
    predictions: List[Dict[str, Any]] = field(default_factory=list)
    oos_table: List[Dict[str, Any]] = field(default_factory=list)
    # 센서 계층 (Cockpit Hub)
    cockpit_summary: Dict[str, Any] = field(default_factory=dict)
    cascade_counts: Dict[str, int] = field(default_factory=dict)
    latest_alerts: List[Dict[str, Any]] = field(default_factory=list)
    # Consolidated 엔진 슬롯
    consolidated: Dict[str, Any] = field(default_factory=dict)
    consolidated_available: bool = False
    # 데이터 원천
    provider: str = "demo_replay"
    quality: str = "GOOD"
    data_source: str = "demo_replay"
    data_quality: str = "GOOD"
    trade_amount_derived: bool = False
    ume_error: str = ""
    # 예측 원장 (Ledger) 계층 — 2026-09-26 추가
    ledger_available: bool = False
    ledger_error: str = ""
    ledger_path: str = ""
    ledger_stats: Dict[str, Any] = field(default_factory=dict)
    ledger_oos: List[Dict[str, Any]] = field(default_factory=list)
    ledger_binary: List[Dict[str, Any]] = field(default_factory=list)
    # TIR v2 4분류 검증 — 원본 함수 결과를 읽기만 함
    tir_v2_available: bool = False
    tir_v2_counts: Dict[str, int] = field(default_factory=dict)
    tir_v2_table: List[Dict[str, Any]] = field(default_factory=list)

    def to_json(self) -> str:
        with self.lock:
            return json.dumps({
                "updated_at": self.updated_at,
                "regime": self.regime,
                "current_priority": self.current_priority,
                "oos_leader": self.oos_leader,
                "priority_reason": self.priority_reason,
                "market_state": self.market_state,
                "predictions": self.predictions,
                "oos_table": self.oos_table,
                "cockpit_summary": self.cockpit_summary,
                "cascade_counts": self.cascade_counts,
                "latest_alerts": self.latest_alerts,
                "consolidated": self.consolidated,
                "consolidated_available": self.consolidated_available,
                "provider": self.provider,
                "quality": self.quality,
                "data_source": self.data_source,
                "data_quality": self.data_quality,
                "trade_amount_derived": self.trade_amount_derived,
                "ume_error": self.ume_error,
                "ledger_available": self.ledger_available,
                "ledger_error": self.ledger_error,
                "ledger_path": self.ledger_path,
                "ledger_stats": self.ledger_stats,
                "ledger_oos": self.ledger_oos,
                "ledger_binary": self.ledger_binary,
                "tir_v2_available": self.tir_v2_available,
                "tir_v2_counts": self.tir_v2_counts,
                "tir_v2_table": self.tir_v2_table,
            }, ensure_ascii=False, default=str)


STATE = MasterState()


# ======================================================================
# 2. 워커 A: Arena (옵저버토리 v4 우선 재사용)
# ======================================================================

def _quality_from_ume(df: pd.DataFrame) -> str:
    """UME quality → Arena quality. 누락/미인식 품질은 GOOD으로 낙관하지 않는다."""
    if "quality" not in df.columns or df.empty:
        return "MISSING"
    vals = df["quality"].dropna().astype(str).str.strip().str.lower()
    if vals.empty:
        return "MISSING"
    return _UME_QUALITY_MAP.get(vals.iloc[-1], "MISSING")


def _reject_mock_as_live(raw: pd.DataFrame) -> None:
    """UME mock provider data is for contract tests, not live market data."""
    if isinstance(raw, pd.DataFrame) and "source" in raw.columns:
        sources = (
            raw["source"].dropna().astype(str).str.strip().str.lower().unique().tolist()
        )
        if sources and all(name == "mock" or name.startswith("mock_") for name in sources):
            raise RuntimeError("UME mock provider data is not live market data")


def _ume_market_to_arena(raw: pd.DataFrame, symbol: str):
    """UME Market.market() 표준 출력 → Arena 계약 DataFrame (이 컨트롤러 책임).

    UME 표준 스펙: source, timestamp, open, high, low, close, volume, quality.
    Arena 필수 8컬럼: timestamp, symbol, open, high, low, close, volume,
    trade_amount. trade_amount는 명시적으로 volume*close 파생한다(derived=True).
    변환 후 Arena v4의 normalize_bars()가 최종 정규화한다(Arena 무수정).
    """
    if not isinstance(raw, pd.DataFrame):
        raise TypeError("UME Market.market() must return a pandas DataFrame")
    if raw.empty:
        raise ValueError("UME Market.market() returned no bars")
    result = raw.copy()
    required = {"timestamp", "open", "high", "low", "close", "volume"}
    missing = sorted(required - set(result.columns))
    if missing:
        raise ValueError(f"UME Market.market() missing columns: {missing}")
    if "symbol" not in result.columns:
        result["symbol"] = symbol
    if "source" not in result.columns:
        result["source"] = "ume"
    if "quality" in result.columns:
        result["quality"] = result["quality"].map(
            lambda quality: _UME_QUALITY_MAP.get(str(quality).strip().lower(), "MISSING")
            if pd.notna(quality) else "MISSING"
        )
    else:
        result["quality"] = "MISSING"
    derived = not any(
        column in result.columns for column in ("trade_amount", "amount", "turnover")
    )
    if derived:
        result["trade_amount"] = (
            pd.to_numeric(result["volume"], errors="coerce")
            * pd.to_numeric(result["close"], errors="coerce")
        )
    return result, derived


def _fetch_arena_bars(data_source: str, ume_providers: list, ume_count: int):
    """Returns (arena_df, provider, quality, trade_amount_derived, error).

    3계층: UME(data_port/BarSource/Market) → 명시적 fallback.
    UME 실패 때 데모 데이터를 UME처럼 표시하지 않는다.
    """
    if data_source == "demo":
        bars = observatory.generate_demo_data()
        df = observatory.normalize_bars(bars, "demo_replay")
        return df, "demo_replay", "GOOD", False, ""

    mode, dp, market_cls = _load_ume_layer()
    if not mode:
        bars = observatory.generate_demo_data()
        df = observatory.normalize_bars(bars, "demo_replay")
        return (
            df, "demo_replay(fallback)", "GOOD", False,
            f"UME_{UME_IMPORT_ERROR or 'unavailable'}",
        )
    try:
        source_kwargs = {"providers": ume_providers}
        if mode == "bar_source" or getattr(dp, "UMEBarSource", None) is not UME_BAR_SOURCE_CLS:
            source_kwargs["count"] = ume_count
        if mode == "data_port":
            source = UME_BAR_SOURCE_CLS(**source_kwargs)
            raw = source.fetch_bars("KOSPI", None, None)
            if raw is None or raw.empty:
                raise ValueError("UME returned no bars")
            _reject_mock_as_live(raw)
            had_trade_amount = any(
                column in raw.columns for column in ("trade_amount", "amount", "turnover")
            )
            arena_df = dp.to_arena_bars(
                raw, source="ume", symbol="KOSPI", derive_trade_amount=True
            )
            if not isinstance(arena_df, pd.DataFrame) or arena_df.empty:
                raise TypeError("data_port.to_arena_bars must return a non-empty DataFrame")
            derived = not had_trade_amount
        elif mode == "bar_source":
            source = UME_BAR_SOURCE_CLS(**source_kwargs)
            raw = source.fetch_bars("KOSPI", None, None)
            if raw is None or raw.empty:
                raise ValueError("UME returned no bars")
            _reject_mock_as_live(raw)
            arena_df, derived = _ume_market_to_arena(raw, "KOSPI")
        else:
            source = market_cls(providers=list(ume_providers), fetch_mode="fallback")
            raw = source.market("KOSPI", count=ume_count)
            if raw is None or raw.empty:
                raise ValueError("UME returned no bars")
            _reject_mock_as_live(raw)
            arena_df, derived = _ume_market_to_arena(raw, "KOSPI")
        quality = _quality_from_ume(raw)
        return arena_df, "ume", quality, derived, ""
    except Exception as exc:
        # 오류 유형만 기록해 내부 상세 내용을 외부 상태에 노출하지 않는다.
        bars = observatory.generate_demo_data()
        df = observatory.normalize_bars(bars, "demo_replay(fallback)")
        return (
            df,
            "demo_replay(fallback)",
            "GOOD",
            False,
            f"UME_{type(exc).__name__}",
        )


def arena_worker(
    interval: float,
    data_source: str = "ume",
    ume_providers: Optional[list] = None,
    ume_count: int = 200,
) -> None:
    """Arena를 주기적으로 재계산한다. Arena/data_port/UME 원본은 수정하지 않는다."""
    ume_providers = ume_providers or ["krx", "naver", "yahoo"]
    while True:
        try:
            df, provider, quality, derived, ume_error = _fetch_arena_bars(
                data_source, ume_providers, ume_count
            )

            arena = observatory.Arena()
            # data_port가 이미 Arena contract를 반환하지만, Arena v4의 기존
            # normalize_bars 계약을 그대로 재사용한다.
            df = observatory.normalize_bars(df, provider)
            arena.run_backtest_replay(df, horizon=5)
            result = arena.evaluate_current(df, provider, quality)

            oos_records = []
            if not result.oos.empty:
                oos_records = result.oos.to_dict(orient="records")

            preds = []
            for p in result.predictions:
                preds.append({
                    "model": p["model"],
                    "signal": p.get("direction", p.get("signal", "?")),
                    "strength": float(p.get("strength", 0)),
                    "fit": observatory.REGIME_FIT.get(p["model"], {}).get(result.regime, 0.5),
                })

            with STATE.lock:
                STATE.updated_at = str(pd.Timestamp.now(tz="Asia/Seoul"))
                STATE.regime = result.regime
                STATE.current_priority = result.current_priority
                STATE.oos_leader = result.oos_leader
                STATE.priority_reason = result.current_reason
                STATE.market_state = dict(result.market_state)
                STATE.predictions = preds
                STATE.oos_table = oos_records
                STATE.provider = provider
                STATE.quality = quality
                STATE.data_source = provider
                STATE.data_quality = quality
                STATE.trade_amount_derived = bool(derived)
                STATE.ume_error = ume_error
        except Exception as exc:
            with STATE.lock:
                STATE.priority_reason = f"[arena error] {exc}"
                STATE.ume_error = f"{type(exc).__name__}: Arena cycle failed"
        time.sleep(interval)


# ======================================================================
# 3. 워커 B: Cockpit Sensor Hub (v1.1 재사용)
# ======================================================================

def cockpit_worker(interval: float) -> None:
    """
    센서 허브 v1.1을 주기적으로 재계산한다.
    실전에서는 df_intraday/df_daily를 ProviderHub가 공급하지만, 데모에서는
    허브 자체의 mock 생성기를 사용한다(모듈 수정 없이 재사용).
    """
    while True:
        try:
            df_daily = cockpit.generate_mock_daily_bars(n_days=250)
            hub = cockpit.KospiCockpitSensorHub()

            # TIR 이벤트 발생일에 분봉을 맞춰 cascade가 실제로 관측되게 한다
            tir_daily = hub.tir_sensor.compute(df_daily)
            event_days = tir_daily.index[tir_daily["tir_event"].fillna(False)]
            demo_date = event_days[-1] if len(event_days) > 0 else df_daily.index[-1]
            df_intraday = cockpit.generate_mock_intraday_bars(
                n_bars=500, start=f"{demo_date.date()} 09:00")

            result = hub.run(df_intraday, df_daily)

            summary = {
                "tir_sensor_real_module": bool(hub.tir_sensor.using_real_module),
                "friction_real_engine": bool(hub.friction_adapter.using_real_engine),
                "n_records": int(len(result)),
                "n_valid": int(result["cascade_label"].notna().sum()),
            }
            tail = result.dropna(subset=["friction_score"]).tail(1)
            if not tail.empty:
                row = tail.iloc[0]
                summary.update({
                    "x_t": float(row.get("x_t", np.nan)),
                    "v_t": float(row.get("v_t", np.nan)),
                    "a_t": float(row.get("a_t", np.nan)),
                    "Q_z": float(row.get("Q_z", np.nan)),
                    "friction_score": float(row.get("friction_score", np.nan)),
                    "friction_spike": bool(row.get("friction_spike", False)),
                    "tir_event": bool(row.get("tir_event", False)),
                    "cascade_label": str(row.get("cascade_label", "")),
                    "regime_alert": bool(row.get("regime_alert", False)),
                })

            counts = result["cascade_label"].value_counts().to_dict()
            alerts = []
            alert_rows = result[result["regime_alert"] == True]  # noqa: E712
            for _, r in alert_rows.head(5).iterrows():
                alerts.append({
                    "timestamp": str(r.name),
                    "Q_z": float(r.get("Q_z", np.nan)),
                    "friction_score": float(r.get("friction_score", np.nan)),
                    "x_t": float(r.get("x_t", np.nan)),
                    "cascade_label": str(r.get("cascade_label", "")),
                })

            with STATE.lock:
                STATE.cockpit_summary = summary
                STATE.cascade_counts = {str(k): int(v) for k, v in counts.items()}
                STATE.latest_alerts = alerts
        except Exception as exc:
            with STATE.lock:
                STATE.cockpit_summary = {"error": str(exc)}
        time.sleep(interval)


# ======================================================================
# 4. 워커 D: Prediction Ledger (공용 원장 + 신뢰도) — 2026-09-26 추가
# ======================================================================

def _supports_timestamped_tir_ledger(ledger) -> bool:
    """True only for a ledger API that can align binary-event outcomes by timestamp."""
    evaluator = getattr(ledger, "evaluate_binary_events", None)
    if not callable(evaluator) or not callable(getattr(ledger, "add", None)):
        return False
    try:
        import inspect
        params = inspect.signature(evaluator).parameters
        return ("at_prediction_timestamp" in params or
                any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values()))
    except (TypeError, ValueError):
        return False


def ledger_worker(interval: float, ledger_path: str) -> None:
    """
    공용 원장(prediction_ledger.py)으로 "예측 영구 기록 -> 실제값 비교 ->
    신뢰도 검증" 사이클을 주기적으로 수행한다.

    - TIR: connected 어댑터의 record/evaluate 함수로 binary_event 예측을
      기록·평가한다 (task='binary_event', at_prediction_timestamp=True).
      connected 어댑터가 없으면 TIR 기록은 건너뛰고 원장 상태에 표시한다.
    - Cockpit: record_cascade_predictions()로 regime_alert 시점의 direction
      예측을 기록하고, 분봉 실제 종가 시계열로 evaluate() 한다.
    - 모든 계산은 모듈을 수정하지 않고 재사용만 한다. 원장 파일 저장은
      append-only(save)이며 dedup 키로 같은 예측의 중복 기록을 막는다.
    - prediction_ledger.py가 없으면 이 워커는 원장 기능만 비활성화하고
      종료한다(다른 워커에 영향 없음).
    """
    if ledger_mod is None:
        with STATE.lock:
            STATE.ledger_available = False
            STATE.ledger_error = ("prediction_ledger.py 미연결 - "
                                  "같은 폴더에 추가하면 재기동 시 자동 인식된다")
        return

    ledger = ledger_mod.PredictionLedger()
    try:
        ledger.load(ledger_path, legacy_symbol="KOSPI")  # 구형 원장 심볼 승격
    except Exception as exc:
        with STATE.lock:
            STATE.ledger_available = False
            STATE.ledger_error = f"[ledger load error] {exc}"
        return

    while True:
        try:
            df_daily = cockpit.generate_mock_daily_bars(n_days=250)

            # (1) TIR binary_event: frozen baseline 재계산 -> 어댑터로 원장 기록
            # [수정 2026-10-09] tir_df를 어댑터 조건과 무관하게 먼저 계산한다.
            # 기존 코드는 tir_df가 (1) 블록 안에서만 할당되어, connected 없이
            # 기본 v1으로 폴백된 경우 (1b)가 tir_df를 참조하다
            # UnboundLocalError('cannot access local variable')로 죽었다.
            # run_backtest_v1()은 v1/connected 모두에 존재하므로 여기서 공용 계산.
            tir_df = None
            tir_added = 0
            tir_error = ""
            # This bundled demo daily frame contains OHLCV only. The frozen TIR
            # baseline also requires spot_close, futures_close, and trade_amount.
            tir_required = {"spot_close", "futures_close", "trade_amount", "high", "low", "close"}
            missing_tir = sorted(tir_required - set(df_daily.columns))
            if tir_connected is None:
                tir_error = "TIR module unavailable"
            elif missing_tir:
                tir_error = "TIR skipped: missing required columns " + ", ".join(missing_tir)
            elif not _supports_timestamped_tir_ledger(ledger):
                tir_error = "TIR skipped: ledger lacks timestamp-keyed binary-event API"
            else:
                try:
                    tir_df = tir_connected.run_backtest_v1(df_daily)
                    if tir_has_adapter and tir_df is not None:
                        tir_added = int(tir_connected.record_tir_predictions(
                            tir_df, ledger, horizon=5))
                        tir_connected.evaluate_tir_predictions(tir_df, ledger)
                except Exception as tir_exc:
                    # TIR failure must not disable the independent Cockpit ledger path.
                    tir_df = None
                    tir_error = f"TIR adapter error: {type(tir_exc).__name__}"

            # (1b) TIR v2 4분류: 원본 함수(classify_v2_states /
            #      compute_breakout_forward / compare_with_baseline)를 수정 없이 호출
            tir_v2_counts: Dict[str, int] = {}
            tir_v2_table: List[Dict[str, Any]] = []
            tir_v2_ok = False
            if tir_df is not None and all(hasattr(tir_connected, fn) for fn in
                                                   ("classify_v2_states", "compute_breakout_forward",
                                                    "compare_with_baseline")):
                v2_df = tir_connected.classify_v2_states(tir_df)
                v2_df = tir_connected.compute_breakout_forward(v2_df)
                if "v2_state" in v2_df.columns:
                    tir_v2_counts = {str(k): int(v) for k, v in
                                     v2_df["v2_state"].value_counts(dropna=True).items()}
                cmp_df = tir_connected.compare_with_baseline(v2_df)
                if cmp_df is not None and not cmp_df.empty:
                    tir_v2_table = cmp_df.to_dict(orient="records")
                tir_v2_ok = True

            # (2) Cockpit cascade direction: regime_alert만 예측으로 기록
            cas_added = 0
            hub = cockpit.KospiCockpitSensorHub()
            tir_daily = hub.tir_sensor.compute(df_daily)
            event_days = tir_daily.index[tir_daily["tir_event"].fillna(False)]
            demo_date = event_days[-1] if len(event_days) > 0 else df_daily.index[-1]
            df_intraday = cockpit.generate_mock_intraday_bars(
                n_bars=500, start=f"{demo_date.date()} 09:00")
            fused = hub.run(df_intraday, df_daily)
            if hasattr(cockpit, "record_cascade_predictions"):
                cas_added = int(cockpit.record_cascade_predictions(
                    fused, df_intraday, ledger, horizon=30))
            ledger.evaluate(df_intraday["close"])  # 실제 종가 시계열로 평가

            ledger.save(ledger_path)  # append-only 저장 (SEC-402/403: 04_data/local/)

            # (3) 신뢰도 요약 (OOSAnalyzer — 판정 로직은 원본과 동일)
            analyzer = ledger_mod.OOSAnalyzer()
            oos_df = analyzer.summarize(ledger)
            bin_df = analyzer.summarize_binary_events(ledger)

            if callable(getattr(ledger, "dataframe", None)):
                df_all = ledger.dataframe()
                n_records = int(len(df_all)) if not df_all.empty else 0
                n_pending = int((df_all["status"] == "PENDING").sum()) if not df_all.empty and "status" in df_all.columns else 0
                n_evaluated = int((df_all["status"] == "EVALUATED").sum()) if not df_all.empty and "status" in df_all.columns else 0
                ledger_api = "shared_timestamped"
            else:
                legacy_records = getattr(ledger, "records", [])
                n_records = len(legacy_records)
                n_pending = 0  # legacy API has no pending/evaluated state model
                n_evaluated = 0
                ledger_api = "legacy"
            stats = {
                "n_records": int(n_records),
                "n_pending": int(n_pending),
                "n_evaluated": int(n_evaluated),
                "ledger_api": ledger_api,
                "tir_added_this_cycle": tir_added,
                "cascade_added_this_cycle": cas_added,
                "tir_adapter": bool(tir_connected is not None and tir_has_adapter and not tir_error),
                "tir_error": tir_error,
                "tir_v2_available": tir_v2_ok,
            }

            with STATE.lock:
                STATE.ledger_available = True
                STATE.ledger_error = ""
                STATE.ledger_path = ledger_path
                STATE.ledger_stats = stats
                STATE.ledger_oos = ([] if oos_df.empty
                                    else oos_df.to_dict(orient="records"))
                STATE.ledger_binary = ([] if bin_df.empty
                                       else bin_df.to_dict(orient="records"))
                STATE.tir_v2_available = tir_v2_ok
                STATE.tir_v2_counts = tir_v2_counts
                STATE.tir_v2_table = tir_v2_table
        except Exception as exc:
            with STATE.lock:
                STATE.ledger_available = False
                STATE.ledger_error = f"[ledger error] {exc}"
        time.sleep(interval)


# ======================================================================
# 5. 워커 C: Consolidated 엔진 슬롯 (market_runtime_kospi_v3_consolidated.py)
# ======================================================================

def consolidated_worker(interval: float) -> None:
    """
    market_runtime_kospi_v3_consolidated.py 연결 워커 (v3 요약본 기준, 2026-09-25 확정).

    파일 성격 확인 결과: 이 파일은 '실행 엔진'이 아니라 핵심 로직 요약본이며,
    원문 스스로 "실제 배포본은 02_engine/ 원본 모듈을 사용하라"고 명시한다.
    따라서 이 워커는 다음 두 가지 '실제 동작하는' 인터페이스만 사용한다:

      1) SessionClock / Phase : KST 장 구간 상태머신 (OFF/PREOPEN/OPEN/AUCTION/POSTCLOSE)
         - TradingCalendar에 휴장일 파일(04_data/krx_holidays_v1.json)이 있으면 로드,
           없으면 주말만 제외하는 기본 달력으로 동작한다.
      2) read_context / validate_context : market_context.json 계약
         - 파일이 있으면 유효성·낡음(asof_date)을 검사해 상태만 보고한다.
         - 정식 컨텍스트 빌더는 이 컨트롤러가 대체하지 않는다(원본 01_strategy/ 역할).
         - 없으면 "context file not found"를 있는 그대로 표시한다 (기본값을
           지어내지 않는다 - 원본 계약 원칙).

    R_dynamic 표기 원칙(사용자 합의 유지):
      - 실제 계산 코드가 아니므로 ReferenceFormulas.example_r_dynamic()의
        '예시 재현값'을 표시하되 R_dynamic_verified=False, 출처를 명시한다.
      - 실제 운영값은 원본 Decision Engine(02_engine/)이 연결될 때만 노출한다.
    """
    module = _load_module("market_runtime_kospi_v3_consolidated.py", "consolidated")

    if module is None:
        with STATE.lock:
            STATE.consolidated_available = False
            STATE.consolidated = {
                "status": "SLOT_UNAVAILABLE",
                "message": "market_runtime_kospi_v3_consolidated.py 미연결 (파일을 같은 폴더에 추가하면 자동 인식)",
            }
        return  # 데모에서는 재시도하지 않는다. 재연결은 재기동으로.

    # 세션 시계 구성: 휴장일 파일이 있으면 로드, 없으면 주말만 제외(휴장일 미관리 상태 표시)
    base_dir = os.path.dirname(os.path.abspath(__file__))
    holidays_path = os.path.join(base_dir, "04_data", "krx_holidays_v1.json")
    holidays_managed = False
    try:
        from pathlib import Path as _P
        calendar = module.TradingCalendar.from_file(_P(holidays_path))
        holidays_managed = True
    except Exception:
        calendar = module.TradingCalendar()
    clock = module.SessionClock(module.SessionConfig(), calendar)

    from pathlib import Path as _P2
    ctx_file = _P2(os.path.join(base_dir, "market_context.json"))

    with STATE.lock:
        STATE.consolidated_available = True

    while True:
        try:
            now = datetime.now(module.KST)
            phase = clock.phase(now)

            # market_context.json 계약 상태 읽기 (기본값 지어내지 않음)
            ctx_status = "CONTEXT_NOT_FOUND"
            ctx_stale = False
            ctx_regime = None
            ctx_engine_level = None
            ctx_problems = []
            if ctx_file.exists():
                read = module.read_context(ctx_file, expected_asof=now.date())
                if read.ctx is None:
                    ctx_status = "CONTEXT_INVALID"
                    ctx_problems = read.problems
                elif read.stale:
                    ctx_status = "CONTEXT_STALE"
                    ctx_regime = read.ctx.get("regime")
                    ctx_engine_level = read.ctx.get("engine_level")
                    ctx_stale = True
                    ctx_problems = read.problems
                elif read.problems:
                    ctx_status = "CONTEXT_PROBLEMS"
                    ctx_problems = read.problems
                else:
                    ctx_status = "CONTEXT_OK"
                    ctx_regime = read.ctx.get("regime")
                    ctx_engine_level = read.ctx.get("engine_level")

            payload = {
                "status": "CONNECTED",
                "phase": getattr(phase, "value", str(phase)),
                "phase_kst": now.isoformat(),
                "holidays_managed": holidays_managed,
                "context_status": ctx_status,
                "context_stale": ctx_stale,
                "context_regime": ctx_regime,
                "context_engine_level": ctx_engine_level,
                "context_problems": ctx_problems,
                # R_dynamic: 실제 계산 아님 - ReferenceFormulas 예시 재현값만 표시
                "R_dynamic": None,
                "R_dynamic_example": round(module.ReferenceFormulas.example_r_dynamic(), 2),
                "R_dynamic_verified": False,
                "message": "v3 요약본 인터페이스(세션 시계·컨텍스트 계약) 연결. "
                           "R_dynamic은 원본 Decision Engine 연결 전까지 예시 재현값만 표시.",
            }
            with STATE.lock:
                STATE.consolidated = payload
        except Exception as exc:
            with STATE.lock:
                STATE.consolidated = {"status": "ERROR", "message": str(exc)}
        time.sleep(min(interval, 60.0))  # 장 구간은 최대 60초 주기로 갱신


# ======================================================================
# 6. 상태 파일 동기화 (외부 프로세스와의 공유 계약)
# ======================================================================

def state_file_worker(path: str = "state.json", interval: float = 2.0) -> None:
    """통합 상태를 state.json으로 계속 내려쓴다. 외부 스크립트가 읽을 수 있다."""
    while True:
        try:
            tmp = path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                f.write(STATE.to_json())
            os.replace(tmp, path)
        except Exception:
            pass
        time.sleep(interval)


# ======================================================================
# 7. 통합 대시보드 (단일 HTML, 단일 포트)
# ======================================================================

CSS = """
:root{--bg:#07111f;--panel:#0d1b2a;--line:#20384f;--text:#e9f1f7;--muted:#8fa7ba;--good:#42d392;--warn:#f4c95d;--bad:#ff6b6b;--blue:#55a7ff}
*{box-sizing:border-box}body{margin:0;background:linear-gradient(135deg,#06101c,#0b1b2b 55%,#07111f);color:var(--text);font-family:Inter,'Malgun Gothic',Arial,sans-serif}
.wrap{max-width:1500px;margin:auto;padding:24px}.title{font-size:30px;font-weight:800}.sub{color:var(--muted);margin-top:5px}
.grid{display:grid;gap:14px}.top{grid-template-columns:repeat(6,1fr);margin:20px 0}.two{grid-template-columns:1.2fr .8fr}.three{grid-template-columns:1fr 1fr 1fr}
.card{background:rgba(13,27,42,.94);border:1px solid var(--line);border-radius:14px;padding:17px;box-shadow:0 10px 30px #0003}
.label{color:var(--muted);font-size:12px;text-transform:uppercase;letter-spacing:.08em}
.value{font-size:22px;font-weight:750;margin-top:7px}.big{font-size:32px}
.good{color:var(--good)}.warn{color:var(--warn)}.bad{color:var(--bad)}
table{width:100%;border-collapse:collapse}th,td{padding:10px 8px;border-bottom:1px solid var(--line);text-align:left;font-size:13px}th{color:var(--muted)}
.bar{height:8px;background:#142c42;border-radius:10px;overflow:hidden}.fill{height:100%;background:var(--blue);border-radius:10px}
.reason{font-size:14px;line-height:1.6;color:#cfe0ec}.pill{display:inline-block;padding:4px 8px;border-radius:999px;background:#16324a;margin:2px;font-size:11px}
.footer{color:#7890a4;font-size:11px;margin-top:18px}
@media(max-width:1000px){.top{grid-template-columns:1fr 1fr 1fr}.two,.three{grid-template-columns:1fr 1fr}}@media(max-width:650px){.top,.two,.three{grid-template-columns:1fr}}
"""


def _fmt(v, digits=2):
    if v is None or (isinstance(v, float) and not np.isfinite(v)):
        return "N/A"
    return f"{v:.{digits}f}"


def _pct(v):
    if v is None or (isinstance(v, float) and not np.isfinite(v)):
        return "N/A"
    return f"{v:.1%}"


def _status_cls(status: str) -> str:
    s = str(status)
    if s == "VERIFIED":
        return "good"
    if s in ("NO_EDGE", "DUPLICATED_SAMPLE"):
        return "bad"
    if s in ("INSUFFICIENT_SAMPLE", "UNVERIFIED"):
        return "warn"
    return ""


def render_page() -> str:
    with STATE.lock:
        s = {
            "updated_at": STATE.updated_at, "regime": STATE.regime,
            "current_priority": STATE.current_priority, "oos_leader": STATE.oos_leader,
            "priority_reason": STATE.priority_reason, "market_state": STATE.market_state or {},
            "predictions": STATE.predictions or [], "oos_table": STATE.oos_table or [],
            "cockpit_summary": STATE.cockpit_summary or {},
            "cascade_counts": STATE.cascade_counts or {}, "latest_alerts": STATE.latest_alerts or [],
            "consolidated": STATE.consolidated or {"status": "SLOT_UNAVAILABLE"},
            "ledger_available": STATE.ledger_available, "ledger_error": STATE.ledger_error,
            "ledger_stats": STATE.ledger_stats or {},
            "ledger_oos": STATE.ledger_oos or [],
            "ledger_binary": STATE.ledger_binary or [],
            "data_source": STATE.data_source,
            "data_quality": STATE.data_quality,
            "trade_amount_derived": STATE.trade_amount_derived,
            "ume_error": STATE.ume_error,
            "tir_v2_available": STATE.tir_v2_available,
            "tir_v2_counts": STATE.tir_v2_counts or {},
            "tir_v2_table": STATE.tir_v2_table or [],
        }

    cs = s["cockpit_summary"]
    cascade = str(cs.get("cascade_label", "N/A"))
    cascade_cls = "bad" if cs.get("regime_alert") else ("warn" if cascade.startswith("TIR") else "good")

    pred_rows = []
    ranked = sorted(s["predictions"], key=lambda p: -(p.get("strength", 0) * p.get("fit", 0)))
    for i, p in enumerate(ranked, 1):
        obs = p.get("strength", 0) * p.get("fit", 0)
        pred_rows.append(
            f"<tr><td><b>#{i}</b></td><td><b>{html.escape(p['model'])}</b></td>"
            f"<td>{html.escape(str(p['signal']))}</td><td>{_fmt(p.get('strength'))}</td>"
            f"<td>{_fmt(p.get('fit'))}</td>"
            f"<td><div class='bar'><div class='fill' style='width:{obs*100:.0f}%'></div></div></td></tr>"
        )

    oos_rows = []
    for r in s["oos_table"]:
        oos_rows.append(
            f"<tr><td><b>{html.escape(str(r.get('model')))}</b></td><td>{int(r.get('n') or 0)}</td>"
            f"<td>{_pct(r.get('directional_accuracy'))}</td><td>{_fmt(r.get('brier'), 3)}</td>"
            f"<td>{_fmt(r.get('mae'), 4)}</td><td>{_fmt(r.get('profit_factor'))}</td>"
            f"<td><span class='pill'>{html.escape(str(r.get('status')))}</span></td></tr>"
        )

    # --- 원장(Ledger) 섹션 행 구성 — 2026-09-26 추가 ---
    ls = s["ledger_stats"]
    if s["ledger_available"]:
        ledger_state_html = (
            f"<div class='value good'>ACTIVE</div>"
            f"<div class='sub'>기록 {ls.get('n_records', 0)}건 · "
            f"PENDING {ls.get('n_pending', 0)} · EVALUATED {ls.get('n_evaluated', 0)} · "
            f"이번 사이클 +TIR {ls.get('tir_added_this_cycle', 0)} / "
            f"+cascade {ls.get('cascade_added_this_cycle', 0)}</div>"
        )
    else:
        err = html.escape(s["ledger_error"] or "prediction_ledger 미연결")
        ledger_state_html = f"<div class='value warn'>DISABLED</div><div class='sub'>{err}</div>"

    ledger_oos_rows = []
    for r in s["ledger_oos"]:
        ledger_oos_rows.append(
            f"<tr><td><b>{html.escape(str(r.get('model')))}</b></td>"
            f"<td>{html.escape(str(r.get('task')))}</td><td>{int(r.get('n') or 0)}</td>"
            f"<td>{_pct(r.get('directional_accuracy'))}</td><td>{_pct(r.get('da_ci_low'))}</td>"
            f"<td><span class='pill {_status_cls(r.get('status'))}'>"
            f"{html.escape(str(r.get('status')))}</span></td></tr>"
        )

    ledger_bin_rows = []
    for r in s["ledger_binary"]:
        ledger_bin_rows.append(
            f"<tr><td><b>{html.escape(str(r.get('model')))}</b></td>"
            f"<td>{int(r.get('n') or 0)}</td><td>{_pct(r.get('event_accuracy'))}</td>"
            f"<td>{_pct(r.get('event_ci_low'))}</td>"
            f"<td><span class='pill {_status_cls(r.get('status'))}'>"
            f"{html.escape(str(r.get('status')))}</span></td></tr>"
        )
    if not s["ledger_available"]:
        ledger_oos_rows = ["<tr><td colspan='6'>원장 미연결 — prediction_ledger.py를 같은 폴더에 두세요</td></tr>"]
        ledger_bin_rows = ["<tr><td colspan='5'>원장 미연결</td></tr>"]
    elif not ls.get("tir_adapter", False):
        ledger_bin_rows = ledger_bin_rows or [
            "<tr><td colspan='5'>TIR connected 어댑터 미연결 — "
            "tir_reflection_backtest_v1_connected.py 필요</td></tr>"]

    # --- TIR v2 4분류 행 구성 ---
    v2_order = ["TRAPPED", "LEAK_WARNING", "일반", "BREAKOUT_후보"]
    v2_labels = {
        "TRAPPED": "A · TRAPPED",
        "LEAK_WARNING": "B · LEAK_WARNING",
        "일반": "C · 일반 (TIR 미충족 + Slow)",
        "BREAKOUT_후보": "D · BREAKOUT_후보 (TIR 미충족 + Fast)",
    }
    tir_v2_count_rows = "".join(
        f"<tr><td>{html.escape(v2_labels[k])}</td><td><b>{int(s['tir_v2_counts'].get(k, 0))}</b></td></tr>"
        for k in v2_order
    )
    tir_v2_cmp_rows = []
    for r in s["tir_v2_table"]:
        tir_v2_cmp_rows.append(
            f"<tr><td>{html.escape(str(r.get('group', '')))}</td><td>{int(r.get('n') or 0)}</td>"
            f"<td>{_pct(r.get('rate'))}</td><td>{_pct(r.get('ci_95_low'))} ~ {_pct(r.get('ci_95_high'))}</td></tr>"
        )
    if not s["tir_v2_available"]:
        tir_v2_count_rows = "<tr><td colspan='2'>N/A — connected TIR v2 함수 미연결/계산 대기 중</td></tr>"
        tir_v2_cmp_rows = ["<tr><td colspan='4'>N/A — connected TIR v2 함수 미연결/계산 대기 중</td></tr>"]
    elif not tir_v2_cmp_rows:
        tir_v2_cmp_rows = ["<tr><td colspan='4'>유효한 돌파 결과 표본 없음</td></tr>"]

    cascade_rows = "".join(
        f"<tr><td>{html.escape(k)}</td><td>{v}건</td></tr>" for k, v in s["cascade_counts"].items()
    ) or "<tr><td colspan='2'>계산 대기 중</td></tr>"

    alert_rows = "".join(
        f"<tr><td>{html.escape(a['timestamp'])}</td><td>{_fmt(a.get('Q_z'))}</td>"
        f"<td>{_fmt(a.get('friction_score'), 4)}</td><td>{_fmt(a.get('x_t'))}</td>"
        f"<td><span class='pill'>{html.escape(a['cascade_label'])}</span></td></tr>"
        for a in s["latest_alerts"]
    ) or "<tr><td colspan='5'>이번 구간에서 붕괴 이벤트 없음 (데모 시드에 따라 다름)</td></tr>"

    cons = s["consolidated"]
    cons_status = html.escape(str(cons.get("status", "SLOT_UNAVAILABLE")))
    cons_cls = "good" if cons_status == "CONNECTED" else "warn"
    r_dyn = _fmt(cons.get("R_dynamic"))
    if r_dyn == "N/A" and cons.get("R_dynamic_example") is not None:
        r_dyn = f"{_fmt(cons.get('R_dynamic_example'))} <span style='font-size:11px;color:#8fa7ba'>(예시 재현값, 미검증)</span>"
    cons_msg = html.escape(str(cons.get("message", "")))
    phase_val = html.escape(str(cons.get("phase", "-")))
    phase_cls = "good" if phase_val in ("OPEN", "AUCTION") else ("warn" if phase_val == "PREOPEN" else "")
    ctx_val = html.escape(str(cons.get("context_status", "-")))
    ctx_cls = "good" if ctx_val == "CONTEXT_OK" else ("warn" if ctx_val == "CONTEXT_STALE" else "bad" if ctx_val == "CONTEXT_INVALID" else "")

    ms = s["market_state"]
    tir_real = "실제 v1 모듈" if cs.get("tir_sensor_real_module") else "폴백 proxy"
    fric_real = "실제 엔진" if cs.get("friction_real_engine") else "폴백 proxy"

    return f"""<!doctype html><html><head><meta charset='utf-8'>
<meta name='viewport' content='width=device-width,initial-scale=1'>
<title>KOSPI Master Cockpit - 통합 대시보드</title><style>{CSS}</style></head>
<body><div class='wrap'>
<div class='title'>🛰 KOSPI MASTER COCKPIT — 통합 대시보드</div>
<div class='sub'>Arena(예측 경쟁) + Cockpit Hub(3센서 cascade) + Prediction Ledger(신뢰도) + Consolidated 슬롯을 한 화면에서 관찰합니다.</div>

<div class='grid top'>
<div class='card'><div class='label'>REGIME</div><div class='value'>{html.escape(s['regime'] or '...')}</div></div>
<div class='card'><div class='label'>CURRENT PRIORITY</div><div class='value big good'>{html.escape(s['current_priority'] or '...')}</div></div>
<div class='card'><div class='label'>OOS LEADER</div><div class='value'>{html.escape(s['oos_leader'] or 'UNVERIFIED')}</div></div>
<div class='card'><div class='label'>CASCADE 상태</div><div class='value {cascade_cls}'>{html.escape(cascade)}</div></div>
<div class='card'><div class='label'>장 구간 (SESSION)</div><div class='value {phase_cls}'>{phase_val}</div><div class='sub'>{ctx_val} · R_dyn {r_dyn}</div></div>
<div class='card'><div class='label'>DATA</div>
<div class='value'>{html.escape(s.get('data_source') or s.get('provider') or 'N/A')}</div>
<div class='sub'>quality {html.escape(s.get('data_quality') or s.get('quality') or 'N/A')} ·
trade_amount {'derived' if s.get('trade_amount_derived') else 'native'} ·
updated {html.escape(s['updated_at'] or '-')}</div>
{("<div class='sub bad'>⚠ FALLBACK: " + html.escape(s.get('ume_error') or 'UME failed') + "</div>") if str(s.get('data_source','')).startswith('demo_replay(fallback)') else ""}</div>
</div>

<div class='grid two'>
<div class='card'><div class='label'>WHY PRIORITY?</div><div class='reason'>{html.escape(s['priority_reason'] or '계산 대기 중...')}</div></div>
<div class='card'><div class='label'>MARKET STATE</div><div class='reason'>
Trend <b>{_fmt(ms.get('trend'))}</b> · Momentum <b>{_fmt(ms.get('momentum'))}</b> ·
Volatility <b>{_fmt(ms.get('volatility'))}</b> · MA distance <b>{_fmt(ms.get('distance_ma'), 4)}</b></div></div>
</div>

<div class='card' style='margin-top:14px'><div class='label'>ARENA — 현재 관측 (신호강도 × Regime 적합도)</div>
<table><thead><tr><th>Rank</th><th>Model</th><th>Signal</th><th>Strength</th><th>Regime Fit</th><th>Obs</th></tr></thead>
<tbody>{''.join(pred_rows) or "<tr><td colspan='6'>계산 대기 중</td></tr>"}</tbody></table></div>

<div class='grid three' style='margin-top:14px'>
<div class='card'><div class='label'>센서 1 — TIR (일봉)</div>
<div class='value'>{'ACTIVE' if cs.get('tir_event') else 'NORMAL'}</div>
<div class='sub'>소스: {tir_real} · Q_z {_fmt(cs.get('Q_z'))}</div></div>
<div class='card'><div class='label'>센서 2 — FRICTION (분봉)</div>
<div class='value {'bad' if cs.get('friction_spike') else 'good'}'>{'SPIKE' if cs.get('friction_spike') else 'NORMAL'}</div>
<div class='sub'>score {_fmt(cs.get('friction_score'), 4)} · 소스: {fric_real}</div></div>
<div class='card'><div class='label'>센서 3 — STATE-SPACE (분봉)</div>
<div class='value'>x {_fmt(cs.get('x_t'))} · v {_fmt(cs.get('v_t'))}</div>
<div class='sub'>a {_fmt(cs.get('a_t'))} · 유효레코드 {cs.get('n_valid', '...')}</div></div>
</div>

<div class='grid two' style='margin-top:14px'>
<div class='card'><div class='label'>CASCADE LABEL 분포 (이번 구간)</div>
<table><thead><tr><th>Label</th><th>건수</th></tr></thead><tbody>{cascade_rows}</tbody></table></div>
<div class='card'><div class='label'>⚠ 저항붕괴 상태전이 알림 (regime_alert)</div>
<table><thead><tr><th>시점</th><th>Q_z</th><th>Friction</th><th>x_t</th><th>Label</th></tr></thead>
<tbody>{alert_rows}</tbody></table></div>
</div>

<div class='card' style='margin-top:14px'><div class='label'>OOS VALIDATION LAYER — Arena walk-forward</div>
<table><thead><tr><th>Model</th><th>N</th><th>Directional Acc</th><th>Brier</th><th>MAE</th><th>PF</th><th>Status</th></tr></thead>
<tbody>{''.join(oos_rows) or "<tr><td colspan='7'>아직 평가된 OOS 예측 없음</td></tr>"}</tbody></table></div>

<div class='grid two' style='margin-top:14px'>
<div class='card'><div class='label'>📚 PREDICTION LEDGER — 상태</div>
{ledger_state_html}
<div class='sub'>판정: VERIFIED(n≥30 & Wilson 95% CI 하한 &gt; 50%) / NO_EDGE / INSUFFICIENT_SAMPLE / DUPLICATED_SAMPLE</div></div>
<div class='card'><div class='label'>LEDGER — 신뢰도: TIR binary_event (OOS)</div>
<table><thead><tr><th>Model</th><th>N</th><th>Event Acc</th><th>CI 하한(95%)</th><th>Status</th></tr></thead>
<tbody>{''.join(ledger_bin_rows)}</tbody></table></div>
</div>

<div class='card' style='margin-top:14px'><div class='label'>LEDGER — 신뢰도: direction OOS (cascade 경보 예측 등)</div>
<table><thead><tr><th>Model</th><th>Task</th><th>N</th><th>Dir Acc</th><th>CI 하한(95%)</th><th>Status</th></tr></thead>
<tbody>{''.join(ledger_oos_rows)}</tbody></table></div>

<div class='grid two' style='margin-top:14px'>
<div class='card'><div class='label'>TIR v2 — 4분류 상태 분포</div>
<table><thead><tr><th>상태</th><th>건수</th></tr></thead><tbody>{tir_v2_count_rows}</tbody></table>
<div class='sub'>BREAKOUT_후보는 TIR 미충족 + Fast에서만 등장하며 확정 신호가 아니라 후보입니다.</div></div>
<div class='card'><div class='label'>TIR v2 — 그룹별 돌파 발생률 (95% Wilson CI)</div>
<table><thead><tr><th>그룹</th><th>N</th><th>Rate</th><th>95% CI</th></tr></thead><tbody>{''.join(tir_v2_cmp_rows)}</tbody></table>
<div class='sub'>B.LEAK_WARNING의 CI가 D.baseline과 겹치면 현재 표본에서 통계적으로 구별되지 않습니다.</div></div>
</div>

<div class='card' style='margin-top:14px'><div class='label'>MARKET RUNTIME v3 — 세션 시계 · 컨텍스트 계약</div>
<div class='reason'>
장 구간: <b>{phase_val}</b> · KST {html.escape(str(cons.get('phase_kst', '-')))} ·
휴장일 관리: {html.escape(str(cons.get('holidays_managed', '-')))}<br>
market_context.json: <b>{ctx_val}</b> · regime {html.escape(str(cons.get('context_regime') or '-'))} ·
engine_level {html.escape(str(cons.get('context_engine_level') or '-'))}<br>
R_dynamic: {r_dyn}<br>
status: <b>{cons_status}</b> · {cons_msg}</div></div>

<div class='footer'>UME가 연결된 경우 DATA=ume가 실제 UME 입력을 의미합니다. demo_replay/fallback은 synthetic replay이며 실제 KOSPI 성능을 의미하지 않습니다. 원본 Arena/data_port/UME 모듈은 수정 없이 재사용됩니다. (10초마다 자동 새로고침)</div>
</div></body></html>"""


class MasterHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in {"/", "/index.html"}:
            body = render_page().encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Refresh", "10")
            self.end_headers()
            self.wfile.write(body)
        elif self.path == "/state.json":
            body = STATE.to_json().encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, fmt, *args):
        return


# ======================================================================
# 8. MAIN — 스레드 기동 + 단일 서버
# ======================================================================

def main():
    parser = argparse.ArgumentParser(description="KOSPI Master Cockpit (통합 진입점)")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--interval", type=float, default=60.0,
                        help="Arena/Cockpit/Ledger 재계산 주기(초)")
    parser.add_argument("--ledger", type=str,
                        default=os.path.join("04_data", "local",
                                             "ledger_master_kospi.jsonl"),
                        help="예측 원장 파일 경로 (SEC-402/403: 04_data/local/ 권장)")
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--data-source", choices=("ume", "demo"), default="ume",
                        help="Arena 입력 데이터 소스 (기본: ume)")
    parser.add_argument("--ume-providers", type=str, default="krx,naver,yahoo",
                        help="UME provider 목록, 쉼표 구분")
    parser.add_argument("--ume-count", type=int, default=200,
                        help="UME 조회 개수")
    args = parser.parse_args()
    ume_providers = [x.strip() for x in args.ume_providers.split(",") if x.strip()]

    print("=" * 70)
    print(" KOSPI MASTER COCKPIT — 통합 런타임 기동")
    print("=" * 70)
    print(f" Arena 버전      : {observatory_version}")
    print(f" TIR 어댑터      : {'connected (원장 기록 가능)' if tir_has_adapter else '기본 v1 (원장 기록 불가)'}")
    print(f" 공용 원장 모듈  : {'연결됨' if ledger_mod is not None else '미연결 (원장 섹션 비활성)'}")
    print(f" 원장 파일       : {args.ledger}")
    # [수정 2026-10-09] "Arena DATA: ume"은 요청 모드일 뿐 실제 데이터 원천이
    # 아니므로, 기동 후 data_source로 확인하도록 표기를 정직하게 바꾼다.
    print(f" Arena DATA      : {args.data_source} (요청 모드 — 실제 데이터 원천은 "
          f"기동 후 대시보드 DATA 카드/state.json의 data_source로 확인)")
    print(f" UME providers   : {','.join(ume_providers)}")
    print(f" UME count       : {args.ume_count}")
    if args.data_source == "ume":
        _mode, _dp, _market = _load_ume_layer()
        if _mode:
            mode_label = {
                "data_port": "kospi_arena.data_port + UMEBarSource",
                "bar_source": "UMEBarSource",
                "market": "universal_quant_engine.Market 공개 API 직접",
            }[_mode]
            print(f" UME 어댑터      : 발견 ({_mode}: {mode_label})")
            print(" UME 연결 상태   : 미검증 — 실제 fetch 성공 전까지 연결 완료로 간주하지 않음")
        else:
            print(" UME 계층        : 미연결 → Arena는 demo_replay(fallback)로 동작")
            if UME_IMPORT_ERROR:
                print(f" UME 미연결 원인 : {UME_IMPORT_ERROR}")

    threads = [
        threading.Thread(
            target=arena_worker,
            args=(args.interval, args.data_source, ume_providers, args.ume_count),
            daemon=True,
            name="arena",
        ),
        threading.Thread(target=cockpit_worker, args=(args.interval,), daemon=True, name="cockpit"),
        threading.Thread(target=ledger_worker, args=(args.interval, args.ledger), daemon=True, name="ledger"),
        threading.Thread(target=consolidated_worker, args=(args.interval,), daemon=True, name="consolidated"),
        threading.Thread(target=state_file_worker, daemon=True, name="state-file"),
    ]
    for t in threads:
        t.start()

    server = ThreadingHTTPServer(("127.0.0.1", args.port), MasterHandler)
    url = f"http://127.0.0.1:{args.port}/"
    print(f"통합 대시보드: {url}")
    print(f"상태 API     : {url}state.json  (외부 프로세스용 계약)")
    print("종료: Ctrl+C\n")
    if not args.no_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n시스템을 안전하게 종료합니다.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()