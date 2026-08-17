-- Before/after for the tempo penalty. READ ONLY — reproduces the new scoring
-- in SQL so you can see rank movement without deploying anything.
--
-- Mirrors api_helpers.py: free below 6%, smoothstep ramp to 18%, then saturated.
-- Allowance = 60% of this query's own sound-score spread.
SET statement_timeout='180s';
SET hnsw.ef_search=200;

WITH q AS (
  SELECT e.* FROM embeddings e JOIN tracks t ON t.id=e.track_id
  WHERE t.artist ILIKE '%shermanology%' OR t.title ILIKE '%sao paulo%'
     OR t.title ILIKE '%são paulo%'
  LIMIT 1
),
cands AS (
  SELECT q.track_id qid, c.track_id cid, q.bpm qbpm, c.bpm cbpm,
         q.vocal_dominance qvd, c.vocal_dominance cvd,
    (1-(q.muq_full<=>c.muq_full)) s_full, (1-(q.muq_vocals<=>c.muq_vocals)) s_voc,
    (1-(q.muq_drums<=>c.muq_drums)) s_dru, (1-(q.muq_bass<=>c.muq_bass)) s_bas,
    (1-(q.muq_other<=>c.muq_other)) s_oth
  FROM q CROSS JOIN LATERAL (
    SELECT * FROM embeddings b WHERE b.track_id<>q.track_id
    ORDER BY b.muq_full <=> q.muq_full LIMIT 400
  ) c
),
sound AS (
  SELECT qid, cid, qbpm, cbpm,
    CASE WHEN qvd>0.20 AND cvd>0.20 THEN 0.40*s_full+0.25*s_voc+0.15*s_dru+0.10*s_bas+0.10*s_oth
         WHEN qvd<0.10 AND cvd<0.10 THEN 0.50*s_full+0.20*s_dru+0.15*s_bas+0.15*s_oth
         ELSE 0.55*s_full+0.15*s_dru+0.10*s_bas+0.20*s_oth END AS s
  FROM cands
),
dist AS (            -- octave-folded relative tempo difference
  SELECT *, CASE
    WHEN qbpm IS NULL OR cbpm IS NULL OR qbpm<=0 OR cbpm<=0 THEN 0.0
    ELSE abs(power(2.0, log(2.0, (qbpm/cbpm)::numeric)
                       - round(log(2.0, (qbpm/cbpm)::numeric))) - 1.0)
  END AS d
  FROM sound
),
pen AS (             -- free / smoothstep / saturated
  SELECT *, CASE
    WHEN d <= 0.06 THEN 0.0
    WHEN d >= 0.18 THEN 1.0
    ELSE (((d-0.06)/0.12)^2) * (3.0 - 2.0*((d-0.06)/0.12))
  END AS p
  FROM dist
),
scored AS (
  SELECT *,
    s - p * ((max(s) OVER () - min(s) OVER ()) * 0.60) AS final
  FROM pen
)
SELECT
  row_number() OVER (ORDER BY final DESC)              AS rank_after,
  rank()       OVER (ORDER BY s DESC)                  AS rank_before,
  t.artist || ' - ' || t.title                         AS track,
  COALESCE(t.source_ref, t.source)                     AS came_from,
  round(cbpm::numeric, 0)                              AS bpm,
  round((d*100)::numeric, 1)                           AS pct_apart,
  round(p::numeric, 2)                                 AS penalty,
  round(s::numeric, 4)                                 AS sound_score,
  round(final::numeric, 4)                             AS final_score
FROM scored JOIN tracks t ON t.id = scored.cid
ORDER BY final DESC
LIMIT 15;
