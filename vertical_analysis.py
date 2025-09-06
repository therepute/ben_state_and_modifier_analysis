import argparse
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import pandas as pd


# -------------------------------
# Data structures
# -------------------------------

@dataclass
class NarrativeColumnMapping:
    description: str
    prominence: str
    sentiment: str
    state: str


@dataclass
class EntityColumnMapping:
    quality_score: Optional[str]
    prominence: str
    sentiment: str
    description: Optional[str]
    state: str
    modifier: str


# -------------------------------
# Constants and configuration
# -------------------------------

TOPIC_PROMINENCE_COL = "O_Overall - Overall-Level Prominence"  # Need to add this column
TOPIC_SENTIMENT_COL = "O_Overall - Overall-Level Sentiment"
TOPIC_STATE_COL = "Topic_State"

OUTLET_SCORE_COL = "Orchestra_Pub_Tier"
PUB_TIER_COL = "Pub_Tier"
BODY_LENGTH_COL = "Body - Length - Words"

NARRATIVE_TIE_PRECEDENCE: List[str] = [
    "Narrative_BusinessMomentum",
    "Narrative_ResponsibleGaming",
    "Narrative_Entertainment", 
    "Narrative_Regulatory",
    "Narrative_IndustryGrowth",
]

NARRATIVE_MAPPINGS: Dict[str, NarrativeColumnMapping] = {
    "Narrative_BusinessMomentum": NarrativeColumnMapping(
        description="O_Overall - Message 1 Description (Business Momentum)",
        prominence="O_Overall - Message 1 Prominence (Business Momentum)",
        sentiment="O_Overall - Message 1 Sentiment (Business Momentum)",
        state="O_M_1state",
    ),
    "Narrative_ResponsibleGaming": NarrativeColumnMapping(
        description="O_Overall - Message 2 Description (Responsible Gaming, Moral Hazard & Legal Scrutiny)",
        prominence="O_Overall - Message 2 Prominence (Responsible Gaming, Moral Hazard & Legal Scrutiny)",
        sentiment="O_Overall - Message 2 Sentiment (Responsible Gaming, Moral Hazard & Legal Scrutiny)",
        state="O_M_2state",
    ),
    "Narrative_Entertainment": NarrativeColumnMapping(
        description="O_Overall - Message 3 Description (Betting enhances sports entertainment)",
        prominence="O_Overall - Message 3 Prominence (Betting enhances sports entertainment)",
        sentiment="O_Overall - Message 3 Sentiment (Betting enhances sports entertainment)",
        state="O_M_3state",
    ),
    "Narrative_Regulatory": NarrativeColumnMapping(
        description="O_Overall - Message 4 Description (Regulatory and policymaker oversight)",
        prominence="O_Overall - Message 4 Prominence (Regulatory and policymaker oversight)",
        sentiment="O_Overall - Message 4 Sentiment (Regulatory and policymaker oversight)",
        state="O_M_4state",
    ),
    "Narrative_IndustryGrowth": NarrativeColumnMapping(
        description="O_Overall - Message 5 Description (Industry growth and economic impact)",
        prominence="O_Overall - Message 5 Prominence (Industry growth and economic impact)",
        sentiment="O_Overall - Message 5 Sentiment (Industry growth and economic impact)",
        state="O_M_5state",
    ),
}

ENTITY_MAPPINGS: Dict[str, EntityColumnMapping] = {
    "Bet365": EntityColumnMapping(
        quality_score="1_Orchestra_Quality_Score",
        prominence="1_Bet365 - Company-Level Prominence",
        sentiment="1_Bet365 - Company-Level Sentiment",
        description="1_Bet365 - Company-Level Description",
        state="1_C_State",
        modifier="1_C_Modifier",
    ),
    "FanDuel": EntityColumnMapping(
        quality_score="2_Orchestra_Quality_Score",
        prominence="2_FanDuel - Company-Level Prominence",
        sentiment="2_FanDuel - Company-Level Sentiment",
        description="2_FanDuel - Company-Level Description",
        state="2_C_State",
        modifier="2_C_Modifier",
    ),
    "DraftKings": EntityColumnMapping(
        quality_score="3_Orchestra_Quality_Score",
        prominence="3_DraftKings - Company-Level Prominence",
        sentiment="3_DraftKings - Company-Level Sentiment",
        description="3_DraftKings - Company-Level Description",
        state="3_C_State",
        modifier="3_C_Modifier",
    ),
    "BetMGM": EntityColumnMapping(
        quality_score="4_Orchestra_Quality_Score",
        prominence="4_BetMGM - Company-Level Prominence",
        sentiment="4_BetMGM - Company-Level Sentiment",
        description="4_BetMGM - Company-Level Description",
        state="4_C_State",
        modifier="4_C_Modifier",
    ),
}


