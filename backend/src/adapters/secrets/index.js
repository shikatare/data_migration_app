async function getSecretFromEnv(name) {
  const map = {
    oracle: {
      user: process.env.ORACLE_USER,
      password: process.env.ORACLE_PASSWORD,
      connectString: process.env.ORACLE_CONNECT_STRING,
    },
    snowflake: {
      account: process.env.SNOWFLAKE_ACCOUNT,
      user: process.env.SNOWFLAKE_USER,
      password: process.env.SNOWFLAKE_PASSWORD,
      warehouse: process.env.SNOWFLAKE_WAREHOUSE,
      database: process.env.SNOWFLAKE_DATABASE,
      schema: process.env.SNOWFLAKE_SCHEMA,
      role: process.env.SNOWFLAKE_ROLE,
    },
  };
  return map[name] || {};
}

async function getSecretFromAws(name) {
  const { SecretsManagerClient, GetSecretValueCommand } = await import(
    "@aws-sdk/client-secrets-manager"
  );
  const client = new SecretsManagerClient({ region: process.env.AWS_REGION });
  const secretId =
    name === "oracle"
      ? process.env.AWS_SECRET_ID_ORACLE
      : process.env.AWS_SECRET_ID_SNOWFLAKE;

  const result = await client.send(new GetSecretValueCommand({ SecretId: secretId }));
  return JSON.parse(result.SecretString);
}

export async function getSecret(name) {
  const mode = process.env.SECRETS_MODE || "env";
  if (mode === "aws") return getSecretFromAws(name);
  return getSecretFromEnv(name);
}