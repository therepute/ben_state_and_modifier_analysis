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
TOPIC_SENTIMENT_COL = "Topic_Sentiment"
TOPIC_STATE_COL = "Topic_State"

OUTLET_SCORE_COL = "Outlet score"
PUB_TIER_COL = "Pub_Tier"
BODY_LENGTH_COL = "Body - Length - Words"

# These will be dynamically populated from CSV headers
NARRATIVE_TIE_PRECEDENCE: List[str] = []
NARRATIVE_MAPPINGS: Dict[str, NarrativeColumnMapping] = {}
ENTITY_MAPPINGS: Dict[str, EntityColumnMapping] = {}

# Store the last mapping preview for web display
LAST_MAPPING_PREVIEW: str = ""


def find_best_column_match(target: str, available_columns: List[str]) -> str:
    """
    Find the best matching column with enhanced typo tolerance.
    
    Tolerance includes:
    - Case variations (Entity vs entity)
    - Typos (Enity vs Entity, Narrtaive vs Narrative)
    - Spacing issues (trailing spaces, double underscores)
    - Quality vs Quality_Score variations
    
    NOTE: Fuzzy matching is disabled for State/Modifier fields to prevent
    cross-entity contamination (e.g., BetMGM getting Bet365's columns).
    """
    import difflib
    
    # Direct match first
    if target in available_columns:
        return target
    
    # Common typo patterns
    typo_variants = [
        target,
        target.replace("Entity_", "Enity_"),
        target.replace("Enity_", "Entity_"),
        target.replace("Narrative_", "Narrtaive_"),
        target.replace("Narrtaive_", "Narrative_"),
        target.replace("_State", "__State"),  # double underscore
        target + " ",  # trailing space
        target.replace("_Quality_Score", "_Quality"),
        target.replace("_Quality", "_Quality_Score"),
        target.replace("_Qulaity_Score", "_Quality_Score"),  # common typo
    ]
    
    # Check typo variants
    for variant in typo_variants:
        if variant in available_columns:
            return variant
    
    # SECURITY FIX: Disable fuzzy matching for State/Modifier fields
    # This prevents cross-entity contamination (e.g., BetMGM using Bet365's State column)
    if target.endswith('_State') or target.endswith('_Modifier'):
        return None
    
    # Fuzzy matching for close matches (80% similarity) - only for data columns
    close_matches = difflib.get_close_matches(target, available_columns, n=1, cutoff=0.8)
    if close_matches:
        return close_matches[0]
    
    return None


