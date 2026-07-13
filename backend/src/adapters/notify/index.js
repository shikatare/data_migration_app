async function notifyConsole(summary) {
  console.log(`[NOTIFY] ${summary.status.toUpperCase()} — run ${summary.runId}: ${summary.message}`);
  return { channel: "console", ok: true };
}

async function notifySlack(summary) {
  const webhook = process.env.SLACK_WEBHOOK_URL;
  if (!webhook) return { channel: "slack", ok: false, error: "SLACK_WEBHOOK_URL not set" };
  try {
    const res = await fetch(webhook, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        text: `*Migration run ${summary.runId}* — ${summary.status.toUpperCase()}\n${summary.message}`,
      }),
    });
    return { channel: "slack", ok: res.ok };
  } catch (e) {
    return { channel: "slack", ok: false, error: e.message };
  }
}

async function notifySns(summary) {
  const topicArn = process.env.AWS_SNS_TOPIC_ARN;
  if (!topicArn) return { channel: "sns", ok: false, error: "AWS_SNS_TOPIC_ARN not set" };
  try {
    const { SNSClient, PublishCommand } = await import("@aws-sdk/client-sns");
    const client = new SNSClient({ region: process.env.AWS_REGION });
    await client.send(
      new PublishCommand({
        TopicArn: topicArn,
        Subject: `Migration run ${summary.runId} — ${summary.status}`,
        Message: summary.message,
      })
    );
    return { channel: "sns", ok: true };
  } catch (e) {
    return { channel: "sns", ok: false, error: e.message };
  }
}

export async function publishNotification(summary) {
  const mode = process.env.NOTIFY_MODE || "console";
  const results = [await notifyConsole(summary)];

  if (mode === "slack") results.push(await notifySlack(summary));
  if (mode === "sns") results.push(await notifySns(summary));

  return results;
}
