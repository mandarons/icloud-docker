### ICloud-Drive-Docker Usage Tracking

We collect following information to analyze usage of `mandarons/icloud-drive-docker` project:

1. `Application version` - to track which versions of `mandarons/icloud-drive-docker` are currently in use
2. `Sync statistics` - anonymized aggregated data about sync operations (file counts, sync duration, error indicators)
3. `Installation events` - new installations and upgrades for usage analytics

On server side, this project uses `IP address` to determine `country` of `mandarons/icloud-drive-docker` installation.

Collecting this data helps keep supporting this project and drive future improvements. **No personally identifiable information is collected.** Aggregate data is made available at [Wapar](https://wapar.mandarons.com).

## How to Opt Out

You can completely disable usage tracking by adding the following to your `config.yaml`:

```yaml
app:
  usage_tracking:
    enabled: false
```

When disabled, no usage data will be collected or transmitted. The sync functionality remains completely unaffected.

## Data Collected

### Installation Data
- Application version
- Installation ID (randomly generated UUID)
- Country (derived from IP address on server side)

### Sync Statistics (when available)
- Sync duration
- Number of files/photos processed (counts only)
- Data transfer volumes (bytes)
- Error indicators (boolean flags, no error details)
- Timestamp of sync operation

### Privacy Guarantees
- No file names, paths, or content
- No personal information or account details
- No iCloud credentials or tokens
- Data is aggregated and anonymized
- Opt-out available at any time
