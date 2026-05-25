"""
storage.py
==========
Thin wrapper around Google Cloud Storage.
Replaces local file paths in cache.py and export.py with GCS equivalents.

All functions accept/return Python objects (dict, str, bytes).
The bucket name is read from config; credentials from the environment
or Streamlit secrets.
"""

import io
import json
import os
from typing import Any, Optional

from google.cloud import storage
from google.oauth2 import service_account


# ── Client initialisation ─────────────────────────────────────────────────────

def _get_client() -> storage.Client:
    """
    Build a GCS client.
    Looks for credentials in this order:
      1. Streamlit secrets  (deployed app)
      2. gcs_key.json in the project root  (local dev)
      3. Application Default Credentials  (fallback)
    """
    # Streamlit Cloud: secrets stored as a JSON string under [gcs]
    try:
        import streamlit as st
        info = json.loads(st.secrets["gcs"]["credentials_json"])
        creds = service_account.Credentials.from_service_account_info(info)
        return storage.Client(credentials=creds, project=info["project_id"])
    except Exception:
        pass

    # Local dev: gcs_key.json in project root
    key_path = os.path.join(os.path.dirname(__file__), "..", "gcs_key.json")
    key_path = os.path.abspath(key_path)
    if os.path.exists(key_path):
        creds = service_account.Credentials.from_service_account_file(key_path)
        with open(key_path) as f:
            project_id = json.load(f)["project_id"]
        return storage.Client(credentials=creds, project=project_id)

    # Fallback: application default credentials
    return storage.Client()


def _bucket(client: storage.Client, bucket_name: str) -> storage.Bucket:
    return client.bucket(bucket_name)


# ── Core read / write ─────────────────────────────────────────────────────────

def upload_json(bucket_name: str, blob_path: str, data: Any) -> None:
    """Serialise data as JSON and upload to bucket_name/blob_path."""
    client = _get_client()
    blob   = _bucket(client, bucket_name).blob(blob_path)
    blob.upload_from_string(
        json.dumps(data),
        content_type="application/json"
    )


def download_json(bucket_name: str, blob_path: str) -> Optional[Any]:
    """Download and deserialise JSON from bucket_name/blob_path. Returns None if not found."""
    client = _get_client()
    blob   = _bucket(client, bucket_name).blob(blob_path)
    if not blob.exists():
        return None
    return json.loads(blob.download_as_text())


def upload_bytes(bucket_name: str, blob_path: str, data: bytes, content_type: str = "application/octet-stream") -> None:
    """Upload raw bytes."""
    client = _get_client()
    blob   = _bucket(client, bucket_name).blob(blob_path)
    blob.upload_from_file(io.BytesIO(data), content_type=content_type)


def download_bytes(bucket_name: str, blob_path: str) -> Optional[bytes]:
    """Download raw bytes. Returns None if not found."""
    client = _get_client()
    blob   = _bucket(client, bucket_name).blob(blob_path)
    if not blob.exists():
        return None
    return blob.download_as_bytes()


def upload_text(bucket_name: str, blob_path: str, text: str, content_type: str = "text/plain") -> None:
    """Upload a plain text or CSV string."""
    client = _get_client()
    blob   = _bucket(client, bucket_name).blob(blob_path)
    blob.upload_from_string(text, content_type=content_type)


def download_text(bucket_name: str, blob_path: str) -> Optional[str]:
    """Download text. Returns None if not found."""
    client = _get_client()
    blob   = _bucket(client, bucket_name).blob(blob_path)
    if not blob.exists():
        return None
    return blob.download_as_text()


def list_blobs(bucket_name: str, prefix: str = "") -> list[str]:
    """List all blob paths under a prefix."""
    client = _get_client()
    return [b.name for b in client.list_blobs(bucket_name, prefix=prefix)]


def delete_blob(bucket_name: str, blob_path: str) -> None:
    """Delete a single blob if it exists."""
    client = _get_client()
    blob   = _bucket(client, bucket_name).blob(blob_path)
    if blob.exists():
        blob.delete()


# ── Cache helpers (mirror cache.py interface but GCS-backed) ──────────────────

def cache_load(bucket_name: str, key: str) -> Optional[dict]:
    return download_json(bucket_name, f"cache/{key}.json")


def cache_save(bucket_name: str, key: str, data: Any) -> None:
    upload_json(bucket_name, f"cache/{key}.json", data)


def cache_clear(bucket_name: str) -> int:
    """Delete all cache entries. Returns count deleted."""
    blobs = list_blobs(bucket_name, prefix="cache/")
    for b in blobs:
        delete_blob(bucket_name, b)
    return len(blobs)


def cache_size(bucket_name: str) -> dict:
    blobs = list_blobs(bucket_name, prefix="cache/")
    return {"count": len(blobs)}


# ── Export helpers ────────────────────────────────────────────────────────────

def upload_csv(bucket_name: str, filename: str, df) -> None:
    """Upload a pandas DataFrame as CSV to exports/filename."""
    upload_text(bucket_name, f"exports/{filename}", df.to_csv(index=False), content_type="text/csv")


def upload_html(bucket_name: str, filename: str, html: str) -> None:
    """Upload a Plotly HTML figure string to exports/filename."""
    upload_text(bucket_name, f"exports/{filename}", html, content_type="text/html")


def download_csv(bucket_name: str, filename: str):
    """Download exports/filename as a pandas DataFrame. Returns None if not found."""
    import pandas as pd
    text = download_text(bucket_name, f"exports/{filename}")
    if text is None:
        return None
    return pd.read_csv(io.StringIO(text))


def list_exports(bucket_name: str) -> list[str]:
    """List all files in exports/."""
    return [b.replace("exports/", "") for b in list_blobs(bucket_name, prefix="exports/")]
