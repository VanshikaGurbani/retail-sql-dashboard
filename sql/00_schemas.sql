-- Layers: raw (text, untouched) -> stg (typed) -> clean (kept lines) -> mart (analysis tables).
-- dq holds the data-quality log and the parameters every later file reads.
CREATE SCHEMA IF NOT EXISTS raw;
CREATE SCHEMA IF NOT EXISTS stg;
CREATE SCHEMA IF NOT EXISTS clean;
CREATE SCHEMA IF NOT EXISTS mart;
CREATE SCHEMA IF NOT EXISTS dq;

-- Parameters. One place to change a threshold; every later file reads these rows.
CREATE OR REPLACE TABLE dq.params AS
SELECT
    DATE '2009-12-01' AS window_start,        -- first day analysed
    DATE '2011-12-01' AS window_end_excl,     -- December 2011 stops on the 9th, so it is left out
    5000              AS large_qty_threshold, -- |quantity| at or above this is flagged, not dropped
    DATE '2011-12-01' AS current_snapshot,    -- "today" for the segmentation the memo acts on
    365               AS rfm_window_days,     -- look-back for frequency and monetary value
    3                 AS outcome_months;      -- the "next quarter" used to measure who comes back

-- RFM snapshots. The last row is the live segmentation; the others are back-tests whose
-- following quarter is fully observed, so lapse rates are measured, not modelled.
-- 2010-12-01 is the same season (December to February) as the quarter the memo plans for.
CREATE OR REPLACE TABLE dq.snapshots AS
SELECT * FROM (VALUES
    (DATE '2010-09-01', 'backtest', FALSE),
    (DATE '2010-12-01', 'backtest', TRUE),
    (DATE '2011-03-01', 'backtest', FALSE),
    (DATE '2011-06-01', 'backtest', FALSE),
    (DATE '2011-09-01', 'backtest', FALSE),
    (DATE '2011-12-01', 'current',  FALSE)
) AS t(snapshot_date, kind, is_same_season);
