"""
Pass 2: Signals engine for topics, narratives, and entities (windowed + article-level).
Outputs additional *_Signals columns; source CSV remains unchanged.
"""

from datetime import timedelta
from typing import List, Tuple

import numpy as np
import pandas as pd


# ------------------------------
# Configuration
# ------------------------------
WINDOW_DAYS = 30
LOW_TIER = {1, 2}
MID_HIGH_TIER = {3, 4, 5}
ENTITY_SIGNAL_CAP = 3

# Severity/structure weights for entity-signal tie-breaking (higher is stronger)
ENTITY_SIGNAL_WEIGHTS = {
    # name: (severity_weight, structural_weight)
    "Narrative Shaping": (9, 3),
    "Strategic Fallout": (8, 2),
    "Strategic Uplift": (7, 2),
    "Echo (tight)": (6, 2),
    "Rising Threat": (7, 2),
    "Rising Opportunity": (7, 2),
    "Deepening Exposure": (6, 1),
    "Strengthening Position": (6, 1),
    "Lost Momentum": (5, 1),
    "Prominence Spike": (5, 1),
    "Momentum Gap": (5, 1),
    "Framing Cage (tight)": (8, 3),
    "Turbulent Frame (tight)": (6, 2),
    "Wedge Potential": (5, 2),
    "Opening Available": (6, 2),
    "Narrative Vacuum": (4, 1),
    "Captured Narrative (article)": (6, 2),
    "Narrative Expansion": (6, 2),
    "Narrative Fragmentation": (5, 2),
    "Second Fiddle": (4, 1),
    "Peer Pressure": (4, 1),
    "Ricochet Risk": (5, 2),
    "Contrast Framing": (5, 1),
    "Polarized Framing": (6, 2),
    "Cautious Schadenfreude": (5, 2),
}


# ------------------------------
# Helpers
# ------------------------------
def _ensure_datetime(df: pd.DataFrame, date_col: str = "Date") -> pd.DataFrame:
    if date_col in df.columns and not np.issubdtype(df[date_col].dtype, np.datetime64):
        # Prefer fast, fixed-format parse; try common formats before generic fallback
        parsed = pd.to_datetime(df[date_col], format="%Y-%m-%d", errors="coerce")

        if parsed.isna().all():
            for fmt in ("%m/%d/%Y", "%m/%d/%y", "%Y-%m-%d %H:%M:%S", "%m/%d/%Y %H:%M:%S"):
                alt = pd.to_datetime(df[date_col], format=fmt, errors="coerce")
                if not alt.isna().all():
                    parsed = alt
                    break

        if parsed.isna().all():
            # Final fallback: generic parse (may be slower)
            parsed = pd.to_datetime(df[date_col], errors="coerce")
        df[date_col] = parsed
    return df


