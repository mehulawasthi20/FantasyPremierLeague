# FPL Recommendation System

An intelligent Fantasy Premier League recommendation system that analyzes your team and suggests optimal transfers and captains using data from official FPL API and expert sources.

## Quick Start

### 1. Installation

```bash
pip install requests pandas beautifulsoup4 fuzzywuzzy python-levenshtein
```

### 2. Setup

**Find your team ID:**
- Go to https://fantasy.premierleague.com/
- Click "Points" → URL shows: `.../entry/123456/...`
- Your team ID is `123456`

**Make team public:**
- FPL website → Click your name → Gameweek history → Configure leagues → Make team visible.

### 3. Configuration

Edit `fpl_recommender.py`:

```python

TEAM_ID = 123456  # Your team ID
SCOUT_URL = "https://www.premierleague.com/en/news/XXXXX/scout-selection-best-fantasy-team-for-gameweek-X"
```

**Finding Scout URL (Weekly):**
1. Go to https://www.premierleague.com/news
2. Search "Scout Selection Gameweek X"
3. Copy full URL
4. Update `SCOUT_URL` in code

### 4. Run

```bash
python fpl_recommender.py
```

**First run:** 70-140 seconds (scraping data)  
**Subsequent runs:** 10-20 seconds (using cache)

---

## What You Get

### Transfer Recommendations
```
1. [MID] Transfer Suggestion: [✓ 4 mentions]
   OUT: Player A (Team X)  £6.0m | Score: 5.2 | Form: 3.5
   IN:  Player B (Team Y)  £6.5m | Score: 8.9 | Form: 7.8
   Improvement: +3.7 points | Cost: £+0.5m
```

### Captain Recommendations
```
1. Mohamed Salah (MID) ⭐ WEB PICK
   Fixture: vs NFO (H) | Difficulty: 2/5
   Captain Score: 8.75/10 | Expected Points: 14.2
   Why: Expert captain pick | Great fixture | Home advantage
```

### Current Squad Analysis
- Player scores based on form, fixtures, and expert opinion
- Next opponent and fixture difficulty
- Web consensus for each player

---

## Features

**Data Sources:**
- Official FPL API (live stats, fixtures, prices)
- Official PL Scout Selection ⭐ (weekly XI)
- Fantasy Football Scout
- Fantasy Football Hub
- FPL Focal
- Fantasy Football Fix

**Analysis:**
- Multi-factor player scoring (form, fixtures, history, experts)
- Fixture difficulty rating (next 5 gameweeks)
- Historical performance vs opponents
- Web expert consensus
- Injury/availability tracking
- Template vs differential strategy

**Smart Features:**
- 6-hour cache (faster subsequent runs)
- Fuzzy player name matching
- Budget constraint handling
- Team composition rules (max 3 per club)

---

## Weekly Workflow

**Thursday (After Scout Selection Published):**
1. Find Scout URL at https://www.premierleague.com/news
2. Update `SCOUT_URL` in `fpl_recommender.py`
3. Run: `python fpl_recommender.py`
4. Review transfer suggestions

**Friday (Before Deadline):**
1. Quick run for final check
2. Confirm captain choice
3. Make transfers in FPL

---

## File Structure

```
fpl_project/
├── fpl_recommender.py      # Main system (RUN THIS)
├── fpl_web_scraper.py      # Multi-source scraping
├── fpl_scout_scraper.py    # Official Scout scraper
└── .fpl_cache/             # Auto-generated cache
```

---

## Configuration Options

### Disable Web Scraping (Faster)
```python
USE_WEB_DATA = False  # 90% faster but less comprehensive
```

### Force Fresh Data
```python
USE_CACHE = False  # Ignore cache, fetch everything fresh
```

### Position-Specific Transfers
```python
suggestions = recommender.suggest_transfers(position_filter='MID')
```

### Clear Cache
```python
recommender.clear_cache()
# Or delete: .fpl_cache/ folder
```

