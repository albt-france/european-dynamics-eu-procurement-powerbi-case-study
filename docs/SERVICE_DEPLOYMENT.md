# Power BI Service: workspaces, access, RLS, refresh, deployment

**Status:** designed and tested in Power BI Desktop; Service deployment documented (no Service tenant was used for
this case study). Everything below is the set-up I would apply for a public-sector client.

## 1. Workspaces and deployment pipeline

| Stage | Workspace | Who works there | Data source parameters |
|---|---|---|---|
| Development | `Procurement Analytics [Dev]` | BI developers | Dev SQL Server, Dev PostgreSQL |
| Test | `Procurement Analytics [Test]` | developers + business testers (UAT) | Test databases (anonymised copy if needed) |
| Production | `Procurement Analytics` | nobody edits by hand; content arrives by pipeline | Production databases |

* A **deployment pipeline** (Dev -> Test -> Prod) moves the semantic model, report and dataflows; **deployment rules**
  switch `ServerName` / `DatabaseName` (and the PostgreSQL parameters) per stage, so the same `.pbip` serves all three.
* The `.pbip` (TMDL + PBIR) lives in git; with **Git integration** the Dev workspace is synced to a branch, and changes
  reach Test only through a reviewed pull request and the pipeline.
* One workspace per subject area and audience, not one per report; production workspaces assigned to a capacity
  (Premium / Fabric) if the audience includes many Free-licence readers.

## 2. Roles and access (least privilege)

| Workspace role | Can | Given to |
|---|---|---|
| Admin | manage access, delete workspace, pipeline settings | 2 named BI leads (never one person only) |
| Member | publish, share, update the app | BI developers (Dev / Test only) |
| Contributor | create and edit content, no sharing | report authors in Dev |
| Viewer | read content, RLS applies | business testers in Test |

* Access is granted to **Microsoft Entra security groups**, never to individuals (joiners / leavers handled in one place).
* Production readers do **not** get a workspace role: they consume the **Power BI app** (audiences per department),
  so RLS always applies and they cannot see draft content. (Workspace Admin / Member / Contributor bypass RLS - another
  reason readers are not given those roles.)
* Build permission on the semantic model only for the analysts who need to create their own reports on it.
* Export to Excel limited to "summarised data"; sensitivity labels (e.g. *Internal*) inherited from the model; tenant
  settings for publish-to-web disabled.

## 3. Row-level security (demonstrated on the SIMULATED service desk page)

* Role **Agency** (dynamic): `DimAgency[AgencyCode] IN CALCULATETABLE ( VALUES ( SecUserAgency[AgencyCode] ),
  SecUserAgency[UserPrincipalName] = USERPRINCIPALNAME () )`. The mapping table `SecUserAgency` is maintained in the
  warehouse (`sim.SecUserAgency`), so a new agency user is a row, not a model change. A user mapped to two agencies
  (`deputy.director@...` in the demo) sees both.
* Role **Ministry (all agencies)**: no filter, for the ministry's management.
* In the Service: semantic model > Security > add the Entra group "Agency users" to *Agency* and "Ministry management"
  to *Ministry (all agencies)*; test with *Test as role* and a sample account.
* **Desktop test procedure**: Modeling > View as > *Other user* `tax.lead@ministry.example` + role *Agency* ->
  expected: the label card shows "Agency view: Tax Administration Agency" and all visuals filter to that agency;
  `deputy.director@ministry.example` -> two agencies; role *Ministry (all agencies)* -> six. The same filter logic was
  checked in SQL (`sim.SecUserAgency` join: 1, 1, 1, 1, 1, 1 and 2 agencies per account); the Desktop screenshot is
  in `docs/img/` once taken.
* The public TED / FTS pages are not filtered (public data); object-level security could hide `SecUserAgency` columns
  from report authors if needed.

## 4. Gateway and refresh

* **On-premises data gateway** (standard mode, clustered for high availability) on a server that reaches SQL Server
  and PostgreSQL; data source credentials stored in the gateway (Windows / database account with read access to the
  `pbi` schema only).
* **Scheduled refresh**: dataflows at 05:00, semantic model at 06:00 (after the warehouse ETL at 04:00), failure
  e-mails to the BI group.
* **Incremental refresh** on `FactAward` (policy: archive 11 years, refresh 2 months, by publication date). It works
  because the date filter folds to SQL Server (see `DATAFLOWS.md`).
* FTS is yearly: refresh the FTS dataflow when the Commission publishes a new year.

## 5. Monitoring

* Refresh history and the *Monitoring hub*; the Fabric capacity metrics app if on a capacity.
* Data-quality results (`qa.CheckResult`) are part of the model: a FAIL row can drive a data alert to the BI group.
* Usage metrics per report to retire pages nobody reads.

## 6. Checklist before go-live

- [ ] RLS tested with real accounts from each group (*Test as role*)
- [ ] Deployment rules set for every parameter, pipeline compare shows no unexpected diff
- [ ] Gateway data sources mapped in Test and Prod
- [ ] App audiences configured, workspace roles = groups only
- [ ] Accessibility checklist passed (`ACCESSIBILITY.md`), Performance Analyzer under target (`PERFORMANCE.md`)
- [ ] Sensitivity label and endorsement (*Promoted*, then *Certified* by the data owner)
