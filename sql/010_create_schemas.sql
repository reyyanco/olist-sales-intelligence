-- Veri ambarı katmanları için şemalar. Tablolar sonraki aşamalarda eklenecek.
-- staging: ham CSV'lerin yüklendiği, dönüştürülmemiş tablolar
-- dw:      boyut ve olgu tabloları (yıldız şema)
CREATE SCHEMA IF NOT EXISTS staging;
CREATE SCHEMA IF NOT EXISTS dw;
