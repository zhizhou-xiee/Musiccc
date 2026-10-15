import { GetObjectCommand, S3Client } from "@aws-sdk/client-s3";
import { getSignedUrl } from "@aws-sdk/s3-request-presigner";

export interface BucketMediaConfig {
  endpoint: string;
  accessKeyId: string;
  secretAccessKey: string;
  bucket: string;
  region: string;
  forcePathStyle: boolean;
  key: string;
}

function first(...names: string[]): string | null {
  for (const name of names) {
    const value = process.env[name]?.trim();
    if (value) return value;
  }
  return null;
}

export function bucketMediaConfig(): BucketMediaConfig | null {
  const endpoint = first("JIEYUE_BUCKET_ENDPOINT", "ENDPOINT", "AWS_ENDPOINT_URL");
  const accessKeyId = first("JIEYUE_BUCKET_ACCESS_KEY_ID", "ACCESS_KEY_ID", "AWS_ACCESS_KEY_ID");
  const secretAccessKey = first(
    "JIEYUE_BUCKET_SECRET_ACCESS_KEY",
    "SECRET_ACCESS_KEY",
    "AWS_SECRET_ACCESS_KEY",
  );
  const bucket = first("JIEYUE_BUCKET_NAME", "BUCKET", "AWS_S3_BUCKET_NAME");
  if (!endpoint && !accessKeyId && !secretAccessKey && !bucket) return null;
  if (!endpoint || !accessKeyId || !secretAccessKey || !bucket) {
    throw new Error("Incomplete JIEYUE_BUCKET_* configuration");
  }
  const url = new URL(endpoint);
  if (url.protocol !== "https:") throw new Error("JIEYUE_BUCKET_ENDPOINT must use https");
  return {
    endpoint: url.href,
    accessKeyId,
    secretAccessKey,
    bucket,
    region: first("JIEYUE_BUCKET_REGION", "REGION", "AWS_DEFAULT_REGION") ?? "auto",
    forcePathStyle: first("JIEYUE_BUCKET_URL_STYLE", "AWS_S3_URL_STYLE") === "path",
    key: first("JIEYUE_BUCKET_KEY") ?? "jieyue-mv-720p.mp4",
  };
}

export async function signedBucketVideoUrl(): Promise<string | null> {
  const config = bucketMediaConfig();
  if (!config) return null;
  const client = new S3Client({
    endpoint: config.endpoint,
    region: config.region,
    forcePathStyle: config.forcePathStyle,
    credentials: {
      accessKeyId: config.accessKeyId,
      secretAccessKey: config.secretAccessKey,
    },
  });
  return getSignedUrl(
    client,
    new GetObjectCommand({
      Bucket: config.bucket,
      Key: config.key,
      ResponseContentType: "video/mp4",
      ResponseCacheControl: "public, max-age=86400",
    }),
    { expiresIn: 21_600 },
  );
}
