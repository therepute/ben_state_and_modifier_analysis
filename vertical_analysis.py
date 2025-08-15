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

TOPIC_PROMINENCE_COL = "Topic_Prominence"
TOPIC_SENTIMENT_COL = "Topic_Sentiment"  # first Topic_Sentiment occurrence will be used
TOPIC_STATE_COL = "Topic_State"

OUTLET_SCORE_COL = "Outlet score"
PUB_TIER_COL = "Pub_Tier"
BODY_LENGTH_COL = "Body - Length - Words"

NARRATIVE_TIE_PRECEDENCE: List[str] = [
    "Narrative_Performance",
    "Narrative_Fun",
    "Narrative_Innovation",
    "Narrative_Experience",
    "Narrative_Sustainability",
]

NARRATIVE_MAPPINGS: Dict[str, NarrativeColumnMapping] = {
    "Narrative_Performance": NarrativeColumnMapping(
        description="Narrative_Performance_Description",
        prominence="Narrative_Performance_Prominence",
        sentiment="Narrative_Performance_Sentiment",
        state="Narrative_Performance_State",
    ),
    "Narrative_Fun": NarrativeColumnMapping(
        description="Narrative_Fun_Description",
        prominence="Narrative_Fun_Prominence",
        sentiment="Narrative_Fun_Sentiment",
        state="Narrative_Fun_State",
    ),
    "Narrative_Innovation": NarrativeColumnMapping(
        description="Narrative_Innovation_Description",
        prominence="Narrative_Innovation_Prominence",
        sentiment="Narrative_Innovation_Sentiment",
        state="Narrative_Innovation_State",
    ),
    "Narrative_Experience": NarrativeColumnMapping(
        description="Narrative_Experience_Description",
        prominence="Narrative_Experience_Prominence",
        sentiment="Narrative_Experience_Sentiment",
        state="Narrative_Experience_State",
    ),
    "Narrative_Sustainability": NarrativeColumnMapping(
        description="Narrative_Sustainability_Description",
        prominence="Narrative_Sustainability_Prominence",
        sentiment="Narrative_Sustainability_Sentiment",
        state="Narrative_Sustainability_State",
    ),
}