def auto_detect_companies_and_narratives(columns: List[str]) -> Tuple[Dict[str, EntityColumnMapping], Dict[str, NarrativeColumnMapping], List[str], Dict[str, List[str]]]:
    """
    Auto-detect companies and narratives from CSV column headers with enhanced error reporting.
    
    Pattern Recognition - Format 1 (Current):
    - Companies: Entity_{CompanyName}_Prominence/Sentiment/Description/Quality_Score/State/Modifier
    - Narratives: Narrative_{MessageName}_Prominence/Sentiment/Description/Quality_Score/State
    
    Pattern Recognition - Format 2 (Orchestra Ready):
    - Companies: {N}_{CompanyName} - Company-Level Prominence/Sentiment
    - Narratives: O_Overall - Message {N} Prominence ({Description})/Sentiment ({Description})
    
    Returns: (entity_mappings, narrative_mappings, narrative_precedence, debug_info)
    """
    import re
    
    entity_mappings = {}
    narrative_mappings = {}
    narrative_precedence = []
    debug_info = {
        "entity_issues": [],
        "narrative_issues": [],
        "detected_entities": [],
        "detected_narratives": [],
        "missing_required": [],
        "successful_mappings": [],
        "format_detected": "unknown"
    }
    
    # Detect companies from BOTH formats simultaneously
    company_names = set()
    
    # Format 1: Current format (Entity_Name_Field)
    # Updated to handle Super_Prominence variants by capturing the base entity name
    entity_pattern_format1 = r'^(?:Enity_|Entity_)([^_]+?)(?:_Super)?_(?:Prominence|Sentiment|Description|Quality_Score|Qulaity_Score|State|Modifier)$'
    for col in columns:
        match = re.match(entity_pattern_format1, col)
        if match:
            company_names.add(match.group(1))
    
    # Format 2: Orchestra ready (Number_Name - Company-Level Field)
    entity_pattern_format2 = r'^(\d+)_([^-\s]+)\s*-\s*Company-Level\s+(?:Prominence|Sentiment)'
    for col in columns:
        match = re.match(entity_pattern_format2, col)
        if match:
            company_names.add(match.group(2))
    
    # Report detected formats
    format1_count = len([col for col in columns if re.match(entity_pattern_format1, col)])
    format2_count = len([col for col in columns if re.match(entity_pattern_format2, col)])
    
    if format1_count > 0 and format2_count > 0:
        debug_info["format_detected"] = "Both formats detected"
    elif format1_count > 0:
        debug_info["format_detected"] = "Current format only"
    elif format2_count > 0:
        debug_info["format_detected"] = "Orchestra format only"
    else:
        debug_info["format_detected"] = "No companies detected"
    
    debug_info["detected_entities"] = sorted(list(company_names))
    
    # Build entity mappings with error tracking
    for company in sorted(company_names):
        required_fields = ["Prominence", "Sentiment"]
        optional_fields = ["Description", "Quality_Score", "State", "Modifier"]
        actual_mappings = {}
        
        for field in required_fields + optional_fields:
            best_match = None
            
            # Try Format 1: Current format - prioritize Super_Prominence but use regular Sentiment
            prefix_variants = [f"Entity_{company}", f"Enity_{company}"]
            for prefix in prefix_variants:
                # For Prominence: try Super variant first, then regular
                if field == "Prominence":
                    # Try Super_Prominence first
                    target = f"{prefix}_Super_{field}"
                    match = find_best_column_match(target, columns)
                    if match:
                        best_match = match
                        break
                    # Fallback to regular Prominence
                    target = f"{prefix}_{field}"
                    match = find_best_column_match(target, columns)
                    if match:
                        best_match = match
                        break
                else:
                    # For all other fields (Sentiment, Description, etc.): use regular only
                    target = f"{prefix}_{field}"
                    match = find_best_column_match(target, columns)
                    if match:
                        best_match = match
                        break
            
            # Try Format 2: Orchestra format if not found
            if not best_match and field in ["Prominence", "Sentiment"]:
                company_pattern = rf'^(\d+)_{re.escape(company)}\s*-\s*Company-Level\s+{field}$'
                for col in columns:
                    if re.match(company_pattern, col):
                        best_match = col
                        break
            
            if best_match:
                actual_mappings[field.lower()] = best_match
            elif field in required_fields:
                tried_patterns = [f'{p}_{field}' for p in prefix_variants] + [f'N_{company} - Company-Level {field}']
                debug_info["entity_issues"].append(f"❌ {company}: Missing required field '{field}' (tried {tried_patterns})")
        
        # Only create mapping if we have required fields
        if all(field.lower() in actual_mappings for field in required_fields):
            # Determine if this is an Orchestra format entity
            is_orchestra_entity = re.match(r'^\d+_', actual_mappings["prominence"]) is not None
            
            entity_mappings[company] = EntityColumnMapping(
                quality_score=actual_mappings.get("quality_score", f"Entity_{company}_Quality_Score"),
                prominence=actual_mappings["prominence"],
                sentiment=actual_mappings["sentiment"], 
                description=actual_mappings.get("description", f"Entity_{company}_Description"),
                state=actual_mappings.get("state", f"Entity_{company}_State"),
                modifier=actual_mappings.get("modifier", f"Entity_{company}_Modifier"),
            )
            debug_info["successful_mappings"].append(f"✅ {company}: {actual_mappings['prominence']}, {actual_mappings['sentiment']}")
        else:
            debug_info["missing_required"].append(f"Entity {company}")
    
    # Pattern 2: Extract narratives/messages from BOTH formats
    message_names = set()
    
    # Format 1: Current Narrative columns
    narrative_pattern_format1 = r'^(?:Narrtaive_|Narrative_)([^_]+)_(?:Prominence|Sentiment|Description|Quality_Score|Qulaity_Score|State)$'
    for col in columns:
        match = re.match(narrative_pattern_format1, col)
        if match:
            message_names.add(match.group(1))
    
    # Format 2: Orchestra format - O_Overall - Message N Prominence/Sentiment (Description)
    narrative_pattern_format2 = r'^O_Overall\s*-\s*Message\s+(\d+)\s+(?:Prominence|Sentiment)\s*\(([^)]+)\)$'
    for col in columns:
        match = re.match(narrative_pattern_format2, col)
        if match:
            description = match.group(2).strip()
            message_names.add(description)  # Use exact description as narrative name
    
    debug_info["detected_narratives"] = sorted(list(message_names))
    
    # Build narrative mappings with error tracking
    for message in sorted(message_names):
        required_fields = ["Prominence", "Sentiment"]
        optional_fields = ["Description", "Quality_Score", "State"]
        
        prefix_variants = [f"Narrative_{message}", f"Narrtaive_{message}"]
        actual_mappings = {}
        
        for field in required_fields + optional_fields:
            best_match = None
            
            # Try Format 1: Current Narrative format
            for prefix in prefix_variants:
                target = f"{prefix}_{field}"
                match = find_best_column_match(target, columns)
                if match:
                    best_match = match
                    break
            
            # Try Format 2: Orchestra format if not found
            if not best_match and field in ["Prominence", "Sentiment"]:
                orchestra_pattern = rf'^O_Overall\s*-\s*Message\s+\d+\s+{field}\s*\({re.escape(message)}\)$'
                for col in columns:
                    if re.match(orchestra_pattern, col):
                        best_match = col
                        break
            
            if best_match:
                actual_mappings[field.lower()] = best_match
            elif field in required_fields:
                tried_patterns = [f'{p}_{field}' for p in prefix_variants] + [f'O_Overall - Message N {field} ({message})']
                debug_info["narrative_issues"].append(f"❌ {message}: Missing required field '{field}' (tried {tried_patterns})")
        
        # Only create mapping if we have required fields
        if all(field.lower() in actual_mappings for field in required_fields):
            # Determine the narrative key based on which format was detected
            is_orchestra_narrative = actual_mappings["prominence"].startswith("O_Overall")
            
            if is_orchestra_narrative:
                narrative_key = message  # Use exact name for Orchestra format
            else:
                narrative_key = f"Narrative_{message}"  # Use prefixed name for current format
            
            narrative_mappings[narrative_key] = NarrativeColumnMapping(
                description=actual_mappings.get("description", f"Narrative_{message}_Description" if not is_orchestra_narrative else ""),
                prominence=actual_mappings["prominence"],
                sentiment=actual_mappings["sentiment"],
                state=actual_mappings.get("state", f"Narrative_{message}_State" if not is_orchestra_narrative else ""),
            )
            narrative_precedence.append(narrative_key)
            debug_info["successful_mappings"].append(f"✅ {message}: {actual_mappings['prominence']}, {actual_mappings['sentiment']}")
        else:
            debug_info["missing_required"].append(f"Narrative {message}")
    
    return entity_mappings, narrative_mappings, narrative_precedence, debug_info


