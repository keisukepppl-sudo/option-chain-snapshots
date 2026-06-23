# AWS Pushover Health Check

This is the first AWS validation step for the breakout bot:

```text
EventBridge Scheduler -> Lambda -> Pushover
```

It does not run the scanner. It only proves that AWS can wake the phone around
04:30 JST without relying on GitHub Actions schedule timing.

## Cost

For this single scheduled Lambda call, expected cost is normally within the AWS
free tier or extremely small. Check your own AWS billing settings before use.

## Deploy

Prerequisites:

- AWS account
- AWS CLI configured
- AWS SAM CLI installed
- Pushover app token
- Pushover user key

From this directory:

```bash
sam build
sam deploy --guided
```

Recommended guided values:

```text
Stack Name: breakout-bot-pushover-healthcheck
AWS Region: ap-northeast-1
PushoverEnabled: true
PushoverAppToken: <your Pushover app token>
PushoverUserKey: <your Pushover user key>
PushoverPriority: 2
PushoverRetry: 60
PushoverExpire: 600
PushoverSound: climb
Confirm changes before deploy: Y
Allow SAM CLI IAM role creation: Y
Save arguments to configuration file: Y
```

The schedule is:

```text
04:30 JST, Monday-Friday
```

implemented as EventBridge Scheduler with:

```text
ScheduleExpression: cron(30 4 ? * MON-FRI *)
ScheduleExpressionTimezone: Asia/Tokyo
FlexibleTimeWindow: OFF
```

## Manual test

After deploy, run:

```bash
aws lambda invoke \
  --function-name <FunctionName from stack output> \
  --payload '{"message":"Manual AWS Pushover health-check test"}' \
  response.json
```

If `PUSHOVER_PRIORITY=2`, acknowledge the emergency notification in the Pushover app.

## CloudWatch logs

The Lambda logs a safe payload only:

- token exists true/false
- user key exists true/false
- priority
- retry
- expire
- sound
- Pushover API status/body

It never logs the token or user key value.

## Next step

If this health check rings reliably around 04:30 JST, the next step is a
separate Lambda container version that runs the production scanner directly.
