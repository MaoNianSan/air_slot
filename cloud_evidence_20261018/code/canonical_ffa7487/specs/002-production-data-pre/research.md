# Research Decisions: Production Data and PRE

## Read-only streaming

**Decision**: Stream CSV/GZIP/ZIP/TAR members and project registered columns; never permanently extract archives.  
**Rationale**: Audited files are large and raw roots are immutable.  
**Alternatives considered**: Whole-file DataFrame loading and permanent extraction were rejected.

## Canonical storage

**Decision**: Parquet with ZSTD, partitioned by dataset/year/month/date/canonical object; manifest-driven atomic commits.  
**Rationale**: Matches authoritative storage contract and supports projection/resume.  
**Alternatives considered**: CSV cache loses schema fidelity; episode partitions create tiny files.

## Availability

**Decision**: Require configured replay lag for replay evidence; preserve schedule reference assumptions and post-hoc-only roles.  
**Rationale**: Neither dataset contains independent availability timestamps.  
**Alternatives considered**: Silent event-time equality is leakage-prone and prohibited.

## Timezones

**Decision**: Use IANA zoneinfo and explicit rollover candidates anchored to FlightDate.  
**Rationale**: Fixed offsets fail across DST and airport domains.  
**Alternatives considered**: Fixed US offsets and naive datetimes were rejected.

## Real smoke

**Decision**: Bound reads by rows/files and use the current audited raw roots when configured.  
**Rationale**: Proves parsers against reality without turning the feature gate into a full run.  
**Alternatives considered**: Synthetic-only validation is insufficient for a first implementable version.