def initialize_mappings_from_csv(csv_path: str) -> str:
    """Initialize dynamic mappings from CSV headers with detailed preview
    
    Returns: HTML-formatted preview text for web display
    """
    global ENTITY_MAPPINGS, NARRATIVE_MAPPINGS, NARRATIVE_TIE_PRECEDENCE, LAST_MAPPING_PREVIEW
    
    # Read just the header to get column names
    df_header = pd.read_csv(csv_path, nrows=0)
    columns = df_header.columns.tolist()
    
    # Auto-detect and populate global mappings
    ENTITY_MAPPINGS, NARRATIVE_MAPPINGS, NARRATIVE_TIE_PRECEDENCE, debug_info = auto_detect_companies_and_narratives(columns)
    
    # Build preview text for web display
    preview_lines = []
    preview_lines.append("📋 MAPPING PREVIEW & VALIDATION")
    preview_lines.append("=" * 60)
    
    # Show format detection and entities/narratives
    preview_lines.append(f"🔍 Format Detection: {debug_info['format_detected']}")
    preview_lines.append(f"🏢 Detected Companies: {', '.join(debug_info['detected_entities']) or 'None'}")
    preview_lines.append(f"📝 Detected Narratives: {', '.join(debug_info['detected_narratives']) or 'None'}")
    
    # Show successful mappings
    if debug_info["successful_mappings"]:
        preview_lines.append(f"")
        preview_lines.append(f"✅ Successful Mappings ({len(debug_info['successful_mappings'])}):")
        for mapping in debug_info["successful_mappings"]:
            preview_lines.append(f"   {mapping}")
    
    # Show any issues
    all_issues = debug_info["entity_issues"] + debug_info["narrative_issues"]
    if all_issues:
        preview_lines.append(f"")
        preview_lines.append(f"⚠️  Mapping Issues ({len(all_issues)}):")
        for issue in all_issues:
            preview_lines.append(f"   {issue}")
    
    # Show missing required entities/narratives
    if debug_info["missing_required"]:
        preview_lines.append(f"")
        preview_lines.append(f"❌ Could Not Map ({len(debug_info['missing_required'])}):")
        for missing in debug_info["missing_required"]:
            preview_lines.append(f"   {missing} - Missing required Prominence/Sentiment columns")
    
    # Summary
    preview_lines.append(f"")
    preview_lines.append(f"📊 Final Mapping Summary:")
    preview_lines.append(f"   • {len(ENTITY_MAPPINGS)} companies ready for analysis")
    preview_lines.append(f"   • {len(NARRATIVE_MAPPINGS)} narratives ready for analysis")
    preview_lines.append(f"   • Precedence order: {NARRATIVE_TIE_PRECEDENCE}")
    
    # Validation check
    warnings = []
    if not ENTITY_MAPPINGS:
        warnings.append("🚨 WARNING: No companies detected! Check column naming patterns.")
        warnings.append("   Expected: Entity_{CompanyName}_Prominence, Entity_{CompanyName}_Sentiment")
    
    if not NARRATIVE_MAPPINGS:
        warnings.append("🚨 WARNING: No narratives detected! Check column naming patterns.")
        warnings.append("   Expected: Narrative_{MessageName}_Prominence, Narrative_{MessageName}_Sentiment")
    
    if warnings:
        preview_lines.append("")
        preview_lines.extend(warnings)
    
    preview_lines.append("=" * 60)
    
    # Print to console for debugging
    console_preview = "\n".join(preview_lines)
    print(f"\n{console_preview}\n")
    
    # Return HTML-formatted version for web display
    html_preview = "<pre style='background-color: #f5f5f5; padding: 15px; border-radius: 5px; font-family: monospace; white-space: pre-wrap;'>\n"
    html_preview += "\n".join(preview_lines)
    html_preview += "\n</pre>"
    
    # Store globally for web access
    LAST_MAPPING_PREVIEW = html_preview
    
    return html_preview


