-- Analiz: müşteri RFM. reporting.fn_customer_rfm(as_of date)
-- Tanımlar ve segmentler: docs/reporting.md, docs/metric_definitions.md (8. bölüm).
--
-- Kurallar:
-- - Birim customer_unique_id; yalnızca satış kapsamındaki (delivered) siparişler.
-- - as_of zorunludur (NULL -> hata). CURRENT_DATE kullanılmaz; tarihsel veri için gözlem tarihi
--   çağıran tarafından verilir (varsayılan önerisi: reporting.v_rfm_observation.observation_date).
-- - as_of gözlem gününün başıdır: purchase_ts < as_of olan satın almalar dahil, as_of günü ve
--   sonrası dışlanır. Böylece recency = as_of - son satın alma günü >= 1 olur.
-- - Sipariş durumu kaynağın son anlık görüntüsüdür; as_of anındaki tarihsel durum bilinmez.
-- - Frequency = farklı sipariş sayısı (kalem sayısı değil). Monetary = ürün satış tutarı (kargo hariç).
-- - Puanlar 1-5; recency'de düşük, frequency ve monetary'de yüksek değer daha iyidir (5 en iyi).
--     R ve M: kümülatif dağılıma göre beşli dilim:
--         ceil(5 * (değeri <= bu müşteri olan müşteri sayısı) / müşteri sayısı)
--       R için 6 - bu değer. Eşit değerler aynı puanı alır (NTILE kullanılmadı: NTILE eşitleri
--       sıraya göre farklı dilimlere bölebilir ve sonucu satır sırasına bağımlı kılar).
--       Tam sayı aritmetiği ile hesaplanır (kayan nokta sınır hatası olmaz).
--     F: sabit eşik: 1, 2, 3, 4, 5+ sipariş -> 1..5. Gerçek veride müşterilerin %97'si tek siparişli
--       olduğundan dilim yöntemi frequency için anlamsız olurdu.
-- - Küçük gruplarda (ör. 3 müşteri) puanlar 1-5 aralığının tamamını kapsamaz; dilim sınırları
--   müşteri sayısına bağlıdır. Segmentler bu yüzden puan eşikleriyle tanımlanır.

CREATE FUNCTION reporting.fn_customer_rfm(as_of date)
RETURNS TABLE (
    customer_unique_id  text,
    first_purchase_date date,
    last_purchase_date  date,
    recency_days        integer,
    frequency           integer,
    monetary            numeric(14,2),
    r_score             smallint,
    f_score             smallint,
    m_score             smallint,
    rfm_code            text,
    segment             text
)
LANGUAGE plpgsql STABLE AS $$
#variable_conflict use_column
BEGIN
    IF as_of IS NULL THEN
        RAISE EXCEPTION 'fn_customer_rfm: as_of zorunludur; gözlem tarihi açıkça verilmelidir';
    END IF;

    RETURN QUERY
    WITH scoped_orders AS (
        -- Gözlem tarihinden önceki, satış kapsamındaki siparişler
        SELECT o.customer_unique_id, o.order_id, o.purchase_ts, o.product_value
        FROM reporting.v_orders o
        WHERE o.in_sales_scope
          AND o.purchase_ts < fn_customer_rfm.as_of::timestamp
    ), customers AS (
        SELECT s.customer_unique_id,
               min(s.purchase_ts)::date      AS first_purchase_date,
               max(s.purchase_ts)::date      AS last_purchase_date,
               count(DISTINCT s.order_id)    AS frequency,
               sum(s.product_value)          AS monetary
        FROM scoped_orders s
        GROUP BY s.customer_unique_id
    ), ranked AS (
        SELECT c.*,
               (fn_customer_rfm.as_of - c.last_purchase_date)                               AS recency_days,
               count(*) OVER ()                                                             AS n,
               -- Varsayılan RANGE çerçevesi eşit değerleri birlikte sayar: "değeri <= bu satır olanlar"
               count(*) OVER (ORDER BY fn_customer_rfm.as_of - c.last_purchase_date)        AS recency_le,
               count(*) OVER (ORDER BY c.monetary)                                          AS monetary_le
        FROM customers c
    ), scored AS (
        SELECT r.*,
               (6 - ceil((5 * r.recency_le)::numeric / r.n))::smallint  AS r_score,
               LEAST(r.frequency, 5)::smallint                          AS f_score,
               ceil((5 * r.monetary_le)::numeric / r.n)::smallint       AS m_score
        FROM ranked r
    )
    SELECT
        s.customer_unique_id,
        s.first_purchase_date,
        s.last_purchase_date,
        s.recency_days::integer,
        s.frequency::integer,
        s.monetary::numeric(14,2),
        s.r_score,
        s.f_score,
        s.m_score,
        s.r_score::text || s.f_score::text || s.m_score::text,
        CASE
            WHEN s.r_score >= 4 AND s.f_score >= 2 AND s.m_score >= 4 THEN 'champions'
            WHEN s.f_score >= 2 AND s.r_score <= 2                    THEN 'at_risk'
            WHEN s.f_score >= 2                                       THEN 'loyal'
            WHEN s.r_score >= 4 AND s.m_score >= 4                    THEN 'new_high_value'
            WHEN s.r_score >= 4                                       THEN 'recent'
            WHEN s.r_score <= 2 AND s.m_score >= 4                    THEN 'hibernating_high_value'
            WHEN s.r_score <= 2                                       THEN 'lost'
            ELSE 'needs_attention'
        END
    FROM scored s
    ORDER BY s.customer_unique_id;
END
$$;

COMMENT ON FUNCTION reporting.fn_customer_rfm(date) IS
    'customer_unique_id başına RFM; as_of zorunlu, as_of günü ve sonrası dışlanır; segmentler docs/reporting.md';