ENTITY_MAPPINGS: Dict[str, EntityColumnMapping] = {
    # Note: The BMW prominence column is misspelled as "Enity_BMW_Prominence" in the CSV; we honor it here.
    "BMW": EntityColumnMapping(
        quality_score="Entity_BMW_Quality_Score",
        prominence="Enity_BMW_Prominence",
        sentiment="Entity_BMW_Sentiment",
        description="Entity_BMW_Description",
        state="Entity_BMW_State",
        modifier="Entity_BMW_Modifier",
    ),
    "Mercedes": EntityColumnMapping(
        quality_score="Entity_Mercedes_Quality_Score",
        prominence="Entity_Mercedes_Prominence",
        sentiment="Entity_Mercedes_Sentiment",
        description="Entity_Mercedes_Description",
        state="Entity_Mercedes_State",
        modifier="Entity_Mercedes_Modifier",
    ),
    # Audi modifier column appears pluralized in CSV
    "Audi": EntityColumnMapping(
        quality_score="Entity_Audi_Quality_score",
        prominence="Entity_Audi_Prominence",
        sentiment="Entity_Audi_Sentiment",
        description="Entity_Audi_Description",
        state="Entity_Audi_State",
        modifier="Entity_Audi_Modifiers",
    ),
    "Tesla": EntityColumnMapping(
        quality_score="Entity_Tesla_Quality_score",
        prominence="Entity_Tesla_Prominence",
        sentiment="Entity_Tesla_Sentiment",
        description="Entity_Tesla_Description",
        state="Entity_Tesla_State",
        modifier="Entity_Tesla_Modifier",
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
    # Collapse weak sentiment to +/-1 and map true neutral (0) to +1
    if raw_sentiment == 0.0:
        return 1.0
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
        return ""
    # Precedence: High Risk, Risky, Healthy, Ambient Risk, Niche
    if topic_prom >= 2.5 and topic_sent <= -2.0:
        return "High Risk"
    if topic_prom >= 2.0 and topic_sent < 0.0:
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
        return ""
    # Precedence: High Risk, Risky, Healthy, Ambient Risk, Niche
    if narr_prom >= 2.5 and narr_sent <= -2.0:
        return "High Risk"
    if narr_prom >= 2.0 and narr_sent < 0.0:
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
    if topic_present and topic_prom >= 2.0 and topic_sent > 0.0 and not any_narrative_present:
        return "Narrative Drift"
    if topic_present and topic_prom < 2.0 and not any_narrative_present:
        return "Not Relevant"
    return ""


def assign_off_stage_modifier(central_prom: float, narr_sent: float, other_prom_ge_2_0_count: int, any_other_prom_ge_2_5: bool, max_other_prom: float) -> str:
    # Deterministic precedence with explicit Missed Opportunity and prominence gates in negative cases
    if central_prom >= 2.0 and narr_sent < 0.0 and other_prom_ge_2_0_count >= 2:
        return "Guilt by Association"
    if central_prom >= 2.0 and narr_sent < 0.0 and other_prom_ge_2_0_count == 1 and max_other_prom >= 2.5:
        return "Innocent Bystander"
    if narr_sent >= 0.0 and any_other_prom_ge_2_5:
        return "Competitor-Led"
    if central_prom >= 2.5 and narr_sent >= 0.0 and not any_other_prom_ge_2_5:
        return "Missed Opportunity"
    if central_prom >= 2.5 and narr_sent < 0.0 and other_prom_ge_2_0_count == 0:
        return "Reporter-Led Risk"
    return "Overlooked"


def assign_supporting_player_modifier(outlet_score: float, entity_sent: float) -> str:
    # Precedence: Strategic Signal, Check the Box, Low-Heat Visibility, Background Noise
    if outlet_score >= 3 and entity_sent > 2.0:
        return "Strategic Signal"
    if outlet_score < 3 and entity_sent > 2.0:
        return "Check the Box"
    if outlet_score >= 3 and 0.5 <= entity_sent <= 2.0:
        return "Low-Heat Visibility"
    if outlet_score < 3 and 0.5 <= entity_sent <= 2.0:
        return "Background Noise"
    return ""


def assign_under_fire_modifier(entity_prom: float, entity_sent: float, outlet_score: float) -> str:
    # Precedence: High-Stakes Takedown, Body Blow, Bumps & Bruises, Stinger, Soft Target, Peripheral Hit
    # HST now requires outlet_score == 5 (word count bonus collapses into score)
    if entity_prom >= 3.0 and entity_sent <= -2.0 and outlet_score == 5:
        return "High-Stakes Takedown"
    if entity_prom >= 3.0 and entity_sent <= -2.0 and outlet_score < 5:
        return "Body Blow"
    if 2.0 <= entity_prom < 3.0 and entity_sent <= -2.0:
        return "Bumps & Bruises"
    # Stinger (Option B adjusted): prom >= 2.0 AND sent <= -2.0 AND not Body Blow/HST (handled above)
    if entity_prom >= 2.0 and entity_sent <= -2.0:
        return "Stinger"
    if entity_prom >= 2.0 and -2.0 < entity_sent < 0.0:
        return "Soft Target"
    if entity_prom < 2.0 and -3.0 < entity_sent < 0.0:
        return "Peripheral Hit"
    return ""


def assign_leader_modifier(entity_prom: float, entity_sent: float, outlet_score: float) -> str:
    # Precedence: Breakthrough Coverage, Great Story, Good Story, Procedurally Positive
    if entity_prom >= 4.0 and entity_sent >= 3.0 and outlet_score >= 4:
        return "Breakthrough Coverage"
    if entity_prom >= 3.0 and entity_sent >= 2.0 and outlet_score >= 3:
        return "Great Story"
    if entity_prom >= 3.0 and (
        (entity_sent >= 1.0 and outlet_score >= 3) or (entity_sent >= 0.0 and outlet_score < 3)
    ):
        return "Good Story"
    if entity_prom >= 3.0 and entity_sent >= 0.0:
        return "Procedurally Positive"
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
    other_prom_ge_2_0_count: int,
    any_other_prom_ge_2_5: bool,
    body_length_words: float,
    max_other_prom: float,
) -> str:
    if entity_state == "Absent":
        return assign_absent_modifier(topic_present, topic_prom, topic_sent, any_narrative_present)
    if entity_state == "Off-Stage":
        return assign_off_stage_modifier(
            central_narr_prom,
            central_narr_sent,
            int(other_prom_ge_2_0_count),
            bool(any_other_prom_ge_2_5),
            max_other_prom,
        )
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

    # Use the first Topic_Sentiment column if duplicated
    if TOPIC_SENTIMENT_COL not in df.columns:
        # Attempt to locate any columns starting with the same name
        topic_sent_cols = [c for c in df.columns if c.startswith("Topic_Sentiment")]
        if topic_sent_cols:
            df[TOPIC_SENTIMENT_COL] = df[topic_sent_cols[0]]
        else:
            df[TOPIC_SENTIMENT_COL] = 0.0

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
            prom = coerce_float(row.get(mapping.prominence, 0.0))
            sent = coerce_float(row.get(mapping.sentiment, 0.0))
            narr_present = is_present(prom)
            gated_sent = gated_sentiment(prom, sent)
            return assign_narrative_state(narr_present, prom, gated_sent)

        df[mapping.state] = df.apply(_narr_state_row, axis=1)

    df["Any_Narrative_Present"] = (
        df[[NARRATIVE_MAPPINGS[k].prominence for k in NARRATIVE_TIE_PRECEDENCE]]
        .applymap(coerce_float)
        .gt(0.0)
        .any(axis=1)
    )

    # Topic state assignment (gate sentiment by presence)
    def _topic_state_row(row: pd.Series) -> str:
        prom = coerce_float(row.get(TOPIC_PROMINENCE_COL, 0.0))
        sent = coerce_float(row.get(TOPIC_SENTIMENT_COL, 0.0))
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
            prom = coerce_float(row.get(mapping.prominence, 0.0))
            sent = coerce_float(row.get(mapping.sentiment, 0.0))
            ent_present = is_present(prom)
            any_narr_present = bool(row.get("Any_Narrative_Present", False))
            gated = gated_sentiment(prom, sent)
            return assign_entity_state(ent_present, any_narr_present, prom, gated)

        def _entity_modifier_row(row: pd.Series) -> str:
            entity_state = row.get(mapping.state, "")
            if not entity_state:
                entity_state = _entity_state_row(row)

            outlet_score = coerce_float(row.get(OUTLET_SCORE_COL, 0.0))
            prom = coerce_float(row.get(mapping.prominence, 0.0))
            # Supporting Player fallback: prefer raw sentiment; if NaN, fall back to normalized.
            raw_sent_val = row.get(mapping.sentiment, None)
            sent_val = coerce_float(raw_sent_val)
            if pd.isna(raw_sent_val):
                sent_val = coerce_float(row.get(sent_norm_col, 0.0))
            sent = gated_sentiment(prom, sent_val)
            topic_present = bool(row.get("Topic_Present", False))
            topic_prom = coerce_float(row.get(TOPIC_PROMINENCE_COL, 0.0))
            topic_sent = gated_sentiment(topic_prom, coerce_float(row.get(TOPIC_SENTIMENT_COL, 0.0)))
            any_narr_present = bool(row.get("Any_Narrative_Present", False))
            central_sent = coerce_float(row.get("Central_Narrative_Sentiment", 0.0))
            central_prom = coerce_float(row.get("Central_Narrative_Prominence", 0.0))
            # Build peer counts excluding self for Off-Stage logic
            other_prom_ge_2_0 = 0
            any_other_prom_ge_2_5 = False
            max_other_prom = 0.0
            for peer_name, peer_map in ENTITY_MAPPINGS.items():
                if peer_name == entity_name:
                    continue
                peer_prom = coerce_float(row.get(peer_map.prominence, 0.0))
                if peer_prom >= 2.0:
                    other_prom_ge_2_0 += 1
                if peer_prom >= 2.5:
                    any_other_prom_ge_2_5 = True
                if peer_prom > max_other_prom:
                    max_other_prom = peer_prom
            body_len = coerce_float(row.get(BODY_LENGTH_COL, 0.0))

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
                other_prom_ge_2_0,
                any_other_prom_ge_2_5,
                body_len,
                max_other_prom,
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


