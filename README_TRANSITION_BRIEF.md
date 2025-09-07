# Ben State and Modifier Analysis System - Transition Brief

## Overview
This system performs vertical analysis of entity states and modifiers for betting companies (Bet365, BetMGM, DraftKings, FanDuel) based on narrative prominence, sentiment, and outlet scores. The system has undergone extensive refinement to align with canonical business rules.

## System Status: ✅ OPERATIONAL

### Recent Critical Fixes (Pass 1 Analysis)

#### 1. **Under Fire Modifier Logic** - ✅ RESOLVED
- **Issue**: Incorrect outlet score thresholds causing misclassification
- **Fix**: Implemented exact canonical logic:
  - **Narrative Shaper**: `Prom ≥ 3, Sent ≤ -2.0, Outlet = 5` (headline requirement removed per Ben's feedback)
  - **Body Blow**: `Prom ≥ 3, Sent ≤ -2.0, Outlet > 2 and != 5`
  - **Stinger**: `Prom ≥ 2.0, Sent ≤ -2.0, Outlet ≤ 3` + canonical gap bridge for `Outlet = 4`
  - **Light Jab**: `Prom ≥ 2.0, -2.0 < Sent < 0`
  - **Collateral Damage**: `Prom < 2.0, Sent ≤ -2.0`
  - **Peripheral Hit**: `Prom < 2.0, -2.0 < Sent < 0`

#### 2. **State Assignment Logic** - ✅ RESOLVED
- **Issue**: System was overwriting existing entity states from input CSV
- **Fix**: **Preserve existing states**, only calculate modifiers based on preserved states
- **Hybrid Handling**: Create state/modifier columns for entities missing them (BetMGM, DraftKings, FanDuel)

#### 3. **State Normalization** - ✅ RESOLVED
- **Issue**: "Offstage" vs "Off-Stage" inconsistencies (601 Bet365 rows)
- **Fix**: Normalize all state values to canonical "Off-Stage" before output

#### 4. **Missing Prominence Columns** - ✅ RESOLVED
- **Issue**: `Entity_*_Prominence` columns missing from output CSV
- **Fix**: Auto-generate prominence columns from `Entity_*_Present` and sentiment data

#### 5. **Off-Stage Modifier Logic** - ✅ VERIFIED
- **Issue**: Peer counting and narrative selection logic
- **Fix**: Use dominant narrative prominence/sentiment with `Prom ≥ 2.0` peer threshold

## File Structure

```
ben_state_and_modifier_analysis/
├── app.py                          # Flask web portal
├── vertical_analysis.py            # Pass 1 core logic (MAIN BUSINESS LOGIC)
├── orchestra_signals_engine.py     # Pass 2 signals analysis
├── requirements.txt                # Python dependencies
├── venv/                           # Virtual environment
├── one_pager/                      # UI assets
└── input_data/                     # CSV files for testing
```

## Core Components

### 1. **Web Portal** (`app.py`)
- **URL**: http://127.0.0.1:8000
- **Features**:
  - File upload with format detection
  - Real-time mapping preview
  - Pass 1 & Pass 2 analysis
  - Download results
  - Reset functionality

### 2. **Vertical Analysis Engine** (`vertical_analysis.py`)
- **Purpose**: Pass 1 analysis - entity state and modifier assignment
- **Key Functions**:
  - `auto_detect_companies_and_narratives()` - Dynamic CSV format detection
  - `assign_entity_state()` - Canonical state assignment
  - `assign_entity_modifier()` - Modifier assignment by state
  - `assign_under_fire_modifier()` - Under Fire sub-modifiers

### 3. **Signal Processing** (`orchestra_signals_engine.py`)
- **Purpose**: Pass 2 analysis - signal generation and trend analysis

## Data Format Support

### Input CSV Formats
1. **Current Format**: `Entity_*_Prominence`, `Entity_*_Sentiment`
2. **Orchestra Format**: `*_Entity_Prominence`, `*_Entity_Sentiment`

### Entity Mappings
- **Bet365**: Has existing `Entity_Bet365_State` and `Entity_Bet365_Modifier` (preserved)
- **BetMGM**: Missing state/modifier columns (created during analysis)
- **DraftKings**: Missing state/modifier columns (created during analysis)  
- **FanDuel**: Missing state/modifier columns (created during analysis)

### Narrative Mappings
- Business, Economic, Entertainment, Morality, Regulatory
- Precedence order maintained for tie-breaking

## Usage Instructions

### Starting the Portal
```bash
# Navigate to project directory
cd "/Users/willvalentine/Ben Comparison Analysis/ben_state_and_modifier_analysis"

# Activate virtual environment
source venv/bin/activate

# Start Flask portal
python app.py
```

### Processing Workflow
1. **Upload CSV**: Navigate to http://127.0.0.1:8000 and upload your CSV file
2. **Review Mapping**: Check the auto-detected company and narrative mappings
3. **Run Pass 1**: Click "Run Vertical Analysis (Pass 1)" 
4. **Download Results**: Download the processed CSV with states and modifiers
5. **Optional Pass 2**: Run signals analysis if needed

### Troubleshooting

#### Port Already in Use
```bash
# Kill existing processes
pkill -f "python app.py"
lsof -ti:8000 | xargs kill -9 2>/dev/null

# Restart portal
source venv/bin/activate && python app.py
```

#### Missing Dependencies
```bash
pip install -r requirements.txt
```

## Canonical Business Rules

### State Assignment
- **Leader**: `entity_prom ≥ 2.0 AND topic_prom ≥ 2.0 AND max_narr_prom > 0`
- **Supporting Player**: `entity_prom ≥ 2.0 AND topic_prom < 2.0 AND max_narr_prom > 0`
- **Under Fire**: `entity_prom ≥ 2.0 AND entity_sent < 0 AND max_narr_prom > 0`
- **Off-Stage**: `entity_prom == 0 AND topic_prom ≥ 2.0 AND max_narr_prom > 0`
- **Absent**: `entity_prom == 0 AND max_narr_prom == 0`

### Modifier Assignment
Each state has specific modifier sub-categories based on prominence, sentiment, and outlet score thresholds. The Under Fire modifiers have been extensively tested and validated.

## Testing Data
- **Primary**: `Bet365_ Messaging Study Fixed headers and updated QS and scrubbed.csv`
- **Entities**: 4 companies with varying state/modifier column availability
- **Rows**: ~30,000 records for comprehensive testing

## Recent Audit Results
- **State Trigger Violations**: 0 (resolved)
- **Under Fire Logic**: 100% canonical compliance
- **Off-Stage Logic**: Verified correct peer counting
- **State Normalization**: All "Offstage" → "Off-Stage" conversions working

## Next Steps
1. **Monitor**: Watch for any edge cases in production data
2. **Validate**: Run additional test datasets through the system
3. **Optimize**: Consider performance improvements for larger datasets

## Contact
For technical questions or business rule clarifications, refer to the canonical documentation in `Topic, narrative and entity signal schema (8-14 v4).txt`.

---
**Last Updated**: September 7, 2025  
**System Version**: Post-Under Fire Logic Fix  
**Status**: Production Ready ✅
