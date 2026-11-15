/* =====================================================================================================
   02  Reference data (hand-maintained, versioned in git)
   - ref.Entity / ref.EntityAlias : name resolution for European Dynamics entities. Raw winner names in TED
     and FTS come in dozens of spellings ("European Dynamics Luxembourg S.A.", "ED LUXEMBOURG",
     "ΕΥΡΩΠΑΪΚΗ ΔΥΝΑΜΙΚΗ ΑΕ", typos such as "European Dyamics"). Each alias is a LIKE pattern applied to the
     normalised name (dwh.fn_NormName); the lowest priority number wins.
   - ref.Procedure, ref.BuyerType : map the legacy TED codes and the eForms codes to one label list.
   - ref.LegalFormToken : company legal forms, used to keep supplier names only when they are organisations.
   ===================================================================================================== */
USE EuroDynDW;
GO
DROP TABLE IF EXISTS ref.EntityAlias;
DROP TABLE IF EXISTS ref.Entity;
CREATE TABLE ref.Entity (
    EntityCode   VARCHAR(10)   NOT NULL CONSTRAINT PK_refEntity PRIMARY KEY,
    EntityName   NVARCHAR(120) NOT NULL,
    EntityCountry CHAR(3)      NULL,
    EntityKind   NVARCHAR(40)  NOT NULL
);
INSERT ref.Entity VALUES
 ('NONE', N'Not European Dynamics',                     NULL,  N'Other supplier'),
 ('ED-GR', N'European Dynamics SA (Greece)',             'GRC', N'European Dynamics entity'),
 ('ED-LU', N'European Dynamics Luxembourg SA',           'LUX', N'European Dynamics entity'),
 ('ED-BE', N'European Dynamics Belgium SA',              'BEL', N'European Dynamics entity'),
 ('ED-DE', N'European Dynamics Deutschland GmbH',        'DEU', N'European Dynamics entity'),
 ('ED-UK', N'European Dynamics UK Ltd',                  'GBR', N'European Dynamics entity'),
 ('ED-CH', N'European Dynamics Swiss AG',                'CHE', N'European Dynamics entity'),
 ('ED-CO', N'European Dynamics consortium (unspecified)', NULL, N'European Dynamics group label'),
 ('ED-XX', N'European Dynamics (entity not specified)',  NULL,  N'European Dynamics entity');

CREATE TABLE ref.EntityAlias (
    AliasId     INT IDENTITY(1,1) CONSTRAINT PK_refEntityAlias PRIMARY KEY,
    Pattern     NVARCHAR(100) NOT NULL,     -- LIKE pattern on dwh.fn_NormName(name)
    EntityCode  VARCHAR(10)   NOT NULL CONSTRAINT FK_alias_entity REFERENCES ref.Entity (EntityCode),
    Priority    TINYINT       NOT NULL,
    Note        NVARCHAR(200) NULL
);
INSERT ref.EntityAlias (Pattern, EntityCode, Priority, Note) VALUES
 (N'%EUROPEAN DY%MICS%LUXEMBOURG%', 'ED-LU', 10, N'all Luxembourg spellings'),
 (N'%ED LUXEMBOURG%',               'ED-LU', 11, N'FTS short name "ED LUXEMBOURG"'),
 (N'%EUROPEAN DYNAMICS LU %',       'ED-LU', 12, N'"European Dynamics LU"'),
 (N'%EUROPEAN DYNAMICS LU',         'ED-LU', 12, NULL),
 (N'%EUROPEAN DY%MICS%BELGIUM%',    'ED-BE', 20, NULL),
 (N'%EUROPEAN DY%MICS%DEUTSCHLAN%', 'ED-DE', 30, N'includes typo "Deutschlang"'),
 (N'%EUROPEAN DY%MICS%SWISS%',      'ED-CH', 40, NULL),
 (N'%EUROPEAN DY%MICS%UK %',        'ED-UK', 50, NULL),
 (N'%EUROPEAN DY%MICS%UK',          'ED-UK', 50, NULL),
 (N'%EUROPEAN DY%MICS%ADVANCE%',    'ED-GR', 60, N'Greek parent company, long legal name'),
 (N'%ΔΥΝΑΜΙΚ%',                     'ED-GR', 61, N'Greek-script name'),
 (N'%EUROPEAN DY%MICS GR%',         'ED-GR', 62, N'"European Dynamics GR"'),
 (N'%EUROPEAN DY%MICS S A%',        'ED-GR', 63, N'"European Dynamics S.A." (normalised to S A)'),
 (N'%EUROPEAN DY%MICS SA%',         'ED-GR', 63, NULL),
 (N'CONSORTIUM%EUROPEAN DY%MICS%',  'ED-CO', 80, N'group label without the member entity'),
 (N'%EUROPEAN DY%MICS%CONSORTIUM%', 'ED-CO', 80, NULL),
 (N'%EUROPEAN DY%MICS%',            'ED-XX', 99, N'catch-all, entity not stated');