def _normalize_headers(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize common header inconsistencies without changing semantics.
    - Fix "Enity_" -> "Entity_"
    - Singularize "_Modifiers" -> "_Modifier"
    - Normalize "Quality_score" -> "Quality_Score" (case/underscore variants)
    """
    rename_map: dict[str, str] = {}
    for col in list(df.columns):
        new_col = col
        if new_col.startswith("Enity_"):
            new_col = "Entity_" + new_col[len("Enity_"):]
        if new_col.endswith("_Modifiers"):
            new_col = new_col[:-1 * len("s")]  # drop trailing 's'
        # Normalize Quality_score variants
        if "Quality_score" in new_col:
            new_col = new_col.replace("Quality_score", "Quality_Score")
        if "Quality score" in new_col:
            new_col = new_col.replace("Quality score", "Quality_Score")
        if new_col != col:
            rename_map[col] = new_col
    if rename_map:
        df = df.rename(columns=rename_map)
    return df


def _window_splits(
    df: pd.DataFrame, date_col: str = "Date", as_of: pd.Timestamp | None = None
) -> Tuple[pd.DataFrame, pd.DataFrame, Tuple[pd.Timestamp, pd.Timestamp], Tuple[pd.Timestamp, pd.Timestamp]]:
    df = _ensure_datetime(df, date_col)
    max_date = pd.to_datetime(as_of) if as_of is not None else df[date_col].max()
    current_start = max_date - pd.Timedelta(days=WINDOW_DAYS - 1)
    prior_start = current_start - pd.Timedelta(days=WINDOW_DAYS)
    prior_end = current_start - pd.Timedelta(days=1)
    df_current = df[(df[date_col] >= current_start) & (df[date_col] <= max_date)].copy()
    df_prior = df[(df[date_col] >= prior_start) & (df[date_col] <= prior_end)].copy()
    return df_current, df_prior, (current_start, max_date), (prior_start, prior_end)


def _mean_safe(series) -> float:
    # Accept Series, list, ndarray; coerce to numeric Series
    s = pd.Series(series)
    s = pd.to_numeric(s, errors="coerce")
    s = s.dropna()
    return float(s.mean()) if len(s) else np.nan


def _std_safe(series: pd.Series) -> float:
    s = pd.to_numeric(series, errors="coerce")
    s = s.dropna()
    return float(s.std(ddof=0)) if len(s) else 0.0


def _iqr_safe(series: pd.Series) -> float:
    s = pd.to_numeric(series, errors="coerce").dropna()
    if s.empty:
        return 0.0
    q3, q1 = np.percentile(s, [75, 25])
    return float(q3 - q1)


def _get_narratives(df: pd.DataFrame) -> List[int]:
    """Discover narrative IDs from coded column patterns like O_M_1prom, O_M_2prom, etc."""
    import re
    narrative_ids = set()
    for col in df.columns:
        match = re.match(r'^O_M_(\d+)', col)
        if match:
            narrative_ids.add(int(match.group(1)))
    return sorted(narrative_ids)


def _get_entities(df: pd.DataFrame) -> List[int]:
    """Discover entity IDs from coded column patterns like 1_C_Prom, 2_C_Prom, etc."""
    import re
    entity_ids = set()
    for col in df.columns:
        match = re.match(r'^(\d+)_C_', col)
        if match:
            entity_ids.add(int(match.group(1)))
    return sorted(entity_ids)


def _narr_cols(narrative_id: int) -> Tuple[str, str]:
    return f"O_M_{narrative_id}prom", f"O_M_{narrative_id}sent"


def _entity_cols(entity_id: int) -> Tuple[str, str, str, str, str, str]:
    # returns (prom, sent, qual, state, modifier, signals_colname)
    return (
        f"{entity_id}_C_Prom",
        f"{entity_id}_C_Sent", 
        f"{entity_id}_Orchestra_Quality_Score",
        f"{entity_id}_C_State",
        f"{entity_id}_C_Modifier",
        f"{entity_id}_C_signals",
    )


def _count_distinct_publications(rows: pd.DataFrame) -> int:
    return rows["Publication"].dropna().astype(str).nunique()


# ------------------------------
# Topic signals
# ------------------------------
def compute_topic_signals(df: pd.DataFrame) -> pd.DataFrame:
    df_cur, df_prev, cur_win, _ = _window_splits(df)
    topic_prom, topic_sent = "O_Sent", "O_Sent"  # Using coded topic columns
    vol_cur = len(df_cur)
    vol_prev = len(df_prev)
    avg_prom_low = _mean_safe(df_cur.loc[df_cur["Orchestra_Pub_Tier"].isin(LOW_TIER), topic_prom]) if vol_cur else np.nan
    avg_prom_mh = _mean_safe(df_cur.loc[df_cur["Orchestra_Pub_Tier"].isin(MID_HIGH_TIER), topic_prom]) if vol_cur else np.nan
    std_prom = _std_safe(df_cur[topic_prom]) if vol_cur else 0.0
    std_sent = _std_safe(df_cur[topic_sent]) if vol_cur else 0.0

    # no-narrative share in window
    narratives = _get_narratives(df)
    if narratives:
        no_narr_mask = (df_cur[[f"O_M_{n}prom" for n in narratives]] > 0).sum(axis=1) == 0
        share_no_narr = float(no_narr_mask.mean())
    else:
        share_no_narr = 0.0
    share_low_tier = float((df_cur["Orchestra_Pub_Tier"].isin(LOW_TIER)).mean()) if vol_cur else 0.0
    avg_topic_prom = _mean_safe(df_cur[topic_prom]) if vol_cur else np.nan

    # init column (dataset-level attaches as a constant per row; we still store on each row for CSV usability)
    if "O_signals" not in df.columns:
        df["O_signals"] = [[] for _ in range(len(df))]
    else:
        df["O_signals"] = df["O_signals"].apply(lambda v: v if isinstance(v, list) else ([] if pd.isna(v) else [str(v)]))

    # Article-level Hot retained, but other topic signals are dataset-level per window
    hot_mask = (df[topic_prom] >= 3.5) & (df[topic_sent] >= 3.0)
    if hot_mask.any():
        df.loc[hot_mask, "O_signals"] = df.loc[hot_mask, "O_signals"].apply(lambda s: s + ["Hot"])

    # Windowed signals (copy to all rows for convenience)
    topic_window_signals: List[str] = []
    if vol_prev > 0 and vol_cur >= 1.30 * vol_prev:
        topic_window_signals.append("Growing")
    if vol_prev > 0 and vol_cur <= 0.70 * vol_prev:
        topic_window_signals.append("Fading")
    if (not np.isnan(avg_prom_low)) and (not np.isnan(avg_prom_mh)) and avg_prom_low >= 2.5 and avg_prom_mh < 1.5:
        topic_window_signals.append("Trade-Locked")
    if std_prom >= 1.0 or std_sent >= 1.5:
        topic_window_signals.append("Fragmented Framing")
    if (not np.isnan(avg_topic_prom)) and (avg_topic_prom >= 2.5) and (share_no_narr >= 0.30) and (share_low_tier >= 0.60):
        topic_window_signals.append("Coverage Split")
    if topic_window_signals:
        const = topic_window_signals
        df["O_signals"] = df["O_signals"].apply(lambda s: s + const)
    return df


# ------------------------------
# Narrative signals
# ------------------------------
def compute_narrative_signals(df: pd.DataFrame) -> pd.DataFrame:
    df_cur, df_prev, cur_win, prev_win = _window_splits(df)
    narratives = _get_narratives(df)
    for n in narratives:
        prom_col, sent_col = _narr_cols(n)
        outcol = f"O_M_{n}signals"
        if outcol not in df.columns:
            df[outcol] = [[] for _ in range(len(df))]
        else:
            df[outcol] = df[outcol].apply(lambda v: v if isinstance(v, list) else ([] if pd.isna(v) else [str(v)]))

        # Article-level Hot
        hot_mask = (df[prom_col] >= 3.5) & (df[sent_col] >= 3.0)
        if hot_mask.any():
            df.loc[hot_mask, outcol] = df.loc[hot_mask, outcol].apply(lambda s: s + ["Hot"])

        # Window masks
        cur_mask = (df["Date"] >= cur_win[0]) & (df["Date"] <= cur_win[1]) & (df[prom_col].notna())
        prev_mask = (df["Date"] >= prev_win[0]) & (df["Date"] <= prev_win[1]) & (df[prom_col].notna())
        vol_cur = int(cur_mask.sum())
        vol_prev = int(prev_mask.sum())

        narr_window_signals: List[str] = []
        share_with_narr = float((df.loc[cur_mask, prom_col] > 0).mean()) if vol_cur else 0.0
        share_prom_ge_2_5 = float((df.loc[cur_mask, prom_col] >= 2.5).mean()) if vol_cur else 0.0
        if share_with_narr >= 0.66 or share_prom_ge_2_5 >= 0.50:
            narr_window_signals.append("Dominant")

        entities = _get_entities(df)
        if entities and vol_cur:
            # Captured / Unowned / Media-Led
            narr_rows_prom = df.loc[cur_mask & (df[prom_col] >= 2.5)]
            if not narr_rows_prom.empty:
                # Captured
                shares = {}
                for e in entities:
                    e_prom = _entity_cols(e)[0]
                    shares[e] = float((narr_rows_prom[e_prom] >= 2.5).mean())
                if shares and max(shares.values()) >= 0.50:
                    narr_window_signals.append("Captured")
                # Unowned
                no_owner_share = float(((narr_rows_prom[[_entity_cols(e)[0] for e in entities]] >= 2.5).sum(axis=1) == 0).mean())
                if no_owner_share >= 0.50:
                    narr_window_signals.append("Unowned")
            # Media-Led on any narrative-present article
            narr_rows_all = df.loc[cur_mask & (df[prom_col] > 0)]
            if not narr_rows_all.empty:
                media_led_share = float(((narr_rows_all[[_entity_cols(e)[0] for e in entities]] >= 2.5).sum(axis=1) == 0).mean())
                if media_led_share >= 0.50:
                    narr_window_signals.append("Media-Led")

        # Fragmented, Overlapping, Trade-Locked, Coverage Split
        if vol_cur:
            std_prom = _std_safe(df.loc[cur_mask, prom_col])
            std_sent = _std_safe(df.loc[cur_mask, sent_col])
            if std_prom >= 1.0 or std_sent >= 1.5:
                narr_window_signals.append("Fragmented")
            if narratives:
                narr_prom_cols = [f"O_M_{nn}prom" for nn in narratives]
                overlap_share = float(((df.loc[cur_mask, narr_prom_cols] >= 2.0).sum(axis=1) >= 2).mean())
                if overlap_share >= 0.30:
                    narr_window_signals.append("Overlapping")
            avg_prom_low = _mean_safe(df.loc[cur_mask & df["Orchestra_Pub_Tier"].isin(LOW_TIER), prom_col])
            avg_prom_mh = _mean_safe(df.loc[cur_mask & df["Orchestra_Pub_Tier"].isin(MID_HIGH_TIER), prom_col])
            if (not np.isnan(avg_prom_low)) and (not np.isnan(avg_prom_mh)) and avg_prom_low >= 2.5 and avg_prom_mh < 1.5:
                narr_window_signals.append("Trade-Locked")
            avg_prom = _mean_safe(df.loc[cur_mask, prom_col])
            if narratives:
                other_cols = [f"O_M_{nn}prom" for nn in narratives if nn != n]
                no_companion_share = float(((df.loc[cur_mask, other_cols] > 0).sum(axis=1) == 0).mean()) if other_cols else 1.0
                low_tier_share = float((df.loc[cur_mask, "Orchestra_Pub_Tier"].isin(LOW_TIER)).mean())
                if (avg_prom >= 2.5) and (no_companion_share >= 0.30) and (low_tier_share >= 0.60):
                    narr_window_signals.append("Coverage Split")

        # Growth/Fatigue/Dead/Strengthening/Deteriorating/Gaining Prominence
        if vol_prev > 0 and vol_cur >= 1.30 * vol_prev:
            narr_window_signals.append("Growing")
        if vol_prev > 0 and vol_cur <= 0.70 * vol_prev:
            narr_window_signals.append("Fatigue")
        if vol_cur == 0:
            narr_window_signals.append("Dead")
        if vol_cur and vol_prev:
            avg_sent_cur = _mean_safe(df.loc[cur_mask, sent_col])
            avg_sent_prev = _mean_safe(df.loc[prev_mask, sent_col])
            avg_prom_cur = _mean_safe(df.loc[cur_mask, prom_col])
            avg_prom_prev = _mean_safe(df.loc[prev_mask, prom_col])
            if (avg_sent_cur - avg_sent_prev) >= 1.5 or (avg_prom_cur >= 1.30 * avg_prom_prev):
                narr_window_signals.append("Strengthening")
            if (avg_sent_prev - avg_sent_cur) >= 1.5:
                narr_window_signals.append("Deteriorating")
            if (avg_prom_prev > 0) and (avg_prom_cur >= 1.30 * avg_prom_prev):
                narr_window_signals.append("Gaining Prominence")

        # Attach dataset-level narrative status only to rows where this narrative is present (>0)
        if narr_window_signals:
            present_mask = df[prom_col] > 0
            if present_mask.any():
                const = narr_window_signals
                df.loc[present_mask, outcol] = df.loc[present_mask, outcol].apply(lambda s: s + const)
    return df


# ------------------------------
# Entity signals
# ------------------------------
def _rank_and_cap_entity_signals(signals_with_meta: List[tuple]) -> List[str]:
    if not signals_with_meta:
        return []
    df_rank = pd.DataFrame(
        signals_with_meta,
        columns=["name", "sev", "struc", "outlet", "prom", "recency"],
    )  # type: ignore
    # Coerce to numeric to avoid mixed-type sort errors in some environments
    for col in ("sev", "struc", "outlet", "prom", "recency"):
        df_rank[col] = pd.to_numeric(df_rank[col], errors="coerce")
    df_rank["name"] = df_rank["name"].astype(str)
    # Fill NaNs with safe defaults for ranking
    df_rank[["sev", "struc", "outlet", "prom", "recency"]] = df_rank[["sev", "struc", "outlet", "prom", "recency"]].fillna(0)
    df_rank = df_rank.sort_values(
        by=["sev", "struc", "outlet", "prom", "recency"],
        ascending=[False, False, False, False, False],
        kind="mergesort",
    )
    return df_rank["name"].tolist()[:ENTITY_SIGNAL_CAP]


def compute_entity_signals(df: pd.DataFrame) -> pd.DataFrame:
    df_cur, df_prev, cur_win, prev_win = _window_splits(df)
    entities = _get_entities(df)
    narratives = _get_narratives(df)

    # Precompute narrative gaining prominence flags
    narr_gain: dict[str, bool] = {}
    for n in narratives:
        prm, _ = _narr_cols(n)
        cur_mask = (df["Date"] >= cur_win[0]) & (df["Date"] <= cur_win[1]) & df[prm].notna()
        prev_mask = (df["Date"] >= prev_win[0]) & (df["Date"] <= prev_win[1]) & df[prm].notna()
        avg_prom_cur = _mean_safe(df.loc[cur_mask, prm])
        avg_prom_prev = _mean_safe(df.loc[prev_mask, prm])
        narr_gain[n] = (avg_prom_prev > 0) and (avg_prom_cur >= 1.30 * avg_prom_prev)

    # Per-entity window stats
    stats: dict[str, dict] = {}
    for e in entities:
        e_prom, e_sent, e_q, e_state, e_mod, e_sig = _entity_cols(e)
        cur_mask = (df["Date"] >= cur_win[0]) & (df["Date"] <= cur_win[1]) & df[e_prom].notna()
        prev_mask = (df["Date"] >= prev_win[0]) & (df["Date"] <= prev_win[1]) & df[e_prom].notna()
        stats[e] = {
            "avg_prom_cur": _mean_safe(df.loc[cur_mask, e_prom]),
            "avg_prom_prev": _mean_safe(df.loc[prev_mask, e_prom]),
            "avg_sent_cur": _mean_safe(df.loc[cur_mask, e_sent]),
            "avg_sent_prev": _mean_safe(df.loc[prev_mask, e_sent]),
            "avg_q_cur": _mean_safe(df.loc[cur_mask, e_q]) if e_q in df.columns else np.nan,
            "avg_q_prev": _mean_safe(df.loc[prev_mask, e_q]) if e_q in df.columns else np.nan,
            "had_HST_prev": (e_mod in df.columns) and (df.loc[prev_mask, e_mod].astype(str).eq("Takedown").any()),
            "had_Breakthrough_prev": (e_mod in df.columns) and (df.loc[prev_mask, e_mod].astype(str).eq("Breakthrough").any()),
        }

    # Ensure signal columns
    for e in entities:
        sig_col = _entity_cols(e)[5]
        if sig_col not in df.columns:
            df[sig_col] = [[] for _ in range(len(df))]
        else:
            df[sig_col] = df[sig_col].apply(lambda v: v if isinstance(v, list) else ([] if pd.isna(v) else [str(v)]))

    # Iterate rows
    for idx, row in df.iterrows():
        outlet = int(row.get("Orchestra_Pub_Tier", 0) or 0)
        recency = int(pd.Timestamp(row.get("Date")).value) if pd.notna(row.get("Date")) else 0

        # Peer cache for the row
        row_peers = {}
        for p in entities:
            p_prom, p_sent, p_q, p_state, p_mod, p_sig = _entity_cols(p)
            row_peers[p] = {
                "prom": float(row.get(p_prom, 0.0) or 0.0),
                "sent": float(row.get(p_sent, 0.0) or 0.0),
                "mod": str(row.get(p_mod, "")) if p_mod in df.columns else "",
            }
        peer_max_prom = max([v["prom"] for v in row_peers.values()] + [0.0])
        peer_max_sent = max([v["sent"] for v in row_peers.values()] + [0.0])

        # Narrative context
        row_narr_proms = {n: float(row.get(_narr_cols(n)[0], 0.0) or 0.0) for n in narratives}

        for e in entities:
            e_prom, e_sent, e_q, e_state, e_mod, e_sig = _entity_cols(e)
            prom = float(row.get(e_prom, 0.0) or 0.0)
            sent = float(row.get(e_sent, 0.0) or 0.0)
            mod = str(row.get(e_mod, "")) if e_mod in df.columns else ""
            # Presence gating: only evaluate entity-level signals when entity is present (>0)
            entity_present = prom > 0.0
            signals_meta: List[tuple] = []

            # Narrative Shaping
            if mod in ["Takedown", "Breakthrough"] or (prom >= 4.0 and outlet >= 4):
                sev, stru = ENTITY_SIGNAL_WEIGHTS["Narrative Shaping"]
                signals_meta.append(("Narrative Shaping", sev, stru, outlet, prom, recency))

            # Wedge Potential: require entity present and same-article narrative present
            if entity_present and narratives and any(v > 0 for v in row_narr_proms.values()):
                for p, pv in row_peers.items():
                    if p == e:
                        continue
                    if (sent - pv["sent"]) >= 1.5:
                        sev, stru = ENTITY_SIGNAL_WEIGHTS["Wedge Potential"]
                        signals_meta.append(("Wedge Potential", sev, stru, outlet, prom, recency))
                        break

            # Second Fiddle
            if entity_present and prom < 3.0 and peer_max_prom >= 3.0:
                sev, stru = ENTITY_SIGNAL_WEIGHTS["Second Fiddle"]
                signals_meta.append(("Second Fiddle", sev, stru, outlet, prom, recency))

            # Peer Pressure
            if entity_present and peer_max_sent >= 2.5 and (0.0 <= sent <= 1.0):
                sev, stru = ENTITY_SIGNAL_WEIGHTS["Peer Pressure"]
                signals_meta.append(("Peer Pressure", sev, stru, outlet, prom, recency))

            # Contrast / Polarized
            for p, pv in row_peers.items():
                if p == e:
                    continue
                if entity_present and abs(sent - pv["sent"]) >= 2.0:
                    sev, stru = ENTITY_SIGNAL_WEIGHTS["Contrast Framing"]
                    signals_meta.append(("Contrast Framing", sev, stru, outlet, prom, recency))
                    break
            for p, pv in row_peers.items():
                if p == e:
                    continue
                if entity_present and (pv["sent"] - sent) >= 4.0:
                    sev, stru = ENTITY_SIGNAL_WEIGHTS["Polarized Framing"]
                    signals_meta.append(("Polarized Framing", sev, stru, outlet, prom, recency))
                    break

            # Ricochet Risk / Cautious Schadenfreude
            if entity_present and any(pv["mod"] in ["Narrative Shaper", "Takedown", "Body Blow", "Stinger", "Collateral Damage"] for pv in row_peers.values()):
                sev, stru = ENTITY_SIGNAL_WEIGHTS["Ricochet Risk"]
                signals_meta.append(("Ricochet Risk", sev, stru, outlet, prom, recency))
                if (prom == 0.0) or (sent >= 0.0):
                    sev, stru = ENTITY_SIGNAL_WEIGHTS["Cautious Schadenfreude"]
                    signals_meta.append(("Cautious Schadenfreude", sev, stru, outlet, prom, recency))

            # Captured Narrative (article)
            if entity_present and prom >= 2.5 and (peer_max_prom < 2.5):
                sev, stru = ENTITY_SIGNAL_WEIGHTS["Captured Narrative (article)"]
                signals_meta.append(("Captured Narrative (article)", sev, stru, outlet, prom, recency))

            # Narrative Vacuum
            if entity_present and narratives and all(v == 0.0 for v in row_narr_proms.values()):
                sev, stru = ENTITY_SIGNAL_WEIGHTS["Narrative Vacuum"]
                signals_meta.append(("Narrative Vacuum", sev, stru, outlet, prom, recency))

            # Window-level signals (attach per row)
            st = stats[e]
            if st["had_HST_prev"] and (not np.isnan(st["avg_q_cur"])) and (not np.isnan(st["avg_q_prev"])) and ((st["avg_q_cur"] - st["avg_q_prev"]) <= -0.5):
                sev, stru = ENTITY_SIGNAL_WEIGHTS["Strategic Fallout"]
                signals_meta.append(("Strategic Fallout", sev, stru, outlet, prom, recency))
            if st["had_Breakthrough_prev"] and (not np.isnan(st["avg_q_cur"])) and (not np.isnan(st["avg_q_prev"])) and ((st["avg_q_cur"] - st["avg_q_prev"]) >= 0.5):
                sev, stru = ENTITY_SIGNAL_WEIGHTS["Strategic Uplift"]
                signals_meta.append(("Strategic Uplift", sev, stru, outlet, prom, recency))

            # Echo (tight)
            if narratives:
                narr_sorted = sorted([(nn, row.get(_narr_cols(nn)[0], 0.0)) for nn in narratives], key=lambda x: x[1], reverse=True)
                if narr_sorted and float(narr_sorted[0][1] or 0.0) >= 2.0:
                    top_n = narr_sorted[0][0]
                    n_prom_col, n_sent_col = _narr_cols(top_n)
                    cur_mask = (df["Date"] >= cur_win[0]) & (df["Date"] <= cur_win[1]) & (df[n_prom_col] >= 2.0)
                    slice_cur = df.loc[cur_mask, ["Publication", n_sent_col, e_sent]]
                    if len(slice_cur) >= 3:
                        med_es = float(pd.to_numeric(slice_cur[e_sent], errors="coerce").dropna().median()) if not slice_cur.empty else np.nan
                        med_ns = float(pd.to_numeric(slice_cur[n_sent_col], errors="coerce").dropna().median()) if not slice_cur.empty else np.nan
                        tight = slice_cur[
                            slice_cur[e_sent].between(med_es - 0.5, med_es + 0.5, inclusive="both")
                            & slice_cur[n_sent_col].between(med_ns - 0.5, med_ns + 0.5, inclusive="both")
                        ]
                        if _count_distinct_publications(tight) >= 3:
                            sev, stru = ENTITY_SIGNAL_WEIGHTS["Echo (tight)"]
                            signals_meta.append(("Echo (tight)", sev, stru, outlet, prom, recency))

            # Rising Threat / Rising Opportunity
            if narratives:
                narr_sorted = sorted([(nn, row.get(_narr_cols(nn)[0], 0.0)) for nn in narratives], key=lambda x: x[1], reverse=True)
                if narr_sorted and float(narr_sorted[0][1] or 0.0) >= 2.0:
                    top_n = narr_sorted[0][0]
                    avg_es_cur = st["avg_sent_cur"]
                    if narr_gain.get(top_n, False) and not np.isnan(avg_es_cur):
                        if avg_es_cur < 0.0:
                            sev, stru = ENTITY_SIGNAL_WEIGHTS["Rising Threat"]
                            signals_meta.append(("Rising Threat", sev, stru, outlet, prom, recency))
                        if avg_es_cur > 1.0:
                            sev, stru = ENTITY_SIGNAL_WEIGHTS["Rising Opportunity"]
                            signals_meta.append(("Rising Opportunity", sev, stru, outlet, prom, recency))

            # Deepening/Strengthening/Lost Momentum/Prominence Spike/Momentum Gap
            if (not np.isnan(st["avg_sent_cur"])) and (not np.isnan(st["avg_sent_prev"])):
                if (st["avg_sent_prev"] - st["avg_sent_cur"]) >= 1.5:
                    sev, stru = ENTITY_SIGNAL_WEIGHTS["Deepening Exposure"]
                    signals_meta.append(("Deepening Exposure", sev, stru, outlet, prom, recency))
                if (st["avg_sent_cur"] - st["avg_sent_prev"]) >= 1.5:
                    sev, stru = ENTITY_SIGNAL_WEIGHTS["Strengthening Position"]
                    signals_meta.append(("Strengthening Position", sev, stru, outlet, prom, recency))
            if (not np.isnan(st["avg_prom_cur"])) and (not np.isnan(st["avg_prom_prev"])):
                if (st["avg_prom_cur"] < st["avg_prom_prev"]) and (st["avg_sent_cur"] < st["avg_sent_prev"]):
                    sev, stru = ENTITY_SIGNAL_WEIGHTS["Lost Momentum"]
                    signals_meta.append(("Lost Momentum", sev, stru, outlet, prom, recency))
                if (st["avg_prom_cur"] - st["avg_prom_prev"]) >= 2.0:
                    sev, stru = ENTITY_SIGNAL_WEIGHTS["Prominence Spike"]
                    signals_meta.append(("Prominence Spike", sev, stru, outlet, prom, recency))
                peer_proms_cur, peer_proms_prev = [], []
                for p in entities:
                    if p == e:
                        continue
                    pst = stats[p]
                    if not np.isnan(pst["avg_prom_cur"]):
                        peer_proms_cur.append(pst["avg_prom_cur"])
                    if not np.isnan(pst["avg_prom_prev"]):
                        peer_proms_prev.append(pst["avg_prom_prev"])
                if peer_proms_cur and peer_proms_prev:
                    peer_avg_cur = float(np.mean(peer_proms_cur))
                    peer_avg_prev = float(np.mean(peer_proms_prev))
                    if (peer_avg_cur > st["avg_prom_cur"]) and ((peer_avg_cur - peer_avg_prev) >= 0.5) and ((st["avg_prom_cur"] - st["avg_prom_prev"]) <= 0):
                        sev, stru = ENTITY_SIGNAL_WEIGHTS["Momentum Gap"]
                        signals_meta.append(("Momentum Gap", sev, stru, outlet, prom, recency))

            # Framing Cage (tight)
            if narratives:
                narr_sorted = sorted([(nn, row.get(_narr_cols(nn)[0], 0.0)) for nn in narratives], key=lambda x: x[1], reverse=True)
                if narr_sorted and float(narr_sorted[0][1] or 0.0) > 0:
                    top_n = narr_sorted[0][0]
                    n_prom_col, _ = _narr_cols(top_n)
                    c_mask = (df["Date"] >= cur_win[0]) & (df["Date"] <= cur_win[1]) & (df[n_prom_col] > 0)
                    if c_mask.any():
                        # Vectorized computation over the windowed slice
                        peer_prom_cols = [_entity_cols(p)[0] for p in entities if p != e]
                        cols_to_use = [e_prom] + peer_prom_cols
                        sub = df.loc[c_mask, cols_to_use].copy()
                        # Coerce to numeric to avoid mixed-type issues
                        for c in cols_to_use:
                            sub[c] = pd.to_numeric(sub[c], errors="coerce").fillna(0.0)
                        peer_ge3_any = (sub[peer_prom_cols] >= 3.0).any(axis=1) if peer_prom_cols else pd.Series(False, index=sub.index)
                        entity_lt3 = sub[e_prom] < 3.0
                        entity_ge3 = sub[e_prom] >= 3.0
                        if len(sub) > 0:
                            share_case = float((peer_ge3_any & entity_lt3).mean())
                            share_entity_ge3 = float((entity_ge3).mean())
                            if (share_case >= 0.60) and (share_entity_ge3 <= 0.10):
                                sev, stru = ENTITY_SIGNAL_WEIGHTS["Framing Cage (tight)"]
                                signals_meta.append(("Framing Cage (tight)", sev, stru, outlet, prom, recency))

            # Turbulent Frame (tight)
            c_mask_e = (df["Date"] >= cur_win[0]) & (df["Date"] <= cur_win[1]) & df[e_prom].notna()
            std_prom = _std_safe(df.loc[c_mask_e, e_prom])
            std_sent = _std_safe(df.loc[c_mask_e, e_sent])
            iqr_sent = _iqr_safe(df.loc[c_mask_e, e_sent])
            if (std_prom >= 1.0) or (std_sent >= 1.5) or (iqr_sent >= 2.0):
                sev, stru = ENTITY_SIGNAL_WEIGHTS["Turbulent Frame (tight)"]
                signals_meta.append(("Turbulent Frame (tight)", sev, stru, outlet, prom, recency))

            # Narrative Expansion / Fragmentation (window-level approximations)
            if narratives:
                pos_narrs = 0
                prom_map = []
                cm = (df["Date"] >= cur_win[0]) & (df["Date"] <= cur_win[1])
                for nn in narratives:
                    n_prom, n_sent = _narr_cols(nn)
                    rows_nn = df.loc[cm & (df[n_prom] > 0)]
                    if rows_nn.empty:
                        continue
                    e_prom_avg = _mean_safe(rows_nn[e_prom])
                    e_sent_avg = _mean_safe(rows_nn[e_sent])
                    prom_map.append((nn, e_prom_avg, e_sent_avg))
                    if (e_prom_avg >= 2.5) and (e_sent_avg > 1.0):
                        pos_narrs += 1
                if pos_narrs >= 2:
                    sev, stru = ENTITY_SIGNAL_WEIGHTS["Narrative Expansion"]
                    signals_meta.append(("Narrative Expansion", sev, stru, outlet, prom, recency))
                if len(prom_map) >= 2:
                    sents = [x[2] for x in prom_map if not np.isnan(x[2])]
                    if sents and (max(sents) - min(sents)) > 3.0 and any(x[1] >= 2.0 for x in prom_map):
                        sev, stru = ENTITY_SIGNAL_WEIGHTS["Narrative Fragmentation"]
                        signals_meta.append(("Narrative Fragmentation", sev, stru, outlet, prom, recency))

            # Final cap per article per entity
            ranked = _rank_and_cap_entity_signals(signals_meta)
            if ranked:
                cur_list = df.at[idx, e_sig] if isinstance(df.at[idx, e_sig], list) else []
                df.at[idx, e_sig] = list(set(cur_list + ranked))
    return df


# ------------------------------
# Orchestrator and entry point
# ------------------------------
def apply_all_signals(df: pd.DataFrame, as_of: str | None = None) -> pd.DataFrame:
    df = df.copy()
    df = _normalize_headers(df)
    df = _ensure_datetime(df, "Date")
    # Topic
    df = compute_topic_signals(df)
    # Narrative
    df = compute_narrative_signals(df)
    # Entity
    df = compute_entity_signals(df)
    # Normalize list columns to pipe-joined strings for CSV
    list_cols = [c for c in df.columns if c.endswith("signals") or c == "O_signals"]
    for c in list_cols:
        df[c] = df[c].apply(lambda v: ", ".join(v) if isinstance(v, list) else (v if isinstance(v, str) else ""))
    return df


def process_signals(csv_path: str, as_of: str | None = None) -> str:
    df = pd.read_csv(csv_path, low_memory=False)
    out_df = apply_all_signals(df, as_of=as_of)
    if "/" in csv_path:
        dirname, filename = csv_path.rsplit("/", 1)
    else:
        dirname, filename = ".", csv_path
    out_path = f"{dirname}/Signals_{filename}"
    out_df.to_csv(out_path, index=False)
    return out_path