# -------------------------------
# Utility functions
# -------------------------------

def coerce_float(value) -> float:
    if pd.isna(value):
        return 0.0
    try:
        return float(value)
    except Exception:
        return 0.0


def is_present(prominence_value: float) -> bool:
    return prominence_value > 0.0


def normalize_sentiment_weak_collapse(raw_sentiment: float) -> float:
    if raw_sentiment == 0.0:
        return 0.0
    if 0.01 <= raw_sentiment <= 1.0:
        return 1.0
    if -1.0 <= raw_sentiment <= -0.01:
        return -1.0
    return raw_sentiment


def gated_sentiment(prominence: float, sentiment: float) -> float:
    # Only consider sentiment if prominence > 0
    return sentiment if prominence > 0.0 else 0.0


def pick_central_narrative(row: pd.Series) -> Tuple[str, float, float]:
    # Returns (narrative_key, prominence, sentiment)
    best_key = ""
    best_prom = -1.0
    best_sent_for_ties = 0.0

    for key in NARRATIVE_TIE_PRECEDENCE:
        mapping = NARRATIVE_MAPPINGS[key]
        prom = coerce_float(row.get(mapping.prominence, 0.0))
        sent = coerce_float(row.get(mapping.sentiment, 0.0))
        if prom > best_prom:
            best_key = key
            best_prom = prom
            best_sent_for_ties = abs(sent)
        elif prom == best_prom:
            # tie-break by higher absolute sentiment, then precedence order is already maintained by loop order
            if abs(sent) > best_sent_for_ties:
                best_key = key
                best_prom = prom
                best_sent_for_ties = abs(sent)

    if best_key == "":
        return ("", 0.0, 0.0)

    best_mapping = NARRATIVE_MAPPINGS[best_key]
    return (
        best_key,
        coerce_float(row.get(best_mapping.prominence, 0.0)),
        coerce_float(row.get(best_mapping.sentiment, 0.0)),
    )


# -------------------------------
# State assignment logic
# -------------------------------

def assign_topic_state(topic_present: bool, topic_prom: float, topic_sent: float) -> str:
    if not topic_present:
        return "Absent"
    # Precedence: High Risk, Risky, Healthy, Ambient Risk, Niche
    if topic_prom >= 2.5 and topic_sent < -2.0:
        return "High Risk"
    if topic_prom >= 2.5 and 0.0 > topic_sent >= -2.0:
        return "Risky"
    # Healthy: central and non-negative
    if topic_prom >= 2.5 and topic_sent >= 0.0:
        return "Healthy"
    if topic_prom < 2.5 and topic_sent < 0.0:
        return "Ambient Risk"
    if topic_prom < 2.5 and topic_sent >= 0.0:
        return "Niche"
    return "Undetermined"


def assign_narrative_state(narr_present: bool, narr_prom: float, narr_sent: float) -> str:
    if not narr_present:
        return "Absent"
    # Precedence: High Risk, Risky, Healthy, Ambient Risk, Niche
    if narr_prom >= 2.5 and narr_sent < -2.0:
        return "High Risk"
    if narr_prom >= 2.5 and 0.0 > narr_sent >= -2.0:
        return "Risky"
    if narr_prom >= 2.5 and narr_sent >= 0.0:
        return "Healthy"
    if narr_prom < 2.5 and narr_sent < 0.0:
        return "Ambient Risk"
    if narr_prom < 2.5 and narr_sent >= 0.0:
        return "Niche"
    return "Undetermined"


def assign_entity_state(entity_present: bool, any_narrative_present: bool, entity_prom: float, entity_sent: float) -> str:
    # Precedence: Absent, Off-Stage, Leader, Under Fire, Supporting Player
    if not entity_present and not any_narrative_present:
        return "Absent"
    if not entity_present and any_narrative_present:
        return "Off-Stage"
    if entity_present and entity_prom >= 3.0 and entity_sent >= 0.0:
        return "Leader"
    if entity_present and entity_prom > 0.0 and entity_sent < 0.0:
        return "Under Fire"
    if entity_present and 0.0 < entity_prom < 3.0 and entity_sent >= 0.0:
        return "Supporting Player"
    return "Undetermined"


