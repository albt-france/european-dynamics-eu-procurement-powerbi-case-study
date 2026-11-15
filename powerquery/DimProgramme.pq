// DimProgramme: EU budget programmes found in FtsStaging, grouped into families for the report.
let
    Source = Table.Distinct(Table.SelectColumns(FtsStaging, {"programme_name"})),
    Family = Table.AddColumn(Source, "ProgrammeFamily", each
        let p = [programme_name] in
        if Text.Contains(p, "Horizon") then "Research (Horizon)"
        else if Text.Contains(p, "administrative expenditure") or Text.Contains(p, "Information and communication technology") then "Commission administration and IT"
        else if Text.Contains(p, "Customs") or Text.Contains(p, "Fiscalis") then "Customs and taxation"
        else if Text.Contains(p, "Digital Europe") or Text.Contains(p, "Connecting Europe") or Text.Contains(p, "ISA") then "Digital programmes"
        else "Other programmes", type text),
    Renamed = Table.RenameColumns(Family, {{"programme_name", "Programme"}})
in
    Renamed
