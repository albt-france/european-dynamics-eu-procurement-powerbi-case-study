# Accessibility checklist (report pages 1-5)

Based on Microsoft's *Design Power BI reports for accessibility* guidance and WCAG 2.1 AA. Status: **done** = set in
the generated report files (`src/build_report_pages.py`, `powerbi/theme.json`); **to verify** = needs a check in
Power BI Desktop / the Service with a screen reader.

| # | Check | Status | How |
|---|---|---|---|
| 1 | **Alt text** on every data visual | done | each visual's `altText` describes what it shows and where the same numbers are readable (e.g. the map points to the bar chart) |
| 2 | **Titles say what to read**; page title = the conclusion, with numbers | done | titles generated from warehouse figures |
| 3 | **Tab order** follows reading order (title, subtitle, navigation, KPI cards left to right, charts top-left to bottom-right) | done | `tabOrder` set from creation order |
| 4 | **No information by colour alone** | done | data labels on bars, legends where two series, ED vs other also named in titles; blue / grey pairs differ in lightness, not only hue |
| 5 | **Contrast** of text | done | text #0B0B0B / #52514E on #FCFCFB (ratios about 19:1 and 7.9:1, above 4.5:1); footer #898781 at 9 pt is the one exception, used only for source notes |
| 6 | **Font sizes**: titles 22 pt, subtitles 12 pt, visual text 11-12 pt, KPI values 26 pt | done | theme and visual objects |
| 7 | **Consistent layout**: same header, navigation and footer on every page | done | `Page.header` / `footer` |
| 8 | **Page navigation** without the mouse (page navigator buttons + Ctrl+F6 / Tab) | done (navigator) / to verify (keyboard pass) | page navigator visual on every page |
| 9 | Tables available for charts (*Show as a table*, Alt+Shift+F11) | to verify | default Power BI behaviour, not disabled |
| 10 | Screen reader pass (Narrator / NVDA) on each page | to verify | read title, alt texts, then a table visual |
| 11 | Map not the only way to read geography | done | bar chart "Awards by buyer country" next to the map |
| 12 | SIMULATED page clearly labelled in its title, tag and footer | done | text, not colour |
| 13 | Tooltips do not hold essential information | done | tooltip page repeats figures available on the page |
| 14 | Hidden documentation page excluded from navigation | done | `visibility: HiddenInViewMode` |
