# Pinned to the same MLflow version BankML's own code depends on (mlops/pyproject.toml) —
# a tracking-server/client version mismatch is a real source of subtle incompatibility, not
# just a version-hygiene nitpick.
FROM python:3.12-slim

RUN pip install --no-cache-dir \
    mlflow==3.16.1 \
    psycopg2-binary \
    azure-storage-blob

EXPOSE 5000
