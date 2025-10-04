## **1\. Executive Summary**

Build a web application that performs comprehensive quality assurance on raw coded CSV data **before** it enters Pass 1 (vertical analysis). This QA module cleans, validates, and prepares data through a step-by-step workflow with user approval at each stage.

**Pipeline Position**:

Raw Coded CSV → QA Module → Clean Coded CSV → Pass 1 (Vertical Analysis) → Pass 2 (Signals) → Header Renaming → Final Output

**Critical Constraints**:

* **Fully dynamic**: Handles ANY number of entities and narratives (could be 2, could be 50\)  
* **Step-by-step workflow**: User reviews and approves each operation before proceeding  
* **Preview-first**: Always show what will change before changing it  
* **No hardcoded assumptions**: Works for any domain (ticketing, gambling, healthcare, etc.)

---

## **2\. Input Files**

### **2.1 Primary Data CSV**

* **Format**: CSV with coded headers (pre-Pass 1\)  
* **Example headers**: `1_C_Sent`, `O_M_1desc`, `Relevance_Score`, `Publication`, `Headline`, `Body`, `Story_Link`  
* **Key columns required**:  
  * `Relevance_Score` (integer 0-10)  
  * `Publication` (string)  
  * `Headline` (string)  
  * `Body` (string, article text)  
  * `Story_Link` (URL)  
  * `Prep_Assign_Quality_Scores` (integer, to be updated with pub tier)  
  * Coded entity clusters: `1_C_Desc`, `1_C_Prom`, `1_C_Sent`, etc.  
  * Coded narrative clusters: `O_M_1desc`, `O_M_1prom`, `O_M_1sent`, etc.

### **2.2 Company Database**

* **File**: `company_database__companies.csv`  
* **Key columns used by QA module**:  
  * `Company` (string) \- company name  
  * `Available_Companies_Descriptions` (text) \- entity names/descriptions  
  * `Messages` (text) \- narrative names  
  * `Prompt1`, `Prompt2`, `Prompt3`, `Prompt4`, `Prompt5`, `Prompt6` (text) \- analysis instructions  
  * `schema_planner_table_name` (string) \- name of schema definition table

### **2.3 Publication YAML**

* **File**: `publication.yaml` (provided by user or system config)  
* **Structure**: Tiered list of publications with metadata

yaml  
tier\_1:  
  \- name: "New York Times"  
    root\_domain: "nytimes.com"  
    tier: 1  
tier\_2:  
  \- name: "Forbes"  
    root\_domain: "forbes.com"  
    tier: 2

*\# ... tier\_3, tier\_4*

### **2.4 Schema Definition Table**

* **Source**: CSV export from Supabase table named in `schema_planner_table_name`  
* **Key column**: `column_name` \- lists all required columns  
* **Example**: `schema_def_stubhub_messaging_study_2025_10_01.csv`

---

## **3\. QA Workflow Overview**

**Step-by-step process with user approval at each stage:**

Step 1: Remove Non-Relevant Articles  
        → Show count of Relevance\_Score=0 articles  
        → User approves deletion

Step 2: Deduplication \- Phase 1 (Exact Matches)  
        → Show clusters of same Headline \+ same Story\_Link  
        → User chooses: Keep one, or manually review

Step 3: Deduplication \- Phase 2 (High Similarity 97%+)  
        → Fuzzy match on Headline \+ Publication  
        → Show clusters with 97%+ similarity  
        → User chooses: Keep one per cluster, or manually review

Step 4: Deduplication \- Phase 3 (Medium Similarity 90-96%)  
        → Fuzzy match on Headline \+ Publication \+ first 100 words  
        → GPT-5 analyzes each cluster: same article or meaningfully different?  
        → Show GPT recommendations  
        → User chooses: Accept GPT recommendations, or manually review

Step 5: Assign Publication Scores  
        → Match publications in CSV against YAML  
        → Update Prep\_Assign\_Quality\_Scores with tier (1-4)  
        → Show unmatched publications  
        → User assigns scores (1-4) for unmapped pubs

Step 6: Schema Validation  
        → Load required columns from schema table  
        → Check all columns present in CSV  
        → Check each column has values in ≥5% of rows  
        → Show missing/empty columns  
        → User decides: proceed with warnings or fix data

Step 7: Entity Sanity Check  
        → For each entity (dynamically discovered), spot check 10 rows  
        → GPT-5 validates scores aren't "obviously wrong"  
        → Show flagged rows (if any)  
        → User reviews flagged items

Step 8: Narrative Sanity Check  
        → For each narrative (dynamically discovered), spot check 10 rows  
        → GPT-5 validates scores aren't "obviously wrong"  
        → Show flagged rows (if any)  
        → User reviews flagged items

Step 9: Download Clean CSV  
        → Generate QA report (summary of all changes)

        → Download cleaned CSV (ready for Pass 1\)

---

## **4\. Dynamic Entity/Narrative Discovery**

**CRITICAL**: The system must discover entities and narratives from the CSV headers, never assume fixed counts or names.

### **4.1 Entity Discovery**

python  
def discover\_entity\_indices(headers: List\[str\]) \-\> List\[int\]:  
    """  
    Scan headers and extract all unique entity indices.  
      
    Could return: \[1, 2, 3, 4, 5\] or \[1, 3, 7, 12\] or \[1\] \- fully variable.  
    """  
    indices \= set()  
    for header in headers:  
        *\# Pattern A: X\_C\_\**  
        match \= re.match(r'^(\\d+)\_C\_', header)  
        if match:  
            indices.add(int(match.group(1)))  
            continue  
          
        *\# Pattern B: X\_Orchestra\_\**  
        match \= re.match(r'^(\\d+)\_Orchestra\_', header)  
        if match:  
            indices.add(int(match.group(1)))  
    

    return sorted(list(indices))

### **4.2 Narrative Discovery**

python  
def discover\_narrative\_indices(headers: List\[str\]) \-\> List\[int\]:  
    """  
    Scan headers and extract all unique narrative indices.  
      
    Could return: \[1, 2, 3, 4, 5, 6\] or \[1, 3, 5\] or \[1, 2\] \- fully variable.  
    """  
    indices \= set()  
    for header in headers:  
        match \= re.match(r'^O\_M\_(\\d+)', header)  
        if match:  
            indices.add(int(match.group(1)))  
    

    return sorted(list(indices))

### **4.3 Prompt Mapping**

Prompts are grouped in pairs (2 entities/narratives per prompt), with the final prompt solo if odd count:

* **Prompt1**: Topic (O\_ fields) analysis  
* **Prompt2**: Entities 1, 2 (or narratives 1, 2\)  
* **Prompt3**: Entities 3, 4 (or narratives 3, 4\)  
* **Prompt4**: Entities 5, 6 (or narratives 5, 6\)  
* **Prompt5**: Entities 7, 8 (or narratives 7, 8\)  
* **Prompt6**: Entity 9 (solo if odd count)

