import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
from app.core.config import settings


def s3_client():
    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url,
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key,
        region_name="us-east-1",
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )


def ensure_bucket() -> None:
    client = s3_client()
    try:
        client.head_bucket(Bucket=settings.s3_bucket)
    except ClientError as exc:
        code = str(exc.response.get("Error", {}).get("Code", ""))
        if code not in {"404", "NoSuchBucket", "NotFound"}:
            raise
        try:
            client.create_bucket(Bucket=settings.s3_bucket)
        except ClientError as create_exc:
            if create_exc.response.get("Error", {}).get("Code") not in {"BucketAlreadyOwnedByYou", "BucketAlreadyExists"}:
                raise


def upload_file(path: str, key: str, content_type: str) -> None:
    s3_client().upload_file(path, settings.s3_bucket, key, ExtraArgs={"ContentType": content_type})


def put_bytes(data: bytes, key: str, content_type: str) -> None:
    s3_client().put_object(Bucket=settings.s3_bucket, Key=key, Body=data, ContentType=content_type)


def get_object(key: str, byte_range: str | None = None):
    params = {"Bucket": settings.s3_bucket, "Key": key}
    if byte_range:
        params["Range"] = byte_range
    return s3_client().get_object(**params)


def delete_object(key: str) -> None:
    s3_client().delete_object(Bucket=settings.s3_bucket, Key=key)


def head_object(key: str):
    return s3_client().head_object(Bucket=settings.s3_bucket, Key=key)
