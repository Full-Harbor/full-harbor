# Quiet Yield Methodology

**Full Harbor Research Brief · March 2026**

---

## What Is Quiet Yield?

Every sailing and yacht club runs on two economies simultaneously.

The **visible economy** appears on IRS Form 990: paid staff salaries, program fees, dock revenues, regatta income. Funders, auditors, and boards see this economy clearly.

The **invisible economy** never appears on any balance sheet. It is the labor of the volunteer race officer who runs Wednesday-night racing 40 times a year, the parent who coordinates carpools and snack schedules for junior sailing, the treasurer who keeps the books, the webmaster who maintains the club site. This labor is real. It has a market price. It simply goes uncounted.

**Quiet Yield** is our term for the gap between what that volunteer labor is *worth* at market rates and what clubs actually *pay* for it — which is usually $0.

---

## Why It Matters

Quiet Yield makes the invisible legible for three audiences:

1. **Funders and grantors** — want to understand the true cost basis of sailing programs, not just what appears on a 990.
2. **Club boards and executives** — need to understand the fragility embedded in volunteer dependency and what it would cost to professionalize key functions.
3. **Equity advocates** — can use Quiet Yield to quantify the uncompensated labor burden that falls disproportionately on certain communities and demographics.

---

## Data Sources

### BLS Occupational Employment and Wage Statistics (OEWS)

