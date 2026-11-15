# DAX measures

All measures live in the hidden-column table `_Measures`, grouped in display folders. Source of truth: `src/build_tmdl.py` (this file is generated from it). *Example* = value with no filter, checked in SQL.

Conventions: `CALCULATE` adds or replaces filters on top of the current filter context (a slicer, a visual's axis); `DIVIDE` returns BLANK instead of an error on a zero denominator; boolean filters such as `FactAward[IsED] = TRUE ()` are rewritten by DAX as `FILTER ( ALL ( FactAward[IsED] ), ... )`, so they replace any existing filter on that column only.

## 1 Awards

### ED Awards

```dax
ED Awards = CALCULATE ( COUNTROWS ( FactAward ), FactAward[IsED] = TRUE () )
```
Number of award rows (notice x lot x winning tender) won by a European Dynamics entity, alone or in a group.  
*Example:* 209  
Format: `#,0`

### All Awards

```dax
All Awards = COUNTROWS ( FactAward )
```
All award rows in the model: European Dynamics plus the CPV 72 market context of the same buyers and EU institutions.  
Format: `#,0`

### ED Award Value

```dax
ED Award Value = CALCULATE ( SUM ( FactAward[ValueSplitEUR] ), FactAward[IsED] = TRUE () )
```
Value of the lots won by European Dynamics, split equally between the winning tenders of a lot (a framework with 5 winners counts 1/5 of its value). Framework values are ceilings, not spending.  
*Example:* 2,071 M EUR  
Format: `€#,0.0,,M`

### All Award Value

```dax
All Award Value = SUM ( FactAward[ValueSplitEUR] )
```
Value of all lots in the model, each lot counted once (equal split summed over its winners).  
Format: `€#,0.0,,M`

### ED Ceiling Value

```dax
ED Ceiling Value = CALCULATE ( SUM ( FactAward[CountedValueEUR] ), FactAward[IsED] = TRUE () )
```
Full published value of lots where European Dynamics is among the winners, counted once per lot (no split). Upper bound; shown for transparency only.  
*Example:* 9,789 M EUR  
Format: `€#,0.0,,M`

### ED Median Award Value

```dax
ED Median Award Value = CALCULATE ( MEDIAN ( FactAward[ValueSplitEUR] ), FactAward[IsED] = TRUE () )
```
Median equal-split value of a European Dynamics award: robust to the very large framework ceilings.  
*Example:* 2,165,887 EUR  
Format: `€#,0`

### ED Buyers

```dax
ED Buyers = CALCULATE ( DISTINCTCOUNT ( FactAward[BuyerKey] ), FactAward[IsED] = TRUE () )
```
Distinct contracting authorities that awarded at least one lot to European Dynamics.  
*Example:* 88  
Format: `#,0`

### ED Repeat Buyers

```dax
ED Repeat Buyers = COUNTROWS ( FILTER ( VALUES ( DimBuyer[BuyerKey] ), [ED Awards] >= 2 ) )
```
Buyers with two or more European Dynamics awards in the current filter context (buyer loyalty).  
Format: `#,0`

### ED Repeat Buyer Rate

```dax
ED Repeat Buyer Rate = DIVIDE ( [ED Repeat Buyers], [ED Buyers] )
```
Share of European Dynamics buyers that awarded it at least twice.  
Format: `0%`

### ED Countries

```dax
ED Countries = CALCULATE ( DISTINCTCOUNT ( FactAward[CountryKey] ), FactAward[IsED] = TRUE () )
```
Distinct buyer countries (location of the contracting authority, so EU agencies count in their host country).  
Format: `#,0`

### ED Share from EU Institutions

```dax
ED Share from EU Institutions = DIVIDE ( CALCULATE ( [ED Awards], DimBuyer[BuyerSegment] = "EU institutions and agencies" ), [ED Awards] )
```
Share of European Dynamics awards whose buyer is an EU institution, agency or body.  
*Example:* 65%  
Format: `0%`

### ED Consortium Share

```dax
ED Consortium Share = DIVIDE ( CALCULATE ( [ED Awards], FactAward[EdRole] = "Consortium with partners" ), [ED Awards] )
```
Share of European Dynamics awards won together with companies outside the group.  
Format: `0%`

## 2 Market and competition

### ED Share of CPV 72 Value

```dax
ED Share of CPV 72 Value = DIVIDE ( CALCULATE ( [ED Award Value], DimCPV[IsITServices] = TRUE () ), CALCULATE ( [All Award Value], DimCPV[IsITServices] = TRUE () ) )
```
European Dynamics' equal-split value / value of all CPV 72 (IT services) lots of the same buyers and of EU institutions.  
Format: `0.0%`

### ED Share of CPV 72 Awards

```dax
ED Share of CPV 72 Awards = DIVIDE ( CALCULATE ( [ED Awards], DimCPV[IsITServices] = TRUE () ), CALCULATE ( [All Awards], DimCPV[IsITServices] = TRUE () ) )
```
Same share, counted in award rows instead of value.  
Format: `0.0%`

### ED Avg Offers

```dax
ED Avg Offers = CALCULATE ( AVERAGE ( FactAward[NumberOfOffers] ), FactAward[IsED] = TRUE () )
```
Average number of offers received on lots won by European Dynamics (where the notice states it).  
Format: `#,0.0`

### Market Avg Offers

```dax
Market Avg Offers = CALCULATE ( AVERAGE ( FactAward[NumberOfOffers] ), FactAward[IsED] = FALSE () )
```
Average number of offers on the other lots of the model (comparison base).  
Format: `#,0.0`

### ED Single-Offer Share

```dax
ED Single-Offer Share = DIVIDE ( CALCULATE ( COUNTROWS ( FactAward ), FactAward[IsED] = TRUE (), FactAward[NumberOfOffers] = 1 ), CALCULATE ( COUNTROWS ( FactAward ), FactAward[IsED] = TRUE (), NOT ISBLANK ( FactAward[NumberOfOffers] ) ) )
```
Share of European Dynamics lots that received one offer. One offer is not an anomaly in itself (e.g. negotiated procedures, specialised maintenance).  
*Example:* 12%  
Format: `0%`

### Market Single-Offer Share

```dax
Market Single-Offer Share = DIVIDE ( CALCULATE ( COUNTROWS ( FactAward ), FactAward[IsED] = FALSE (), FactAward[NumberOfOffers] = 1 ), CALCULATE ( COUNTROWS ( FactAward ), FactAward[IsED] = FALSE (), NOT ISBLANK ( FactAward[NumberOfOffers] ) ) )
```
Same share for the other lots of the model.  
*Example:* 20%  
Format: `0%`

### ED Framework Share

```dax
ED Framework Share = DIVIDE ( CALCULATE ( [ED Awards], FactAward[IsFramework] = TRUE () ), [ED Awards] )
```
Share of European Dynamics awards that are framework agreements.  
Format: `0%`

## 3 Time intelligence

### ED Awards YTD

```dax
ED Awards YTD = TOTALYTD ( [ED Awards], DimDate[Date] )
```
Year-to-date European Dynamics awards (calendar year).  
Format: `#,0`

### ED Awards PY

```dax
ED Awards PY = CALCULATE ( [ED Awards], SAMEPERIODLASTYEAR ( DimDate[Date] ) )
```
European Dynamics awards in the same period of the previous year.  
Format: `#,0`

### ED Awards YoY %

```dax
ED Awards YoY % = VAR cur = [ED Awards] VAR py = [ED Awards PY] RETURN IF ( NOT ISBLANK ( py ), DIVIDE ( cur - py, py ) )
```
Change versus previous year. 2026 is a partial year (data to mid-November).  
Format: `+0%;-0%;0%`

### ED Awards 3Y Moving Avg

```dax
ED Awards 3Y Moving Avg = VAR lastDate = MAX ( DimDate[Date] ) RETURN DIVIDE ( CALCULATE ( [ED Awards], DATESINPERIOD ( DimDate[Date], lastDate, -3, YEAR ) ), 3 )
```
Average yearly awards over the last three years ending at the current date context.  
Format: `#,0.0`

## 4 EU budget (FTS)

### FTS Contracted

```dax
FTS Contracted = SUM ( FactFts[ContractedEUR] )
```
European Commission legal commitments to European Dynamics entities, by year of commitment (FTS).  
*Example:* 380 M EUR  
Format: `€#,0.0,,M`

### FTS Est. Consumed

```dax
FTS Est. Consumed = SUM ( FactFts[EstConsumedEUR] )
```
Estimated consumed amount of those commitments (payments made until publication, as reported by FTS).  
Format: `€#,0.0,,M`

### FTS Consumption Rate

```dax
FTS Consumption Rate = DIVIDE ( [FTS Est. Consumed], [FTS Contracted] )
```
Estimated consumed / contracted.  
Format: `0%`

### FTS Top Department Share

```dax
FTS Top Department Share = DIVIDE ( MAXX ( VALUES ( DimDepartment[Department] ), [FTS Contracted] ), [FTS Contracted] )
```
Share of the largest Commission department in the contracted amount (concentration).  
Format: `0%`

### FTS Departments

```dax
FTS Departments = CALCULATE ( DISTINCTCOUNT ( FactFts[Department] ), FactFts[ContractedEUR] > 0 )
```
Commission departments with a positive commitment.  
Format: `#,0`

## 5 Service desk (SIMULATED)

### Requests

```dax
Requests = COUNTROWS ( FactServiceRequest )
```
SIMULATED citizen requests.  
Format: `#,0`

### SLA Met %

```dax
SLA Met % = DIVIDE ( CALCULATE ( COUNTROWS ( FactServiceRequest ), FactServiceRequest[IsSlaMet] = TRUE () ), CALCULATE ( COUNTROWS ( FactServiceRequest ), FactServiceRequest[IsClosed] = TRUE () ) )
```
Closed requests resolved within their SLA target (24 h high, 72 h normal, 120 h low).  
*Example:* 86.0%  
Format: `0.0%`

### SLA Gap vs 90% Target

```dax
SLA Gap vs 90% Target = [SLA Met %] - 0.9
```
Distance to the 90% SLA target set by the fictional ministry.  
Format: `+0.0%;-0.0%;0.0%`

### Median Resolution (h)

```dax
Median Resolution (h) = MEDIAN ( FactServiceRequest[ResolutionHours] )
```
Median hours from opening to closing (closed requests).  
Format: `#,0.0`

### P90 Resolution (h)

```dax
P90 Resolution (h) = PERCENTILE.INC ( FactServiceRequest[ResolutionHours], 0.9 )
```
90th percentile of resolution time: the slow tail citizens notice.  
Format: `#,0.0`

### Open Backlog

```dax
Open Backlog = CALCULATE ( COUNTROWS ( FactServiceRequest ), FactServiceRequest[IsClosed] = FALSE () )
```
Requests still open at the end of the simulated period.  
Format: `#,0`

### Avg Satisfaction

```dax
Avg Satisfaction = AVERAGE ( FactServiceRequest[Satisfaction] )
```
Average satisfaction score (1-5) of closed requests.  
Format: `0.00`

### Visible Agencies Label

```dax
Visible Agencies Label = VAR n = DISTINCTCOUNT ( DimAgency[AgencyCode] ) RETURN IF ( n = 1, "Agency view: " & SELECTEDVALUE ( DimAgency[AgencyName] ), "Ministry view: " & n & " agencies" )
```
Dynamic label: shows which agencies the current user may see (RLS check).  
Format: `text`

## Calculation group `Time Calc`

One definition of each time variant, applied to whatever measure is in the visual (`SELECTEDMEASURE ()`). Put `Time Calc[Period]` on columns of a matrix and any measure in values.

* **Selected period**: `SELECTEDMEASURE ()`
* **Previous year**: `CALCULATE ( SELECTEDMEASURE (), SAMEPERIODLASTYEAR ( DimDate[Date] ) )`
* **YoY change**: `VAR cur = SELECTEDMEASURE () VAR py = CALCULATE ( SELECTEDMEASURE (), SAMEPERIODLASTYEAR ( DimDate[Date] ) ) RETURN IF ( NOT ISBLANK ( py ), cur - py )`
* **YoY %**: `VAR cur = SELECTEDMEASURE () VAR py = CALCULATE ( SELECTEDMEASURE (), SAMEPERIODLASTYEAR ( DimDate[Date] ) ) RETURN IF ( NOT ISBLANK ( py ), DIVIDE ( cur - py, py ) )` (format "+0%;-0%;0%")
* **Year to date**: `CALCULATE ( SELECTEDMEASURE (), DATESYTD ( DimDate[Date] ) )`
* **3-year total**: `CALCULATE ( SELECTEDMEASURE (), DATESINPERIOD ( DimDate[Date], MAX ( DimDate[Date] ), -3, YEAR ) )`

## Field parameter `Axis`

A calculated table built with `NAMEOF`; a slicer on `Axis[Axis]` swaps the column used by the visuals that reference it: Buyer country (`DimCountry[CountryName]`), Buyer segment (`DimBuyer[BuyerSegment]`), CPV division (`DimCPV[Division]`), Procedure (`DimProcedure[ProcedureLabel]`), European Dynamics entity (`DimEntity[EntityName]`).
