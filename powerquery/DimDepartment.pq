// DimDepartment: Commission departments (Directorates-General, executive agencies) found in FtsStaging.
let
    Source = Table.Distinct(Table.SelectColumns(FtsStaging, {"department"})),
    Code = Table.AddColumn(Source, "DepartmentCode", each Text.Trim(Text.BeforeDelimiter([department], " - ")), type text),
    Name = Table.AddColumn(Code, "DepartmentName", each Text.Trim(Text.AfterDelimiter([department], " - ")), type text),
    Renamed = Table.RenameColumns(Name, {{"department", "Department"}})
in
    Renamed