All wage benchmarks are drawn from the Bureau of Labor Statistics **Occupational Employment and Wage Statistics** survey, published annually under the [BLS OEWS program](https://www.bls.gov/oes/).

The OEWS survey collects data from approximately 1.1 million establishments annually, covering 800+ detailed occupations across all industry sectors. It is the standard national reference for occupation-level wage benchmarking.

**Base data: BLS OEWS May 2024 (national medians)**

The calculator uses national median hourly wages as the appropriate benchmark because:
- Sailing clubs operate across all 50 states; national medians avoid geographic cherry-picking.
- Volunteer labor substitutes for professional labor regardless of local market conditions.
- The national median is a well-understood, citable standard.

The `--bls-api` flag fetches live OEWS data from the [BLS Public Data API v2](https://api.bls.gov/publicAPI/v2/timeseries/data/). When the API is unavailable, the calculator falls back to hardcoded May 2024 values automatically — no silent failures.

---

## Role-to-SOC Mapping

Each volunteer role is mapped to the closest BLS Standard Occupational Classification (SOC) code. The mapping is intentionally conservative — we use the closest professional equivalent, not the highest-paying plausible comparator.

| Club Role | BLS Occupation | SOC Code | May 2024 Median Hourly |
|-----------|---------------|----------|------------------------|
| Race Officer / Race Committee | Meeting, Convention, and Event Planners | 13-1121 | $24.68 |
| Youth Sailing Director | Recreation and Fitness Studies Teachers, Postsecondary | 25-1193 | $33.24 |
| Sailing Coach | Coaches and Scouts | 27-2022 | $22.43 |
| Club Treasurer (volunteer) | Financial Managers | 11-3031 | $70.68 |
| Club Secretary / Administrator | Executive Secretaries and Executive Administrative Assistants | 43-6011 | $30.84 |
| Newsletter Editor / Communications | Public Relations Specialists | 27-3031 | $31.20 |
| Volunteer Webmaster | Web Developers | 15-1254 | $40.40 |
| Fleet Captain / Program Coordinator | Social and Community Service Managers | 11-9151 | $37.37 |
| Junior Sailing Program Parent Volunteer | Education, Training, and Library Workers, All Other | 25-9099 | $18.50 |
| Mark Layer / Safety Boat Operator | Sailors and Marine Oilers | 53-5011 | $23.15 |
| Regatta Chair / Event Director | Meeting, Convention, and Event Planners | 13-1121 | $24.68 |
| Board Member / Director (volunteer) | Chief Executives | 11-1011 | $104.17 |

*Sources: BLS OEWS May 2024 national data. [https://www.bls.gov/oes/current/oes_nat.htm](https://www.bls.gov/oes/current/oes_nat.htm)*

---

## Calculation Method

For each volunteer role:

```
Total Hours  = Volunteers × Hours per person per year
Market Value = BLS Median Hourly Wage × Total Hours
Quiet Yield  = Market Value − Actual Compensation Paid
```

At the club level:

```
Club Quiet Yield = Σ(Quiet Yield for each role)
Quiet Yield as % of Revenue = Club Quiet Yield ÷ Reported 990 Revenue × 100
```

### Default Role Assumptions

The default model assumes a mid-sized Texas Gulf Coast yacht club with active racing and junior sailing programs:

| Role | Volunteers | Hours/Person/Year | Total Hours |
|------|-----------|-------------------|-------------|
| Race Officers | 8 | 80 | 640 |
| Safety Boat / Mark Layers | 6 | 60 | 360 |
| Junior Sailing Committee Chair | 1 | 200 | 200 |
| Junior Program Parent Volunteers | 12 | 40 | 480 |
| Regatta Chairs | 3 | 60 | 180 |
| Club Treasurer | 1 | 120 | 120 |
| Newsletter Editor | 1 | 60 | 60 |
| Volunteer Webmaster | 1 | 80 | 80 |
| Fleet Captains | 4 | 50 | 200 |
| Board Members | 8 | 40 | 320 |
| **TOTAL** | **46** | | **2,640** |

These assumptions are calibrated through interviews with club managers and officers at Gulf Coast racing clubs. They are conservative — typical active racing clubs likely exceed these hour estimates.

---

## Findings: TX Gulf Coast Reference Clubs (2023)

Using default role assumptions and 990 revenue data from Harbor Commons:

| Club | Quiet Yield / Year | Volunteer Hours | % of Reported Revenue |
|------|-------------------|-----------------|----------------------|
| Lakewood Yacht Club | $98,494 | 2,640 | 1.4% |
| Houston Yacht Club | $98,494 | 2,640 | 3.1% |
| Texas Corinthian YC | $98,494 | 2,640 | n/a (revenue pending) |

**Interpretation:** HYC carries proportionally twice the quiet yield burden as LYC relative to its reported revenue — not because it has more volunteers, but because its revenue base is smaller. Smaller clubs absorb the same invisible labor load but have fewer dollars to show for it.

---

## The Funder Argument

> "Every sailing club in America is absorbing roughly $98,000/year in professional-equivalent labor through volunteers. Multiply by 1,300 clubs nationally: **$127 million/year in invisible infrastructure labor** that never appears on any balance sheet.
>
> Full Harbor's shared services model converts Quiet Yield into durable capacity — by making the invisible visible, quantifying it precisely, and providing clubs with the tools to act on it."

The $127M national estimate uses:
- 1,300 clubs (conservative estimate from US Sailing + NOAA recreational boating data)
- $98,494 Quiet Yield per club (default model, 2024 BLS wages)
- 1,300 × $98,494 = **$128M** (rounded to $127M for conservatism)

---

## Limitations and Caveats

1. **Hours are estimated.** The default model uses field-research estimates, not time-tracking data. Actual volunteer hours vary significantly by club size, culture, and activity level.

2. **National median wages may overstate rural club Quiet Yield.** A race officer in rural Michigan is not literally competing for wages with event planners in New York. However, using regional wages would require club-level geographic data that is not consistently available across all 1,300 clubs, and would understate the burden for high-cost-of-living areas.

3. **The SOC mapping is an approximation.** "Race Officer" is not a BLS occupation. Meeting, Convention, and Event Planners is the closest professional equivalent. The mapping intentionally errs toward comparables *already employed* in club contexts (professional race officers, paid event directors) rather than aspirational comparisons.

4. **Board member Quiet Yield is sensitive to hour assumptions.** At $104.17/hr, board members are the highest-rate role. A change of ±10 hours per person has a $8,334 impact on total Quiet Yield. Clubs with large, active boards will see this figure vary significantly.

5. **Quiet Yield ≠ cost to replace.** If a club were to professionalize all volunteer roles, it would not hire 46 separate professionals. The Quiet Yield figure represents the *market value of the labor*, not a staffing plan.

---

## Using the Calculator

```bash
# Single club report (uses hardcoded May 2024 BLS values)
python3 quiet_yield.py --club lyc

# All three TX reference clubs, individual reports + comparison table
python3 quiet_yield.py --club all

# Comparison table only
python3 quiet_yield.py --compare-all --state TX

# Fetch live BLS OEWS data (falls back to hardcoded if API unavailable)
python3 quiet_yield.py --club hyc --bls-api

# Interactive custom role calculator
python3 quiet_yield.py --custom

# JSON output for downstream use
python3 quiet_yield.py --club lyc --json
```

Set `BLS_API_KEY` environment variable or use `--bls-api-key` to increase BLS API rate limits.

---

## Citation

When citing Quiet Yield figures in grant applications or reports:

> Full Harbor (2026). *Quiet Yield: Quantifying the Invisible Volunteer Labor Economy of American Sailing Clubs.* Methodology based on BLS Occupational Employment and Wage Statistics (OEWS), May 2024 national medians. Available at: https://github.com/Full-Harbor/full-harbor

BLS citation:
> U.S. Bureau of Labor Statistics. (2024). *Occupational Employment and Wage Statistics, May 2024.* U.S. Department of Labor. https://www.bls.gov/oes/

---

*Questions: contact the Full Harbor practitioner. This document is maintained in `docs/research/quiet-yield-methodology.md`.*
