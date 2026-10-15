#!/usr/bin/env node

import { createReadStream } from "node:fs";
import { stat } from "node:fs/promises";
import { basename, resolve } from "node:path";

import { HeadObjectCommand, PutObjectCommand, S3Client } from "@aws-sdk/client-s3";

function first(...names) {
  for (const name of names) {
    const value = process.env[name]?.trim();
    if (value) return value;
  }
  throw new Error(`Missing ${names.join(" or ")}. Run this command through Railway with Bucket variable references.`);
}

const input = process.argv.slice(2).find((argument) => argument !== "--");
if (!input) {
  throw new Error("Usage: pnpm upload:video -- /absolute/path/to/video.mp4");
}

const path = resolve(input);
const file = await stat(path);
if (!file.isFile()) throw new Error(`Not a file: ${path}`);

const endpoint = first("JIEYUE_BUCKET_ENDPOINT", "ENDPOINT", "AWS_ENDPOINT_URL");
const bucket = first("JIEYUE_BUCKET_NAME", "BUCKET", "AWS_S3_BUCKET_NAME");
const key = process.env.JIEYUE_BUCKET_KEY?.trim() || "jieyue-mv-720p.mp4";
const client = new S3Client({
  endpoint,
  region:
    process.env.JIEYUE_BUCKET_REGION?.trim() ||
    process.env.REGION?.trim() ||
    process.env.AWS_DEFAULT_REGION?.trim() ||
    "auto",
  forcePathStyle:
    (process.env.JIEYUE_BUCKET_URL_STYLE?.trim() || process.env.AWS_S3_URL_STYLE?.trim()) === "path",
  credentials: {
    accessKeyId: first("JIEYUE_BUCKET_ACCESS_KEY_ID", "ACCESS_KEY_ID", "AWS_ACCESS_KEY_ID"),
    secretAccessKey: first(
      "JIEYUE_BUCKET_SECRET_ACCESS_KEY",
      "SECRET_ACCESS_KEY",
      "AWS_SECRET_ACCESS_KEY",
    ),
  },
});

console.log(`Uploading ${basename(path)} (${file.size} bytes) as ${key}…`);
await client.send(
  new PutObjectCommand({
    Bucket: bucket,
    Key: key,
    Body: createReadStream(path),
    ContentLength: file.size,
    ContentType: "video/mp4",
    CacheControl: "public, max-age=86400",
  }),
);
const uploaded = await client.send(new HeadObjectCommand({ Bucket: bucket, Key: key }));
if (uploaded.ContentLength !== file.size) {
  throw new Error(`Upload verification failed: expected ${file.size}, received ${uploaded.ContentLength ?? "unknown"}`);
}
console.log(`Uploaded and verified ${key} (${uploaded.ContentLength} bytes, ${uploaded.ContentType ?? "unknown type"}).`);