python  
def get\_prompt\_for\_entity(entity\_index: int) \-\> str:  
    """  
    Map entity index to correct prompt.  
      
    Examples:  
    \- Entity 1 or 2 → Prompt2  
    \- Entity 3 or 4 → Prompt3  
    \- Entity 5 or 6 → Prompt4  
    \- Entity 7 or 8 → Prompt5  
    \- Entity 9 (solo) → Prompt6  
    """  
    prompt\_num \= ((entity\_index \- 1) // 2) \+ 2  
    return f"Prompt{prompt\_num}"

def get\_prompt\_for\_narrative(narrative\_index: int) \-\> str:  
    """  
    Map narrative index to correct prompt.  
      
    Same logic as entities.  
    """  
    prompt\_num \= ((narrative\_index \- 1) // 2) \+ 2

    return f"Prompt{prompt\_num}"

---

## **5\. Step 1: Remove Non-Relevant Articles**

### **5.1 Logic**

python  
def identify\_non\_relevant(df: pd.DataFrame) \-\> pd.DataFrame:  
    """  
    Find all rows where Relevance\_Score \== 0\.  
      
    Returns: DataFrame of non-relevant rows  
    """

    return df\[df\['Relevance\_Score'\] \== 0\].copy()

### **5.2 Preview UI**

html  
\<div class\="step-preview"\>  
  \<h3\>Step 1: Remove Non-Relevant Articles\</h3\>  
  \<p\>\<strong\>Found:\</strong\> 47 articles with Relevance\_Score \= 0\</p\>  
    
  \<table\>  
    \<thead\>  
      \<tr\>\<th\>Record ID\</th\>\<th\>Publication\</th\>\<th\>Headline\</th\>\</tr\>  
    \</thead\>  
    \<tbody\>  
      *\<\!-- Show sample of non-relevant articles \--\>*  
    \</tbody\>  
  \</table\>  
    
  \<button onclick\="approveRemoval()"\>✓ Remove These Articles\</button\>  
  \<button onclick\="skipStep()"\>Skip This Step\</button\>

\</div\>

### **5.3 Apply**

python  
def remove\_non\_relevant(df: pd.DataFrame) \-\> pd.DataFrame:  
    """  
    Remove all rows where Relevance\_Score \== 0\.  
      
    Returns: Cleaned DataFrame  
    """

    return df\[df\['Relevance\_Score'\] \!= 0\].copy()

---

## **6\. Step 2: Deduplication \- Phase 1 (Exact Matches)**

### **6.1 Logic**

python  
def find\_exact\_duplicates(df: pd.DataFrame) \-\> Dict\[str, List\[int\]\]:  
    """  
    Find articles with identical Headline AND Story\_Link.  
      
    Returns: {  
        "cluster\_1": \[row\_index\_1, row\_index\_2, row\_index\_3\],  
        "cluster\_2": \[row\_index\_4, row\_index\_5\],  
        ...  
    }  
    """  
    df\['dedup\_key'\] \= df\['Headline'\].fillna('') \+ '|||' \+ df\['Story\_Link'\].fillna('')  
      
    clusters \= {}  
    for key, group in df.groupby('dedup\_key'):  
        if len(group) \> 1:  
            cluster\_name \= f"cluster\_{len(clusters) \+ 1}"  
            clusters\[cluster\_name\] \= group.index.tolist()  
    

    return clusters

### **6.2 Preview UI**

html  
\<div class\="step-preview"\>  
  \<h3\>Step 2: Exact Duplicate Detection\</h3\>  
  \<p\>\<strong\>Found:\</strong\> 12 clusters (35 total duplicate articles)\</p\>  
    
  \<div class\="cluster"\>  
    \<h4\>Cluster 1 (3 duplicates)\</h4\>  
    \<p\>\<strong\>Headline:\</strong\> "StubHub Announces Q3 Revenue Growth"\</p\>  
    \<p\>\<strong\>Link:\</strong\> https://example.com/article123\</p\>  
    \<table\>  
      \<tr\>\<th\>Record ID\</th\>\<th\>Publication\</th\>\<th\>Date\</th\>\<th\>Action\</th\>\</tr\>  
      \<tr\>\<td\>rec001\</td\>\<td\>Forbes\</td\>\<td\>2025-01-15\</td\>\<td\>✓ Keep (first)\</td\>\</tr\>  
      \<tr\>\<td\>rec002\</td\>\<td\>Forbes\</td\>\<td\>2025-01-15\</td\>\<td\>❌ Delete\</td\>\</tr\>  
      \<tr\>\<td\>rec003\</td\>\<td\>Forbes\</td\>\<td\>2025-01-15\</td\>\<td\>❌ Delete\</td\>\</tr\>  
    \</table\>  
  \</div\>  
    
  \<button onclick\="approveDeduplication()"\>✓ Keep First, Delete Rest\</button\>  
  \<button onclick\="manualReview()"\>👁️ Manual Review\</button\>

\</div\>

### **6.3 Apply**

python  
def apply\_deduplication\_keep\_first(df: pd.DataFrame, clusters: Dict) \-\> pd.DataFrame:  
    """  
    For each cluster, keep the first row and delete the rest.  
      
    Returns: Deduplicated DataFrame  
    """  
    rows\_to\_delete \= \[\]  
    for cluster\_rows in clusters.values():  
        *\# Keep first, delete rest*  
        rows\_to\_delete.extend(cluster\_rows\[1:\])  
    

    return df.drop(index\=rows\_to\_delete)

---

## **7\. Step 3: Deduplication \- Phase 2 (High Similarity 97%+)**

### **7.1 Logic**

python  
from rapidfuzz import fuzz

def find\_high\_similarity\_duplicates(df: pd.DataFrame, threshold: int \= 97) \-\> Dict:  
    """  
    Find articles with 97%+ similarity on Headline \+ Publication.  
      
    Uses rapidfuzz for fuzzy string matching.  
      
    Returns: clusters dict similar to Phase 1  
    """  
    clusters \= {}  
    processed \= set()  
      
    for idx1, row1 in df.iterrows():  
        if idx1 in processed:  
            continue  
          
        cluster \= \[idx1\]  
        key1 \= f"{row1\['Headline'\]} {row1\['Publication'\]}"  
          
        for idx2, row2 in df.iterrows():  
            if idx2 \<= idx1 or idx2 in processed:  
                continue  
              
            key2 \= f"{row2\['Headline'\]} {row2\['Publication'\]}"  
            similarity \= fuzz.ratio(key1, key2)  
              
            if similarity \>= threshold:  
                cluster.append(idx2)  
                processed.add(idx2)  
          
        if len(cluster) \> 1:  
            clusters\[f"cluster\_{len(clusters) \+ 1}"\] \= cluster  
            processed.add(idx1)  
    

    return clusters

### **7.2 Preview UI**

html  
\<div class\="step-preview"\>  
  \<h3\>Step 3: High Similarity Duplicates (97%+)\</h3\>  
  \<p\>\<strong\>Found:\</strong\> 8 clusters (22 similar articles)\</p\>  
    
  \<div class\="cluster"\>  
    \<h4\>Cluster 1 (3 articles, 98% similar)\</h4\>  
    \<table\>  
      \<tr\>  
        \<th\>Record ID\</th\>\<th\>Publication\</th\>\<th\>Headline\</th\>  
        \<th\>Similarity\</th\>\<th\>Action\</th\>  
      \</tr\>  
      \<tr\>  
        \<td\>rec010\</td\>\<td\>TechCrunch\</td\>  
        \<td\>"StubHub Launches New Mobile App"\</td\>  
        \<td\>100%\</td\>\<td\>✓ Keep\</td\>  
      \</tr\>  
      \<tr\>  
        \<td\>rec011\</td\>\<td\>TechCrunch\</td\>  
        \<td\>"StubHub Launches New Mobile Application"\</td\>  
        \<td\>98%\</td\>\<td\>❌ Delete\</td\>  
      \</tr\>  
      \<tr\>  
        \<td\>rec012\</td\>\<td\>Tech Crunch\</td\>  
        \<td\>"StubHub Launches New Mobile App"\</td\>  
        \<td\>98%\</td\>\<td\>❌ Delete\</td\>  
      \</tr\>  
    \</table\>  
  \</div\>  
    
  \<button onclick\="approveDeduplication()"\>✓ Keep First, Delete Rest\</button\>  
  \<button onclick\="manualReview()"\>👁️ Manual Review All Clusters\</button\>

\</div\>

---

## **8\. Step 4: Deduplication \- Phase 3 (Medium Similarity 90-96% \+ GPT Review)**

### **8.1 Logic**

python  
def find\_medium\_similarity\_duplicates(df: pd.DataFrame) \-\> Dict:  
    """  
    Find articles with 90-96% similarity on:  
    \- Headline  
    \- Publication    
    \- First 100 words of Body  
      
    Returns: clusters dict  
    """  
    clusters \= {}  
    processed \= set()  
      
    for idx1, row1 in df.iterrows():  
        if idx1 in processed:  
            continue  
          
        cluster \= \[idx1\]  
        body1\_preview \= ' '.join(str(row1\['Body'\]).split()\[:100\])  
        key1 \= f"{row1\['Headline'\]} {row1\['Publication'\]} {body1\_preview}"  
          
        for idx2, row2 in df.iterrows():  
            if idx2 \<= idx1 or idx2 in processed:  
                continue  
              
            body2\_preview \= ' '.join(str(row2\['Body'\]).split()\[:100\])  
            key2 \= f"{row2\['Headline'\]} {row2\['Publication'\]} {body2\_preview}"  
              
            similarity \= fuzz.ratio(key1, key2)  
              
            if 90 \<= similarity \< 97:  
                cluster.append(idx2)  
                processed.add(idx2)  
          
        if len(cluster) \> 1:  
            clusters\[f"cluster\_{len(clusters) \+ 1}"\] \= cluster  
            processed.add(idx1)  
    

    return clusters

### **8.2 GPT-5 Analysis**

python  
import openai  
from dotenv import load\_dotenv

load\_dotenv("/Users/willvalentine/scrape\_tracker.git/scrape\_tracker/.env")

def analyze\_cluster\_with\_gpt(cluster\_rows: pd.DataFrame) \-\> Dict:  
    """  
    Send cluster to GPT-5 for analysis.  
      
    Prompt: "Are these the same article or meaningfully different articles?"  
      
    Returns: {  
        "recommendation": "same" | "different",  
        "reasoning": "explanation",  
        "confidence": "high" | "medium" | "low"  
    }  
    """  
    *\# Prepare cluster data*  
    articles \= \[\]  
    for idx, row in cluster\_rows.iterrows():  
        articles.append({  
            "id": row\['Record ID'\],  
            "publication": row\['Publication'\],  
            "headline": row\['Headline'\],  
            "first\_100\_words": ' '.join(str(row\['Body'\]).split()\[:100\])  
        })  
      
    prompt \= f"""You are reviewing a cluster of potentially duplicate articles. 

Articles in cluster:  
{json.dumps(articles, indent\=2)}

Question: Are these the SAME article (duplicates/republications) or MEANINGFULLY DIFFERENT articles?

Respond in JSON format:  
{{  
  "recommendation": "same" or "different",  
  "reasoning": "brief explanation",  
  "confidence": "high", "medium", or "low"  
}}  
"""  
      
    response \= openai.chat.completions.create(  
        model\="GPT-5",  *\# or "o1-preview" if available*  
        messages\=\[  
            {"role": "system", "content": "You are a data quality analyst specializing in detecting duplicate articles."},  
            {"role": "user", "content": prompt}  
        \],  
        response\_format\={"type": "json\_object"}  
    )  
    

    return json.loads(response.choices\[0\].message.content)

### **8.3 Preview UI with GPT Recommendations**

html  
\<div class\="step-preview"\>  
  \<h3\>Step 4: Medium Similarity Duplicates (90-96%) with GPT Analysis\</h3\>  
  \<p\>\<strong\>Found:\</strong\> 15 clusters (analyzing with GPT-5...)\</p\>  
    
  \<div class\="cluster"\>  
    \<h4\>Cluster 1 (2 articles, 93% similar)\</h4\>  
    \<div class\="gpt-recommendation"\>  
      \<p\>\<strong\>GPT-5 Recommendation:\</strong\> \<span class\="badge-same"\>SAME ARTICLE\</span\>\</p\>  
      \<p\>\<strong\>Reasoning:\</strong\> Both articles cover the same event (StubHub Q3 earnings) with nearly identical information. The second appears to be a syndicated version.\</p\>  
      \<p\>\<strong\>Confidence:\</strong\> High\</p\>  
    \</div\>  
    \<table\>  
      \<tr\>\<th\>Record ID\</th\>\<th\>Publication\</th\>\<th\>Headline\</th\>\<th\>Action\</th\>\</tr\>  
      \<tr\>\<td\>rec020\</td\>\<td\>Bloomberg\</td\>\<td\>"StubHub Reports Q3 Earnings Beat"\</td\>\<td\>✓ Keep\</td\>\</tr\>  
      \<tr\>\<td\>rec021\</td\>\<td\>Yahoo Finance\</td\>\<td\>"StubHub Q3 Earnings Exceed Expectations"\</td\>\<td\>❌ Delete (if approved)\</td\>\</tr\>  
    \</table\>  
  \</div\>  
    
  \<div class\="cluster"\>  
    \<h4\>Cluster 2 (2 articles, 91% similar)\</h4\>  
    \<div class\="gpt-recommendation"\>  
      \<p\>\<strong\>GPT-5 Recommendation:\</strong\> \<span class\="badge-different"\>DIFFERENT ARTICLES\</span\>\</p\>  
      \<p\>\<strong\>Reasoning:\</strong\> While both discuss StubHub pricing, the first focuses on dynamic pricing algorithms while the second covers customer complaints about fees. Different angles on related topic.\</p\>  
      \<p\>\<strong\>Confidence:\</strong\> High\</p\>  
    \</div\>  
    \<table\>  
      \<tr\>\<td\>rec030\</td\>\<td\>WSJ\</td\>\<td\>"StubHub's Dynamic Pricing Model"\</td\>\<td\>✓ Keep\</td\>\</tr\>  
      \<tr\>\<td\>rec031\</td\>\<td\>Forbes\</td\>\<td\>"StubHub Pricing Controversy Grows"\</td\>\<td\>✓ Keep\</td\>\</tr\>  
    \</table\>  
  \</div\>  
    
  \<button onclick\="acceptGptRecommendations()"\>✓ Accept All GPT-5 Recommendations\</button\>  
  \<button onclick\="manualReview()"\>👁️ Manual Review All Clusters\</button\>

\</div\>

---

## **9\. Step 5: Assign Publication Scores**

### **9.1 Logic**

python  
import yaml

def load\_publication\_yaml(yaml\_path: str) \-\> Dict\[str, int\]:  
    """  
    Load publication.yaml and create mapping of:  
    \- name → tier  
    \- root\_domain → tier  
      
    Returns: {  
        "New York Times": 1,  
        "nytimes.com": 1,  
        "Forbes": 2,  
        "forbes.com": 2,  
        ...  
    }  
    """  
    with open(yaml\_path) as f:  
        data \= yaml.safe\_load(f)  
      
    mapping \= {}  
    for tier\_name, pubs in data.items():  
        for pub in pubs:  
            name \= pub\['name'\]  
            domain \= pub\['root\_domain'\]  
            tier \= pub\['tier'\]  
              
            mapping\[name.lower()\] \= tier  
            mapping\[domain.lower()\] \= tier  
      
    return mapping

def assign\_publication\_scores(df: pd.DataFrame, pub\_mapping: Dict) \-\> Tuple\[pd.DataFrame, List\[str\]\]:  
    """  
    Match publications against YAML and update Prep\_Assign\_Quality\_Scores.  
      
    Matching logic:  
    1\. Try exact match on Publication name  
    2\. Try root domain extraction from Story\_Link  
    3\. If no match, flag as "unmatched"  
      
    Returns: (updated\_df, list\_of\_unmatched\_pubs)  
    """  
    from urllib.parse import urlparse  
      
    unmatched\_pubs \= set()  
      
    for idx, row in df.iterrows():  
        pub\_name \= str(row\['Publication'\]).lower().strip()  
        story\_link \= str(row\['Story\_Link'\])  
          
        *\# Try exact name match*  
        if pub\_name in pub\_mapping:  
            df.at\[idx, 'Prep\_Assign\_Quality\_Scores'\] \= pub\_mapping\[pub\_name\]  
            continue  
          
        *\# Try domain match*  
        try:  
            domain \= urlparse(story\_link).netloc.lower()  
            *\# Strip www. if present*  
            domain \= domain.replace('www.', '')  
              
            if domain in pub\_mapping:  
                df.at\[idx, 'Prep\_Assign\_Quality\_Scores'\] \= pub\_mapping\[domain\]  
                continue  
        except:  
            pass  
          
        *\# No match found*  
        unmatched\_pubs.add(row\['Publication'\])  
    

    return df, sorted(list(unmatched\_pubs))

### **9.2 Preview UI for Unmatched Publications**

html  
\<div class\="step-preview"\>  
  \<h3\>Step 5: Assign Publication Scores\</h3\>  
  \<p\>\<strong\>Matched:\</strong\> 1,089 articles (98.5%)\</p\>  
  \<p\>\<strong\>Unmatched:\</strong\> 17 articles from 3 publications\</p\>  
    
  \<h4\>Assign Scores for Unmatched Publications\</h4\>  
  \<form id\="pub-score-form"\>  
    \<div class\="form-group"\>  
      \<label\>The Ticketing Times (5 articles)\</label\>  
      \<select name\="pub\_1" required\>  
        \<option value\=""\>Select tier...\</option\>  
        \<option value\="1"\>Tier 1 \- Elite (NYT, WSJ, BBC)\</option\>  
        \<option value\="2"\>Tier 2 \- Major (Forbes, CNN, Reuters)\</option\>  
        \<option value\="3"\>Tier 3 \- Niche/Trade\</option\>  
        \<option value\="4"\>Tier 4 \- Low Quality/Aggregators\</option\>  
      \</select\>  
    \</div\>  
      
    \<div class\="form-group"\>  
      \<label\>Sports Business Daily (8 articles)\</label\>  
      \<select name\="pub\_2" required\>  
        \<option value\=""\>Select tier...\</option\>  
        \<option value\="1"\>Tier 1 \- Elite\</option\>  
        \<option value\="2"\>Tier 2 \- Major\</option\>  
        \<option value\="3"\>Tier 3 \- Niche/Trade\</option\>  
        \<option value\="4"\>Tier 4 \- Low Quality/Aggregators\</option\>  
      \</select\>  
    \</div\>  
      
    \<div class\="form-group"\>  
      \<label\>Unknown Blog (4 articles)\</label\>  
      \<select name\="pub\_3" required\>  
        \<option value\=""\>Select tier...\</option\>  
        \<option value\="1"\>Tier 1 \- Elite\</option\>  
        \<option value\="2"\>Tier 2 \- Major\</option\>  
        \<option value\="3"\>Tier 3 \- Niche/Trade\</option\>  
        \<option value\="4"\>Tier 4 \- Low Quality/Aggregators\</option\>  
      \</select\>  
    \</div\>  
      
    \<button type\="submit"\>✓ Apply Publication Scores\</button\>  
  \</form\>

\</div\>

### **9.3 Apply Manual Scores**

python  
def apply\_manual\_pub\_scores(df: pd.DataFrame, manual\_scores: Dict\[str, int\]) \-\> pd.DataFrame:  
    """  
    Apply user-provided scores for unmatched publications.  
      
    Args:  
        manual\_scores: {"The Ticketing Times": 3, "Sports Business Daily": 2, ...}  
      
    Returns: Updated DataFrame  
    """  
    for pub\_name, tier in manual\_scores.items():  
        mask \= df\['Publication'\] \== pub\_name  
        df.loc\[mask, 'Prep\_Assign\_Quality\_Scores'\] \= tier  
    

    return df

---

## **10\. Step 6: Schema Validation**

### **10.1 Load Schema Definition**

python  
def load\_schema\_definition(schema\_table\_name: str) \-\> List\[str\]:  
    """  
    Load required columns from schema definition table.  
      
    Args:  
        schema\_table\_name: e.g., "schema\_def\_stubhub\_messaging\_study\_2025\_10\_01"  
      
    Returns: List of required column names  
      
    Note: User provides this as CSV export from Supabase  
    """  
    schema\_df \= pd.read\_csv(f"{schema\_table\_name}.csv")

    return schema\_df\['column\_name'\].dropna().tolist()

### **10.2 Validation Logic**

python  
def validate\_schema(df: pd.DataFrame, required\_columns: List\[str\]) \-\> Dict:  
    """  
    Check that all required columns:  
    1\. Are present in the CSV  
    2\. Have non-null values in at least 5% of rows  
      
    Returns: {  
        "missing\_columns": \["col1", "col2"\],  
        "empty\_columns": \[  
            {"column": "col3", "fill\_rate": 0.02},  
            {"column": "col4", "fill\_rate": 0.00}  
        \],  
        "valid\_columns": \["col5", "col6", ...\],  
        "status": "passed" | "warnings" | "failed"  
    }  
    """  
    missing \= \[\]  
    empty \= \[\]  
    valid \= \[\]  
      
    for col in required\_columns:  
        if col not in df.columns:  
            missing.append(col)  
            continue  
          
        *\# Calculate fill rate*  
        non\_null\_count \= df\[col\].notna().sum()  
        fill\_rate \= non\_null\_count / len(df)  
          
        if fill\_rate \< 0.05:  *\# Less than 5%*  
            empty.append({"column": col, "fill\_rate": fill\_rate})  
        else:  
            valid.append(col)  
      
    *\# Determine status*  
    if missing:  
        status \= "failed"  
    elif empty:  
        status \= "warnings"  
    else:  
        status \= "passed"  
      
    return {  
        "missing\_columns": missing,  
        "empty\_columns": empty,  
        "valid\_columns": valid,  
        "status": status

    }

### **10.3 Preview UI**

html  
\<div class\="step-preview"\>  
  \<h3\>Step 6: Schema Validation\</h3\>  
    
  \<div class\="validation-passed"\>  
    \<h4\>✓ Valid Columns (58 of 60 required)\</h4\>  
    \<p\>These columns are present and have values in ≥5% of rows.\</p\>  
  \</div\>  
    
  \<div class\="validation-warnings"\>  
    \<h4\>⚠️ Low Fill Rate Columns (2)\</h4\>  
    \<table\>  
      \<tr\>\<th\>Column\</th\>\<th\>Fill Rate\</th\>\<th\>Status\</th\>\</tr\>  
      \<tr\>\<td\>Entity\_Gametime\_Description\</td\>\<td\>3.2%\</td\>\<td class\="warning"\>Below 5% threshold\</td\>\</tr\>  
      \<tr\>\<td\>Narrative\_TicketingTechnologyInnovation\_State\</td\>\<td\>1.8%\</td\>\<td class\="warning"\>Below 5% threshold\</td\>\</tr\>  
    \</table\>  
    \<p\>\<small\>These columns exist but have few values. This may indicate data quality issues.\</small\>\</p\>  
  \</div\>  
    
  \<div class\="validation-failed"\>  
    \<h4\>❌ Missing Columns (0)\</h4\>  
    \<p\>All required columns are present.\</p\>  
  \</div\>


  \<button onclick="proceedWith

Retry  
WV

Continue

Edit

Continuing from section 10.3:

\<artifact identifier="qa-module-brief" type="application/vnd.ant.code" language="markdown" title="Data QA Module \- Developer Brief"\> \[Previous content through section 10.3 remains unchanged\]

### **10.3 Preview UI**

html  
\<div class\="step-preview"\>  
  \<h3\>Step 6: Schema Validation\</h3\>  
    
  \<div class\="validation-passed"\>  
    \<h4\>✓ Valid Columns (58 of 60 required)\</h4\>  
    \<p\>These columns are present and have values in ≥5% of rows.\</p\>  
  \</div\>  
    
  \<div class\="validation-warnings"\>  
    \<h4\>⚠️ Low Fill Rate Columns (2)\</h4\>  
    \<table\>  
      \<tr\>\<th\>Column\</th\>\<th\>Fill Rate\</th\>\<th\>Status\</th\>\</tr\>  
      \<tr\>\<td\>Entity\_Gametime\_Description\</td\>\<td\>3.2%\</td\>\<td class\="warning"\>Below 5% threshold\</td\>\</tr\>  
      \<tr\>\<td\>Narrative\_TicketingTechnologyInnovation\_State\</td\>\<td\>1.8%\</td\>\<td class\="warning"\>Below 5% threshold\</td\>\</tr\>  
    \</table\>  
    \<p\>\<small\>These columns exist but have few values. This may indicate data quality issues.\</small\>\</p\>  
  \</div\>  
    
  \<div class\="validation-failed"\>  
    \<h4\>❌ Missing Columns (0)\</h4\>  
    \<p\>All required columns are present.\</p\>  
  \</div\>  
    
  \<button onclick\="proceedWithWarnings()"\>✓ Proceed (with warnings noted)\</button\>  
  \<button onclick\="fixData()"\>🔧 Fix Data Before Proceeding\</button\>

\</div\>

---

## **11\. Step 7: Entity Sanity Check**

### **11.1 Sample Selection Logic**

python  
def select\_entity\_spot\_check\_samples(  
    df: pd.DataFrame,  
    entity\_index: int,  
    sample\_size: int \= 10  
) \-\> pd.DataFrame:  
    """  
    Select 10 rows for entity spot checking.  
      
    Criteria:  
    \- Entity must have \[X\]\_C\_Prom \> 2.0 (meaningful presence)  
    \- All three fields must be present: \_Desc, \_Prom, \_Sent  
    \- Only check ONE entity cluster per row (don't try to validate all entities in same row)  
      
    Returns: DataFrame with 10 sample rows  
    """  
    prom\_col \= f"{entity\_index}\_C\_Prom"  
    desc\_col \= f"{entity\_index}\_C\_Desc"  
    sent\_col \= f"{entity\_index}\_C\_Sent"  
      
    *\# Filter: prominence \> 2.0 and all fields present*  
    eligible \= df\[  
        (df\[prom\_col\] \> 2.0) &  
        (df\[desc\_col\].notna()) &  
        (df\[sent\_col\].notna())  
    \].copy()  
      
    *\# Sample 10 randomly (or all if fewer than 10\)*  
    if len(eligible) \<= sample\_size:  
        return eligible  
    

    return eligible.sample(n\=sample\_size, random\_state\=42)

### **11.2 GPT-5 Spot Check**

python  
def spot\_check\_entity\_with\_gpt(  
    row: pd.Series,  
    entity\_index: int,  
    entity\_name: str,  
    prompt\_text: str  
) \-\> Dict:  
    """  
    Send article \+ entity scores to GPT-5 for sanity check.  
      
    Question: Are these scores obviously wrong, or within reasonable interpretation?  
      
    Args:  
        row: DataFrame row with article data  
        entity\_index: e.g., 1, 2, 3  
        entity\_name: e.g., "StubHub", "BetMGM"  
        prompt\_text: The analysis instructions from Prompt2/Prompt3/etc.  
      
    Returns: {  
        "status": "pass" | "flag",  
        "reasoning": "explanation",  
        "confidence": "high" | "medium" | "low"  
    }  
    """  
    desc\_col \= f"{entity\_index}\_C\_Desc"  
    prom\_col \= f"{entity\_index}\_C\_Prom"  
    sent\_col \= f"{entity\_index}\_C\_Sent"  
      
    article\_data \= {  
        "headline": row\['Headline'\],  
        "body": row\['Body'\]\[:1000\],  *\# First 1000 chars to save tokens*  
        "entity\_name": entity\_name,  
        "scores": {  
            "description": row\[desc\_col\],  
            "prominence": float(row\[prom\_col\]),  
            "sentiment": float(row\[sent\_col\])  
        }  
    }  
      
    gpt\_prompt \= f"""You are reviewing entity scoring quality for a media analysis project.

Analysis Instructions (for reference):  
{prompt\_text\[:500\]}

Article:  
Headline: {article\_data\['headline'\]}  
Body (excerpt): {article\_data\['body'\]}

Entity Being Analyzed: {entity\_name}

Scores Assigned:  
\- Description: "{article\_data\['scores'\]\['description'\]}"  
\- Prominence: {article\_data\['scores'\]\['prominence'\]}  
\- Sentiment: {article\_data\['scores'\]\['sentiment'\]}

Question: Are these scores OBVIOUSLY WRONG, or are they within reasonable interpretation boundaries?

Examples of "obviously wrong":  
\- Article never mentions the entity, but prominence is 4.0  
\- Article is clearly negative, but sentiment is \+3.0  
\- Description says something completely contradicted by article

Examples of "reasonable" (even if you'd score differently):  
\- Prominence is 3.0 but you think it should be 2.5 (minor difference)  
\- Sentiment is \+1.0 but you think it should be \+1.5 (interpretation variance)  
\- Description is accurate but you'd phrase it differently

Respond in JSON:  
{{  
  "status": "pass" or "flag",  
  "reasoning": "brief explanation",  
  "confidence": "high", "medium", or "low"  
}}  
"""  
      
    response \= openai.chat.completions.create(  
        model\="GPT-5",  
        messages\=\[  
            {"role": "system", "content": "You are a quality assurance analyst. Flag only scores that are obviously incorrect, not minor interpretation differences."},  
            {"role": "user", "content": gpt\_prompt}  
        \],  
        response\_format\={"type": "json\_object"}  
    )  
    

    return json.loads(response.choices\[0\].message.content)

### **11.3 Preview UI**

html  
\<div class\="step-preview"\>  
  \<h3\>Step 7: Entity Sanity Check\</h3\>  
  \<p\>Spot checking 10 rows per entity using GPT-5...\</p\>  
    
  \<div class\="entity-check"\>  
    \<h4\>Entity 1: StubHub\</h4\>  
    \<p\>\<strong\>Status:\</strong\> ✓ 10/10 samples passed\</p\>  
    \<p\>\<small\>All scores appear reasonable given article content.\</small\>\</p\>  
  \</div\>  
    
  \<div class\="entity-check"\>  
    \<h4\>Entity 2: TicketmasterLiveNation\</h4\>  
    \<p\>\<strong\>Status:\</strong\> ✓ 9/10 samples passed\</p\>  
    \<p\>\<strong\>Flagged:\</strong\> 1 article for review\</p\>  
      
    \<div class\="flagged-row"\>  
      \<h5\>Flagged Article\</h5\>  
      \<p\>\<strong\>Record ID:\</strong\> rec045\</p\>  
      \<p\>\<strong\>Headline:\</strong\> "StubHub Announces Partnership with NFL"\</p\>  
      \<p\>\<strong\>Issue:\</strong\> TicketmasterLiveNation has prominence 3.5 but is only mentioned once in passing. May be over-scored.\</p\>  
      \<p\>\<strong\>Current Scores:\</strong\> Prom: 3.5, Sent: 1.0\</p\>  
      \<p\>\<strong\>GPT Suggestion:\</strong\> Prominence might be closer to 1.5-2.0 based on minimal mention.\</p\>  
      \<button onclick\="viewFullArticle('rec045')"\>View Full Article\</button\>  
      \<button onclick\="acceptScore()"\>Accept Anyway\</button\>  
      \<button onclick\="flagForManualReview()"\>Flag for Manual Review\</button\>  
    \</div\>  
  \</div\>  
    
  \<div class\="entity-check"\>  
    \<h4\>Entity 3: SeatGeek\</h4\>  
    \<p\>\<strong\>Status:\</strong\> ✓ 10/10 samples passed\</p\>  
  \</div\>  
    
  \<button onclick\="proceedToNext()"\>✓ Continue to Narrative Check\</button\>

\</div\>

---

## **12\. Step 8: Narrative Sanity Check**

### **12.1 Sample Selection Logic**

python  
def select\_narrative\_spot\_check\_samples(  
    df: pd.DataFrame,  
    narrative\_index: int,  
    sample\_size: int \= 10  
) \-\> pd.DataFrame:  
    """  
    Select 10 rows for narrative spot checking.  
      
    Criteria:  
    \- Narrative must have O\_M\_\[X\]prom \> 2.0 (meaningful presence)  
    \- All three fields must be present: desc, prom, sent  
    \- Only check ONE narrative cluster per row  
      
    Returns: DataFrame with 10 sample rows  
    """  
    prom\_col \= f"O\_M\_{narrative\_index}prom"  
    desc\_col \= f"O\_M\_{narrative\_index}desc"  
    sent\_col \= f"O\_M\_{narrative\_index}sent"  
      
    *\# Filter: prominence \> 2.0 and all fields present*  
    eligible \= df\[  
        (df\[prom\_col\] \> 2.0) &  
        (df\[desc\_col\].notna()) &  
        (df\[sent\_col\].notna())  
    \].copy()  
      
    *\# Sample 10 randomly*  
    if len(eligible) \<= sample\_size:  
        return eligible  
    

    return eligible.sample(n\=sample\_size, random\_state\=42)

### **12.2 GPT-5 Spot Check**

python  
def spot\_check\_narrative\_with\_gpt(  
    row: pd.Series,  
    narrative\_index: int,  
    narrative\_name: str,  
    prompt\_text: str  
) \-\> Dict:  
    """  
    Send article \+ narrative scores to GPT-5 for sanity check.  
      
    Similar to entity check, but for narratives.  
      
    Note: Prompt text and Body may look nearly identical \- that's OK.  
    The goal is to confirm scoring isn't contradictory, not to check for duplication.  
      
    Returns: {  
        "status": "pass" | "flag",  
        "reasoning": "explanation",  
        "confidence": "high" | "medium" | "low"  
    }  
    """  
    desc\_col \= f"O\_M\_{narrative\_index}desc"  
    prom\_col \= f"O\_M\_{narrative\_index}prom"  
    sent\_col \= f"O\_M\_{narrative\_index}sent"  
      
    article\_data \= {  
        "headline": row\['Headline'\],  
        "body": row\['Body'\]\[:1000\],  
        "narrative\_name": narrative\_name,  
        "scores": {  
            "description": row\[desc\_col\],  
            "prominence": float(row\[prom\_col\]),  
            "sentiment": float(row\[sent\_col\])  
        }  
    }  
      
    gpt\_prompt \= f"""You are reviewing narrative scoring quality for a media analysis project.

Analysis Instructions (for reference):  
{prompt\_text\[:500\]}

Article:  
Headline: {article\_data\['headline'\]}  
Body (excerpt): {article\_data\['body'\]}

Narrative Being Analyzed: {narrative\_name}

Scores Assigned:  
\- Description: "{article\_data\['scores'\]\['description'\]}"  
\- Prominence: {article\_data\['scores'\]\['prominence'\]}  
\- Sentiment: {article\_data\['scores'\]\['sentiment'\]}

Question: Are these scores OBVIOUSLY WRONG, or within reasonable interpretation?

Note: The prompt instructions and body text may look similar \- that's expected. Focus on whether the SCORES make sense given the content.

Flag only if:  
\- Narrative is described but doesn't appear in article  
\- Prominence is high but narrative barely mentioned  
\- Sentiment contradicts clear article tone

Respond in JSON:  
{{  
  "status": "pass" or "flag",  
  "reasoning": "brief explanation",  
  "confidence": "high", "medium", or "low"  
}}  
"""  
      
    response \= openai.chat.completions.create(  
        model\="GPT-5",  
        messages\=\[  
            {"role": "system", "content": "You are a QA analyst. Flag only obviously incorrect scores."},  
            {"role": "user", "content": gpt\_prompt}  
        \],  
        response\_format\={"type": "json\_object"}  
    )  
    

    return json.loads(response.choices\[0\].message.content)

### **12.3 Preview UI**

html  
\<div class\="step-preview"\>  
  \<h3\>Step 8: Narrative Sanity Check\</h3\>  
  \<p\>Spot checking 10 rows per narrative using GPT-5...\</p\>  
    
  \<div class\="narrative-check"\>  
    \<h4\>Narrative 1: BusinessMomentum\</h4\>  
    \<p\>\<strong\>Status:\</strong\> ✓ 10/10 samples passed\</p\>  
  \</div\>  
    
  \<div class\="narrative-check"\>  
    \<h4\>Narrative 2: EventAffordability\</h4\>  
    \<p\>\<strong\>Status:\</strong\> ⚠️ 8/10 samples passed\</p\>  
    \<p\>\<strong\>Flagged:\</strong\> 2 articles for review\</p\>  
      
    \<div class\="flagged-row"\>  
      \<h5\>Flagged Article 1\</h5\>  
      \<p\>\<strong\>Record ID:\</strong\> rec078\</p\>  
      \<p\>\<strong\>Headline:\</strong\> "Concert Ticket Prices Soar Amid Inflation"\</p\>  
      \<p\>\<strong\>Issue:\</strong\> Description mentions "StubHub reducing fees" but article doesn't discuss fee reductions.\</p\>  
      \<p\>\<strong\>GPT Reasoning:\</strong\> The narrative description appears to reference different content than what's in the article. Possible copy-paste error or misalignment.\</p\>  
      \<button onclick\="viewFullArticle('rec078')"\>View Full Article\</button\>  
      \<button onclick\="acceptScore()"\>Accept Anyway\</button\>  
      \<button onclick\="flagForManualReview()"\>Flag for Manual Review\</button\>  
    \</div\>  
  \</div\>  
    
  \<button onclick\="proceedToFinal()"\>✓ Continue to Download\</button\>

\</div\>

---

## **13\. Step 9: Download Clean CSV & QA Report**

### **13.1 Generate QA Report**

python  
def generate\_qa\_report(qa\_session: Dict) \-\> str:  
    """  
    Generate comprehensive QA report summarizing all changes.  
      
    Args:  
        qa\_session: Dictionary tracking all QA operations  
      
    Returns: Markdown-formatted report  
    """  
    report \= f"""\# Data QA Report  
Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

\#\# Summary

\*\*Original Data:\*\*  
\- Total articles: {qa\_session\['original\_count'\]}

\*\*QA Processing:\*\*

\#\#\# Step 1: Non-Relevant Removal  
\- Articles removed: {qa\_session\['non\_relevant\_removed'\]}  
\- Remaining: {qa\_session\['after\_non\_relevant'\]}

\#\#\# Step 2-4: Deduplication  
\- Phase 1 (Exact): {qa\_session\['dedup\_phase1\_removed'\]} removed  
\- Phase 2 (High Similarity 97%+): {qa\_session\['dedup\_phase2\_removed'\]} removed  
\- Phase 3 (Medium Similarity 90-96%): {qa\_session\['dedup\_phase3\_removed'\]} removed  
\- Total duplicates removed: {qa\_session\['total\_dupes\_removed'\]}  
\- Remaining: {qa\_session\['after\_dedup'\]}

\#\#\# Step 5: Publication Scores  
\- Publications matched: {qa\_session\['pubs\_matched'\]}  
\- Publications manually scored: {qa\_session\['pubs\_manual'\]}  
\- Articles scored: {qa\_session\['articles\_scored'\]}

\#\#\# Step 6: Schema Validation  
\- Required columns: {qa\_session\['schema\_required\_cols'\]}  
\- Valid columns: {qa\_session\['schema\_valid\_cols'\]}  
\- Missing columns: {qa\_session\['schema\_missing\_cols'\]}  
\- Low fill rate warnings: {qa\_session\['schema\_warnings'\]}  
\- Status: {qa\_session\['schema\_status'\]}

\#\#\# Step 7: Entity Sanity Checks  
"""  
      
    for entity\_name, results in qa\_session\['entity\_checks'\].items():  
        report \+= f"\\n\*\*{entity\_name}:\*\*\\n"  
        report \+= f"- Samples checked: {results\['samples\_checked'\]}\\n"  
        report \+= f"- Passed: {results\['passed'\]}\\n"  
        report \+= f"- Flagged: {results\['flagged'\]}\\n"  
      
    report \+= "\\n\#\#\# Step 8: Narrative Sanity Checks\\n"  
      
    for narrative\_name, results in qa\_session\['narrative\_checks'\].items():  
        report \+= f"\\n\*\*{narrative\_name}:\*\*\\n"  
        report \+= f"- Samples checked: {results\['samples\_checked'\]}\\n"  
        report \+= f"- Passed: {results\['passed'\]}\\n"  
        report \+= f"- Flagged: {results\['flagged'\]}\\n"  
      
    report \+= f"""

\#\# Final Output

\*\*Clean Data:\*\*  
\- Total articles: {qa\_session\['final\_count'\]}  
\- Articles removed: {qa\_session\['total\_removed'\]}  
\- Retention rate: {qa\_session\['retention\_rate'\]:.1%}

\*\*Data Quality:\*\*  
\- Schema compliance: {qa\_session\['schema\_status'\]}  
\- Entity scoring: {qa\_session\['entity\_quality\_summary'\]}  
\- Narrative scoring: {qa\_session\['narrative\_quality\_summary'\]}

\---

\*\*Notes:\*\*  
{qa\_session.get('user\_notes', 'No additional notes.')}  
"""  
    

    return report

### **13.2 Save Outputs**

python  
def save\_qa\_outputs(  
    clean\_df: pd.DataFrame,  
    qa\_report: str,  
    company\_name: str,  
    input\_path: str  
) \-\> Dict\[str, str\]:  
    """  
    Save cleaned CSV and QA report.  
      
    Returns: {  
        'csv': path\_to\_cleaned\_csv,  
        'report': path\_to\_qa\_report  
    }  
    """  
    from pathlib import Path  
      
    *\# Determine output directory*  
    input\_dir \= Path(input\_path).parent  
      
    *\# Generate filenames*  
    timestamp \= datetime.now().strftime('%Y%m%d\_%H%M%S')  
    csv\_filename \= f"{company\_name}\_QA\_Clean\_{timestamp}.csv"  
    report\_filename \= f"{company\_name}\_QA\_Report\_{timestamp}.md"  
      
    csv\_path \= input\_dir / csv\_filename  
    report\_path \= input\_dir / report\_filename  
      
    *\# Save CSV*  
    clean\_df.to\_csv(csv\_path, index\=False)  
      
    *\# Save report*  
    with open(report\_path, 'w') as f:  
        f.write(qa\_report)  
      
    return {  
        'csv': str(csv\_path),  
        'report': str(report\_path)

    }

### **13.3 Download UI**

html  
\<div class\="step-preview"\>  
  \<h3\>QA Complete\!\</h3\>  
    
  \<div class\="summary-card"\>  
    \<h4\>Processing Summary\</h4\>  
    \<ul\>  
      \<li\>Original articles: 1,112\</li\>  
      \<li\>Non-relevant removed: 47\</li\>  
      \<li\>Duplicates removed: 89\</li\>  
      \<li\>Final clean articles: 976\</li\>  
      \<li\>Retention rate: 87.8%\</li\>  
    \</ul\>  
  \</div\>  
    
  \<div class\="quality-summary"\>  
    \<h4\>Quality Checks\</h4\>  
    \<ul\>  
      \<li\>✓ Schema validation: Passed (2 warnings)\</li\>  
      \<li\>✓ Entity scoring: 5 entities checked, 2 flags for review\</li\>  
      \<li\>✓ Narrative scoring: 6 narratives checked, 3 flags for review\</li\>  
    \</ul\>  
  \</div\>  
    
  \<div class\="downloads"\>  
    \<h4\>Download Files\</h4\>  
    \<button onclick\="downloadCSV()" class\="btn-download"\>  
      📥 Download Clean CSV (Ready for Pass 1\)  
    \</button\>  
    \<button onclick\="downloadReport()" class\="btn-download"\>  
      📄 Download QA Report  
    \</button\>  
  \</div\>  
    
  \<div class\="next-steps"\>  
    \<h4\>Next Steps\</h4\>  
    \<p\>The cleaned CSV is ready for \<strong\>Pass 1 (Vertical Analysis)\</strong\>.\</p\>  
    \<p\>Review the QA Report for details on all changes made.\</p\>  
  \</div\>  
    
  \<button onclick\="startNewQA()"\>🔄 Start New QA Session\</button\>

\</div\>

---

## **14\. Technology Stack**

### **14.1 Backend**

* **Framework**: Flask or FastAPI  
* **Python**: 3.9+  
* **Libraries**:  
  * `pandas` \- CSV processing  
  * `rapidfuzz` \- Fuzzy string matching  
  * `openai` \- GPT-5 API calls  
  * `pyyaml` \- Publication YAML parsing  
  * `python-dotenv` \- Environment variables

### **14.2 Frontend**

* **HTML/CSS/JavaScript**  
* **UI Framework**: Bootstrap or Tailwind CSS  
* **JavaScript**: Vanilla JS or Alpine.js for interactivity

### **14.3 External Dependencies**

* **OpenAI API**: Configured in `/Users/willvalentine/scrape_tracker.git/scrape_tracker/.env`  
* **Model**: GPT-5 (or o1-preview if available)

---

## **15\. API Endpoints**

POST /api/qa/upload  
\- Upload input CSV, company database, publication YAML, schema definition  
\- Return: session\_id

POST /api/qa/step1/preview  
\- body: {session\_id}  
\- Return: {count: 47, preview\_rows: \[...\]}

POST /api/qa/step1/apply  
\- body: {session\_id}  
\- Apply non-relevant removal  
\- Return: {status: "complete", remaining: 1065}

POST /api/qa/step2/preview  
\- Dedup Phase 1 preview  
\- Return: {clusters: \[...\]}

POST /api/qa/step2/apply  
\- body: {session\_id, action: "keep\_first" | "manual\_review"}  
\- Apply dedup Phase 1  
\- Return: {status: "complete"}

... (similar for steps 3-8)

POST /api/qa/spot-check/entity  
\- body: {session\_id, entity\_index, sample\_rows: \[...\]}  
\- Run GPT-5 spot checks  
\- Return: {results: \[...\]}

GET /api/qa/download/{session\_id}/csv  
\- Download cleaned CSV

GET /api/qa/download/{session\_id}/report

\- Download QA report

---

## **16\. Error Handling**

### **16.1 User-Facing Errors**

**Missing Required Columns**:

* Message: "Input CSV is missing required columns: Relevance\_Score, Publication, Headline"  
* Action: Block processing until fixed

**Empty CSV**:

* Message: "CSV has no data rows (only headers)"  
* Action: Block processing

**Invalid Publication YAML**:

* Message: "Could not parse publication.yaml \- check format"  
* Action: Block processing

**OpenAI API Error**:

* Message: "GPT-5 API call failed. Check your API key in .env file"  
* Action: Retry or skip spot checks

### **16.2 Warnings (Non-Blocking)**

**Low Fill Rate Columns**:

* Display warning but allow user to proceed

**Unmatched Publications**:

* Allow user to manually assign scores

**Spot Check Flags**:

* Show flagged rows but allow user to accept anyway

---

## **17\. Performance Optimization**

### **17.1 Fuzzy Matching**

* Use `rapidfuzz` (faster than `fuzzywuzzy`)  
* Process in batches of 1000 rows  
* Cache similarity calculations

### **17.2 GPT-5 API Calls**

* Batch multiple spot checks in single API call where possible  
* Use async requests for parallel processing  
* Implement rate limiting to avoid API throttling  
* Estimated cost per dataset: $0.10-$0.50 (20-50 spot checks)

### **17.3 Large Files**

* Stream CSV processing where possible  
* Use `chunksize` parameter in pandas for very large files  
* Progress indicators for long-running operations

---

## **18\. Testing Requirements**

### **18.1 Unit Tests**

**Test entity/narrative discovery**:

python  
def test\_discover\_entities():  
    headers \= \["1\_C\_Sent", "3\_C\_Prom", "5\_Orchestra\_Quality\_Score"\]  
    assert discover\_entity\_indices(headers) \== \[1, 3, 5\]

def test\_discover\_narratives():  
    headers \= \["O\_M\_2desc", "O\_M\_5prom"\]

    assert discover\_narrative\_indices(headers) \== \[2, 5\]

**Test prompt mapping**:

python  
def test\_get\_prompt\_for\_entity():  
    assert get\_prompt\_for\_entity(1) \== "Prompt2"  
    assert get\_prompt\_for\_entity(2) \== "Prompt2"  
    assert get\_prompt\_for\_entity(3) \== "Prompt3"

    assert get\_prompt\_for\_entity(9) \== "Prompt6"

**Test fuzzy matching**:

python  
def test\_fuzzy\_similarity():

    assert fuzz.ratio("StubHub Launches App", "StubHub Launches Application") \>= 90

### **18.2 Integration Tests**

**End-to-End QA Flow**:

1. Upload test CSV with known issues  
2. Run all 9 QA steps  
3. Verify cleaned CSV has expected row count  
4. Verify QA report contains all sections

### **18.3 GPT-5 Mock Testing**

For development/testing without API costs:

python  
class MockGPTClient:  
    def spot\_check(self, article, scores):  
        *\# Return mock responses for testing*

        return {"status": "pass", "reasoning": "Test mock", "confidence": "high"}

---

## **19\. Deployment Checklist**

* Flask/FastAPI app configured  
* OpenAI API key loaded from .env  
* File upload handling (CSV, YAML)  
* Session management for multi-step workflow  
* All 9 QA steps implemented  
* Dynamic entity/narrative discovery  
* Fuzzy deduplication (rapidfuzz)  
* GPT-5 spot check integration  
* Publication YAML parser  
* Schema validation  
* QA report generator  
* Download endpoints (CSV \+ report)  
* Error handling for all failure modes  
* Unit tests passing  
* Integration tests passing  
* User documentation

---

## **20\. Critical Reminders**

### **20.1 Never Hardcode**

**DO NOT hardcode**:

* Number of entities or narratives  
* Entity names or narrative names  
* Publication scores (always load from YAML)  
* Spot check thresholds without user configuration

### **20.2 Preview Every Change**

**NEVER apply changes without user approval**:

* Always show what will be deleted/modified  
* Allow user to review before applying  
* Provide "skip this step" option

### **20.3 Dynamic Discovery**

**Always discover from data**:

* Scan headers to find entity/narrative indices  
* Don't assume 5 entities and 6 narratives  
* Could be 2 entities, could be 50

### **20.4 Spot Check Tolerance**

**GPT-5 should flag only "obviously wrong" scores**:

* Not minor interpretation differences  
* Not "I would have scored it 2.5 instead of 3.0"  
* Only clear contradictions or impossibilities

---

## **21\. Example Complete Session**

User uploads:  
\- stubhub\_raw\_data.csv (1,112 rows)  
\- company\_database\_\_companies.csv  
\- publication.yaml  
\- schema\_def\_stubhub\_messaging\_study\_2025\_10\_01.csv

Step 1: Remove 47 non-relevant articles → 1,065 remain

Step 2: Remove 23 exact duplicates → 1,042 remain

Step 3: Remove 41 high-similarity duplicates (97%+) → 1,001 remain

Step 4: GPT-5 analyzes 15 medium-similarity clusters  
        \- 8 clusters \= same article (remove)  
        \- 7 clusters \= different (keep both)  
        → 25 removed → 976 remain

Step 5: Assign pub scores  
        \- 970 matched automatically  
        \- 6 unmatched → user assigns manually

Step 6: Schema validation  
        \- 60 required columns  
        \- 58 valid  
        \- 2 warnings (low fill rate)  
        → User proceeds with warnings

Step 7: Entity spot checks (5 entities × 10 samples \= 50 checks)  
        \- GPT-5 flags 2 articles  
        \- User reviews, accepts 1, flags 1 for manual review

Step 8: Narrative spot checks (6 narratives × 10 samples \= 60 checks)  
        \- GPT-5 flags 3 articles  
        \- User reviews, accepts all

Step 9: Download  
        \- Clean CSV: StubHub\_QA\_Clean\_20250115\_143022.csv (976 rows)  
        \- QA Report: StubHub\_QA\_Report\_20250115\_143022.md

Result: Ready for Pass 1 (Vertical Analysis)

---

## **End of QA Module Brief**

