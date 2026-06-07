import * as cdk from 'aws-cdk-lib';
import * as logs from 'aws-cdk-lib/aws-logs';
import * as cloudwatch from 'aws-cdk-lib/aws-cloudwatch';
import type { Construct } from 'constructs';

export class ObservabilityStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    new logs.LogGroup(this, 'EngineLogs', {
      logGroupName: '/pdlcflow/engine',
      retention: logs.RetentionDays.ONE_MONTH,
    });
    new logs.LogGroup(this, 'WorkerLogs', {
      logGroupName: '/pdlcflow/worker',
      retention: logs.RetentionDays.ONE_MONTH,
    });

    new cloudwatch.Dashboard(this, 'Dashboard', {
      dashboardName: 'pdlcflow',
    });
  }
}