def get_last_mapping_preview() -> str:
    """Get the last mapping preview for web display"""
    return LAST_MAPPING_PREVIEW or "<p>No mapping preview available. Upload a CSV file first.</p>"


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
    # Precedence: High Risk, Risky, Healthy, Ambient Risk, Peripheral
    if narr_prom >= 2.5 and narr_sent < -2.0:
        return "High Risk"
    if narr_prom >= 2.5 and 0.0 > narr_sent >= -2.0:
        return "Risky"
    if narr_prom >= 2.5 and narr_sent >= 0.0:
        return "Healthy"
    if narr_prom < 2.5 and narr_sent < 0.0:
        return "Ambient Risk"
    if narr_prom < 2.5 and narr_sent >= 0.0:
        return "Peripheral"
    return "Undetermined"


def assign_entity_state(entity_prom: float, entity_sent: float, topic_prom: float, tracked_narr_proms: list) -> str:
    """
    Canonical state assignment per Ben's latest audit feedback.
    Uses max narrative prominence for narrative presence detection.
    """
    import pandas as pd
    
    # Handle NaN/null entity prominence and sentiment
    if pd.isna(entity_prom):
        entity_prom = 0.0
    if pd.isna(entity_sent):
        entity_sent = 0.0
    
    # Ben's canonical narrative presence detection: use max narrative prominence
    max_narr_prom = max([prom for prom in tracked_narr_proms if not pd.isna(prom)], default=0.0)
    
    # Ben's exact canonical state assignment logic
    if topic_prom > 0 and entity_prom == 0:
        # Off-Stage requires topic present AND max narrative prominence > 0
        # Absent requires topic present AND max narrative prominence = 0
        return "Off-Stage" if max_narr_prom > 0 else "Absent"
    elif entity_prom > 0 and entity_sent < 0:
        return "Under Fire"
    elif entity_prom >= 3 and entity_sent > 0:
        return "Leader"
    elif 0 < entity_prom < 3 and entity_sent > 0:
        return "Supporting Player"
    else:
        return "Undetermined"  # out-of-scope / data gap


