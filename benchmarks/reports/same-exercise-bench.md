# Same-exercise bench (us vs TOON vs Headroom, one ruler)

tasks: 18 (frozen eval) | headroom headroom-ai 0.39.1 | toon toon-format 1.0.0

## Selection (full repo in, tokens out)

median baseline 3213.0 | ours 782.0 (min recall 1.0) | headroom 3633.0 (min symbols 0.0, deterministic: True)

## Format (identical pack rendered)

json 1417.5 | markdown 1035.0 | compact 890.0 | toon 1134.0 (round-trip: True)
