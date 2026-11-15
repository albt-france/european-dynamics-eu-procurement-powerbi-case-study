// QualityChecks: results of sql/06_quality_checks.sql, exported by src/load_sql.py (documentation page).
let
    Source = Csv.Document(File.Contents(DataFolder & "qa_checks.csv"), [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),
    Promoted = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),
    Typed = Table.TransformColumnTypes(Promoted, {{"CheckId", type text}, {"CheckName", type text}, {"Actual", type number},
        {"Expected", type text}, {"Status", type text}, {"Note", type text}}, "en-US")
in
    Typed