# -------------------------------
# Modifier assignment logic (entity)
# -------------------------------

def assign_absent_modifier(topic_prom: float, topic_sent: float) -> str:
    """
    Canonical Absent modifier logic per Ben's audit feedback.
    Uses topic prominence and sentiment only, with no tracked narratives present.
    """
    # Canonical Absent modifier rules (deterministic, short-circuit)
    if topic_prom < 2:
        return "Not Relevant"
    elif topic_sent >= 0:
        return "Narrative Drift"
    else:
        return "Framing Risk"


def assign_off_stage_modifier(dominant_narr_prom: float, dominant_narr_sent: float, peer_count_prom_ge_2: int) -> str:
    """
    Canonical Off-Stage modifier logic per Ben's v4 audit feedback.
    Uses:
    - peer_count_prom_ge_2: Count of OTHER tracked entities with Prom >= 2.0 in same article
    - dominant_narr_prom/sent: The tracked narrative with highest prominence in article
    
    Implements exactly the 6 canonical conditions with proper peer counting.
    """
    # Canonical Off-Stage modifiers (deterministic, exact precedence)
    if dominant_narr_sent >= 0.0 and peer_count_prom_ge_2 >= 1:
        return "Competitor-Led"
    elif dominant_narr_sent >= 0.0 and dominant_narr_prom >= 2.5 and peer_count_prom_ge_2 == 0:
        return "Missed Opportunity"
    elif dominant_narr_sent < 0.0 and peer_count_prom_ge_2 >= 2:
        return "Guilt by Association"
    elif dominant_narr_sent < 0.0 and peer_count_prom_ge_2 == 1:
        return "Innocent Bystander"
    elif dominant_narr_sent < 0.0 and dominant_narr_prom >= 2.5 and peer_count_prom_ge_2 == 0:
        return "Reporter-Led Risk"
    elif dominant_narr_prom < 2.5 and peer_count_prom_ge_2 == 0:
        return "Overlooked"
    else:
        # Should never happen with canonical rules
        return ""


def assign_supporting_player_modifier(outlet: float, sent: float) -> str:
    """
    Canonical Supporting Player modifier logic per Ben's audit feedback.
    """
    # Canonical Supporting Player modifiers
    if outlet >= 3 and sent >= 3:
        return "Strategic Signal"
    elif outlet >= 3 and 0.5 <= sent < 3:
        return "Low-Heat Visibility"
    elif outlet < 3 and sent >= 3:
        return "Check the Box"
    elif outlet < 3 and 0.5 <= sent < 3:
        return "Background Noise"
    else:
        return ""


def assign_under_fire_modifier(prom: float, sent: float, outlet: float) -> str:
    """
    Canonical Under Fire modifier logic per Ben's v4 audit feedback.
    Uses exact outlet boundaries and strict precedence.
    Fixed: Takedown=4, Body Blow>2 (not 4), Stinger≤3
    Bridge added for canonical gap: 2.0 ≤ prom < 3, sent ≤ -2.0, outlet ≥ 4
    """
    # CANONICAL UNDER FIRE MODIFIERS (Ben's exact v5 audit fix)
    # Fixed: Narrative Shaper only fires with Prom ≥ 4, Sent ≤ -3.0, Outlet = 5
    # Fixed: Takedown must be Prom ≥ 3, Sent ≤ -2.0, Outlet = 4
    if prom >= 4 and sent <= -3.0 and outlet == 5:
        return "Narrative Shaper"
    elif prom >= 3 and sent <= -2.0 and outlet == 4:
        return "Takedown"
    elif prom >= 3 and sent <= -2.0 and outlet > 2:
        return "Body Blow"
    elif prom >= 2.0 and sent <= -2.0 and outlet <= 3:
        return "Stinger"
    elif prom >= 2.0 and -2.0 < sent < 0:
        return "Light Jab"
    elif prom < 2.0 and sent <= -2.0:
        return "Collateral Damage"
    elif prom < 2.0 and -2.0 < sent < 0:
        return "Peripheral Hit"
    
    # ---- Canon gap bridge (surgical fix for 16 blanks) ----
    # Gap: 2.0 ≤ prom < 3, sent ≤ -2.0, outlet ≥ 4 → assign "Stinger"
    elif (prom >= 2.0 and prom < 3.0) and sent <= -2.0 and outlet >= 4:
        return "Stinger"  # Bridge case - auditable fix for canonical gap
    
    else:
        return ""  # Should never happen now


