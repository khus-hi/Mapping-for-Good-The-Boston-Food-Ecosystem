# Reupload Runner

Runs all schema tests and ingests in sequence for:
- farmers markets
- restaurants
- grocery stores
- food pantries

Parsers are located in `parsers/`, and data files are organized under:
- `data/cleaned_data/`
- `data/rejects/`

## Usage

```bash
scripts/reupload/run_all_ingests.sh
```

## Useful flags

```bash
scripts/reupload/run_all_ingests.sh --dry-run
scripts/reupload/run_all_ingests.sh --dry-run --no-geocode --limit 100
scripts/reupload/run_all_ingests.sh --skip-tests
```
