# Local development setup

Environment-specific setup for a development machine. **Nothing here is referenced from `src/`** —
all machine-specific values reach the code through environment variables, so this document
describes how to set them, not what the code assumes.

---

## Data storage

Datasets are never committed to the repository. They live under `BANKML_DATA_ROOT`, which
defaults to `./data` inside the repo and is gitignored.

**Current setup:** the machine's internal disk. The DVC remote is the source of truth, so the
local copy is a working cache that can be rebuilt with `dvc pull` at any time.

### Space required

| Item | Approximate |
|---|---|
| Home Credit (7 tables, uncompressed) | ~2.5 GB |
| Sparkov fraud transactions | ~0.5 GB |
| Tier 2 fixtures (Churn, Marketing) | < 50 MB |
| DVC cache | roughly the size of the tracked data |
| MLflow artifacts, model binaries | 1–2 GB and growing |
| Docker images and build layers | 10–30 GB once Phase 4 starts |

Budget around **20 GB** for data and artifacts, and check before starting:

```bash
df -h /
```

Docker is usually the surprise, not the datasets. If space gets tight, `docker system prune`
recovers more than deleting any dataset would.

### Using a separate drive instead

If the data root moves to an external drive or a NAS, only `.env` changes. Two requirements
apply to whatever filesystem it lands on:

| Requirement | Why |
|---|---|
| Symlink and hardlink support | DVC links files from its cache into the workspace. Without it, DVC copies, duplicating every dataset. |
| No 4 GB file-size ceiling | FAT32 caps individual files at 4 GB and fails partway through a larger write. |
| Journaling | FAT32 and exFAT have none, so an unclean eject can corrupt the filesystem rather than one file. |

FAT32 and exFAT fail all three; APFS and ext4 pass. Note also that **FAT32 and exFAT support
neither encryption nor file permissions** — anything stored on such a drive is readable on any
machine it is plugged into.

If an external drive is used, guard against it being unmounted:

```make
.PHONY: check-data
check-data:
	@test -n "$(BANKML_DATA_ROOT)" || { echo "BANKML_DATA_ROOT is not set. Copy .env.example to .env."; exit 1; }
	@test -d "$(BANKML_DATA_ROOT)" || { echo "Data root not found at $(BANKML_DATA_ROOT). Is the drive mounted?"; exit 1; }
```

Any target that reads data depends on `check-data`.

---

## Configuration

```bash
cp .env.example .env
# edit .env with the paths for this machine
```

`.env` is gitignored. Machine-specific paths never enter version control — CI has no access to
a developer's disk, and a hardcoded absolute path would break every other environment.

---

## DVC

```bash
dvc cache dir "$BANKML_DVC_CACHE"
dvc config cache.type hardlink,symlink
dvc config cache.shared group
```

`cache.type` matters. The default includes `copy` as a fallback, which is what quietly doubles
disk usage when links are unavailable. Setting it explicitly means DVC fails loudly on a
filesystem that cannot link, instead of wasting space silently.

Raw datasets are downloaded from their original sources — see
[`docs/datasets/`](../datasets/README.md) for the list, sizes and licensing terms — then added
with `dvc add` and pushed to the private remote. The remote is the source of truth; the local
copy is a working cache. If the machine is lost or wiped, `dvc pull` restores everything.

---

## Migrating to the homelab

When a homelab machine takes over from the laptop:

1. Point `BANKML_DATA_ROOT` and `BANKML_DVC_CACHE` at the new location in `.env`.
2. Run `dvc pull` to rebuild the workspace from the remote.

That is the whole migration. Do not plan to carry data across on a physical disk — the datasets
are public downloads backed by the DVC remote, so restoring from the remote is faster and less
error-prone than moving a drive between machines with different filesystems.