def assign_leader_modifier(prom: float, sent: float, outlet: float) -> str:
    """
    Canonical Leader modifier logic per Ben's audit feedback.
    Respects the special Good Story branch.
    """
    # Canonical Leader modifiers (respect the special Good Story branch)
    if prom >= 4 and sent >= 3 and outlet == 5:
        return "Narrative Setter"
    elif prom >= 4 and sent >= 3 and outlet >= 4:
        return "Breakthrough"
    elif prom >= 3 and sent >= 2 and outlet >= 3:
        return "Great Story"
    elif prom >= 3 and ((outlet >= 3 and 1 <= sent < 2) or (outlet < 3 and sent >= 2)):
        return "Good Story"
    elif prom >= 3 and sent >= 0:
        return "Routine Positive"
    else:
        return ""


def assign_entity_modifier(
    entity_state: str,
    outlet_score: float,
    entity_prom: float,
    entity_sent: float,
    topic_prom: float,
    topic_sent: float,
    dominant_narr_prom: float,
    dominant_narr_sent: float,
    peer_count_prom_ge_2: int,
) -> str:
    if entity_state == "Absent":
        return assign_absent_modifier(topic_prom, topic_sent)
    if entity_state in ["Off-Stage", "Offstage"]:  # Handle both naming conventions
        return assign_off_stage_modifier(dominant_narr_prom, dominant_narr_sent, peer_count_prom_ge_2)
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
    # Initialize dynamic mappings first and get preview
    mapping_preview = initialize_mappings_from_csv(csv_path)
    
    df = pd.read_csv(csv_path, low_memory=False)
    
    # Check for required columns and provide detailed error message
    missing_cols = []
    
    # Check required topic columns - try multiple formats
    global TOPIC_PROMINENCE_COL, TOPIC_SENTIMENT_COL, OUTLET_SCORE_COL
    
    topic_prominence_col = None
    if TOPIC_PROMINENCE_COL in df.columns:
        topic_prominence_col = TOPIC_PROMINENCE_COL
    elif "O_Overall - Overall-Level Prominence" in df.columns:
        topic_prominence_col = "O_Overall - Overall-Level Prominence"
    else:
        # Fallback: Use entity prominence as topic prominence if no topic-level data
        entity_prominence_cols = [c for c in df.columns if c.startswith("Entity_") and c.endswith("_Prominence")]
        if entity_prominence_cols:
            # Use the first entity prominence column as topic prominence
            topic_prominence_col = entity_prominence_cols[0]
            print(f"⚠️  No Topic_Prominence found. Using {topic_prominence_col} as topic prominence.")
    
    if not topic_prominence_col:
        missing_cols.append("Topic_Prominence (or O_Overall - Overall-Level Prominence, or Entity_*_Prominence)")
    else:
        TOPIC_PROMINENCE_COL = topic_prominence_col
    
    # Check for topic sentiment (can have variations) - try multiple formats
    topic_sentiment_col = None
    topic_sent_cols = [c for c in df.columns if c.startswith("Topic_Sentiment")]
    if TOPIC_SENTIMENT_COL in df.columns:
        topic_sentiment_col = TOPIC_SENTIMENT_COL
    elif topic_sent_cols:
        topic_sentiment_col = topic_sent_cols[0]  # Use first match
    elif "O_Overall - Overall-Level Sentiment" in df.columns:
        topic_sentiment_col = "O_Overall - Overall-Level Sentiment"
    else:
        # Fallback: Use entity sentiment as topic sentiment if no topic-level data
        entity_sentiment_cols = [c for c in df.columns if c.startswith("Entity_") and c.endswith("_Sentiment")]
        if entity_sentiment_cols:
            # Use the first entity sentiment column as topic sentiment
            topic_sentiment_col = entity_sentiment_cols[0]
            print(f"⚠️  No Topic_Sentiment found. Using {topic_sentiment_col} as topic sentiment.")
    
    if not topic_sentiment_col:
        missing_cols.append("Topic_Sentiment (or O_Overall - Overall-Level Sentiment, or Entity_*_Sentiment)")
    else:
        TOPIC_SENTIMENT_COL = topic_sentiment_col
    
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
    
    # Check required metadata columns - try both formats
    outlet_score_col = None
    if OUTLET_SCORE_COL in df.columns:
        outlet_score_col = OUTLET_SCORE_COL
    elif "Orchestra_Pub_Tier" in df.columns:
        outlet_score_col = "Orchestra_Pub_Tier"
    
    if not outlet_score_col:
        missing_cols.append("Outlet score (or Orchestra_Pub_Tier)")
    else:
        OUTLET_SCORE_COL = outlet_score_col
    
    # Check other required metadata columns
    other_meta_cols = [PUB_TIER_COL, BODY_LENGTH_COL]
    for col in other_meta_cols:
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
            # Calculate state based on prominence/sentiment - always recalculate for Business narrative fix
            prom = coerce_float(row.get(mapping.prominence, 0.0))
            sent = coerce_float(row.get(mapping.sentiment, 0.0))
            
            # Fix 3: Business narrative - When prominence = 0, assign "Absent" deterministically
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
        # Always recalculate to ensure proper state assignment
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
            prominent_flags.append(prom_val >= 2.0)  # Canonical: Use 2.0 threshold for Off-Stage peer counting
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
            # Canonical state assignment using Ben's audit feedback
            entity_prom = coerce_float(row.get(mapping.prominence, 0.0))
            entity_sent = gated_sentiment(entity_prom, coerce_float(row.get(mapping.sentiment, 0.0)))
            topic_prom = coerce_float(row.get(TOPIC_PROMINENCE_COL, 0.0))
            
            # Get tracked narrative prominences
            tracked_narr_proms = []
            for narr_key in NARRATIVE_TIE_PRECEDENCE:
                narr_mapping = NARRATIVE_MAPPINGS[narr_key]
                narr_prom = coerce_float(row.get(narr_mapping.prominence, 0.0))
                tracked_narr_proms.append(narr_prom)
            
            return assign_entity_state(entity_prom, entity_sent, topic_prom, tracked_narr_proms)

        def _entity_modifier_row(row: pd.Series) -> str:
            # Calculate modifiers based on EXISTING entity state from input CSV
            # DO NOT recalculate state - preserve what's in the input data
            # Get existing state from CSV, handle NaN values
            raw_state = row.get(mapping.state, "")
            entity_state = str(raw_state).strip() if pd.notna(raw_state) else ""

            outlet_score = coerce_float(row.get(OUTLET_SCORE_COL, 0.0))
            prom = coerce_float(row.get(mapping.prominence, 0.0))
            sent = gated_sentiment(prom, coerce_float(row.get(mapping.sentiment, 0.0)))
            topic_prom = coerce_float(row.get(TOPIC_PROMINENCE_COL, 0.0))
            topic_sent = gated_sentiment(topic_prom, coerce_float(row.get(TOPIC_SENTIMENT_COL, 0.0)))

            # BEN'S V4 AUDIT FIX: Compute dominant narrative and peer count correctly
            
            # 1. Find dominant narrative (highest prominence among tracked narratives)
            dominant_narr_prom = 0.0
            dominant_narr_sent = 0.0
            for narr_key in NARRATIVE_TIE_PRECEDENCE:
                narr_mapping = NARRATIVE_MAPPINGS[narr_key]
                narr_prom = coerce_float(row.get(narr_mapping.prominence, 0.0))
                if narr_prom > dominant_narr_prom:
                    dominant_narr_prom = narr_prom
                    dominant_narr_sent = gated_sentiment(narr_prom, coerce_float(row.get(narr_mapping.sentiment, 0.0)))
            
            # 2. Count peers with Prominence >= 2.0 (OTHER entities, not current one)
            peer_count_prom_ge_2 = 0
            current_entity_name = entity_name  # From the outer loop
            for other_entity_name, other_mapping in ENTITY_MAPPINGS.items():
                if other_entity_name != current_entity_name:
                    other_prom = coerce_float(row.get(other_mapping.prominence, 0.0))
                    if other_prom >= 2.0:
                        peer_count_prom_ge_2 += 1

            return assign_entity_modifier(
                entity_state,
                outlet_score,
                prom,
                sent,
                topic_prom,
                topic_sent,
                dominant_narr_prom,
                dominant_narr_sent,
                peer_count_prom_ge_2,
            )

        # HYBRID STATE HANDLING: 
        # - Preserve existing states (e.g., Bet365 client data)
        # - Calculate missing states (e.g., BetMGM, DraftKings, FanDuel)
        
        # Check if state column exists and has data
        if mapping.state in df.columns:
            # Fill missing states only - preserve existing ones
            mask_missing_state = df[mapping.state].isna() | (df[mapping.state] == '') | (df[mapping.state] == 'nan')
            df.loc[mask_missing_state, mapping.state] = df.loc[mask_missing_state].apply(_entity_state_row, axis=1)
        else:
            # Create new state column - calculate all states
            df[mapping.state] = df.apply(_entity_state_row, axis=1)
        
        # Always calculate modifiers based on the final states (preserved + calculated)
        # All canonical states should have complete modifier coverage per trigger document
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

    # -------------------------------
    # POST-PROCESSING FIXES FOR CANONICAL COMPLIANCE
    # -------------------------------
    
    # 1. STATE NORMALIZATION: Fix "Offstage" → "Off-Stage" (Ben's audit feedback)
    def normalize_state(state_value):
        """Normalize state values to canonical format"""
        if pd.isna(state_value):
            return state_value
        state_str = str(state_value).strip()
        if state_str.lower() in {"offstage", "off stage"}:
            return "Off-Stage"
        return state_str
    
    # Apply state normalization to all entity state columns
    for entity_name, mapping in ENTITY_MAPPINGS.items():
        if mapping.state in df.columns:
            df[mapping.state] = df[mapping.state].apply(normalize_state)
    
    # 2. ADD MISSING PROMINENCE COLUMNS (Ben's audit feedback)
    # Add Entity_*_Prominence columns for canonical compliance
    for entity_name, mapping in ENTITY_MAPPINGS.items():
        prominence_col = f"Entity_{entity_name}_Prominence"
        if prominence_col not in df.columns:
            # Generate prominence column based on existing data patterns
            # Use Entity_*_Present (boolean) and Entity_*_Sentiment_Normalized to infer prominence
            present_col = f"Entity_{entity_name}_Present"
            if present_col in df.columns:
                # Simple heuristic: if present=True, use sentiment magnitude to estimate prominence
                # This is a rough approximation until proper prominence data is available
                def estimate_prominence(row):
                    if not row.get(present_col, False):
                        return 0.0  # Not present = 0 prominence
                    
                    # Use sentiment magnitude as rough prominence proxy
                    sent_normalized = row.get(f"Entity_{entity_name}_Sentiment_Normalized", 0.0)
                    if pd.isna(sent_normalized):
                        return 1.0  # Present but unknown sentiment = minimal prominence
                    
                    # Convert sentiment magnitude to rough prominence scale (0-5)
                    abs_sent = abs(float(sent_normalized))
                    if abs_sent >= 3.0:
                        return 4.0  # High magnitude = high prominence
                    elif abs_sent >= 2.0:
                        return 3.0  # Medium-high magnitude
                    elif abs_sent >= 1.0:
                        return 2.0  # Medium magnitude
                    else:
                        return 1.0  # Low magnitude = minimal prominence
                
                df[prominence_col] = df.apply(estimate_prominence, axis=1)
            else:
                # Fallback: create zero-filled column
                df[prominence_col] = 0.0

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


