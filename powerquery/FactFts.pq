// FactFts: one row per FTS line (year x legal commitment x budget line x beneficiary). PUBLIC DATA.
// Amounts are LEGAL COMMITMENTS by year (contracted amounts), not cash payments.
let
    Source = FtsStaging,
    DateKey = Table.AddColumn(Source, "DateKey", each [year] * 10000 + 101, Int64.Type),
    Consortium = Table.AddColumn(DateKey, "IsConsortium", each Text.StartsWith([BeneficiaryClean], "CONSORTIUM"), type logical),
    Selected = Table.SelectColumns(Consortium, {"year", "DateKey", "EntityCode", "department", "programme_name",
        "contract_type", "expense_type", "IsConsortium", "contracted_eur", "est_consumed_eur"}),
    Renamed = Table.RenameColumns(Selected, {{"year", "Year"}, {"department", "Department"}, {"programme_name", "Programme"},
        {"contract_type", "ContractType"}, {"expense_type", "ExpenseType"}, {"contracted_eur", "ContractedEUR"},
        {"est_consumed_eur", "EstConsumedEUR"}})
in
    Renamed
