import fs from "fs/promises";
import path from "path";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const RUNS_FILE = path.join(__dirname, "../../data/runs/runs.json");

async function readRunsFile() {
  try {
    const raw = await fs.readFile(RUNS_FILE, "utf-8");
    return JSON.parse(raw);
  } catch {
    return [];
  }
}

async function writeRunsFile(runs) {
  await fs.mkdir(path.dirname(RUNS_FILE), { recursive: true });
  await fs.writeFile(RUNS_FILE, JSON.stringify(runs, null, 2));
}

/**
 * Local storage adapter — a JSON file standing in for DynamoDB.
 * Same record shape a real DynamoDB adapter would use, so swapping
 * STORAGE_MODE=aws later is a drop-in.
 */
async function putRunRecordLocal(record) {
  const runs = await readRunsFile();
  runs.unshift(record);
  await writeRunsFile(runs.slice(0, 200)); // keep last 200 runs
  return record;
}

async function getRunHistoryLocal() {
  return readRunsFile();
}

async function putRunRecordAws(record) {
  const { DynamoDBClient } = await import("@aws-sdk/client-dynamodb");
  const { DynamoDBDocumentClient, PutCommand } = await import("@aws-sdk/lib-dynamodb");
  const client = DynamoDBDocumentClient.from(new DynamoDBClient({ region: process.env.AWS_REGION }));
  await client.send(
    new PutCommand({ TableName: process.env.AWS_DYNAMO_TABLE, Item: record })
  );
  return record;
}

async function getRunHistoryAws() {
  const { DynamoDBClient } = await import("@aws-sdk/client-dynamodb");
  const { DynamoDBDocumentClient, ScanCommand } = await import("@aws-sdk/lib-dynamodb");
  const client = DynamoDBDocumentClient.from(new DynamoDBClient({ region: process.env.AWS_REGION }));
  const result = await client.send(new ScanCommand({ TableName: process.env.AWS_DYNAMO_TABLE }));
  return result.Items || [];
}

export async function putRunRecord(record) {
  const mode = process.env.STORAGE_MODE || "local";
  return mode === "aws" ? putRunRecordAws(record) : putRunRecordLocal(record);
}

export async function getRunHistory() {
  const mode = process.env.STORAGE_MODE || "local";
  return mode === "aws" ? getRunHistoryAws() : getRunHistoryLocal();
}