---

## Troubleshooting

### "Error fetching team data"
- Make sure team is public
- Verify team ID is correct

### "KeyError: 'fixtures'"
```bash
# Clear cache and run again
rm -rf .fpl_cache/
python fpl_recommender.py
```

### "Module not found"
```bash
pip install requests pandas beautifulsoup4 fuzzywuzzy python-levenshtein
```

### "No recommendations found"
- Your team might already be optimal!
- Try: `suggestions = recommender.suggest_transfers(num_transfers=5)`

### Wrong Gameweek
```python
# System auto-detects next gameweek
# If wrong, clear cache:
recommender.clear_cache()
```

---

## Understanding Scores

**Player Score (0-10):**
- 8.0+: Excellent choice
- 6.0-8.0: Good option  
- Below 6.0: Risky pick

**Improvement Score:**
- 3.0+: Strong upgrade
- 1.5-3.0: Good upgrade
- Below 1.0: Marginal gain

**Fixture Difficulty (FDR 1-5):**
- 1-2: Easy fixtures ✅
- 3: Medium fixtures ⚠️
- 4-5: Hard fixtures ❌

---

## Advanced Usage

### Compare Multiple Strategies
```python
# Get more transfer options
all_suggestions = recommender.suggest_transfers(num_transfers=5)

# Check specific player
player = recommender.fuzzy_match_player('Salah')
score = recommender.calculate_player_score(player)
```

### Get Detailed Captain Analysis
```python
# Top 10 captain options
captain_options = recommender.suggest_captain(top_n=10)

# Conservative (high ownership)
safe_captain = max(captain_options, key=lambda x: x['selected_by'])

# Differential (low ownership)
diff_captain = min(captain_options, key=lambda x: x['selected_by'])
```

---

## Tips for Success

1. **Update Scout URL Weekly** - Takes 30 seconds, huge impact.
2. **Run Thursday** - After team news, before price changes.
3. **Use Cache** - Much faster, respects rate limits.
4. **Cross-Reference** - System is a tool, apply your judgment.
5. **Track Performance** - Note hits/misses to build confidence.

---

## Key Metrics

**Scoring Weights:**
- Form: 25%
- Fixtures: 20%
- Expert Consensus: 20%
- Historical vs Opponent: 15%
- Season Points: 12%
- ICT Index: 8%

**Captain Weights:**
- Next Fixture: 40%
- Form: 25%
- Historical: 20%
- Expert Picks: 15%

---

## Support

**Common Issues:**
- Team not public → FPL settings
- Wrong gameweek → Clear cache
- Slow performance → Enable cache
- Scout URL not working → Verify in browser

**Best Practices:**
- Run once per gameweek
- Update Scout URL weekly
- Clear cache if data seems stale
- Use web data for better recommendations

---

## What Makes This System Different

✅ **Multi-source** - Combines 6 expert sources  
✅ **Official backing** - Includes PL Scout Selection  
✅ **Intelligent** - Fuzzy matching, smart caching  
✅ **Comprehensive** - Transfers, captains, differentials  
✅ **Fast** - Caches data for quick reruns  
✅ **Transparent** - Shows reasoning for each pick  

---

## Quick Reference

```bash
# Standard run
python fpl_recommender.py

# Clear cache
rm -rf .fpl_cache/

# Test Scout scraper only
python fpl_scout_scraper.py
```

**Weekly checklist:**
- [ ] Find Scout Selection URL.
- [ ] Update `SCOUT_URL` in code.
- [ ] Run system.
- [ ] Review transfers.
- [ ] Note captain pick.
- [ ] Make FPL transfers.
- [ ] Set captain.

---

## Version

**v1.0** - Current
- Transfer recommendations.
- Captain analysis.
- 5 expert sources + Official Scout.
- Smart caching.
- Fuzzy matching.
- Fixture analysis.

---