# -------------------------------
# Modifier assignment logic (entity)
# -------------------------------

def assign_absent_modifier(topic_present: bool, topic_prom: float, topic_sent: float, any_narrative_present: bool) -> str:
    # Precedence: Framing Risk, Narrative Drift, Not Relevant
    if topic_present and topic_prom >= 2.0 and topic_sent < 0.0 and not any_narrative_present:
        return "Framing Risk"
    if topic_present and topic_prom >= 2.0 and topic_sent >= 0.0 and not any_narrative_present:
        return "Narrative Drift"
    if topic_present and topic_prom < 2.0 and not any_narrative_present:
        return "Not Relevant"
    return ""


def assign_off_stage_modifier(narr_prom: float, narr_sent: float, prominent_tracked_entities: int) -> str:
    # Precedence: Guilt by Association, Innocent Bystander, Reporter-Led Risk, Competitor-Led, Missed Opportunity, Overlooked
    
    # First evaluate high-prominence narratives (≥ 2.5)
    if narr_prom >= 2.5:
        # Negative sentiment cases
        if narr_sent < 0.0:
            if prominent_tracked_entities >= 2:
                return "Guilt by Association"
            if prominent_tracked_entities == 1:
                return "Innocent Bystander"
            if prominent_tracked_entities == 0:
                return "Reporter-Led Risk"
        # Non-negative sentiment cases
        else:  # narr_sent >= 0.0
            if prominent_tracked_entities >= 1:
                return "Competitor-Led"
            if prominent_tracked_entities == 0:
                return "Missed Opportunity"
    
    # Low-prominence narratives (< 2.5) - only assign Overlooked if no prominent peers
    if narr_prom < 2.5 and prominent_tracked_entities == 0:
        return "Overlooked"
    
    return ""


def assign_supporting_player_modifier(outlet_score: float, entity_sent: float) -> str:
    # Precedence: Strategic Signal, Low-Heat Visibility, Check the Box, Background Noise
    if outlet_score >= 3 and entity_sent >= 3.0:
        return "Strategic Signal"
    if outlet_score >= 3 and 0.5 <= entity_sent < 3.0:
        return "Low-Heat Visibility"
    if outlet_score < 3 and entity_sent >= 3.0:
        return "Check the Box"
    if outlet_score < 3 and 0.5 <= entity_sent < 3.0:
        return "Background Noise"
    return ""


def assign_under_fire_modifier(entity_prom: float, entity_sent: float, outlet_score: float) -> str:
    # Precedence: Narrative Shaper, Takedown, Body Blow, Stinger, Light Jab, Collateral Damage, Peripheral Hit
    # Note: Narrative Shaper would require headline detection - not implemented yet
    if entity_prom >= 3.0 and entity_sent <= -2.0 and outlet_score >= 4:
        return "Takedown"
    if entity_prom >= 3.0 and entity_sent <= -2.0 and outlet_score > 2:
        return "Body Blow"
    if entity_prom >= 2.0 and entity_sent <= -2.0:
        return "Stinger"
    if entity_prom >= 2.0 and 0.0 > entity_sent > -2.0:
        return "Light Jab"
    if entity_prom < 2.0 and entity_sent <= -2.0:
        return "Collateral Damage"
    if entity_prom < 2.0 and 0.0 > entity_sent > -2.0:
        return "Peripheral Hit"
    return ""


def assign_leader_modifier(entity_prom: float, entity_sent: float, outlet_score: float) -> str:
    # Precedence: Narrative Setter, Breakthrough, Great Story, Good Story, Routine Positive
    # Note: Narrative Setter would require headline detection - not implemented yet
    if entity_prom >= 4.0 and entity_sent >= 3.0 and outlet_score >= 4:
        return "Breakthrough"
    if entity_prom >= 3.0 and entity_sent >= 2.0 and outlet_score >= 3:
        return "Great Story"
    if entity_prom >= 3.0 and (
        (entity_sent >= 1.0 and outlet_score >= 3) or (entity_sent >= 0.0 and outlet_score < 3)
    ):
        return "Good Story"
    if entity_prom >= 3.0 and entity_sent >= 0.0:
        return "Routine Positive"
    return ""


