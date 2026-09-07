# AI Bond Index website (v0.1)

Static **Terminal Quant** page generated from the pipeline snapshot.

## Generate

```bash
python3 site/generate.py
```

Reads `data/latest.csv` (or `AI_BOND_DATA_DIR`) and copies
`data/ai_bond_benchmark_spreads_30d.png` into `site/`. Emits `site/index.html`.
No JS framework. Cron should re-run this after each snapshot.

## Deploy

Gaudi: `/var/www/aifinancials.xyz/` — copy `index.html` + the PNG from current
`main`. Nginx template: `site/nginx/aifinancials.xyz.conf` (port 80). TLS via
certbot once DNS resolves.