DROP TABLE IF EXISTS ref.[Procedure];
CREATE TABLE ref.[Procedure] (
    SourceCode      VARCHAR(20)  NOT NULL CONSTRAINT PK_refProcedure PRIMARY KEY,  -- L: legacy TED, E: eForms
    ProcedureLabel  NVARCHAR(80) NOT NULL,
    ProcedureFamily NVARCHAR(40) NOT NULL,
    SortOrder       TINYINT      NOT NULL
);
INSERT ref.[Procedure] VALUES
 ('L:OPE', N'Open', N'Open', 1),                        ('E:open', N'Open', N'Open', 1),
 ('L:RES', N'Restricted', N'Restricted', 2),            ('E:restricted', N'Restricted', N'Restricted', 2),
 ('L:NIC', N'Negotiated with prior call', N'Negotiated', 3),  ('E:neg-w-call', N'Negotiated with prior call', N'Negotiated', 3),
 ('L:NIP', N'Negotiated with prior call', N'Negotiated', 3),
 ('L:NOC', N'Negotiated without prior call', N'Negotiated', 4), ('E:neg-wo-call', N'Negotiated without prior call', N'Negotiated', 4),
 ('L:NOP', N'Negotiated without prior call', N'Negotiated', 4),
 ('L:AWP', N'Award without prior publication', N'Negotiated', 4),
 ('L:COD', N'Competitive dialogue', N'Competitive dialogue', 5), ('E:comp-dial', N'Competitive dialogue', N'Competitive dialogue', 5),
 ('L:INP', N'Innovation partnership', N'Other', 6),      ('E:innovation', N'Innovation partnership', N'Other', 6),
 ('E:oth-single', N'Other single-stage procedure', N'Other', 7),
 ('E:oth-mult', N'Other multi-stage procedure', N'Other', 7),
 ('UNKNOWN', N'Not stated', N'Not stated', 9);

DROP TABLE IF EXISTS ref.BuyerType;
CREATE TABLE ref.BuyerType (
    SourceCode  VARCHAR(30)  NOT NULL CONSTRAINT PK_refBuyerType PRIMARY KEY,
    BuyerType   NVARCHAR(60) NOT NULL,
    IsEU        BIT          NOT NULL,
    SortOrder   TINYINT      NOT NULL
);
INSERT ref.BuyerType VALUES
 ('L:5', N'EU institution or agency', 1, 1),  ('L:5A', N'EU institution or agency', 1, 1), ('E:eu-ins-bod-ag', N'EU institution or agency', 1, 1),
 ('L:1', N'National or federal authority', 0, 2), ('L:N', N'National or federal authority', 0, 2), ('E:cga', N'National or federal authority', 0, 2),
 ('L:3', N'Regional or local authority', 0, 3), ('L:R', N'Regional or local authority', 0, 3), ('E:ra', N'Regional or local authority', 0, 3),
 ('E:la', N'Regional or local authority', 0, 3),
 ('L:6', N'Body governed by public law', 0, 4), ('E:body-pl', N'Body governed by public law', 0, 4),
 ('E:body-pl-cga', N'Body governed by public law', 0, 4), ('E:body-pl-ra', N'Body governed by public law', 0, 4),
 ('E:body-pl-la', N'Body governed by public law', 0, 4),
 ('L:4', N'Utilities and public undertakings', 0, 5), ('E:pub-undert', N'Utilities and public undertakings', 0, 5),
 ('E:pub-undert-cga', N'Utilities and public undertakings', 0, 5), ('E:spec-rights-entity', N'Utilities and public undertakings', 0, 5),
 ('E:def-cont', N'Other public buyer', 0, 6), ('L:8', N'Other public buyer', 0, 6), ('L:Z', N'Other public buyer', 0, 6),
 ('UNKNOWN', N'Not stated', 0, 9);

DROP TABLE IF EXISTS ref.LegalFormToken;
CREATE TABLE ref.LegalFormToken (Token NVARCHAR(20) NOT NULL CONSTRAINT PK_refLegalForm PRIMARY KEY);
INSERT ref.LegalFormToken VALUES (N'SA'),(N'S A'),(N'AG'),(N'GMBH'),(N'LTD'),(N'LIMITED'),(N'SARL'),(N'S A R L'),
 (N'SPA'),(N'S P A'),(N'SRL'),(N'NV'),(N'BV'),(N'AB'),(N'OY'),(N'OYJ'),(N'AS'),(N'A S'),(N'SL'),(N'S L'),(N'SLU'),
 (N'PLC'),(N'INC'),(N'LLP'),(N'SE'),(N'SAS'),(N'KFT'),(N'ZRT'),(N'UAB'),(N'AE'),(N'IKE'),(N'EPE'),(N'SP Z O O'),
 (N'CONSORTIUM'),(N'GROUP'),(N'SOLUTIONS'),(N'SYSTEMS'),(N'CONSULTING'),(N'SERVICES'),(N'TECHNOLOGIES'),
 (N'BIETERGEMEINSCHAFT'),(N'ARGE'),(N'APS'),(N'SPRL'),(N'SRO'),(N'S R O'),(N'DOO'),(N'D O O'),(N'OU'),(N'SIA'),
 (N'LDA'),(N'GIE'),(N'CVBA'),(N'BVBA'),(N'KG'),(N'CO'),(N'CORPORATION'),(N'SOFTWARE'),(N'INFORMATIQUE');
GO