def assign_entity_modifier(
    entity_state: str,
    outlet_score: float,
    entity_prom: float,
    entity_sent: float,
    topic_present: bool,
    topic_prom: float,
    topic_sent: float,
    any_narrative_present: bool,
    central_narr_prom: float,
    central_narr_sent: float,
    prominent_tracked_entities: int,
) -> str:
    if entity_state == "Absent":
        return assign_absent_modifier(topic_present, topic_prom, topic_sent, any_narrative_present)
    if entity_state == "Off-Stage":
        return assign_off_stage_modifier(central_narr_prom, central_narr_sent, prominent_tracked_entities)
    if entity_state == "Supporting Player":
        return assign_supporting_player_modifier(outlet_score, entity_sent)
    if entity_state == "Under Fire":
        return assign_under_fire_modifier(entity_prom, entity_sent, outlet_score)
    if entity_state == "Leader":
        return assign_leader_modifier(entity_prom, entity_sent, outlet_score)
    return ""


# -------------------------------
# Processing
# -------------------------------

def process(csv_path: str) -> str:
    df = pd.read_csv(csv_path, low_memory=False)
    
    # Check for required columns and provide detailed error message
    missing_cols = []
    
    # Check required topic columns - create Topic Prominence if missing
    if TOPIC_PROMINENCE_COL not in df.columns:
        # Create Topic Prominence as max of all message prominences
        message_prom_cols = [
            "O_Overall - Message 1 Prominence (Business Momentum)",
            "O_Overall - Message 2 Prominence (Responsible Gaming, Moral Hazard & Legal Scrutiny)",
            "O_Overall - Message 3 Prominence (Betting enhances sports entertainment)",
            "O_Overall - Message 4 Prominence (Regulatory and policymaker oversight)",
            "O_Overall - Message 5 Prominence (Industry growth and economic impact)"
        ]
        available_prom_cols = [col for col in message_prom_cols if col in df.columns]
        if available_prom_cols:
            df[TOPIC_PROMINENCE_COL] = df[available_prom_cols].apply(lambda row: row.max(), axis=1)
        else:
            missing_cols.append(TOPIC_PROMINENCE_COL)
    
    # Check for topic sentiment (can have variations)
    topic_sent_cols = [c for c in df.columns if c.startswith("Topic_Sentiment")]
    if TOPIC_SENTIMENT_COL not in df.columns and not topic_sent_cols:
        missing_cols.append(TOPIC_SENTIMENT_COL)
    
    # Check required narrative columns
    for key, mapping in NARRATIVE_MAPPINGS.items():
        if mapping.prominence not in df.columns:
            missing_cols.append(mapping.prominence)
        if mapping.sentiment not in df.columns:
            missing_cols.append(mapping.sentiment)
    
    # Check required entity columns
    for entity_name, mapping in ENTITY_MAPPINGS.items():
        if mapping.prominence not in df.columns:
            missing_cols.append(mapping.prominence)
        if mapping.sentiment not in df.columns:
            missing_cols.append(mapping.sentiment)
    
    # Check required metadata columns
    required_meta_cols = [OUTLET_SCORE_COL, PUB_TIER_COL, BODY_LENGTH_COL]
    for col in required_meta_cols:
        if col not in df.columns:
            missing_cols.append(col)
    
    if missing_cols:
        available_cols = sorted(df.columns.tolist())
        raise ValueError(f"Missing required columns: {missing_cols}\n\nAvailable columns in your CSV: {available_cols}\n\nPlease ensure your CSV has all required columns for analysis.")

    # Use the first Topic_Sentiment column if duplicated
    if TOPIC_SENTIMENT_COL not in df.columns:
        # Attempt to locate any columns starting with the same name
        topic_sent_cols = [c for c in df.columns if c.startswith("Topic_Sentiment")]
        if topic_sent_cols:
            df[TOPIC_SENTIMENT_COL] = df[topic_sent_cols[0]]
        else:
            df[TOPIC_SENTIMENT_COL] = 0.0

    # Handle common Topic_State column name typos
    if TOPIC_STATE_COL not in df.columns:
        # Check for common misspellings
        if "Topic_Sate" in df.columns:
            # Don't overwrite if already has states, just ensure our expected column exists
            if df["Topic_Sate"].isna().all() or (df["Topic_Sate"].astype(str).str.strip() == "").all():
                # Empty column, we can calculate states
                pass
            else:
                # Has existing states, copy them to our expected column name
                df[TOPIC_STATE_COL] = df["Topic_Sate"]

    # Derived presence and normalized sentiment for topic
    df["Topic_Present"] = df[TOPIC_PROMINENCE_COL].apply(coerce_float).apply(lambda x: is_present(x))
    df["Topic_Sentiment_Normalized"] = (
        df[TOPIC_SENTIMENT_COL].apply(coerce_float).apply(normalize_sentiment_weak_collapse)
    )

    # Any narrative present?
    for key, mapping in NARRATIVE_MAPPINGS.items():
        present_col = f"{key}_Present"
        sent_norm_col = f"{key}_Sentiment_Normalized"
        df[present_col] = df[mapping.prominence].apply(coerce_float).apply(lambda x: is_present(x))
        df[sent_norm_col] = df[mapping.sentiment].apply(coerce_float).apply(normalize_sentiment_weak_collapse)

        # Assign narrative state
        def _narr_state_row(row: pd.Series) -> str:
            # Check if state already exists and is not empty
            existing_state = row.get(mapping.state, "")
            if existing_state and str(existing_state).strip() and str(existing_state) not in ["nan", "NaN", ""]:
                return str(existing_state)
            
            # Calculate state if empty or missing
            prom = coerce_float(row.get(mapping.prominence, 0.0))
            sent = coerce_float(row.get(mapping.sentiment, 0.0))
            
            # Fix 2B: When prominence = 0, assign "Absent" deterministically
            if prom == 0.0:
                return "Absent"
            
            narr_present = is_present(prom)
            gated_sent = gated_sentiment(prom, sent)
            return assign_narrative_state(narr_present, prom, gated_sent)

        df[mapping.state] = df.apply(_narr_state_row, axis=1)

    df["Any_Narrative_Present"] = (
        df[[NARRATIVE_MAPPINGS[k].prominence for k in NARRATIVE_TIE_PRECEDENCE]]
        .apply(lambda s: s.map(coerce_float))
        .gt(0.0)
        .any(axis=1)
    )

    # Topic state assignment (gate sentiment by presence)
    def _topic_state_row(row: pd.Series) -> str:
        # Check if state already exists and is not empty (handles both Topic_State and Topic_Sate)
        existing_state = row.get(TOPIC_STATE_COL, "") or row.get("Topic_Sate", "")
        if existing_state and str(existing_state).strip() and str(existing_state) not in ["nan", "NaN", ""]:
            return str(existing_state)
        
        # Calculate state if empty or missing
        prom = coerce_float(row.get(TOPIC_PROMINENCE_COL, 0.0))
        sent = coerce_float(row.get(TOPIC_SENTIMENT_COL, 0.0))
        
        # Fix 2B: When prominence = 0, assign "Absent" deterministically
        if prom == 0.0:
            return "Absent"
        
        present = is_present(prom)
        gated = gated_sentiment(prom, sent)
        return assign_topic_state(present, prom, gated)

    df[TOPIC_STATE_COL] = df.apply(_topic_state_row, axis=1)

    # Counts for tracked entities
    def _entity_presence_counts(row: pd.Series) -> Tuple[int, int]:
        presences = []
        prominent_flags = []
        for ent_key, ent_map in ENTITY_MAPPINGS.items():
            prom_val = coerce_float(row.get(ent_map.prominence, 0.0))
            presences.append(prom_val > 0.0)
            prominent_flags.append(prom_val >= 2.0)
        return sum(presences), sum(prominent_flags)

    counts = df.apply(_entity_presence_counts, axis=1, result_type="expand")
    df["tracked_entities_in_article"] = counts[0]
    df["prominent_tracked_entities_in_article"] = counts[1]

    # Central narrative for Off-Stage modifiers
    central = df.apply(pick_central_narrative, axis=1, result_type="expand")
    df["Central_Narrative_Key"] = central[0]
    df["Central_Narrative_Prominence"] = central[1]
    df["Central_Narrative_Sentiment"] = central[2]

    # Assign entity states and modifiers
    for entity_name, mapping in ENTITY_MAPPINGS.items():
        present_col = f"Entity_{entity_name}_Present"
        sent_norm_col = f"Entity_{entity_name}_Sentiment_Normalized"

        df[present_col] = df[mapping.prominence].apply(coerce_float).apply(lambda x: is_present(x))
        df[sent_norm_col] = df[mapping.sentiment].apply(coerce_float).apply(normalize_sentiment_weak_collapse)

        def _entity_state_row(row: pd.Series) -> str:
            # Check if state already exists and is not empty
            existing_state = row.get(mapping.state, "")
            if existing_state and str(existing_state).strip() and str(existing_state) not in ["nan", "NaN", ""]:
                return str(existing_state)
            
            # Calculate state if empty or missing
            prom = coerce_float(row.get(mapping.prominence, 0.0))
            sent = coerce_float(row.get(mapping.sentiment, 0.0))
            ent_present = is_present(prom)
            any_narr_present = bool(row.get("Any_Narrative_Present", False))
            gated = gated_sentiment(prom, sent)
            return assign_entity_state(ent_present, any_narr_present, prom, gated)

        def _entity_modifier_row(row: pd.Series) -> str:
            # Check if modifier already exists and is not empty
            existing_modifier = row.get(mapping.modifier, "")
            if existing_modifier and str(existing_modifier).strip() and str(existing_modifier) not in ["nan", "NaN", ""]:
                return str(existing_modifier)
            
            # Calculate modifier if empty or missing
            entity_state = row.get(mapping.state, "")
            if not entity_state:
                entity_state = _entity_state_row(row)

            outlet_score = coerce_float(row.get(OUTLET_SCORE_COL, 0.0))
            prom = coerce_float(row.get(mapping.prominence, 0.0))
            sent = gated_sentiment(prom, coerce_float(row.get(mapping.sentiment, 0.0)))
            topic_present = bool(row.get("Topic_Present", False))
            topic_prom = coerce_float(row.get(TOPIC_PROMINENCE_COL, 0.0))
            topic_sent = gated_sentiment(topic_prom, coerce_float(row.get(TOPIC_SENTIMENT_COL, 0.0)))
            any_narr_present = bool(row.get("Any_Narrative_Present", False))
            central_prom = coerce_float(row.get("Central_Narrative_Prominence", 0.0))
            central_sent = gated_sentiment(central_prom, coerce_float(row.get("Central_Narrative_Sentiment", 0.0)))
            prominent_cnt = int(row.get("prominent_tracked_entities_in_article", 0))

            return assign_entity_modifier(
                entity_state,
                outlet_score,
                prom,
                sent,
                topic_present,
                topic_prom,
                topic_sent,
                any_narr_present,
                central_prom,
                central_sent,
                prominent_cnt,
            )

        df[mapping.state] = df.apply(_entity_state_row, axis=1)
        df[mapping.modifier] = df.apply(_entity_modifier_row, axis=1)

    # Basic validation flags
    def _validation_notes(row: pd.Series) -> str:
        notes: List[str] = []
        # Range checks
        t_prom = coerce_float(row.get(TOPIC_PROMINENCE_COL, 0.0))
        t_sent = coerce_float(row.get(TOPIC_SENTIMENT_COL, 0.0))
        outlet = coerce_float(row.get(OUTLET_SCORE_COL, 0.0))
        if not (0.0 <= t_prom <= 5.0):
            notes.append("topic_prominence_out_of_range")
        if not (-4.0 <= t_sent <= 4.0):
            notes.append("topic_sentiment_out_of_range")
        if outlet and not (1.0 <= outlet <= 5.0):
            notes.append("outlet_score_out_of_range")
        # Count sanity
        tracked = int(row.get("tracked_entities_in_article", 0))
        prominent = int(row.get("prominent_tracked_entities_in_article", 0))
        if prominent > tracked:
            notes.append("prominent_count_exceeds_tracked")
        return ",".join(notes)

    df["validation_notes"] = df.apply(_validation_notes, axis=1)
    df["is_valid_row"] = df["validation_notes"].apply(lambda x: len(str(x).strip()) == 0)

    # Output path
    if "/" in csv_path:
        dirname, filename = csv_path.rsplit("/", 1)
    else:
        dirname, filename = ".", csv_path
    output_path = f"{dirname}/Veritical_Analysis_{filename}"

    df.to_csv(output_path, index=False)
    return output_path


def main():
    parser = argparse.ArgumentParser(description="Orchestra Vertical Analysis Processor")
    parser.add_argument("csv_path", help="Path to the input CSV file")
    args = parser.parse_args()
    output = process(args.csv_path)
    print(output)


if __name__ == "__main__":
    main()


